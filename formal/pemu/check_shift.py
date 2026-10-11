#!/usr/bin/env python3
"""Prove isolated axpe shift occupancy under the core's caller contract."""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from check_timing import ROOT, BUILD, expression, sha

HERE = Path(__file__).resolve().parent
COVERS = ("covered_zero", "covered_max_count", "covered_max_delay", "covered_chain",
          "covered_mode0", "covered_mode1", "covered_mode2", "covered_mode3")


def execute(yosys: str, script: Path, seconds: int) -> tuple[int, str]:
    log = script.with_suffix(".log")
    with log.open("w") as stream:
        result = subprocess.run([yosys, "-Q", "-T", "-s", str(script)], cwd=ROOT,
                                stdout=stream, stderr=subprocess.STDOUT, timeout=seconds)
    return result.returncode, log.read_text()


def check(args, output: Path, shift: Path, timer: Path, harness: str,
          params: dict, mutant: bool = False) -> dict:
    output.mkdir(parents=True)
    source = output / "shift.sv"
    source.write_text(harness)
    # Resolve parameters and flatten the timer before exposing observations.
    # The unparameterized harness instance preserves these resolved ports.
    prep = (f"read_verilog -sv {json.dumps(str(timer))} {json.dumps(str(shift))}\n"
            f"chparam -set REG_W {params['reg_width']} -set DELAY_BITS {params['delay_bits']} "
            f"-set UIO_PINS {params['uio_pins']} axpe_shift\n"
            "hierarchy -top axpe_shift\nflatten\n"
            "expose axpe_shift/state axpe_shift/index axpe_shift/total axpe_shift/u_cell.remaining\n"
            "cd axpe_shift\nrename u_cell.remaining remaining\ncd ..\n"
            f"read_verilog -formal -sv {json.dumps(str(source))}\n"
            "prep -top shift_formal -flatten\nasync2sync\ndffunmap\n")
    script = output / "proof.ys"
    script.write_text(prep + "sat -seq 4 -tempinduct -maxsteps 4 -prove-asserts -set-assumes -verify\n")
    code, log = execute(args.yosys, script, args.timeout_seconds)
    record = {"harness_sha256": sha(source), "proof_script_sha256": sha(script),
              "proof_log_sha256": sha(script.with_suffix(".log"))}
    if mutant:
        if not (code and "model found for base case: FAIL!" in log):
            raise ValueError(f"mutation lacks an actual counterexample: {output}")
        return {**record, "result": "expected counterexample", "shift_sha256": sha(shift)}
    if code or "Induction step proven: SUCCESS!" not in log:
        raise ValueError(f"induction failed: {script.with_suffix('.log')}")
    covers = {}
    for name in COVERS:
        script = output / f"{name}.ys"
        # Enough sampled edges to finish the default maximum bit count at D=1.
        script.write_text(prep + f"sat -seq {params['reg_width'] + 3} -set-assumes "
                          f"-set-at {params['reg_width'] + 3} {name} 1 -show-outputs\n")
        code, log = execute(args.yosys, script, args.timeout_seconds)
        if code or "SAT solving finished - model found:" not in log:
            raise ValueError(f"cover unreachable: {script}")
        covers[name] = {"script_sha256": sha(script),
                        "log_sha256": sha(script.with_suffix(".log"))}
    return {**record, "result": "inductive pass", "covers": covers}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yosys", default=os.environ.get("YOSYS", "yosys"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args()
    if not 1 <= args.timeout_seconds <= 3600:
        raise ValueError("proof timeout must be 1..3600 seconds per job")
    isa = ROOT / "sw/pemu/isa/axpe-isa.json"
    manifest = ROOT / "components/pemu/axpe/component.json"
    spec = json.loads(isa.read_text())
    params = {name: item["default"] for name, item in
              json.loads(manifest.read_text())["parameters"].items()}
    if not (params["reg_width"] == spec["registers"]["width"] == 16
            and params["delay_bits"] == 16 and 1 <= params["uio_pins"] <= 8):
        raise ValueError("this proof supports the default 16-bit architecture only")
    # Decompose n*cell_duration into an independent bit index and cell age;
    # proving those transitions establishes the product without SAT multipliers.
    rule = spec["timing"]["perbit"]["formula"]
    tree = ast.parse(rule, mode="eval").body
    if not (isinstance(tree, ast.BinOp) and isinstance(tree.op, ast.Mult)
            and isinstance(tree.left, ast.Name) and tree.left.id == "n"):
        raise ValueError("unsupported ISA perbit timing formula")
    register_rule = spec["timing"]["perbit_reg"]["formula"]
    if ast.dump(ast.parse(register_rule.replace("P", "D"), mode="eval").body) != ast.dump(tree):
        raise ValueError("encoded and register-selected cell-duration rules differ")
    xfield = spec["encoding"]["fields"]["x"]
    template = HERE / "shift.sv.in"
    harness = template.read_text()
    replacements = {"@COUNT_W@": xfield["hi"] - xfield["lo"] + 1,
                    "@DELAY_W@": params["delay_bits"], "@REG_W@": params["reg_width"],
                    "@UIO_PINS@": params["uio_pins"],
                    "@DURATION@": expression(tree.right, params["delay_bits"])}
    fields = {item["name"]: item for item in spec["shcfg_layout"]}
    replacements["@CFG_W@"] = max(item["hi"] for item in fields.values()) + 1
    replacements["@NO_CLOCK@"] = (1 << (fields["clk"]["hi"] - fields["clk"]["lo"] + 1)) - 1
    for name, field in fields.items():
        for end in ("hi", "lo"):
            replacements[f"@{name.upper()}_{end.upper()}@"] = field[end]
    for before, after in replacements.items():
        harness = harness.replace(before, str(after))
    shift = ROOT / "components/pemu/axpe/axpe_shift.sv"
    timer = ROOT / "components/pemu/axpe/axpe_timing.sv"
    inputs = [isa, manifest, shift, timer, template, HERE / "check_timing.py",
              Path(__file__).resolve()]
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in inputs}
    BUILD.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="shift-", dir=BUILD))
    if output == BUILD or BUILD not in output.parents:
        raise ValueError(f"output must be a new child of {BUILD}")
    if args.output:
        output.mkdir(parents=True, exist_ok=False)
    record = {"schema": "org.atomix.axpe-shift-proof.v1", "status": "running",
              "inputs_sha256": hashes, "formula": rule,
              "register_formula": register_rule, "parameters": params,
              "scope": "isolated shift occupancy and busy/done; arbitrary binary data/inputs",
              "assumptions": ["first sampled edge resets; reset interrupts a transfer",
                              "start only while idle or on the expected final cycle",
                              "legal bit count and pins; clocked delay is even and at least two",
                              "SHCFG stable while active; effective delay stable except at final cycle"],
              "not_proved": ["core enforces caller contract and selects encoded/register period",
                             "core instruction retirement/handoff", "shifted data correctness",
                             "pin waveform/glitches", "reset recovery", "physical timing"]}
    try:
        record["proof"] = check(args, output / "original", shift, timer, harness, params)
        mutations = {"extra-first-cell-cycle":
                     ("timer_delay = clocked ? half : whole;",
                      "timer_delay = clocked ? half : whole + 1'b1;"),
                     "early-final-bit": ("index + 5'd1 == total", "index + 5'd2 == total")}
        record["mutations"] = {}
        text = shift.read_text()
        for name, (before, after) in mutations.items():
            if text.count(before) != 1:
                raise ValueError(f"mutation anchor changed: {name}")
            changed = output / f"{name}.sv"
            changed.write_text(text.replace(before, after))
            record["mutations"][name] = check(args, output / name, changed, timer,
                                                harness, params, True)
        for name, expected in hashes.items():
            if sha(ROOT / name) != expected:
                raise ValueError(f"proof input changed during run: {name}")
        record["yosys"] = subprocess.check_output([args.yosys, "-V"], text=True).strip()
        record["status"] = "passed"
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        record["status"] = "failed"
        record["failure"] = str(exc)
        raise
    finally:
        (output / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"axpe shift proof: PASS (induction, 8 covers, 2 mutations); {output}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, SyntaxError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print(f"axpe shift proof: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
