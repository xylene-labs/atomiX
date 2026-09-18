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

    # Bit layouts inside a field: `shcfg_layout` and `shift_b_layout` at the
    # top level, and an instruction's own `imm8_layout`. Overlapping sub-fields
    # are the kind of encoding bug that decodes correctly in the one case
    # anybody tried, so they are refused here rather than left to a reviewer.
    def check_layout(where: str, entries: list[dict[str, Any]], width: int) -> None:
        taken: dict[int, str] = {}
        for entry in entries:
            if not 0 <= entry["lo"] <= entry["hi"] < width:
                raise IsaError(f"{where}.{entry['name']} is outside its {width}-bit field")
            for bit in range(entry["lo"], entry["hi"] + 1):
                if bit in taken:
                    raise IsaError(f"{where}: {taken[bit]} and {entry['name']} "
                                   f"both claim bit {bit}")
                taken[bit] = entry["name"]

    for name, entries in layouts(isa).items():
        check_layout(name, entries, field_width(isa, layout_field(name)))

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
        if "imm8_layout" in insn:
            check_layout(f"{mnemonic}.imm8_layout", insn["imm8_layout"],
                         field_width(isa, "b") + field_width(isa, "x"))
        if "b_layout" in insn and insn["b_layout"] not in layouts(isa):
            raise IsaError(f"{mnemonic} names layout {insn['b_layout']!r}, "
                           "which is not described")
        alternate = insn.get("timing_p")
        if alternate is not None:
            if alternate not in isa["timing"]:
                raise IsaError(f"{mnemonic} has unknown timing_p {alternate!r}")
            if "b_layout" not in insn:
                raise IsaError(f"{mnemonic} selects a second timing but describes "
                               "no field to select it with")
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
    # second data-dependent instruction cannot pass unnoticed.  An instruction
    # with an alternate timing is checked in both of them: a select bit that
    # smuggled in a data-dependent cost would defeat the whole proof.
    def costs(insn: dict[str, Any]) -> list[dict[str, Any]]:
        names = [insn["timing"]] + ([insn["timing_p"]] if "timing_p" in insn else [])
        return [isa["timing"][name] for name in names]

    inexact = [i["mnemonic"] for i in isa["instructions"]
               if not all(c["exact"] for c in costs(i))]
    if inexact != ["WAITE"]:
        raise IsaError(f"only WAITE may have an inexact cost, but {inexact} do")

    # Exact and statically known are different claims, and conflating them is
    # how "the listing prints the cycle count" would quietly become false.  A
    # cost that is not exact cannot be static; a cost that is exact may still
    # be unknown until the machine runs, which is what the period register
    # makes true of a shift.
    for name, rule in isa["timing"].items():
        if "static" not in rule:
            raise IsaError(f"timing {name} does not say whether it is static")
        if rule["static"] and not rule["exact"]:
            raise IsaError(f"timing {name} claims to be static without being exact")

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


def field_width(isa: dict[str, Any], name: str) -> int:
    spec = isa["encoding"]["fields"][name]
    return spec["hi"] - spec["lo"] + 1


def layout_field(name: str) -> str:
    """Which encoding field a `<what>_<field>_layout` key lays out.

    The convention is the last underscore-separated word before `_layout`, so
    `shift_b_layout` describes bits inside the `b` field.
    """
    return name[: -len("_layout")].rsplit("_", 1)[-1]


def layouts(isa: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Top-level layouts of bits inside an *encoding field*.

    `shcfg_layout` is deliberately not one of these. It describes a register
    the machine holds, not a slice of the instruction word, so there is no
    field width to check it against and no decoder constant to generate from
    it; it stays a documented layout that the RTL and the model read by hand.
    """
    fields = isa["encoding"]["fields"]
    return {key: value for key, value in isa.items()
            if key.endswith("_layout") and layout_field(key) in fields}


def layout_prefix(name: str) -> str:
    return name[: -len("_layout")].upper()


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
    for name, entries in layouts(isa).items():
        lines += ["", f"// Bits inside the {layout_field(name)} field: {name}"]
        for entry in entries:
            upper = f"{layout_prefix(name)}_{entry['name'].upper()}"
            lines.append(f"localparam int AXPE_{upper}_HI = {entry['hi']};")
            lines.append(f"localparam int AXPE_{upper}_LO = {entry['lo']};")
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
    for name, entries in layouts(isa).items():
        lines.append(f"/* Bits inside the {layout_field(name)} field: {name} */")
        for entry in entries:
            upper = f"{layout_prefix(name)}_{entry['name'].upper()}"
            mask = ((1 << (entry["hi"] - entry["lo"] + 1)) - 1) << entry["lo"]
            lines.append(f"#define AXPE_{upper}_LO   {entry['lo']}")
            lines.append(f"#define AXPE_{upper}_MASK 0x{mask:02x}u")
        lines.append("")
    lines += ["typedef enum {"]
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
            # An instruction with a select bit costs one of two things, and
            # printing only the first would be the table telling half the
            # truth about the one property this ISA exists for.
            formula = " or ".join(f"`{isa['timing'][name]['formula']}`"
                                  for name in [insn["timing"]]
                                  + ([insn["timing_p"]] if "timing_p" in insn else []))
            lines.append(f"| `{insn['opcode']:02X}` | `{insn['mnemonic']}` | {operands} "
                         f"| {formula} | {insn['doc']} |")
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
