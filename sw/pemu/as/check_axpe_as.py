#!/usr/bin/env python3
"""Self-checks for the axpe assembler and the ISA's timing contract.

These assert the two things that must not drift apart: the encoding in
sw/pemu/isa/axpe-isa.md, and what axpe_as.py emits for it.  The timing cases
derive their expected cycle counts from the ISA rule (1 + D, 1 + n*D, bounded
by D) rather than repeating a number, so re-hardcoding a cost in the assembler
fails here instead of silently changing a protocol's bit period.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from axpe_as import (
    DELAY_MAX,
    OPCODES,
    RETURNS_TIME,
    AsmError,
    assemble,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
import axpe_isa

HERE = Path(__file__).resolve().parent
FIRMWARE = HERE.parent / "firmware"
FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)


def asm(text: str, imem_words: int = 256):
    return assemble(text, Path("<test>"), imem_words)


def expect_error(text: str, fragment: str, what: str, imem_words: int = 256) -> None:
    try:
        asm(text, imem_words)
    except AsmError as exc:
        check(fragment in str(exc), f"{what}: expected {fragment!r} in {exc}")
        return
    FAILURES.append(f"{what}: expected an AsmError, got none")


def check_encoding() -> None:
    """Spot-check the field layout against hand-computed words."""
    cases = [
        ("PDIR 0x01, D=0",      0x38010000, "PDIR imm8 lands in the x field"),
        ("SHOUT R0, 8, D=434",  0x580801B2, "SHOUT packs bit count and delay"),
        ("WAITE R0, 0x11, D=6944", 0x48111B20, "WAITE uses delay as its timeout"),
        ("WAITE R3, 0x11, D=0",    0x4B110000, "WAITE names a destination register"),
        ("BR T, 19, D=0",       0xE5130000, "BR puts the condition in a"),
        ("HALT D=0",            0xF8000000, "HALT is opcode 0x1F"),
        ("MOV R3, R5, D=0",     0x83A00000, "MOV packs both registers"),
    ]
    for text, expected, what in cases:
        word = asm(text)[0].word
        check(word == expected, f"{what}: got {word:#010x}, expected {expected:#010x}")


def check_timing_rule() -> None:
    """Every fixed-cost instruction occupies exactly max(D, 1). No exceptions."""
    for mnemonic, (_opcode, _shape, timing) in sorted(OPCODES.items()):
        if timing != "fixed":
            continue
        operands = {
            "none": "", "imm8": " 0x00,", "reg": " R0,", "reg_reg": " R0, R1,",
            "reg_imm8": " R0, 0x00,", "reg_shift": " R0, 1,", "branch": " Z, 0,",
            "target": " 0,",
        }[_shape]
        for delay in (0, 1, 999, DELAY_MAX):
            insn = asm(f"{mnemonic}{operands} D={delay}")[0]
            expected = max(delay, 1)
            check(insn.cycles == expected,
                  f"{mnemonic} at D={delay} costs {insn.cycles}, ISA says {expected}")
            check(not insn.bounded, f"{mnemonic} must not be a bounded cost")


def check_perbit_rule() -> None:
    """Shift instructions occupy n*max(D,1), for every n the field can hold."""
    for mnemonic in ("SHOUT", "SHIN", "SHIO"):
        for nbits in range(1, 17):
            for delay in (0, 7, 434):
                insn = asm(f"{mnemonic} R0, {nbits}, D={delay}")[0]
                expected = nbits * max(delay, 1)
                check(insn.cycles == expected,
                      f"{mnemonic} R0,{nbits} at D={delay} costs {insn.cycles}, "
                      f"ISA says {expected}")


def check_waite_is_bounded() -> None:
    insn = asm("WAITE R0, 0x11, D=6944")[0]
    check(insn.bounded, "WAITE must report a bound, not a value")
    check(insn.cycles == 6944, "WAITE's bound is max(D, 1)")
    for mnemonic in OPCODES:
        if mnemonic == "WAITE":
            continue
        shape = OPCODES[mnemonic][1]
        if shape != "none":
            continue
        check(not asm(f"{mnemonic} D=5")[0].bounded,
              f"{mnemonic} must be exact; only WAITE may be bounded")


def check_waite_returns_time() -> None:
    """WAITE is the only instruction that hands its elapsed count back.

    The `a` field was unused by WAITE before this, so the destination register
    costs nothing in the encoding -- which is the whole reason the measurement
    feature is affordable. Guard both halves of that claim.
    """
    check(set(RETURNS_TIME) == {"WAITE"},
          f"only WAITE should return time, got {sorted(RETURNS_TIME)}")
    for reg in range(8):
        word = asm(f"WAITE R{reg}, 0x11, D=100")[0].word
        check((word >> 24) & 0x7 == reg,
              f"WAITE R{reg} should encode {reg} in the a field, got {(word >> 24) & 0x7}")
    # The destination register must not disturb any other field.
    base = asm("WAITE R0, 0x11, D=100")[0].word
    for reg in range(1, 8):
        word = asm(f"WAITE R{reg}, 0x11, D=100")[0].word
        check(word & ~(0x7 << 24) == base & ~(0x7 << 24),
              f"WAITE R{reg} changed a field other than a")


def check_isa_is_the_single_source() -> None:
    """Every generated artifact must still match axpe-isa.json.

    This is the bet that the ISA is written once. If it can drift, it is not.
    """
    try:
        isa = axpe_isa.load()
    except axpe_isa.IsaError as exc:
        FAILURES.append(f"axpe-isa.json is invalid: {exc}")
        return
    for path, content in axpe_isa.artifacts(isa):
        if not path.exists():
            FAILURES.append(f"{path.name} has never been generated")
        elif path.read_text(encoding="utf-8") != content:
            FAILURES.append(f"{path.name} has drifted from axpe-isa.json")

    check(OPCODES.keys() == {i["mnemonic"] for i in isa["instructions"]},
          "the assembler's opcode table should come entirely from the ISA file")
    described = len(isa["instructions"]) + len(isa["reserved_opcodes"])
    check(described == 32, f"{described} encodings described, the op field holds 32")


def check_autobaud_firmware() -> None:
    """The autobaud routine must measure, not assume."""
    program = asm((FIRMWARE / "autobaud.s").read_text(encoding="utf-8"))
    waits = [i for i in program if i.mnemonic == "WAITE"]
    check(len(waits) == 2, f"autobaud should use two WAITEs, found {len(waits)}")
    check(all(i.bounded for i in waits), "both WAITEs must report a bound")
    check({(i.word >> 24) & 0x7 for i in waits} == {0, 1},
          "autobaud should capture its two measurements into different registers")
    check(not any(i.mnemonic in ("SHOUT", "SHIN", "SHIO") for i in program),
          "autobaud only listens; it should not drive the shift engine")


def check_uart_firmware() -> None:
    """The UART transmit path costs exactly 7 + 10*BAUD, as the ISA doc claims.

    Derived from the rule, not copied from a previous run: three setup
    instructions and a RET at 1 cycle each, a start and a stop bit at 1 + BAUD,
    and eight data bits at 1 + 8*BAUD.
    """
    source = (FIRMWARE / "uart.s").read_text(encoding="utf-8")
    program = asm(source)
    by_line = {insn.text.split()[0]: insn for insn in program}
    check("SHOUT" in by_line, "uart.s should contain a SHOUT")

    baud = 50000000 // 115200
    start = next(i for i, x in enumerate(program) if x.text.startswith("LDIL   R1, SHCFG_TX_LO"))
    end = next(i for i, x in enumerate(program[start:], start=start) if x.mnemonic == "RET")
    tx = program[start:end + 1]

    expected = 3 * 1 + baud + 8 * baud + baud + 1
    actual = sum(i.cycles for i in tx)
    check(expected == 4 + 10 * baud, "the ISA document's closed form should match the rule")
    check(actual == expected,
          f"uart_tx costs {actual} cycles, the ISA rule gives {expected}")
    check(not any(i.bounded for i in tx), "the transmit path must be exact, with no WAITE")


def check_diagnostics() -> None:
    """A bad program must fail loudly, not assemble into something plausible."""
    expect_error("MOV R8, R1, D=0", "register", "register out of range")
    expect_error("DELAY D=70000", "out of range", "delay past the 16-bit field")
    expect_error("FROB R0, D=0", "unknown instruction", "unknown mnemonic")
    expect_error("CALL 300, D=0", "out of range", "call target past the 8-bit field")
    expect_error("SHOUT R0, 17, D=1", "bit count", "shift count past 16 bits")
    expect_error("BR NOPE, 0, D=0", "unknown condition", "unknown branch condition")
    expect_error("DELAY D=NOSUCH", "undefined symbol", "undefined symbol")
    expect_error("MOV R0, R1, D=0\n" * 4, "imem_words", "program larger than imem",
                 imem_words=3)
    expect_error("DELAY D=1/0", "division by zero", "division by zero")


def check_imem_bound_is_a_knob() -> None:
    """imem_words is a profile knob, so the same program fits or does not."""
    program = "NOP\n" * 8
    check(len(asm(program, imem_words=8)) == 8, "8 words should fit an 8-word imem")
    expect_error_small = False
    try:
        assemble(program, Path("<test>"), imem_words=4)
    except AsmError:
        expect_error_small = True
    check(expect_error_small, "8 words must not fit a 4-word imem")


def main() -> int:
    for probe in (check_encoding, check_timing_rule, check_perbit_rule,
                  check_waite_is_bounded, check_waite_returns_time,
                  check_isa_is_the_single_source, check_uart_firmware,
                  check_autobaud_firmware, check_diagnostics,
                  check_imem_bound_is_a_knob):
        try:
            probe()
        except Exception as exc:  # a crashing check is a failing check
            FAILURES.append(f"{probe.__name__} raised {exc!r}")

    if FAILURES:
        print(f"axpe-as self-check: {len(FAILURES)} failure(s)", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("axpe-as self-check: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
