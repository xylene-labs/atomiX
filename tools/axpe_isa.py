#!/usr/bin/env python3
"""Load, validate, and generate from the single axpe ISA description.

`sw/pemu/isa/axpe-isa.json` is the only place the instruction set is written
down.  The assembler imports it at runtime; the SystemVerilog decoder, the C
golden model's tables, and the instruction tables inside `axpe-isa.md` are
generated from it here.

The point is not tidiness.  An instruction set that is transcribed into an
assembler, a model, a decoder, a proof, and a document is written five times,
and five copies drift -- usually silently, and usually in the field that nobody
re-reads, which for this design is a cycle count.  Generating them removes the
opportunity rather than policing it.

    python3 tools/axpe_isa.py generate   # rewrite every derived artifact
    python3 tools/axpe_isa.py check      # fail if any of them has drifted

`check` is what a build gate runs, mirroring `make requirements-check`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ISA_JSON = ROOT / "sw" / "pemu" / "isa" / "axpe-isa.json"
ISA_DOC = ROOT / "sw" / "pemu" / "isa" / "axpe-isa.md"
MANIFEST = ROOT / "components" / "pemu" / "axpe" / "component.json"
SV_HEADER = ROOT / "sw" / "pemu" / "isa" / "axpe_isa.svh"
C_HEADER = ROOT / "sw" / "pemu" / "isa" / "axpe_isa.h"

BANNER = "axpe-isa.json"
DOC_BEGIN = "<!-- generated from axpe-isa.json: instructions -->"
DOC_END = "<!-- end generated -->"


class IsaError(Exception):
    """The ISA description is internally inconsistent."""


def load(path: Path = ISA_JSON) -> dict[str, Any]:
    """Load the description and reject one that cannot be implemented."""
    isa = json.loads(path.read_text(encoding="utf-8"))

    width = isa["encoding"]["width"]
    fields = isa["encoding"]["fields"]

    covered: dict[int, str] = {}
    for name, spec in fields.items():
        if not 0 <= spec["lo"] <= spec["hi"] < width:
            raise IsaError(f"field {name} is outside the {width}-bit word")
        for bit in range(spec["lo"], spec["hi"] + 1):
            if bit in covered:
                raise IsaError(f"fields {covered[bit]} and {name} both claim bit {bit}")
            covered[bit] = name
    missing = sorted(set(range(width)) - set(covered))
    if missing:
        raise IsaError(f"bits {missing} belong to no field; the encoding has holes")

    op_bits = fields["op"]["hi"] - fields["op"]["lo"] + 1
    seen: dict[int, str] = {}
    for insn in isa["instructions"]:
        opcode, mnemonic = insn["opcode"], insn["mnemonic"]
        if opcode in seen:
            raise IsaError(f"opcode {opcode} used by both {seen[opcode]} and {mnemonic}")
        if not 0 <= opcode < (1 << op_bits):
            raise IsaError(f"{mnemonic} opcode {opcode} does not fit {op_bits} bits")
        if insn["shape"] not in isa["shapes"]:
            raise IsaError(f"{mnemonic} has unknown shape {insn['shape']!r}")
        if insn["timing"] not in isa["timing"]:
            raise IsaError(f"{mnemonic} has unknown timing {insn['timing']!r}")
        if insn["group"] not in isa["groups"]:
            raise IsaError(f"{mnemonic} has unknown group {insn['group']!r}")
        seen[opcode] = mnemonic

    for opcode in isa["reserved_opcodes"]:
        if opcode in seen:
            raise IsaError(f"opcode {opcode} is both reserved and used by {seen[opcode]}")

    total = len(seen) + len(isa["reserved_opcodes"])
    if total != (1 << op_bits):
        raise IsaError(f"{total} encodings described, but {op_bits} opcode bits hold "
                       f"{1 << op_bits}; every encoding must be named or reserved")

    # Exactly one instruction may have a cost that is a bound rather than a
    # value.  This is the central property, checked here so that adding a
    # second data-dependent instruction cannot pass unnoticed.
    inexact = [i["mnemonic"] for i in isa["instructions"]
               if not isa["timing"][i["timing"]]["exact"]]
    if inexact != ["WAITE"]:
        raise IsaError(f"only WAITE may have an inexact cost, but {inexact} do")

    for alias, spec in isa.get("aliases", {}).items():
        if alias in seen.values():
            raise IsaError(f"alias {alias} collides with a real instruction")
        if spec["expands_to"] not in seen.values():
            raise IsaError(f"alias {alias} expands to unknown {spec['expands_to']!r}")

    return isa


def check_manifest_agrees(isa: dict[str, Any], manifest_path: Path = MANIFEST) -> None:
    """The component manifest and the ISA description must not drift apart.

    The manifest owns the build knobs a profile can change; this file owns the
    architecture.  They overlap on register count, register width, and the
    delay field, and a profile that silently disagrees with the ISA about how
    wide a register is would produce an assembler and an RTL that compile
    happily and then disagree on real pins.  The manifest's *default* is the
    architecture's value; a profile may still override it, which is the whole
    point of a knob.
    """
    if not manifest_path.exists():
        raise IsaError(f"{manifest_path.name} is missing; the ISA has no component to build")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parameters = manifest.get("parameters", {})

    delay = isa["encoding"]["fields"]["delay"]
    expected = {
        "reg_count": isa["registers"]["count"],
        "reg_width": isa["registers"]["width"],
        "delay_bits": delay["hi"] - delay["lo"] + 1,
    }
    for name, value in expected.items():
        if name not in parameters:
            raise IsaError(f"{manifest_path.name} declares no {name!r} parameter, "
                           f"but the ISA fixes it at {value}")
        default = parameters[name]["default"]
        if default != value:
            raise IsaError(f"{manifest_path.name} defaults {name} to {default}, "
                           f"but axpe-isa.json says {value}")

    # A knob with no `doc` reads as configurable and explains nothing, which is
    # the failure mode the project's own rule exists to prevent.
    undocumented = sorted(n for n, spec in parameters.items()
                          if not spec.get("doc") or "define" not in spec)
    if undocumented:
        raise IsaError(f"{manifest_path.name} parameters missing doc or define: {undocumented}")


def field_mask(spec: dict[str, int]) -> int:
    return ((1 << (spec["hi"] - spec["lo"] + 1)) - 1) << spec["lo"]


def render_sv(isa: dict[str, Any]) -> str:
    """SystemVerilog localparams for the decoder."""
    lines = [
        "// Generated from " + BANNER + ". Do not edit.",
        "// Regenerate with: python3 tools/axpe_isa.py generate",
        "",
        "`ifndef AXPE_ISA_SVH",
        "`define AXPE_ISA_SVH",
        "",
        "// This header exports the whole instruction set. A consumer using a",
        "// subset of it is the normal case, not a defect.",
        "/* verilator lint_off UNUSEDPARAM */",
        "",
        f"localparam int AXPE_WORD_W = {isa['encoding']['width']};",
        f"localparam int AXPE_REGS   = {isa['registers']['count']};",
        f"localparam int AXPE_REG_W  = {isa['registers']['width']};",
        "",
        "// Field positions",
    ]
    for name, spec in isa["encoding"]["fields"].items():
        upper = name.upper()
        lines.append(f"localparam int AXPE_{upper}_HI = {spec['hi']};")
        lines.append(f"localparam int AXPE_{upper}_LO = {spec['lo']};")
    lines += ["", "// Opcodes"]
    op_bits = isa["encoding"]["fields"]["op"]["hi"] - isa["encoding"]["fields"]["op"]["lo"] + 1
    for insn in isa["instructions"]:
        lines.append(f"localparam logic [{op_bits - 1}:0] AXPE_OP_{insn['mnemonic']} = "
                     f"{op_bits}'d{insn['opcode']};")
    lines += ["", "// Branch conditions"]
    for name, value in isa["conditions"].items():
        lines.append(f"localparam logic [2:0] AXPE_COND_{name} = 3'd{value};")
    lines += ["", "/* verilator lint_on UNUSEDPARAM */", "`endif", ""]
    return "\n".join(lines)


def render_c(isa: dict[str, Any]) -> str:
    """Opcode enum and timing table for the golden model."""
    lines = [
        "/* Generated from " + BANNER + ". Do not edit.",
        " * Regenerate with: python3 tools/axpe_isa.py generate */",
        "",
        "#ifndef AXPE_ISA_H",
        "#define AXPE_ISA_H",
        "",
        "#include <stdint.h>",
        "",
        f"#define AXPE_REGS  {isa['registers']['count']}",
        f"#define AXPE_REG_W {isa['registers']['width']}",
        "",
    ]
    for name, spec in isa["encoding"]["fields"].items():
        upper = name.upper()
        lines.append(f"#define AXPE_{upper}_LO   {spec['lo']}")
        lines.append(f"#define AXPE_{upper}_MASK 0x{field_mask(spec):08x}u")
    lines += ["", "typedef enum {"]
    for insn in isa["instructions"]:
        lines.append(f"    AXPE_OP_{insn['mnemonic']} = {insn['opcode']},")
    lines += ["} axpe_opcode_t;", ""]

    lines += ["/* How each opcode spends cycles. */", "typedef enum {"]
    for name in isa["timing"]:
        lines.append(f"    AXPE_TIMING_{name.upper()},  /* {isa['timing'][name]['formula']} */")
    lines += ["} axpe_timing_t;", ""]

    lines += ["static const axpe_timing_t axpe_timing_of[32] = {"]
    by_opcode = {i["opcode"]: i for i in isa["instructions"]}
    for opcode in range(32):
        insn = by_opcode.get(opcode)
        if insn is None:
            lines.append(f"    [{opcode}] = AXPE_TIMING_FIXED,  /* reserved */")
        else:
            lines.append(f"    [{opcode}] = AXPE_TIMING_{insn['timing'].upper()},"
                         f"  /* {insn['mnemonic']} */")
    lines += ["};", ""]

    lines += ["static const char *const axpe_mnemonic_of[32] = {"]
    for opcode in range(32):
        insn = by_opcode.get(opcode)
        name = f'"{insn["mnemonic"]}"' if insn else "0"
        lines.append(f"    [{opcode}] = {name},")
    lines += ["};", "", "#endif /* AXPE_ISA_H */", ""]
    return "\n".join(lines)


def render_doc_tables(isa: dict[str, Any]) -> str:
    """The instruction tables for axpe-isa.md."""
    lines = [DOC_BEGIN, ""]
    by_group: dict[str, list[dict[str, Any]]] = {}
    for insn in isa["instructions"]:
        by_group.setdefault(insn["group"], []).append(insn)

    for group, heading in isa["groups"].items():
        if group not in by_group:
            continue
        lines += [f"### {heading}", "",
                  "| Op | Mnemonic | Operands | Retires in | Effect |",
                  "|---|---|---|---|---|"]
        for insn in by_group[group]:
            shape = isa["shapes"][insn["shape"]]
            operands = ", ".join(shape["operands"]) or "--"
            formula = isa["timing"][insn["timing"]]["formula"]
            lines.append(f"| `{insn['opcode']:02X}` | `{insn['mnemonic']}` | {operands} "
                         f"| `{formula}` | {insn['doc']} |")
        lines.append("")

    reserved = ", ".join(f"`{o:02X}`" for o in isa["reserved_opcodes"])
    lines += [f"Reserved encodings: {reserved}. Held for stretch protocols.", "",
              DOC_END]
    return "\n".join(lines)


def splice_doc(existing: str, tables: str) -> str:
    if DOC_BEGIN not in existing or DOC_END not in existing:
        raise IsaError(f"{ISA_DOC.name} is missing the {DOC_BEGIN} / {DOC_END} markers")
    head = existing.split(DOC_BEGIN)[0]
    tail = existing.split(DOC_END, 1)[1]
    return head + tables + tail


def artifacts(isa: dict[str, Any]) -> list[tuple[Path, str]]:
    out = [(SV_HEADER, render_sv(isa)), (C_HEADER, render_c(isa))]
    if ISA_DOC.exists():
        out.append((ISA_DOC, splice_doc(ISA_DOC.read_text(encoding="utf-8"),
                                        render_doc_tables(isa))))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("generate", "check"))
    args = parser.parse_args(argv)

    try:
        isa = load()
        check_manifest_agrees(isa)
        generated = artifacts(isa)
    except (IsaError, KeyError) as exc:
        print(f"axpe-isa: {exc}", file=sys.stderr)
        return 1

    if args.action == "generate":
        for path, content in generated:
            path.write_text(content, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
        return 0

    stale = [path for path, content in generated
             if not path.exists() or path.read_text(encoding="utf-8") != content]
    if stale:
        print("axpe-isa: these are stale against axpe-isa.json:", file=sys.stderr)
        for path in stale:
            print(f"  - {path.relative_to(ROOT)}", file=sys.stderr)
        print("Run: python3 tools/axpe_isa.py generate", file=sys.stderr)
        return 1
    print(f"axpe-isa: {len(generated)} generated artifact(s) match axpe-isa.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
