#!/usr/bin/env python3
"""Verify bundled candidate hashes before compiling its mapped replay."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware-dir", type=Path)
    parser.add_argument("--rate-firmware-dir", type=Path)
    parser.add_argument("--rate-profile")
    args = parser.parse_args()
    if bool(args.rate_firmware_dir) != bool(args.rate_profile):
        parser.error("--rate-firmware-dir and --rate-profile are required together")
    manifest = json.loads((ROOT / ".atomix-candidate.json").read_text())
    require(manifest["schema"] == "org.atomix.axpe-candidate-package.v1", "unknown manifest schema")
    for name, digest in manifest["files_sha256"].items():
        path = (ROOT / name).resolve()
        require(path.is_relative_to(ROOT), f"path escapes package: {name}")
        require(sha(path) == digest, f"package input changed: {name}")
    replay = json.loads((ROOT / "verification/candidate/replay.json").read_text())
    nl = sha(ROOT / "hardened/design.nl.v")
    require(nl == manifest["netlist_sha256"] == replay["input_sha256"][replay["netlist"]], "netlist binding differs")
    require(sha(ROOT / "hardened/design.gds") == manifest["gds_sha256"], "GDS binding differs")
    require(sha(ROOT / "hardened/cells.v") == manifest["functional_model_sha256"] == replay["functional_model_sha256"], "cell model binding differs")
    require(replay["status"] == "passed" and replay["startup_seeds"] == [1, 17, 91], "replay is incomplete")
    require(manifest["checks"] and all(value == 0 for value in manifest["checks"].values()), "physical checks failed")
    if manifest.get("precheck"):
        precheck = json.loads((ROOT / "verification/precheck/evidence.json").read_text())
        require(precheck["status"] == "passed" and precheck["returncode"] == 0,
                "Tiny Tapeout precheck did not pass")
        require(sha(ROOT / "verification/precheck/evidence.json")
                == manifest["precheck"]["receipt_sha256"], "precheck receipt binding differs")
        require(precheck["gds_sha256"] == manifest["gds_sha256"]
                == manifest["precheck"]["gds_sha256"], "precheck GDS binding differs")
        require(precheck["signoff_state_sha256"] == manifest["signoff_state_sha256"],
                "precheck signoff state binding differs")
        require(precheck["checks"] == manifest["precheck"]["checks"]
                and precheck["checks"]
                and all(check["status"] == "passed" for check in precheck["checks"]),
                "precheck checks differ or failed")
        results = ET.parse(ROOT / "verification/precheck/tt/precheck/reports/results.xml").getroot()
        suites = results.findall("testsuite") if results.tag == "testsuites" else [results]
        require(len(suites) == 1 and suites[0].tag == "testsuite", "unexpected precheck suite")
        cases = suites[0].findall("testcase")
        require(sorted(case.get("name", "") for case in cases) == manifest["precheck"]["expected_checks"]
                and all(not any(case.find(tag) is not None for tag in ("error", "failure", "skipped"))
                        for case in cases), "precheck result XML failed or incomplete")
    for name, digest in manifest["hardware_sources"].items():
        require(sha(ROOT / name) == digest, f"hardware source changed: {name}")
    if args.firmware_dir:
        for name, digest in manifest["firmware_sha256"].items():
            require(sha(args.firmware_dir / name) == digest, f"assembled payload changed: {name}")
    if manifest.get("rate_profiles") is not None:
        require(manifest["rate_profiles"] == replay.get("rate_profiles"), "runtime-rate replay differs")
        for name, rate in manifest["rate_profiles"].items():
            for filename, digest in rate["outputs_sha256"].items():
                require(sha(ROOT / "verification/candidate/rates" / name / filename) == digest,
                        f"runtime-rate image changed: {name}/{filename}")
    if args.rate_firmware_dir:
        require(args.rate_profile in manifest.get("rate_profiles", {}), "unknown runtime-rate profile")
        expected = manifest["rate_profiles"][args.rate_profile]
        for filename, digest in expected["outputs_sha256"].items():
            # The regenerated receipt names its new host paths; executable
            # images, cycle listings and clock contract must remain identical.
            if filename != "profile.json":
                require(sha(args.rate_firmware_dir / filename) == digest,
                        f"reassembled runtime-rate input changed: {filename}")
        regenerated = json.loads((args.rate_firmware_dir / "profile.json").read_text())
        for field in ("settings", "imem_words", "cycles_per_bit", "outputs_sha256"):
            require(regenerated[field] == expected["build_receipt"][field],
                    f"reassembled runtime-rate metadata differs: {field}")
    print("axpe candidate package hashes and signoff/replay netlist binding: PASS")


if __name__ == "__main__":
    main()
