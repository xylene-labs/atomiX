#!/usr/bin/env python3
"""Assembler for the axpe protocol emulator.

Normative reference: sw/pemu/isa/axpe-isa.md.  Where this file and that
document disagree, the document is right and this file is the bug.

The assembler's second job matters as much as the first.  Because every axpe
instruction declares its own retirement cost, a program's timing is a property
of its text, so `--listing` prints the exact cycle cost of every instruction and
every labelled block.  A protocol's bit period is then something you read, not
something you measure on a scope.  `WAITE` is the one instruction whose cost is
a bound rather than a value, and the listing says so rather than averaging it
away.
"""

from __future__ import annotations

import argparse
import ast
import re
import struct
import sys
from pathlib import Path
from typing import NamedTuple


# --- the instruction set ----------------------------------------------------
#
# Everything below is derived from sw/pemu/isa/axpe-isa.json at import time.
# The assembler deliberately holds no second copy of the opcode table: a
# transcribed instruction set drifts, and the field it drifts in is usually a
# cycle count that nobody re-reads until a protocol misbehaves on real pins.

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))

from axpe_isa import load as load_isa

ISA = load_isa()

_FIELDS = ISA["encoding"]["fields"]
OP_SHIFT = _FIELDS["op"]["lo"]
A_SHIFT = _FIELDS["a"]["lo"]
B_SHIFT = _FIELDS["b"]["lo"]
X_SHIFT = _FIELDS["x"]["lo"]


def _width(name: str) -> int:
    return _FIELDS[name]["hi"] - _FIELDS[name]["lo"] + 1


DELAY_MAX = (1 << _width("delay")) - 1
IMM8_MAX = (1 << (_width("b") + _width("x"))) - 1
SHIFT_MAX = (1 << _width("x")) - 1
REG_MAX = ISA["registers"]["count"] - 1
MAX_SHIFT_BITS = ISA["registers"]["width"]

# Operand shape names, mirrored from the description so the dispatch below can
# compare against constants rather than bare strings.
NONE, IMM8, REG, REG_N, REG_REG, REG_IMM8, REG_SHIFT, BRANCH, TARGET = (
    "none", "imm8", "reg", "reg_n", "reg_reg", "reg_imm8", "reg_shift", "branch", "target",
)

# mnemonic -> (opcode, shape, timing).  `timing` selects the retirement rule:
# "fixed" is 1 + D, "perbit" is 1 + n*D, "bounded" is 1 + w for w <= D.
OPCODES: dict[str, tuple[int, str, str]] = {
    insn["mnemonic"]: (insn["opcode"], insn["shape"], insn["timing"])
    for insn in ISA["instructions"]
}

CONDITIONS: dict[str, int] = dict(ISA["conditions"])

ALIASES: dict[str, tuple[str, list[str]]] = {
    name: (spec["expands_to"], list(spec.get("operands", [])))
    for name, spec in ISA.get("aliases", {}).items()
}

# Instructions that write the measured wait back into their `a` register.
RETURNS_TIME = frozenset(
    insn["mnemonic"] for insn in ISA["instructions"] if insn.get("returns_time")
)


class AsmError(Exception):
    """A diagnostic carrying the source line that caused it."""

    def __init__(self, path: Path, lineno: int, message: str) -> None:
        super().__init__(f"{path}:{lineno}: {message}")


class Insn(NamedTuple):
    word: int
    mnemonic: str
    addr: int
    cost: str          # human-readable retirement cost
    cycles: int        # exact cycles, or the upper bound for WAITE
    bounded: bool      # True when `cycles` is a bound rather than a value
    lineno: int
    text: str


# --- expression evaluation --------------------------------------------------

_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
                   ast.Mod, ast.LShift, ast.RShift, ast.BitOr, ast.BitAnd, ast.BitXor)


