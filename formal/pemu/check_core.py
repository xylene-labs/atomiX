#!/usr/bin/env python3
"""Prove complete legal axpe instruction-stream timing at the selected profile."""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from check_timing import ROOT, BUILD, expression, sha
from check_shift import execute

sys.path.insert(0, str(ROOT / "tools"))
import configure

HERE = Path(__file__).resolve().parent
COVERS = (
    "register_period",
    "shift_wait",
    "wait_shift",
    "shift_chain",
    "wait_chain",
    "changed_word",
    "max_delay",
    "max_count",
    "timeout",
    "final_event",
    "immediate",
    "mode0",
    "mode1",
    "mode2",
    "mode3",
)


def render(spec, params):
    fields = spec["encoding"]["fields"]
    if spec["encoding"]["width"] != 32 or any(
        fields[key]["hi"] - fields[key]["lo"] + 1 != width
        for key, width in (("op", 5), ("a", 3), ("b", 3), ("x", 5), ("delay", 16))
    ):
        raise ValueError("unsupported instruction field widths")
    insns = {i["mnemonic"]: i for i in spec["instructions"]}
    supported = set(
        "DELAY PINSET PINCLR PINTOG PINW POUT PINR PDIR PDRN WAITE SHCFG SHOUT SHIN SHIO SHPER MOV ADD SUB AND OR XOR SHL SHR LDIL LDIH ADDI CMP BR CALL RET HALT".split()
    )
    if set(insns) != supported:
        raise ValueError("instruction set changed; extend the proof domain")
    for name, item in insns.items():
        expected = (
            "perbit"
            if name in ("SHOUT", "SHIN", "SHIO")
            else "bounded"
            if name == "WAITE"
            else "fixed"
        )
        if item["timing"] != expected:
            raise ValueError(f"timing class changed: {name}")
    formula = spec["timing"]["fixed"]["formula"]
    duration = expression(ast.parse(formula, mode="eval").body, params["delay_bits"])
    tree = ast.parse(spec["timing"]["perbit"]["formula"], mode="eval").body
    if not (
        isinstance(tree, ast.BinOp)
        and isinstance(tree.op, ast.Mult)
        and isinstance(tree.left, ast.Name)
        and tree.left.id == "n"
        and ast.dump(tree.right) == ast.dump(ast.parse(formula, mode="eval").body)
    ):
        raise ValueError("shift formula is not n times the fixed cell formula")
    if ast.dump(
        ast.parse(spec["timing"]["perbit_reg"]["formula"].replace("P", "D"), mode="eval").body
    ) != ast.dump(tree):
        raise ValueError("register-period formula differs")
    bounded = re.fullmatch(r"w,\s*1<=w<=(.+)", spec["timing"]["bounded"]["formula"])
    if not bounded or ast.dump(ast.parse(bounded[1], mode="eval").body) != ast.dump(tree.right):
        raise ValueError("wait bound differs from fixed duration")
    cfg = {item["name"]: item for item in spec["shcfg_layout"]}
    shape = {item["name"]: item for item in spec["shift_b_layout"]}
    wait = {item["name"]: item for item in insns["WAITE"]["imm8_layout"]}
    imm_fields = [fields[name] for name in spec["encoding"]["overlays"]["imm8"]["fields"]]
    replacements = {
        "OP_CONSTANTS": "\n    ".join(
            f"localparam [4:0] OP_{name}=5'd{item['opcode']};" for name, item in insns.items()
        ),
        "LEGAL_OPS": " || ".join(f"op==OP_{name}" for name in insns),
        "LEGAL_CONDITIONS": " || ".join(f"ra==3'd{value}" for value in spec["conditions"].values()),
        "DURATION": duration,
        "CELL_DURATION": duration.replace("delay", "effective_cell"),
        "HELD_DURATION": duration.replace("delay", "hold_delay"),
        "ENCODED_DURATION": duration.replace("delay", "encoded_cell"),
        "MAX_DELAY": (1 << params["delay_bits"]) - 1,
        "REG_W": params["reg_width"],
        "UIO_PINS": params["uio_pins"],
        "STACK_W": params["call_depth"].bit_length(),
        "CALL_DEPTH": params["call_depth"],
        "IMEM_REACH": min(
            params["imem_words"],
            1 << (max(x["hi"] for x in imm_fields) - min(x["lo"] for x in imm_fields) + 1),
        ),
        "IMM_LO": min(x["lo"] for x in imm_fields),
        "IMM_HI": max(x["hi"] for x in imm_fields),
        "PERIOD_BIT": shape["p"]["lo"],
        "RSV_HI": shape["rsv"]["hi"],
        "RSV_LO": shape["rsv"]["lo"],
        "NO_CLOCK": (1 << (cfg["clk"]["hi"] - cfg["clk"]["lo"] + 1)) - 1,
        "WAIT_IMM_MAX": (1 << (max(wait["pin"]["hi"], wait["edge"]["hi"]) + 1)) - 1,
    }
    for name, prefix in (("op", "OP"), ("a", "A"), ("b", "B"), ("x", "X"), ("delay", "D")):
        for end in ("hi", "lo"):
            replacements[f"{prefix}_{end.upper()}"] = fields[name][end]
    for name in ("clk", "dout", "din", "cpol", "cpha"):
        for end in ("hi", "lo"):
            replacements[f"{name.upper()}_{end.upper()}"] = cfg[name][end]
    for name in ("pin", "edge"):
        for end in ("hi", "lo"):
            replacements[f"{name.upper()}_{end.upper()}"] = wait[name][end]
    harness = (HERE / "core.sv.in").read_text()
    for key, value in replacements.items():
        harness = harness.replace(f"@{key}@", str(value))
    if re.search(r"@\w+@", harness):
        raise ValueError("unresolved harness placeholder")
    return harness, insns


