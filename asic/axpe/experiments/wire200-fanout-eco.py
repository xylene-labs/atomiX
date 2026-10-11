#!/usr/bin/env python3
"""Prepare one pinned net4 fanout ECO; run inside the locked Nix shell.

This is an experiment recipe, not an RTL transformation or a general flow.
Outputs stay in build/asic/ and existing results are never replaced.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
PARENT = ROOT / "build/asic/tt-axpe-25ns-postgrt-noant-wire200/runs/pe10-25ns-postgrt-noant-wire200-from3/03-openroad-stamidpnr-3/state_out.json"
OUTPUT = ROOT / "build/asic/wire200-fanout-eco"
PDK = ROOT / "build/asic/pdk-cmos5l"
PDK_COMMIT = "2bbec755dc67ca3db0261c3d6163e15735d66710"
INPUT_HASHES = {
    "odb": "99fdc276147ffb0b684e9e99780cb6233977d21cf855acc34533e3a9c3cf6f55",
    "nl": "886761b6ab321e5b0c171dfc519141550abf38de7f02aeb84576905f28e735c2",
    "sdc": "32c7cca7c2936483a39e48c808703e509fc24a96d0ec25c88d044a8dc4d96810",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cells(path):
    result = {}
    for cell, name, body in re.findall(
            r"^\s*(sg13cmos5l_\w+)\s+(\S+)\s*\((.*?)\);",
            Path(path).read_text(), re.M | re.S):
        if name in result:
            raise ValueError(f"duplicate instance: {name}")
        pins = {pin: net.strip() for pin, net in
                re.findall(r"\.(\w+)\(([^()]*)\)", body)}
        if not pins:
            raise ValueError(f"unparsed instance: {name}")
        result[name] = (cell, pins)
    if not result:
        raise ValueError(f"no standard cells parsed: {path}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "build/asic"):
        raise ValueError("experiment output must stay under build/asic")
    state = json.loads(PARENT.read_text())
    for key, expected in INPUT_HASHES.items():
        if digest(state[key]) != expected:
            raise ValueError(f"pinned {key} input changed")
    commit = subprocess.check_output(
        ["git", "-C", str(PDK), "rev-parse", "HEAD"], text=True).strip()
    if commit != PDK_COMMIT:
        raise ValueError("PDK commit differs from the flow lock")
    if output.exists():
        raise ValueError(f"refusing to replace existing experiment: {output}")
    output.mkdir(parents=True)
    prefix = output / "tt_um_shubhgau_atomix_axpe"
    script = Path(__file__).with_suffix(".tcl")
    liberty = PDK / "ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/lib/sg13cmos5l_stdcell_slow_1p08V_125C.lib"
    env = os.environ.copy()
    env.update(AXPE_ECO_LIBERTY=str(liberty), AXPE_ECO_ODB=state["odb"],
               AXPE_ECO_SDC=state["sdc"], AXPE_ECO_OUTPUT_PREFIX=str(prefix))
    with (output / "openroad.log").open("w") as log:
        subprocess.run(["openroad", "-exit", "-no_splash", str(script)],
                       cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True)

    expected = cells(state["nl"])
    actual = cells(str(prefix) + ".nl.v")
    additions = actual.keys() - expected.keys()
    if len(additions) != 1:
        raise ValueError("expected exactly one added cell")
    name = next(iter(additions))
    cell, pins = actual[name]
    if (not name.startswith("eco_net4_mux") or cell != "sg13cmos5l_buf_1"
            or set(pins) != {"A", "X"} or pins["A"] != "net4"
            or not pins["X"].startswith("eco_net4_mux_net")):
        raise ValueError("unexpected ECO buffer or connections")
    child = pins["X"]
    for name in ("_09704_", "_09988_"):
        if expected[name][1]["A1"] != "net4":
            raise ValueError(f"unexpected source connection: {name}")
        expected[name][1]["A1"] = child
    added = next(iter(additions))
    expected[added] = (cell, pins)
    if actual != expected:
        raise ValueError("netlist delta exceeds one buffer and two load moves")

    # Keep interface metadata and constraints, clear all stale timing/physical
    # views and metrics. Global routing and extraction must regenerate them.
    clean = {key: state[key] for key in ("json_h", "vh", "sdc")}
    clean.update({key: str(prefix) + suffix for key, suffix in
                  (("odb", ".odb"), ("def", ".def"), ("nl", ".nl.v"))})
    clean["metrics"] = {}
    (output / "state_out.json").write_text(json.dumps(clean, indent=2) + "\n")
    record = {
        "schema": "org.atomix.axpe-fanout-eco.v1",
        "parent_state": str(PARENT.relative_to(ROOT)),
        "parent_state_sha256": digest(PARENT),
        "inputs": INPUT_HASHES,
        "pdk_commit": commit,
        "liberty_sha256": digest(liberty),
        "recipe_sha256": digest(__file__),
        "tcl_sha256": digest(script),
        "outputs": {path.name: digest(path) for path in output.iterdir()
                    if path.is_file()},
        "connectivity_check": "pass: exactly one buf_1 and two A1 load moves",
        "added_buffer": added,
        "child_net": child,
        "scope": "legalized pre-route ECO only; no timing or antenna claim",
    }
    (output / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"ECO prepared: {output / 'state_out.json'}; connectivity delta passes")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"wire200 fanout ECO: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
