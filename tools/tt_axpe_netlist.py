#!/usr/bin/env python3
"""Replay the unchanged axpe chip suite on a selected CMOS5L mapped netlist.

Cell logic is generated from the pinned Liberty files, never handwritten.
This is a two-state, zero-delay functional check, not SDF or timing evidence.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from collections import Counter

import tt_axpe
import tt_axpe_flow

ROOT = tt_axpe.ROOT
CORNERS = ("typ_1p20V_25C", "fast_1p32V_m40C", "slow_1p08V_125C")
TOP = "tt_um_shubhgau_atomix_axpe"
MODULE = re.compile(r"^module\s+(\w+)\s*\([^;]*\);(.*?)endmodule", re.M | re.S)
INSTANCE = re.compile(r"^\s*(sg13cmos5l_\w+)\s+(\S+)\s*\((.*?)\);", re.M | re.S)
PIN = re.compile(r"\.(\w+)\(([^()]*)\)")


def bindings(netlist: str, models: str) -> dict[str, int]:
    """Reject missing models or input pins before relaxing unused-output lint.

    The reader supports OpenROAD's named-port netlist and Yosys's generated
    Liberty modules. It deliberately fails on other formats.
    """
    available = {}
    for name, body in MODULE.findall(models):
        inputs = set(re.findall(r"\binput\s+(\w+)\s*;", body))
        outputs = set(re.findall(r"\boutput\s+(\w+)\s*;", body))
        available[name] = (inputs, outputs)
    counts = Counter()
    names = set()
    for cell, name, body in INSTANCE.findall(netlist):
        if name in names:
            raise ValueError(f"duplicate instance: {name}")
        names.add(name)
        if cell not in available:
            raise ValueError(f"no functional Liberty model for {cell}")
        connections = PIN.findall(body)
        pins = dict(connections)
        if len(pins) != len(connections):
            raise ValueError(f"duplicate port on {name}")
        inputs, outputs = available[cell]
        missing = {pin for pin in inputs if not pins.get(pin, "").strip()}
        unknown = pins.keys() - inputs - outputs
        if missing or unknown:
            raise ValueError(f"{name}: missing inputs {sorted(missing)}, "
                             f"unknown ports {sorted(unknown)}")
        counts[cell] += 1
    if not counts:
        raise ValueError("no mapped CMOS5L instances found")
    # Each statement that looks like a cell instance must have been parsed;
    # foreign cells and positional connections cannot silently disappear.
    all_instances = [item for item in
                     re.findall(r"^\s*(\w+)\s+(\S+)\s*\(", netlist, re.M)
                     if item[0] != "module"]
    if len(all_instances) != sum(counts.values()):
        raise ValueError("unsupported or unparsed netlist instance")
    return dict(sorted(counts.items()))


def self_test() -> None:
    models = "module sg13cmos5l_buf_1(A, X); input A; output X; assign X=A; endmodule"
    good = "module test(clk, out);\n sg13cmos5l_buf_1 a (.A(clk), .X(out));\nendmodule\n"
    assert bindings(good, models) == {"sg13cmos5l_buf_1": 1}
    assert bindings(" sg13cmos5l_buf_1 load (.A(clk));\n", models)
    bad = [
        good.replace(".A(clk), ", ""),
        good.replace(".A(clk)", ".A()"),
        good.replace(".A(clk)", ".UNKNOWN(clk)"),
        good.replace("buf_1", "lgcp_1"),
        good + good,
        good.replace(".A(clk)", ".A(clk), .A(clk)"),
        " sg13cmos5l_buf_1 a (clk, out);\n",
        good + " foreign_cell b (.A(clk));\n",
    ]
    for netlist in bad:
        try:
            bindings(netlist, models)
        except ValueError:
            continue
        raise AssertionError(f"bad binding accepted: {netlist}")
    print("axpe netlist contract: PASS (8 rejection cases; unused output allowed)")


def run_command(command: list[str], log: Path, record: dict) -> None:
    record.setdefault("commands", []).append(command)
    with log.open("w") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream,
                                stderr=subprocess.STDOUT, check=False)
    record.setdefault("logs", {})[str(log.name)] = tt_axpe.file_hash(log)
    if result.returncode:
        raise ValueError(f"command exited {result.returncode}; see {log}")


def run(args: argparse.Namespace) -> None:
    if args.state is None or args.output is None:
        raise ValueError("replay requires --state and a new --output directory")
    output = tt_axpe_flow.require_workdir(args.output)
    if output.exists():
        raise ValueError(f"refusing to replace existing replay: {output}")
    state_path = args.state.resolve()
    state = tt_axpe.read_json(state_path)
    netlist = Path(state["nl"]).resolve()
    if not netlist.is_file():
        raise ValueError(f"mapped netlist is missing: {netlist}")
    lock_path = args.flow_lock.resolve()
    lock = tt_axpe.read_json(lock_path)
    tt_axpe.validate_lock(lock)
    tt_axpe_flow.require_commit(args.pdk_root.resolve(), lock["flow"]["pdk_commit"], "PDK")
    if not 1 <= args.jobs <= 64:
        raise ValueError("--jobs must be between 1 and 64")

    sources = [state_path, netlist, lock_path, Path(__file__).resolve()]
    sources += [ROOT / "tools" / name for name in
                ("tt_axpe.py", "tt_axpe_flow.py", "configure.py", "axpe_isa.py")]
    sources += [ROOT / "sim/pemu" / name for name in
                ("axpe_tt_tb.cpp", "axpe_device.h", "axpe_cases.h", "axpe_peers.h", "axpe_trace.h")]
    sources += list((ROOT / "sw/pemu/firmware").glob("*.s"))
    rate_profiles = sorted((ROOT / "sw/pemu/firmware/profiles").glob("*.json"))
    architecture_profile = ROOT / lock["candidate"]["profile"]
    imem_words = tt_axpe.component_parameters(
        tt_axpe.configure.resolved_config(architecture_profile), "pemu")["imem_words"]
    sources.append(architecture_profile)
    sources += rate_profiles + [ROOT / "sw/pemu/firmware/build_demos.py",
                              ROOT / "sw/pemu/firmware/demo.json"]
    sources += [ROOT / "sw/pemu" / name for name in
                ("model/axpe_model.c", "model/axpe_model.h", "isa/axpe_isa.h",
                 "isa/axpe-isa.json", "as/axpe_as.py")]
    libs = [args.pdk_root.resolve() / "ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/lib" /
            f"sg13cmos5l_stdcell_{corner}.lib" for corner in CORNERS]
    sources += libs
    hashes = {str(path): tt_axpe.file_hash(path) for path in sources}
    output.mkdir(parents=True)
    record = {
        "schema": "org.atomix.axpe-netlist-replay.v1",
        "status": "running", "input_state": str(state_path),
        "netlist": str(netlist), "input_sha256": hashes,
        "pdk_commit": lock["flow"]["pdk_commit"],
        "semantics": "two-state zero-delay Liberty-derived cells; no SDF",
        "not_claimed": ["timing simulation", "four-state startup proof", "silicon"],
    }
    try:
        models = []
        for corner, liberty in zip(CORNERS, libs):
            model = output / f"{corner}.v"
            # Ignore cells the frontend cannot model only if the mapped design
            # never uses them. bindings() checks every instance below.
            script = (f"read_liberty -ignore_miss_func {json.dumps(str(liberty))}; "
                      f"write_verilog -noattr {json.dumps(str(model))}")
            run_command([args.yosys, "-Q", "-T", "-p", script],
                        output / f"{corner}.log", record)
            models.append(model)
        model_hashes = [tt_axpe.file_hash(model) for model in models]
        if len(set(model_hashes)) != 1:
            raise ValueError("functional Liberty models differ across corners")
        record["functional_model_sha256"] = model_hashes[0]
        record["cell_counts"] = bindings(netlist.read_text(), models[0].read_text())
        firmware = output / "fw"
        firmware.mkdir()
        for name in ("uart-demo", "spi-demo", "i2c-demo", "autobaud-demo"):
            run_command([sys.executable, str(ROOT / "sw/pemu/as/axpe_as.py"),
                         "--imem-words", str(imem_words), "--hex", str(firmware / f"{name}.hex"),
                         str(ROOT / f"sw/pemu/firmware/{name}.s")],
                        output / f"{name}.log", record)
        record["firmware_sha256"] = {path.name: tt_axpe.file_hash(path)
                                     for path in sorted(firmware.iterdir())}
        obj = output / "obj"
        run_command([args.verilator, "--cc", "--exe", "--build", "-j", str(args.jobs),
                     "-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSEDSIGNAL", "-Wno-PINMISSING",
                     "--x-initial", "unique", "--x-assign", "unique",
                     "--top-module", TOP, "--Mdir", str(obj), str(netlist), str(models[0]),
                     str(ROOT / "sim/pemu/axpe_tt_tb.cpp"),
                     str(ROOT / "sw/pemu/model/axpe_model.c")],
                    output / "verilator.log", record)
        for seed in (1, 17, 91):
            run_command([str(obj / f"V{TOP}"), str(firmware),
                         "+verilator+rand+reset+2", f"+verilator+seed+{seed}"],
                        output / f"suite-seed-{seed}.log", record)
        record["rate_profiles"] = {}
        for profile in rate_profiles:
            images = output / "fw-rates" / profile.stem
            run_command([sys.executable, str(ROOT / "sw/pemu/firmware/build_demos.py"),
                         "--profile", str(profile), "--imem-words", str(imem_words), "--output", str(images)],
                        output / f"rates-{profile.stem}-build.log", record)
            record["rate_profiles"][profile.stem] = {
                "profile_sha256": tt_axpe.file_hash(profile),
                "build_receipt": tt_axpe.read_json(images / "profile.json"),
                "outputs_sha256": {path.name: tt_axpe.file_hash(path) for path in sorted(images.iterdir())}}
            for seed in (1, 17, 91):
                run_command([str(obj / f"V{TOP}"), str(images),
                             "+verilator+rand+reset+2", f"+verilator+seed+{seed}"],
                            output / f"rates-{profile.stem}-seed-{seed}.log", record)
        for path, expected in hashes.items():
            if tt_axpe.file_hash(Path(path)) != expected:
                raise ValueError(f"input changed during replay: {path}")
        record["status"] = "passed"
        record["startup_seeds"] = [1, 17, 91]
        record["tools"] = {
            name: subprocess.check_output([executable, flag], text=True).strip()
            for name, executable, flag in
            (("yosys", args.yosys, "-V"), ("verilator", args.verilator, "--version"))}
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        record["status"] = "failed"
        record["failure"] = str(exc)
        raise
    finally:
        (output / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"axpe mapped replay: PASS (3 startup seeds, all chip cases); {output / 'evidence.json'}")


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--flow-lock", type=Path, default=tt_axpe_flow.DEFAULT_LOCK)
    parser.add_argument("--pdk-root", type=Path, default=tt_axpe_flow.BUILD / "pdk-cmos5l")
    parser.add_argument("--yosys", default=os.environ.get("YOSYS", "yosys"))
    parser.add_argument("--verilator", default=os.environ.get("VERILATOR", "verilator"))
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            run(args)
    except (ValueError, OSError, KeyError, AssertionError, tt_axpe.ExportError,
            tt_axpe_flow.FlowError, subprocess.CalledProcessError) as exc:
        print(f"axpe mapped replay: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()