def check(args, directory, core, harness, params, insns, mutant=False):
    directory.mkdir(parents=True)
    source = directory / "core.sv"
    source.write_text(harness)
    rtl = ROOT / "components/pemu/axpe"
    files = [rtl / f"axpe_{name}.sv" for name in ("decode", "timing", "shift", "pads")] + [core]
    settings = {
        "IMEM_WORDS": "imem_words",
        "REGS": "reg_count",
        "REG_W": "reg_width",
        "DELAY_BITS": "delay_bits",
        "UIO_PINS": "uio_pins",
        "CALL_DEPTH": "call_depth",
    }
    options = " ".join(f"-set {name} {params[key]}" for name, key in settings.items())
    observations = "state issue wait_over wait_timeout wait_count retire_data ft wait_prev hold_wpin hold_wedge hold_delay halt_pending reject src_a period shcfg sp cell_delay sh_delay sh_start sh_busy sh_done".split()
    nested = {
        "u_cell.remaining": "cell_remaining",
        "u_shift.state": "sh_state",
        "u_shift.index": "sh_index",
        "u_shift.total": "sh_total",
        "u_shift.u_cell.remaining": "sh_remaining",
    }
    prep = "read_verilog -sv -Isw/pemu/isa " + " ".join(json.dumps(str(p)) for p in files) + "\n"
    prep += f"chparam {options} axpe\nhierarchy -top axpe\nflatten\n"
    prep += (
        "expose " + " ".join("axpe/" + name for name in observations + list(nested)) + "\ncd axpe\n"
    )
    prep += "".join(f"rename {before} {after}\n" for before, after in nested.items()) + "cd ..\n"
    prep += f"read_verilog -formal -sv {json.dumps(str(source))}\nprep -top core_formal -flatten\nasync2sync\ndffunmap\n"
    script = directory / "proof.ys"
    script.write_text(
        prep + "sat -seq 6 -tempinduct -maxsteps 8 -prove-asserts -set-assumes -verify\n"
    )
    code, log = execute(args.yosys, script, args.timeout_seconds)
    record = {
        "harness_sha256": sha(source),
        "proof_script_sha256": sha(script),
        "proof_log_sha256": sha(script.with_suffix(".log")),
    }
    if mutant:
        if not (code and "model found for base case: FAIL!" in log):
            raise ValueError(f"mutation lacks a base-case counterexample: {directory}")
        return {**record, "result": "expected counterexample", "core_sha256": sha(core)}
    if code or "Induction step proven: SUCCESS!" not in log:
        raise ValueError(f"induction failed: {script.with_suffix('.log')}")
    record["result"] = "inductive pass"
    if args.proof_only:
        return record
    checks = {f"op_{name}": f"completed_op {1 << item['opcode']}" for name, item in insns.items()}
    checks.update({name: f"covered_{name} 1" for name in COVERS})
    record["covers"] = {}
    for name, condition in checks.items():
        script = directory / f"cover_{name}.ys"
        # Covers need a witness, not a long arbitrary prefix. Keep enough
        # setup for SHCFG/SHPER and reserve longer traces for full transfers.
        depth = 8 if name.startswith("op_") else 12
        if name == "max_count" or name.startswith("mode"):
            depth = params["reg_width"] + 6
        script.write_text(
            prep + f"sat -seq {depth} -set-assumes -set-at {depth} {condition} -show-outputs\n"
        )
        code, log = execute(args.yosys, script, args.timeout_seconds)
        if code or "SAT solving finished - model found:" not in log:
            raise ValueError(f"unreachable cover: {script}")
        record["covers"][name] = {
            "script_sha256": sha(script),
            "log_sha256": sha(script.with_suffix(".log")),
        }
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yosys", default=os.environ.get("YOSYS", "yosys"))
    parser.add_argument("--profile", type=Path, default=ROOT / "configs/tt-axpe-6x4.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument(
        "--proof-only",
        action="store_true",
        help="exploratory induction only; not an accepted complete gate",
    )
    args = parser.parse_args()
    if not 1 <= args.timeout_seconds <= 3600:
        raise ValueError("timeout must be 1..3600 seconds per job")
    profile = args.profile.resolve()
    resolved = configure.resolved_config(profile)
    component = resolved["components"].get("pemu")
    if not component or component["id"] != "pemu.axpe":
        raise ValueError("profile must select pemu.axpe")
    params = {
        k: resolved["parameters"].get("pemu", {}).get(k, v["default"])
        for k, v in component["parameters"].items()
    }
    if any(
        params[k] != v
        for k, v in (("reg_count", 8), ("reg_width", 16), ("delay_bits", 16), ("uio_pins", 8))
    ):
        raise ValueError(
            "proof supports the default eight-register 16-bit architecture and eight UIO pins"
        )
    isa = ROOT / "sw/pemu/isa/axpe-isa.json"
    spec = json.loads(isa.read_text())
    harness, insns = render(spec, params)
    rtl = ROOT / "components/pemu/axpe"
    core = rtl / "axpe.sv"
    files = [
        isa,
        profile,
        rtl / "component.json",
        HERE / "core.sv.in",
        Path(__file__).resolve(),
        HERE / "check_timing.py",
        HERE / "check_shift.py",
        ROOT / "tools/configure.py",
        ROOT / "sw/pemu/isa/axpe_isa.svh",
    ]
    files += [rtl / f"axpe{suffix}.sv" for suffix in ("", "_decode", "_timing", "_shift", "_pads")]
    hashes = {str(p): sha(p) for p in files}
    BUILD.mkdir(parents=True, exist_ok=True)
    output = (
        args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="core-", dir=BUILD))
    )
    if output == BUILD or BUILD not in output.parents:
        raise ValueError(f"output must be a new child of {BUILD}")
    if args.output:
        output.mkdir(parents=True, exist_ok=False)
    record = {
        "schema": "org.atomix.axpe-core-timing-proof.v1",
        "status": "running",
        "inputs_sha256": hashes,
        "profile": str(profile),
        "parameters": params,
        "instructions": {k: v["timing"] for k, v in insns.items()},
        "scope": "all legal instruction occupancy and handoff over an abstract word interface; binary sampled edges",
        "assumptions": [
            "first sampled edge resets; later resets interrupt an instruction",
            "legal opcode/operands at reference issue, balanced stack and in-range branch/call targets",
            "legal shift configuration and effective period at reference issue",
        ],
        "not_proved": [
            "program-memory/fetch data correctness",
            "ALU/data/pin waveform correctness",
            "non-default register/delay/pin composition",
            "asynchronous reset recovery or physical timing",
        ],
    }
    try:
        record["proof"] = check(args, output / "original", core, harness, params, insns)
        if not args.proof_only:
            text = core.read_text()
            mutations = {
                "lost-shift-handoff": ("|| wait_over || shift_over;", "|| wait_over;"),
                "live-word-shift-delay": (
                    "issue ? cell_delay : hold_delay;",
                    "issue ? cell_delay : delay;",
                ),
                "wrong-period-selection": ("period_sel ? period_wide[15:0] : delay;", "delay;"),
                "early-halt": (
                    "if (halt_pending) begin",
                    "if (halt_pending || op == AXPE_OP_HALT) begin",
                ),
                "late-wait-timeout": ("wait_elapsed >= wait_bound", "wait_elapsed > wait_bound"),
            }
            record["mutations"] = {}
            for name, (before, after) in mutations.items():
                if text.count(before) != 1:
                    raise ValueError(f"mutation anchor changed: {name}")
                changed = output / f"{name}.sv"
                changed.write_text(text.replace(before, after))
                record["mutations"][name] = check(
                    args, output / name, changed, harness, params, insns, True
                )
        for p, digest in hashes.items():
            if sha(Path(p)) != digest:
                raise ValueError(f"proof input changed during run: {p}")
        record["yosys"] = subprocess.check_output([args.yosys, "-V"], text=True).strip()
        record["status"] = "exploratory induction pass" if args.proof_only else "passed"
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        record["status"] = "failed"
        record["failure"] = str(exc)
        raise
    finally:
        (output / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"axpe core timing proof: {record['status']}; {output}")


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        SyntaxError,
        OSError,
        KeyError,
        configure.ConfigError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"axpe core timing proof: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
