#!/usr/bin/env python3
"""Inductively check axpe's cell timer against the normative ISA formula.

This proves the isolated timer; it does not prove core instruction retirement.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BUILD = ROOT / "build/formal/pemu"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expression(node: ast.AST, width: int) -> str:
    if isinstance(node, ast.Name) and node.id == "D":
        return "delay"
    if (isinstance(node, ast.Constant) and type(node.value) is int
            and 0 <= node.value < 2**width):
        return f"{width}'d{node.value}"
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "max" and len(node.args) == 2 and not node.keywords):
        a, b = (expression(arg, width) for arg in node.args)
        return f"(({a} > {b}) ? {a} : {b})"
    raise ValueError("unsupported ISA cell-duration expression")


def check(yosys: str, directory: Path, width: int, timer: Path,
          formula: str, template: str, mutant: bool = False) -> dict:
    directory.mkdir(parents=True)
    harness = directory / "timing.sv"
    harness.write_text(template.replace("@WIDTH@", str(width)).replace(
        "@DURATION@", expression(ast.parse(formula, mode="eval").body, width)))
    preparation = (
        f"read_verilog -sv {json.dumps(str(timer))}\n"
        f"chparam -set DELAY_BITS {width} axpe_timing\n"
        "expose axpe_timing/remaining\n"
        f"read_verilog -formal -sv {json.dumps(str(harness))}\n"
        "prep -top axpe_timer_formal -flatten\n"
        "async2sync\ndffunmap\n")
    proof = directory / "proof.ys"
    proof.write_text(preparation +
                    "sat -seq 4 -tempinduct -maxsteps 8 -prove-asserts -set-assumes -verify\n")
    with (directory / "proof.log").open("w") as log:
        result = subprocess.run([yosys, "-Q", "-T", "-s", str(proof)],
                                stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    text = (directory / "proof.log").read_text()
    passed = result.returncode == 0 and "Induction step proven: SUCCESS!" in text
    failed = result.returncode != 0 and "model found for base case: FAIL!" in text
    if mutant:
        if not failed:
            raise ValueError(f"mutation did not produce a counterexample: {directory}")
        return {"width": width, "result": "expected counterexample",
                "proof_log_sha256": sha(directory / "proof.log"),
                "timer_sha256": sha(timer)}
    if not passed:
        raise ValueError(f"induction failed: {directory / 'proof.log'}")
    covers = {}
    for name in ("seen_zero", "seen_one", "seen_long"):
        script = directory / f"{name}.ys"
        # Cover witnesses demonstrate the assumptions admit real loads and
        # completion, including the zero-delay clamp and a multi-cycle cell.
        script.write_text(preparation +
                          f"sat -seq 12 -set-assumes -set-at 12 {name} 1 "
                          "-show-inputs -show-outputs\n")
        log_path = directory / f"{name}.log"
        with log_path.open("w") as log:
            result = subprocess.run([yosys, "-Q", "-T", "-s", str(script)],
                                    stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
        if result.returncode or "SAT solving finished - model found:" not in log_path.read_text():
            raise ValueError(f"cover unreachable: {log_path}")
        covers[name] = sha(log_path)
    return {"width": width, "result": "inductive pass", "formula": formula,
            "proof_log_sha256": sha(directory / "proof.log"),
            "proof_script_sha256": sha(proof),
            "harness_sha256": sha(harness), "cover_log_sha256": covers}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yosys", default=os.environ.get("YOSYS", "yosys"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    isa = ROOT / "sw/pemu/isa/axpe-isa.json"
    manifest = ROOT / "components/pemu/axpe/component.json"
    spec = json.loads(isa.read_text())
    formula = spec["timing"]["fixed"]["formula"]
    width = json.loads(manifest.read_text())["parameters"]["delay_bits"]["default"]
    encoded = spec["encoding"]["fields"]["delay"]
    encoded_width = encoded["hi"] - encoded["lo"] + 1
    if not 8 <= width <= encoded_width:
        raise ValueError("unsupported component delay width for this proof")
    timer = ROOT / "components/pemu/axpe/axpe_timing.sv"
    source = timer.read_text()
    template_path = HERE / "timing.sv.in"
    sources = [isa, manifest, timer, template_path, Path(__file__).resolve()]
    hashes = {str(path.relative_to(ROOT)): sha(path) for path in sources}
    BUILD.mkdir(parents=True, exist_ok=True)
    output = (args.output.resolve() if args.output else
              Path(tempfile.mkdtemp(prefix="timing-", dir=BUILD)))
    if output == BUILD or BUILD not in output.parents:
        raise ValueError(f"proof output must be a child of {BUILD}")
    if args.output:
        output.mkdir(parents=True, exist_ok=False)
    record = {"schema": "org.atomix.axpe-timing-proof.v1", "status": "running",
              "inputs_sha256": hashes, "formula": formula,
              "scope": "isolated cell timer at clock edges; arbitrary binary delay, load and reset",
              "not_proved": ["core retirement/handoff", "shift-engine total cost",
                             "WAITE timeout", "asynchronous reset recovery timing"]}
    try:
        record["proofs"] = [check(args.yosys, output / f"width-{w}", w, timer,
                                  formula, template_path.read_text())
                            for w in (width, width // 2)]
        mutations = {
            "decrement-two": ("remaining - 1'b1", "remaining - 2'd2"),
            "extra-load-cycle": ("remaining <= cell_cycles;", "remaining <= cell_cycles + 1'b1;"),
        }
        record["mutations"] = {}
        for name, (before, after) in mutations.items():
            if source.count(before) != 1:
                raise ValueError(f"mutation anchor changed: {name}")
            mutated = output / f"{name}.sv"
            mutated.write_text(source.replace(before, after))
            record["mutations"][name] = check(args.yosys, output / name, width,
                                              mutated, formula, template_path.read_text(), True)
        for name, expected in hashes.items():
            if sha(ROOT / name) != expected:
                raise ValueError(f"proof input changed: {name}")
        record["yosys"] = subprocess.check_output([args.yosys, "-V"], text=True).strip()
        record["status"] = "passed"
    except (ValueError, SyntaxError, OSError, subprocess.CalledProcessError) as exc:
        record["status"] = "failed"
        record["failure"] = str(exc)
        raise
    finally:
        (output / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"axpe timer proof: PASS (widths {width}/{width // 2}, three covers each, two mutations); {output}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, SyntaxError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"axpe timer proof: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