def evaluate(expr: str, symbols: dict[str, int], path: Path, lineno: int) -> int:
    """Evaluate an integer constant expression over `symbols`.

    Cycle counts are integers, so `/` means floor division here.  Writing
    `BAUD/2` in a delay field and silently getting a float would be a way to
    describe a bit period that no hardware can produce.
    """
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError:
        raise AsmError(path, lineno, f"cannot parse expression {expr!r}")

    def walk(node: ast.AST) -> int:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in symbols:
                raise AsmError(path, lineno, f"undefined symbol {node.id!r}")
            return symbols[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = walk(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, (ast.Div, ast.FloorDiv)):
                if right == 0:
                    raise AsmError(path, lineno, "division by zero")
                return left // right
            return {
                ast.Add: lambda: left + right,
                ast.Sub: lambda: left - right,
                ast.Mult: lambda: left * right,
                ast.Mod: lambda: left % right,
                ast.LShift: lambda: left << right,
                ast.RShift: lambda: left >> right,
                ast.BitOr: lambda: left | right,
                ast.BitAnd: lambda: left & right,
                ast.BitXor: lambda: left ^ right,
            }[type(node.op)]()
        raise AsmError(path, lineno, f"unsupported expression {expr!r}")

    return walk(tree)


# --- parsing ----------------------------------------------------------------

LABEL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
EQU_RE = re.compile(r"^\.equ\s+([A-Za-z_][A-Za-z0-9_]*)\s*,?\s*(.+)$", re.IGNORECASE)


def split_operands(rest: str) -> tuple[list[str], str | None]:
    """Split an operand list, pulling out a trailing `D=<expr>` if present.

    Commas inside parentheses stay put, so `(1<<4)|1` survives as one operand.
    """
    delay: str | None = None
    parts: list[str] = []
    depth = 0
    current = ""
    for ch in rest:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
            continue
        current += ch
    if current.strip():
        parts.append(current)

    kept: list[str] = []
    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue
        if stripped.upper().startswith("D=") or stripped.upper().startswith("D ="):
            delay = stripped.split("=", 1)[1]
        else:
            kept.append(stripped)
    return kept, delay


def parse_register(token: str, path: Path, lineno: int) -> int:
    token = token.strip().upper()
    if not re.fullmatch(rf"R[0-{REG_MAX}]", token):
        raise AsmError(path, lineno,
                       f"expected a register R0-R{REG_MAX}, got {token!r}")
    return int(token[1:])


def check_range(value: int, limit: int, what: str, path: Path, lineno: int) -> int:
    if not 0 <= value <= limit:
        raise AsmError(path, lineno, f"{what} {value} out of range 0..{limit}")
    return value


def bounded_imm(token: str, limit: int, what: str, symbols: dict[str, int],
                path: Path, lineno: int) -> int:
    """Evaluate an immediate and range-check it in one step."""
    return check_range(evaluate(token, symbols, path, lineno), limit, what, path, lineno)


def expect_operands(mnemonic: str, operands: list[str], count: int,
                    path: Path, lineno: int) -> None:
    if len(operands) != count:
        raise AsmError(path, lineno,
                       f"{mnemonic} takes {count} operand(s), got {len(operands)}")


# --- assembly ---------------------------------------------------------------

def assemble(source: str, path: Path, imem_words: int = 256) -> list[Insn]:
    """Two passes: collect labels, then encode.

    A branch target that does not fit the 8-bit field is an error here rather
    than a truncation, because a silently wrapped jump is the kind of defect
    that only shows up as a protocol glitch on real pins.
    """
    symbols: dict[str, int] = {}
    raw: list[tuple[int, str, str, list[str], str | None]] = []
    addr = 0

    for lineno, line in enumerate(source.splitlines(), start=1):
        line = line.split(";", 1)[0].rstrip()
        if not line.strip():
            continue

        match = LABEL_RE.match(line.strip())
        while match:
            symbols[match.group(1)] = addr
            line = match.group(2)
            if not line.strip():
                break
            match = LABEL_RE.match(line.strip())
        if not line.strip():
            continue

        equ = EQU_RE.match(line.strip())
        if equ:
            symbols[equ.group(1)] = evaluate(equ.group(2), symbols, path, lineno)
            continue

        tokens = line.strip().split(None, 1)
        mnemonic = tokens[0].upper()
        rest = tokens[1] if len(tokens) > 1 else ""

        if mnemonic in ALIASES:
            mnemonic, extra = ALIASES[mnemonic]
            rest = ", ".join(extra + ([rest] if rest.strip() else []))
        if mnemonic not in OPCODES:
            raise AsmError(path, lineno, f"unknown instruction {mnemonic!r}")

        operands, delay = split_operands(rest)
        raw.append((lineno, line.strip(), mnemonic, operands, delay))
        addr += 1

    if addr > imem_words:
        raise AsmError(path, 0, f"program is {addr} words, imem_words is {imem_words}")

    out: list[Insn] = []
    for index, (lineno, text, mnemonic, operands, delay_expr) in enumerate(raw):
        opcode, shape, timing = OPCODES[mnemonic]
        delay = evaluate(delay_expr, symbols, path, lineno) if delay_expr else 0
        check_range(delay, DELAY_MAX, "delay", path, lineno)

        a = b = x = 0
        nbits = 1

        if shape == NONE:
            expect_operands(mnemonic, operands, 0, path, lineno)
        elif shape == IMM8:
            expect_operands(mnemonic, operands, 1, path, lineno)
            value = bounded_imm(operands[0], IMM8_MAX, "immediate", symbols, path, lineno)
            b, x = value >> 5, value & SHIFT_MAX
        elif shape == REG:
            expect_operands(mnemonic, operands, 1, path, lineno)
            a = parse_register(operands[0], path, lineno)
        elif shape == REG_N:
            expect_operands(mnemonic, operands, 2, path, lineno)
            a = parse_register(operands[0], path, lineno)
            nbits = evaluate(operands[1], symbols, path, lineno)
            if not 1 <= nbits <= MAX_SHIFT_BITS:
                raise AsmError(path, lineno,
                               f"bit count {nbits} out of range 1..{MAX_SHIFT_BITS}")
            x = nbits & SHIFT_MAX
        elif shape == REG_REG:
            expect_operands(mnemonic, operands, 2, path, lineno)
            a = parse_register(operands[0], path, lineno)
            b = parse_register(operands[1], path, lineno)
        elif shape == REG_IMM8:
            expect_operands(mnemonic, operands, 2, path, lineno)
            a = parse_register(operands[0], path, lineno)
            value = bounded_imm(operands[1], IMM8_MAX, "immediate", symbols, path, lineno)
            b, x = value >> 5, value & SHIFT_MAX
        elif shape == REG_SHIFT:
            expect_operands(mnemonic, operands, 2, path, lineno)
            a = parse_register(operands[0], path, lineno)
            x = bounded_imm(operands[1], MAX_SHIFT_BITS, "shift amount", symbols, path, lineno)
        elif shape == BRANCH:
            expect_operands(mnemonic, operands, 2, path, lineno)
            cond = operands[0].strip().upper()
            if cond not in CONDITIONS:
                raise AsmError(path, lineno,
                               f"unknown condition {cond!r}, expected one of "
                               f"{', '.join(sorted(CONDITIONS))}")
            a = CONDITIONS[cond]
            target = bounded_imm(operands[1], IMM8_MAX, "branch target", symbols, path, lineno)
            b, x = target >> 5, target & SHIFT_MAX
        elif shape == TARGET:
            expect_operands(mnemonic, operands, 1, path, lineno)
            target = bounded_imm(operands[0], IMM8_MAX, "call target", symbols, path, lineno)
            b, x = target >> 5, target & SHIFT_MAX

        word = ((opcode << OP_SHIFT) | (a << A_SHIFT) | (b << B_SHIFT)
                | (x << X_SHIFT) | delay)

        # D is the cell duration, and every instruction occupies at least one
        # cycle. A trailing fetch cycle here would put every waveform edge one
        # cycle past its bit period, which no firmware could correct.
        cell = max(delay, 1)
        if timing == "perbit":
            cycles, cost, bounded = nbits * cell, f"{nbits}x{cell}", False
        elif timing == "bounded":
            cycles, cost, bounded = cell, f"w<={cell}", True
        else:
            cycles, cost, bounded = cell, f"{cell}", False

        out.append(Insn(word, mnemonic, index, cost, cycles, bounded, lineno, text))

    return out


# --- output -----------------------------------------------------------------

def format_listing(program: list[Insn]) -> str:
    """A listing whose right-hand columns are the timing argument."""
    # Built from the row format so the columns cannot drift apart.
    header = f"{'addr':<4}  {'word':<8}  {'cycles':>14}  {'total':>8}  source"
    lines = [header, "-" * len(header)]
    running = 0
    bounded_seen = False
    for insn in program:
        running += insn.cycles
        bounded_seen |= insn.bounded
        marker = "<=" if insn.bounded else "  "
        lines.append(f"{insn.addr:04d}  {insn.word:08x}  {insn.cost:>14}  "
                     f"{marker}{running:6d}  {insn.text}")
    lines.append("")
    if bounded_seen:
        lines.append(f"Worst case {running} cycles. The program contains a WAITE, so this "
                     "is an upper")
        lines.append("bound rather than an exact duration; every other instruction is exact.")
    else:
        lines.append(f"Exactly {running} cycles. No WAITE, so this is a value, not a bound.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="assembly source file")
    parser.add_argument("-o", "--output", type=Path, help="write a little-endian binary image")
    parser.add_argument("--listing", action="store_true",
                        help="print the static timing listing")
    parser.add_argument("--hex", type=Path, help="write a $readmemh image for simulation")
    parser.add_argument("--imem-words", type=int, default=256,
                        help="program memory depth, matching the profile knob (default: 256)")
    args = parser.parse_args(argv)

    try:
        program = assemble(args.source.read_text(encoding="utf-8"),
                           args.source, args.imem_words)
    except AsmError as exc:
        print(f"axpe-as: {exc}", file=sys.stderr)
        return 1

    if args.output:
        args.output.write_bytes(b"".join(struct.pack("<I", i.word) for i in program))
    if args.hex:
        args.hex.write_text("".join(f"{i.word:08x}\n" for i in program), encoding="utf-8")
    if args.listing or not (args.output or args.hex):
        print(format_listing(program))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
