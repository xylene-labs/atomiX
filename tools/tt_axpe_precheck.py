#!/usr/bin/env python3
"""Run unchanged Tiny Tapeout prechecks on exact selected CMOS5L artifacts.

Each attempt preserves inputs, upstream checks, reports and a hash-bound
receipt under build/asic. A clean local STA/DRC result is not a precheck pass.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

import tt_axpe
import tt_axpe_flow

ROOT = tt_axpe.ROOT
BUILD = ROOT / "build/asic"
CHECKS = {
    "KLayout pin label overlapping drawing", "KLayout SG13CMOS5L DRC",
    "KLayout zero area", "KLayout Checks", "Pin check", "Boundary check",
    "Layer check", "Cell name check", "Analog pin check",
}


def results(path: Path, returncode: int) -> list[dict]:
    """Fail closed on truncated, skipped, duplicate or incomplete reports."""
    root = ET.parse(path).getroot()
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]
    if len(suites) != 1 or suites[0].tag != "testsuite":
        raise ValueError("expected one Tiny Tapeout precheck suite")
    cases = suites[0].findall("testcase")
    names = [case.get("name") for case in cases]
    if len(names) != len(CHECKS) or set(names) != CHECKS:
        raise ValueError(f"incomplete or unexpected CMOS5L precheck set: {names}")
    checks = []
    for case in cases:
        if case.find("skipped") is not None:
            raise ValueError(f"precheck skipped {case.get('name')}")
        errors = case.findall("error") + case.findall("failure")
        checks.append({"name": case.get("name"),
                       "status": "failed" if errors else "passed",
                       "errors": [error.get("message", error.text or "")
                                  for error in errors]})
    failed = any(check["status"] == "failed" for check in checks)
    if bool(returncode) != failed:
        raise ValueError("precheck exit status disagrees with its report")
    return checks


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="axpe-precheck-contract-") as tmp:
        path = Path(tmp) / "results.xml"

        def report(names, child=""):
            path.write_text('<testsuites><testsuite>' + ''.join(
                f'<testcase name="{name}">{child if i == 0 else ""}</testcase>'
                for i, name in enumerate(names)) + '</testsuite></testsuites>')

        names = sorted(CHECKS)
        report(names)
        assert all(check["status"] == "passed" for check in results(path, 0))
        report(names, '<error message="real DRC failure"/>')
        assert results(path, 1)[0]["errors"] == ["real DRC failure"]
        bad = [(names[:-1], "", 0), (names + names[:1], "", 0),
               (names[:-1] + ["foreign check"], "", 0),
               (names, "<skipped/>", 0), (names, "", 1),
               (names, '<failure message="DRC"/>', 0)]
        for names, child, code in bad:
            report(names, child)
            try:
                results(path, code)
            except ValueError:
                continue
            raise AssertionError("invalid precheck report accepted")
    print("axpe precheck contract: PASS (6 rejection cases and retained DRC failure)")


def run(args: argparse.Namespace) -> None:
    if args.state is None or args.export is None or args.output is None:
        raise ValueError("precheck requires --state, --export and a fresh --output")
    output = tt_axpe_flow.require_workdir(args.output)
    if output.exists():
        raise ValueError(f"refusing to replace existing precheck: {output}")
    lock_path = args.flow_lock.resolve()
    lock = tt_axpe.read_json(lock_path)
    tt_axpe.validate_lock(lock)
    support = args.support_tools.resolve()
    pdk = args.pdk_root.resolve()
    tt_axpe_flow.require_commit(support, lock["flow"]["support_tools_commit"], "support tools")
    tt_axpe_flow.require_commit(pdk, lock["flow"]["pdk_commit"], "PDK")
    portable = args.nix_portable.resolve()
    if tt_axpe.file_hash(portable) != lock["flow"]["nix_portable_sha256"]:
        raise ValueError("nix-portable differs from the flow lock")
    export = args.export.resolve()
    manifest = tt_axpe.read_json(export / tt_axpe.MARKER)
    if manifest["flow_lock_sha256"] != tt_axpe.file_hash(lock_path):
        raise ValueError("export flow lock differs from the selected precheck lock")
    state_path = args.state.resolve()
    state = tt_axpe.read_json(state_path)
    top = lock["candidate"]["top_module"]
    assets = {"gds": Path(state["gds"]).resolve(),
              "lef": Path(state["lef"]).resolve(),
              "v": Path(state["pnl"]).resolve()}
    if assets["gds"].stem != top:
        raise ValueError("selected GDS top name differs from the flow lock")
    for path in assets.values():
        if not path.is_file():
            raise ValueError(f"missing selected artifact: {path}")
    output.mkdir(parents=True)
    record = {
        "schema": "org.atomix.axpe-precheck-evidence.v1",
        "level": "local Tiny Tapeout CMOS5L precheck of exact supplied GDS/LEF/netlist",
        "status": "running",
        "flow_lock_sha256": tt_axpe.file_hash(lock_path),
        "support_tools_commit": lock["flow"]["support_tools_commit"],
        "pdk_commit": lock["flow"]["pdk_commit"],
        "gds_sha256": tt_axpe.file_hash(assets["gds"]),
        "signoff_state_sha256": tt_axpe.file_hash(state_path),
        "input_sha256": {},
        "limits": ["precheck does not establish ECO flow reproduction or maintainer approval",
                   "no pad characterization or physical-operation claim"],
    }
    receipt = output / "evidence.json"
    try:
        # Preserve relative precheck/tech paths expected by upstream pin_check.
        tracked = subprocess.check_output([
            "git", "-C", str(support), "ls-files", "-z", "--",
            "precheck", "tech/ihp-sg13cmos5l"]).decode().split("\0")
        for relative in filter(None, tracked):
            destination = output / "tt" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(support / relative, destination)
        reports = output / "tt/precheck/reports"
        reports.mkdir(exist_ok=True)
        submission = output / "submission"
        submission.mkdir()
        for extension, source in assets.items():
            shutil.copy2(source, submission / f"{top}.{extension}")
        shutil.copy2(export / "info.yaml", submission / "info.yaml")
        shutil.copy2(state_path, output / "signoff-state.json")
        shutil.copy2(lock_path, output / "flow-lock.json")
        inputs = [path for path in output.rglob("*") if path.is_file()]
        # Include the actual PDK deck and its supporting technology files.
        inputs += [path for path in (pdk / "ihp-sg13cmos5l/libs.tech/klayout").rglob("*")
                   if path.is_file()]
        inputs += [portable, Path(__file__).resolve()]
        record["input_sha256"] = {str(path): tt_axpe.file_hash(path)
                                  for path in sorted(inputs)}
        env = os.environ.copy()
        env.update(PDK_ROOT=str(pdk), PDK="ihp-sg13cmos5l",
                   NP_LOCATION=str(args.nix_state.resolve()))
        shell = [str(portable), "nix-shell", str(output / "tt/precheck/default.nix")]
        # Preserve the venv path: resolving its interpreter symlink bypasses
        # pyvenv.cfg and silently selects the base interpreter's packages.
        python = str(args.python.absolute())
        probe = (
            "import importlib.metadata as m, json, platform, subprocess; "
            "print(json.dumps({'python': platform.python_version(), "
            "'packages': {d.metadata['Name']: d.version for d in m.distributions()}, "
            "'klayout': subprocess.check_output(['klayout', '-v'], text=True).strip(), "
            "'magic': subprocess.check_output(['magic', '--version'], text=True).strip()}))")
        command = shell + ["--run", shlex.join([python, "-c", probe])]
        record["commands"] = [command]
        versions = subprocess.run(command, env=env, cwd=output,
                                  capture_output=True, text=True, check=True)
        (output / "tools.json").write_text(versions.stdout)
        (output / "tools.log").write_text(versions.stderr)
        record["tools"] = json.loads(versions.stdout)
        command = shell + ["--run", shlex.join([
            python, "precheck.py", "--gds", str(submission / f"{top}.gds"),
            "--tech", "ihp-sg13cmos5l"])]
        record["commands"].append(command)
        with (output / "precheck.log").open("w") as log:
            done = subprocess.run(command, cwd=output / "tt/precheck", env=env,
                                  stdout=log, stderr=subprocess.STDOUT, check=False)
        record["returncode"] = done.returncode
        record["checks"] = results(reports / "results.xml", done.returncode)
        # A receipt cannot certify different inputs than the checks consumed.
        for path, expected in record["input_sha256"].items():
            if tt_axpe.file_hash(Path(path)) != expected:
                raise ValueError(f"precheck input changed during execution: {path}")
        record["status"] = "failed" if done.returncode else "passed"
        if done.returncode:
            raise ValueError(f"Tiny Tapeout precheck failed; see {output / 'precheck.log'}")
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = str(exc)
        raise
    finally:
        record["report_sha256"] = {
            str(path.relative_to(output)): tt_axpe.file_hash(path)
            for path in sorted(output.rglob("*")) if path.is_file()
            and (path.suffix in (".log", ".xml", ".md") or path.name == "tools.json")}
        receipt.write_text(json.dumps(record, indent=2) + "\n")
        print(f"axpe Tiny Tapeout precheck: {record['status']}; receipt: {receipt}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--export", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--flow-lock", type=Path,
                        default=ROOT / "asic/axpe/flow-lock-25ns-postgrt-noant-wire200-am0.json")
    parser.add_argument("--support-tools", type=Path, default=BUILD / "tt-axpe-flow/tt")
    parser.add_argument("--pdk-root", type=Path, default=BUILD / "pdk-cmos5l")
    parser.add_argument("--nix-portable", type=Path, default=BUILD / "nix-portable")
    parser.add_argument("--nix-state", type=Path, default=BUILD / "nix-portable-state")
    parser.add_argument("--python", type=Path, default=BUILD / "tt-precheck-py311/bin/python")
    args = parser.parse_args()
    try:
        self_test() if args.self_test else run(args)
    except (ValueError, OSError, KeyError, ET.ParseError, subprocess.CalledProcessError,
            tt_axpe.ExportError, tt_axpe_flow.FlowError) as exc:
        print(f"axpe precheck: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
