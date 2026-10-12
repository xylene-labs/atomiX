#!/usr/bin/env python3
"""Run capacity probes on axpe RTL with every parameter resolved from a profile.

A failed elaboration is a failed check, never an expected-pass substitution.
Each attempt uses a new directory and retains commands, diagnostics and hashes.
This is host RTL simulation, not a physical-flow or complete ISA-model claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import configure

ROOT = Path(__file__).resolve().parents[1]
PARAMETERS = {
    "imem_words": "IMEM_WORDS",
    "reg_count": "REGS",
    "reg_width": "REG_W",
    "delay_bits": "DELAY_BITS",
    "uio_pins": "UIO_PINS",
    "call_depth": "CALL_DEPTH",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_profile(path: Path) -> tuple[dict[str, int], list[Path], str]:
    resolved = configure.resolved_config(path)
    make = configure.to_make(resolved)  # also rejects typos, types and declared bounds
    if set(resolved["components"]) != {"pemu"}:
        raise ValueError("profile must select only pemu.axpe")
    component = resolved["components"]["pemu"]
    if component["id"] != "pemu.axpe" or set(component["parameters"]) != set(PARAMETERS):
        raise ValueError("capacity harness must map every declared axpe parameter")
    supplied = resolved["parameters"].get("pemu", {})
    params = {
        name: supplied.get(name, spec["default"]) for name, spec in component["parameters"].items()
    }
    # These are limits of this probe, not declarations of supported hardware.
    # In particular, widths inside these limits can and do fail elaboration.
    limits = {
        "reg_count": (1, 8),
        "reg_width": (8, 16),
        "delay_bits": (2, 16),
        "uio_pins": (1, 8),
        "call_depth": (1, 32),
    }
    for name, (low, high) in limits.items():
        if not low <= params[name] <= high:
            raise ValueError(f"capacity probe requires {low} <= {name} <= {high}")
    if params["imem_words"] < 2 * params["call_depth"] + 6:
        raise ValueError("capacity probe's nested-call program does not fit this store")
    sources = [configure.resolve_source(component, src) for src in component["sources"]]
    return params, sources, make


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=ROOT / "configs/sim-axpe-capacity.json")
    parser.add_argument("--output", type=Path, help="fresh child of build/pemu/profiles")
    args = parser.parse_args()
    base = (ROOT / "build/pemu/profiles").resolve()
    base.mkdir(parents=True, exist_ok=True)
    if args.output:
        output = args.output.resolve()
        if not output.is_relative_to(base) or output == base:
            parser.error("output must be a fresh child of build/pemu/profiles")
        try:
            output.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            parser.error("output already exists; previous evidence must not be overwritten")
    else:
        output = Path(tempfile.mkdtemp(prefix="check-", dir=base))
    receipt = {
        "schema": "org.atomix.axpe-profile-check.v1",
        "level": "host RTL simulation",
        "profile": str(args.profile.resolve()),
        "status": "failed",
        "commands": [],
    }
    inputs = {
        str(path): digest(path)
        for path in [
            args.profile.resolve(),
            Path(__file__).resolve(),
            ROOT / "tools/configure.py",
            ROOT / "components/pemu/axpe/component.json",
        ]
        if path.is_file()
    }
    receipt["inputs_sha256"] = inputs
    try:
        params, sources, make = check_profile(args.profile.resolve())
        receipt["parameters"] = params
        (output / "profile.mk").write_text(make)
        (output / "parameters.json").write_text(json.dumps(params, indent=2) + "\n")
        bench = ROOT / "sim/pemu/axpe_profile_tb.cpp"
        inputs = {
            str(path): digest(path)
            for path in [
                args.profile.resolve(),
                *sources,
                bench,
                Path(__file__).resolve(),
                ROOT / "tools/configure.py",
                ROOT / "components/pemu/axpe/component.json",
                ROOT / "sw/pemu/isa/axpe_isa.svh",
                ROOT / "sw/pemu/isa/axpe_isa.h",
                ROOT / "sw/pemu/model/axpe_model.h",
                ROOT / "sim/pemu/axpe_trace.h",
            ]
        }
        receipt["inputs_sha256"] = inputs
        version = subprocess.run(
            ["verilator", "--version"], check=True, capture_output=True, text=True, timeout=10
        )
        receipt["verilator_version"] = version.stdout.strip()
        flags = [f"-G{rtl}={params[name]}" for name, rtl in PARAMETERS.items()]
        cflags = " ".join(f"-DPROFILE_{rtl}={params[name]}" for name, rtl in PARAMETERS.items())
        build_command = [
            "verilator",
            "--cc",
            "--exe",
            "--build",
            "-j",
            "2",
            "-Wall",
            "--public-flat-rw",
            "--top-module",
            "axpe",
            "--Mdir",
            str(output / "obj"),
            f"-I{ROOT / 'sw/pemu/isa'}",
            *flags,
            "-CFLAGS",
            cflags,
            *map(str, sources),
            str(bench),
        ]
        for stage, command, timeout in [
            ("build", build_command, 180),
            ("probe", [str(output / "obj/Vaxpe")], 30),
        ]:
            log = output / f"{stage}.log"
            attempt = {
                "stage": stage,
                "argv": command,
                "cwd": str(ROOT),
                "timeout_seconds": timeout,
                "log": str(log),
            }
            receipt["commands"].append(attempt)
            with log.open("w") as stream:
                try:
                    result = subprocess.run(
                        command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout
                    )
                    attempt["returncode"] = result.returncode
                except subprocess.TimeoutExpired:
                    attempt["timeout"] = True
                    raise RuntimeError(f"{stage} timed out; see {log}") from None
                finally:
                    stream.flush()
                    attempt["log_sha256"] = digest(log)
            if result.returncode:
                print(f"{stage} diagnostics (last 40 lines):", file=sys.stderr)
                print("\n".join(log.read_text(errors="replace").splitlines()[-40:]),
                      file=sys.stderr)
                raise RuntimeError(f"{stage} failed ({result.returncode}); see {log}")
        receipt["status"] = "passed"
        receipt["scope"] = [
            "elaborated register/stack capacities",
            "highest register and instruction slots",
            "pin count and open-drain release",
            "maximum scalar delay and wait timeout",
            "full call-stack unwind, overflow and underflow",
            "out-of-range branch when encodable",
        ]
    except (
        configure.ConfigError,
        ValueError,
        RuntimeError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        receipt["error"] = str(error)
    finally:
        changed = [
            name
            for name, value in inputs.items()
            if not Path(name).is_file() or digest(Path(name)) != value
        ]
        if changed:
            receipt["status"] = "failed"
            receipt["changed_inputs"] = changed
        (output / "evidence.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"axpe profile: {receipt['status'].upper()}: {output / 'evidence.json'}")
    if receipt.get("error"):
        print(receipt["error"], file=sys.stderr)
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
