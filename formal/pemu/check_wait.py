#!/usr/bin/env python3
"""Prove WAITE/DELAY timing on the original core with an abstract word source."""
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
COVERS = ("timeout", "zero_timeout", "final_event", "word_change", "immediate",
          "chain", "max_delay", "edge0", "edge1", "edge2", "level")


def check(args, directory: Path, core: Path, harness: str, parameters: dict,
          mutant: bool = False) -> dict:
    directory.mkdir(parents=True)
    source = directory / "wait.sv"
    source.write_text(harness)
    rtl = ROOT / "components/pemu/axpe"
    files = [rtl / f"axpe_{name}.sv" for name in ("decode", "timing", "shift", "pads")]
    setting = {"IMEM_WORDS": "imem_words", "REGS": "reg_count", "REG_W": "reg_width",
               "DELAY_BITS": "delay_bits", "UIO_PINS": "uio_pins", "CALL_DEPTH": "call_depth"}
    options = " ".join(f"-set {name} {parameters[key]}" for name, key in setting.items())
    prep = ("read_verilog -sv -Isw/pemu/isa "
            + " ".join(json.dumps(str(p)) for p in files + [core]) + "\n"
            + f"chparam {options} axpe\nhierarchy -top axpe\nflatten\n"
            "expose axpe/state axpe/issue axpe/wait_over axpe/wait_timeout axpe/wait_count "
            "axpe/u_cell.remaining axpe/retire_data axpe/ft axpe/wait_prev "
            "axpe/hold_wpin axpe/hold_wedge axpe/hold_delay axpe/halt_pending axpe/reject\n"
            "cd axpe\nrename u_cell.remaining cell_remaining\ncd ..\n"
            f"read_verilog -formal -sv {json.dumps(str(source))}\n"
            "prep -top wait_formal -flatten\nasync2sync\ndffunmap\n")
    script = directory / "proof.ys"
    script.write_text(prep + "sat -seq 4 -tempinduct -maxsteps 4 -prove-asserts -set-assumes -verify\n")
    code, log = execute(args.yosys, script, args.timeout_seconds)
    record = {"harness_sha256": sha(source), "proof_script_sha256": sha(script),
              "proof_log_sha256": sha(script.with_suffix(".log"))}
    if mutant:
        if not (code and "model found for base case: FAIL!" in log):
            raise ValueError(f"mutation lacks an actual counterexample: {directory}")
        return {**record, "result": "expected counterexample", "core_sha256": sha(core)}
    if code or "Induction step proven: SUCCESS!" not in log:
        raise ValueError(f"induction failed: {script.with_suffix('.log')}")
    covers = {}
    for name in COVERS:
        script = directory / f"covered_{name}.ys"
        script.write_text(prep + f"sat -seq 19 -set-assumes -set-at 19 covered_{name} 1 -show-outputs\n")
        code, log = execute(args.yosys, script, args.timeout_seconds)
        if code or "SAT solving finished - model found:" not in log:
            raise ValueError(f"cover unreachable: {script}")
        covers[name] = {"script_sha256": sha(script), "log_sha256": sha(script.with_suffix(".log"))}
    return {**record, "result": "inductive pass", "covers": covers}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yosys", default=os.environ.get("YOSYS", "yosys"))
    parser.add_argument("--profile", type=Path, default=ROOT / "configs/tt-axpe-6x4.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args()
    if not 1 <= args.timeout_seconds <= 3600:
        raise ValueError("proof timeout must be 1..3600 seconds per job")
    profile = args.profile.resolve()
    resolved = configure.resolved_config(profile)
    component = resolved["components"].get("pemu")
    if not component or component["id"] != "pemu.axpe":
        raise ValueError("proof profile must select pemu.axpe")
    params = {name: resolved["parameters"].get("pemu", {}).get(name, item["default"])
              for name, item in component["parameters"].items()}
    if any(params[name] != value for name, value in
           (("reg_count", 8), ("reg_width", 16), ("delay_bits", 16), ("uio_pins", 8))):
        raise ValueError("this core proof supports eight 16-bit registers, 16-bit delay and eight uio pins")
    isa = ROOT / "sw/pemu/isa/axpe-isa.json"
    spec = json.loads(isa.read_text())
    fields = spec["encoding"]["fields"]
    if spec["encoding"]["width"] != 32 or any(fields[key]["hi"] - fields[key]["lo"] + 1 != width
        for key, width in (("op", 5), ("a", 3), ("b", 3), ("x", 5), ("delay", 16))):
        raise ValueError("unsupported ISA field widths for the core proof")
    instructions = {item["mnemonic"]: item for item in spec["instructions"]}
    rule = spec["timing"][instructions["WAITE"]["timing"]]["formula"]
    bounded = re.fullmatch(r"w,\s*1<=w<=(.+)", rule)
    if not bounded:
        raise ValueError("unsupported bounded occupancy formula")
    duration = expression(ast.parse(spec["timing"][instructions["DELAY"]["timing"]]["formula"],
                                    mode="eval").body, params["delay_bits"])
    bound = expression(ast.parse(bounded[1], mode="eval").body, params["delay_bits"])
    layout = {item["name"]: item for item in instructions["WAITE"]["imm8_layout"]}
    base = min(fields[key]["lo"] for key in spec["encoding"]["overlays"]["imm8"]["fields"])
    replacements = {"@OP_W@": 5, "@WAIT@": instructions["WAITE"]["opcode"],
                    "@DELAY@": instructions["DELAY"]["opcode"], "@DURATION@": duration,
                    "@BOUND@": bound, "@HELD_BOUND@": bound.replace("delay", "hold_delay"),
                    "@MAX_DELAY@": (1 << params["delay_bits"]) - 1}
    for field, prefix in (("op", "OP"), ("a", "A"), ("delay", "D")):
        for end in ("hi", "lo"):
            replacements[f"@{prefix}_{end.upper()}@"] = fields[field][end]
    for field in ("pin", "edge"):
        for end in ("hi", "lo"):
            replacements[f"@{field.upper()}_{end.upper()}@"] = base + layout[field][end]
    template = HERE / "wait.sv.in"
    harness = template.read_text()
    for before, after in replacements.items():
        harness = harness.replace(before, str(after))
    rtl = ROOT / "components/pemu/axpe"
    core = rtl / "axpe.sv"
    files = [isa, profile, rtl / "component.json", template, Path(__file__).resolve(),
             HERE / "check_timing.py", HERE / "check_shift.py", ROOT / "tools/configure.py",
             ROOT / "sw/pemu/isa/axpe_isa.svh"]
    files += [rtl / name for name in ("axpe.sv", "axpe_decode.sv", "axpe_timing.sv", "axpe_shift.sv", "axpe_pads.sv")]
    hashes = {str(p): sha(p) for p in files}
    BUILD.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="wait-", dir=BUILD))
    if output == BUILD or BUILD not in output.parents:
        raise ValueError(f"output must be a new child of {BUILD}")
    if args.output:
        output.mkdir(parents=True, exist_ok=False)
    record = {"schema": "org.atomix.axpe-wait-proof.v1", "status": "running",
              "inputs_sha256": hashes, "profile": str(profile), "parameters": params,
              "bounded_formula": rule, "scope": "DELAY/WAITE-only core stream, binary sampled edges",
              "assumptions": ["first sampled edge resets; reset interrupts an instruction",
                              "abstract instruction source supplies only legal DELAY/WAITE words"],
              "not_proved": ["program memory/fetch behavior", "other instruction classes",
                             "immediate-level zero return register value (separately model/RTL tested)",
                             "non-default register/delay/pin composition", "physical timing or reset recovery"]}
    try:
        record["proof"] = check(args, output / "original", core, harness, params)
        text = core.read_text()
        mutations = {"late-timeout": ("wait_elapsed >= wait_bound", "wait_elapsed > wait_bound"),
                     "live-word-timeout": ("                                           : hold_delay;",
                                           "                                           : delay;")}
        record["mutations"] = {}
        for name, (before, after) in mutations.items():
            if text.count(before) != 1:
                raise ValueError(f"mutation anchor changed: {name}")
            changed = output / f"{name}.sv"
            changed.write_text(text.replace(before, after))
            record["mutations"][name] = check(args, output / name, changed, harness, params, True)
        for path, expected in hashes.items():
            if sha(Path(path)) != expected:
                raise ValueError(f"proof input changed during run: {path}")
        record["yosys"] = subprocess.check_output([args.yosys, "-V"], text=True).strip()
        record["status"] = "passed"
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        record["status"] = "failed"
        record["failure"] = str(exc)
        raise
    finally:
        (output / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"axpe wait proof: PASS (induction, 11 covers, 2 mutations); {output}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, SyntaxError, OSError, KeyError, configure.ConfigError, subprocess.SubprocessError) as exc:
        print(f"axpe wait proof: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
