#!/usr/bin/env python3
"""Bind a completed local CMOS5L candidate to its standalone functional replay.

Outputs are review artifacts under build/asic, never an external submission.
No flow is run, source changed, or existing directory replaced by this tool.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import tempfile

import tt_axpe
import tt_axpe_flow as flow
import tt_axpe_netlist as replay_tool
import tt_axpe_precheck as precheck_tool

ROOT = tt_axpe.ROOT
OVERLAY = tt_axpe.OVERLAY


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def precheck_copies(directory: Path, state_path: Path, lock_path: Path,
                    lock: dict) -> tuple[dict, dict]:
    """Accept only a complete unchanged precheck of this signoff's exact GDS."""
    receipt_path = directory / "evidence.json"
    receipt = tt_axpe.read_json(receipt_path)
    require(receipt.get("schema") == "org.atomix.axpe-precheck-evidence.v1"
            and receipt.get("status") == "passed" and receipt.get("returncode") == 0,
            "a passing Tiny Tapeout precheck receipt is required")
    state = tt_axpe.read_json(state_path)
    require(receipt["gds_sha256"] == tt_axpe.file_hash(Path(state["gds"]))
            and receipt["signoff_state_sha256"] == tt_axpe.file_hash(state_path),
            "precheck and selected signoff GDS/state differ")
    require(receipt["flow_lock_sha256"] == tt_axpe.file_hash(lock_path)
            and receipt["support_tools_commit"] == lock["flow"]["support_tools_commit"]
            and receipt["pdk_commit"] == lock["flow"]["pdk_commit"],
            "precheck flow/tool/PDK identity differs")
    checks = precheck_tool.results(directory / "tt/precheck/reports/results.xml", 0)
    require(receipt["checks"] == checks, "precheck report differs from its receipt")
    require("tt/precheck/reports/results.xml" in receipt["report_sha256"],
            "precheck result XML must be hash-bound and bundled")
    copies = {"verification/precheck/evidence.json": receipt_path}
    for relative, digest in receipt["report_sha256"].items():
        source = (directory / relative).resolve()
        require(source.is_relative_to(directory), "precheck report path escapes its directory")
        require(tt_axpe.file_hash(source) == digest, f"precheck report changed: {relative}")
        copies["verification/precheck/" + relative] = source
    # Verify all inputs while they are available locally; the portable package
    # binds its own copied GDS and reports without requiring these host paths.
    for name, digest in receipt["input_sha256"].items():
        require(tt_axpe.file_hash(Path(name)) == digest, f"precheck input changed: {name}")
    return copies, {"gds_sha256": receipt["gds_sha256"], "checks": checks,
                    "expected_checks": sorted(precheck_tool.CHECKS),
                    "receipt_sha256": tt_axpe.file_hash(receipt_path),
                    "scope": receipt["level"]}


def bundle_timing_proof(staging: Path, proof: Path, parameters: dict) -> dict:
    """Relocate accepted SAT jobs without changing the harness or RTL bytes."""
    receipt = tt_axpe.read_json(proof / "evidence.json")
    require(receipt.get("status") == "passed", "complete timing proof is required")
    require(receipt.get("parameters") == parameters, "formal and hardened parameters differ")
    isa = tt_axpe.read_json(ROOT / "sw/pemu/isa/axpe-isa.json")
    instructions = {item["mnemonic"]: item["timing"] for item in isa["instructions"]}
    require(receipt["instructions"] == instructions, "formal instruction set differs")
    for name, digest in receipt["inputs_sha256"].items():
        require(tt_axpe.file_hash(Path(name)) == digest, f"formal input changed: {name}")
        source = Path(name)
        if source.is_relative_to(ROOT / "formal/pemu"):
            target = staging / "verification/formal/generator" / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    expected = [("original/proof.ys", "induction", receipt["proof"]["proof_script_sha256"])]
    covers = receipt["proof"]["covers"]
    require(
        all("op_" + name in covers for name in instructions), "missing opcode completion witnesses"
    )
    for name, item in covers.items():
        require(re.fullmatch(r"[A-Za-z0-9_-]+", name) is not None, "invalid formal cover name")
        expected.append((f"original/cover_{name}.ys", "cover", item["script_sha256"]))
    require(len(receipt["mutations"]) >= 5, "missing timing mutation checks")
    for name, item in receipt["mutations"].items():
        require(re.fullmatch(r"[A-Za-z0-9_-]+", name) is not None, "invalid formal mutation name")
        require(item["result"] == "expected counterexample", f"mutation did not fail: {name}")
        expected.append((f"{name}/proof.ys", "counterexample", item["proof_script_sha256"]))
    target = staging / "verification/formal"
    target.mkdir(parents=True, exist_ok=True)
    harnesses = {"original/core.sv": receipt["proof"]["harness_sha256"]}
    for name, item in receipt["mutations"].items():
        harnesses[f"{name}/core.sv"] = item["harness_sha256"]
        harnesses[f"{name}.sv"] = item["core_sha256"]
    # Each accepted script references only original RTL, its harness and (for
    # mutation jobs) its changed core copy. Exact replacements keep it runnable
    # from the exported repository, without reaching back into atomiX.
    replacements = {
        str(ROOT / "components/pemu/axpe" / name): "src/" + name
        for name in ("axpe.sv", "axpe_decode.sv", "axpe_timing.sv", "axpe_shift.sv", "axpe_pads.sv")
    }
    for relative, digest in harnesses.items():
        source = proof / relative
        require(
            tt_axpe.file_hash(source) == digest, f"formal harness/core copy changed: {relative}"
        )
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        replacements[str(source)] = str(destination.relative_to(staging))
    jobs = []
    input_hashes = dict(receipt["inputs_sha256"])
    input_hashes[str(proof / "evidence.json")] = tt_axpe.file_hash(proof / "evidence.json")
    input_hashes.update({str(proof / name): digest for name, digest in harnesses.items()})
    for relative, kind, digest in expected:
        source = proof / relative
        require(tt_axpe.file_hash(source) == digest, f"formal job changed: {relative}")
        input_hashes[str(source)] = digest
        script = source.read_text()
        for before, after in replacements.items():
            script = script.replace(before, after)
        require(str(ROOT) not in script, f"unrelocated formal job: {relative}")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(script)
        jobs.append(
            {
                "path": str(destination.relative_to(staging)),
                "kind": kind,
                "original_sha256": digest,
                "sha256": tt_axpe.file_hash(destination),
            }
        )
    shutil.copy2(proof / "evidence.json", staging / "verification/candidate/timing-proof.json")
    shutil.copy2(OVERLAY / "demo/check_timing.py", staging / "verification/check_timing.py")
    return {
        "receipt_sha256": tt_axpe.file_hash(proof / "evidence.json"),
        "scope": receipt["scope"],
        "assumptions": receipt["assumptions"],
        "not_proved": receipt["not_proved"],
        "input_sha256": input_hashes,
        "jobs": jobs,
    }


def package(args: argparse.Namespace) -> None:
    workdir = flow.require_workdir(args.workdir)
    output = flow.require_workdir(args.output)
    require(not output.exists(), f"refusing to replace existing package: {output}")
    require(not output.is_relative_to(workdir), "package must be outside the flow workspace")
    profile, lock_path = args.profile.resolve(), args.flow_lock.resolve()
    lock = tt_axpe.read_json(lock_path)
    tt_axpe.validate_lock(lock)
    flow.validate_export(workdir, lock_path, profile, lock)
    require(args.tag == Path(args.tag).name and args.tag not in (".", ".."), "invalid run tag")
    run = workdir / "runs" / args.tag
    state_path = run / "17-misc-reportmanufacturability/state_out.json"
    require(state_path.is_file(), "completed Classic signoff state is required")
    state = tt_axpe.read_json(state_path)
    physical_receipt_path = ROOT / "research/benchmarks/axpe-cmos5l-25ns.json"
    physical_receipt = tt_axpe.read_json(physical_receipt_path)
    selected = physical_receipt["post_grt_max_wire_200_fanout_eco_trial"]
    require(
        selected["signoff"]["status"] == "passed"
        and selected["signoff"]["state_sha256"] == tt_axpe.file_hash(state_path),
        "signoff state differs from the recorded selected ECO",
    )
    require(
        tt_axpe.file_hash(OVERLAY / "experiments/wire200-fanout-eco.py")
        == selected["recipe_record"]["recipe_sha256"]
        and tt_axpe.file_hash(OVERLAY / "experiments/wire200-fanout-eco.tcl")
        == selected["recipe_record"]["tcl_sha256"],
        "recorded ECO recipe changed",
    )
    metrics = tt_axpe.read_json(run / "final/metrics.json")
    require(metrics == state["metrics"], "final metrics differ from the completed signoff state")
    summary = tt_axpe.read_json(run / "summary.json")
    require(
        summary["metrics_sha256"] == tt_axpe.file_hash(run / "final/metrics.json"),
        "stale physical summary",
    )
    require(summary["flow_lock_sha256"] == tt_axpe.file_hash(lock_path), "summary lock differs")
    require(summary["candidate"] == lock["candidate"], "summary candidate differs")
    require(summary["run"] == args.tag, "summary run differs")
    require(
        summary["export_manifest_sha256"] == tt_axpe.file_hash(workdir / tt_axpe.MARKER),
        "hardened source manifest changed after signoff",
    )
    physical_checks = (
        "route__drc_errors",
        "antenna__violating__nets",
        "antenna__violating__pins",
        "magic__drc_error__count",
        "design__lvs_error__count",
        "design__lvs_device_difference__count",
        "design__lvs_net_difference__count",
        "design__lvs_property_fail__count",
        "design__lvs_unmatched_device__count",
        "design__lvs_unmatched_net__count",
        "design__lvs_unmatched_pin__count",
    )
    for key in physical_checks:
        require(metrics.get(key) == 0, f"missing or failing physical check: {key}")
    for corner in replay_tool.CORNERS:
        for key in (
            "timing__setup_vio__count",
            "timing__hold_vio__count",
            "design__max_slew_violation__count",
            "design__max_fanout_violation__count",
            "design__max_cap_violation__count",
        ):
            require(
                metrics.get(f"{key}__corner:nom_{corner}") == 0,
                f"missing or failing electrical check: {key} {corner}",
            )
    replay = args.replay.resolve()
    receipt_path = replay / "evidence.json"
    receipt = tt_axpe.read_json(receipt_path)
    require(
        receipt.get("status") == "passed" and receipt.get("startup_seeds") == [1, 17, 91],
        "a completed three-seed mapped replay is required",
    )
    require(receipt["pdk_commit"] == lock["flow"]["pdk_commit"], "replay PDK differs")
    nl = Path(state["nl"])
    nl_hash = tt_axpe.file_hash(nl)
    require(
        nl_hash == selected["signoff"]["netlist_sha256"]
        and tt_axpe.file_hash(Path(state["gds"])) == selected["signoff"]["gds_sha256"],
        "selected hardened assets changed after signoff",
    )
    require(
        receipt["input_sha256"][receipt["netlist"]] == nl_hash,
        "signoff and replay netlist hashes differ",
    )
    model = replay / f"{replay_tool.CORNERS[0]}.v"
    require(
        tt_axpe.file_hash(model) == receipt["functional_model_sha256"], "replay cell model changed"
    )
    replay_tool.bindings(nl.read_text(), model.read_text())
    # Build helpers may evolve after a historical run. Every *functional* input
    # copied for this new replay must still match the accepted run exactly.
    functional = [
        ROOT / "sim/pemu" / name
        for name in (
            "axpe_tt_tb.cpp",
            "axpe_cases.h",
            "axpe_device.h",
            "axpe_peers.h",
            "axpe_trace.h",
        )
    ]
    functional += [
        ROOT / "sw/pemu" / name
        for name in (
            "model/axpe_model.c",
            "model/axpe_model.h",
            "isa/axpe_isa.h",
            "isa/axpe-isa.json",
            "as/axpe_as.py",
        )
    ]
    functional += list((ROOT / "sw/pemu/firmware").glob("*.s"))
    functional += [ROOT / "sw/pemu/firmware/build_demos.py", ROOT / "sw/pemu/firmware/demo.json"]
    functional += sorted((ROOT / "sw/pemu/firmware/profiles").glob("*.json"))
    for path in functional:
        require(
            receipt["input_sha256"].get(str(path)) == tt_axpe.file_hash(path),
            f"functional input changed after accepted replay: {path}",
        )
    rate_profiles = receipt.get("rate_profiles", {})
    require(set(rate_profiles) == {p.stem for p in (ROOT / "sw/pemu/firmware/profiles").glob("*.json")},
            "completed runtime-rate replay required for every supplied profile")
    copies = {
        "hardened/design.gds": Path(state["gds"]),
        "hardened/design.nl.v": nl,
        "hardened/cells.v": model,
        "verification/candidate/summary.json": run / "summary.json",
        "verification/candidate/metrics.json": run / "final/metrics.json",
        "verification/candidate/replay.json": receipt_path,
        "verification/candidate/physical-evidence.json": physical_receipt_path,
        "verification/candidate/drc.magic.rpt": run / "07-magic-drc/reports/drc.magic.rpt",
        "verification/candidate/lvs.netgen.rpt": run / "11-netgen-lvs/reports/lvs.netgen.rpt",
        "verification/candidate/lvs.netgen.json": run / "11-netgen-lvs/reports/lvs.netgen.json",
        "verification/candidate/manufacturability.rpt": run
        / "17-misc-reportmanufacturability/manufacturability.rpt",
        "verification/candidate/profile.json": profile,
        "verification/candidate/flow-lock.json": lock_path,
        "verification/check_package.py": OVERLAY / "demo/check_package.py",
        "verification/restore_eco_parent.py": OVERLAY / "demo/restore_eco_parent.py",
        "docs/physical-candidate.md": OVERLAY / "docs/physical-candidate.md",
        "verification/candidate/eco.py": OVERLAY / "experiments/wire200-fanout-eco.py",
        "verification/candidate/eco.tcl": OVERLAY / "experiments/wire200-fanout-eco.tcl",
    }
    precheck = None
    if args.precheck:
        extra, precheck = precheck_copies(args.precheck.resolve(), state_path, lock_path, lock)
        copies.update(extra)
    for name in receipt["firmware_sha256"]:
        path = replay / "fw" / name
        require(
            tt_axpe.file_hash(path) == receipt["firmware_sha256"][name], "replay firmware changed"
        )
        copies[f"verification/candidate/firmware/{name}"] = path
    for name, rate in rate_profiles.items():
        for filename, digest in rate["outputs_sha256"].items():
            source = replay / "fw-rates" / name / filename
            require(tt_axpe.file_hash(source) == digest, f"rate image changed: {name}/{filename}")
            copies[f"verification/candidate/rates/{name}/{filename}"] = source
        for seed in (1, 17, 91):
            filename = f"rates-{name}-seed-{seed}.log"
            source = replay / filename
            require(tt_axpe.file_hash(source) == receipt["logs"][filename], "rate replay log changed")
            copies[f"verification/candidate/rates/{filename}"] = source
    # Include the exact pre-ECO checkpoint so reproducing the selected delta
    # does not depend on retaining the original workstation's build tree.
    parent_path = ROOT / selected["recipe_record"]["parent_state"]
    require(
        tt_axpe.file_hash(parent_path) == selected["recipe_record"]["parent_state_sha256"],
        "ECO parent state changed",
    )
    parent = tt_axpe.read_json(parent_path)
    parent_files = {}
    copies["verification/candidate/eco-parent/original-state.json"] = parent_path
    for key in ("odb", "nl", "sdc", "json_h", "vh"):
        source = Path(parent[key])
        digest = tt_axpe.file_hash(source)
        if key in selected["recipe_record"]["inputs"]:
            require(digest == selected["recipe_record"]["inputs"][key], f"ECO parent {key} changed")
        relative = f"verification/candidate/eco-parent/{source.name}"
        copies[relative] = source
        parent_files[key] = {"path": relative, "sha256": digest}
    input_hashes = {str(p): tt_axpe.file_hash(p) for p in copies.values()}
    input_hashes[str(state_path)] = tt_axpe.file_hash(state_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".axpe-package-", dir=output.parent) as tmp:
        staging = Path(tmp) / "export"
        manifest = tt_axpe.export(profile, staging, lock_path)
        original = tt_axpe.read_json(workdir / tt_axpe.MARKER)
        require(
            manifest["sources"] == original["sources"],
            "export hardware differs from hardened inputs",
        )
        require(
            tt_axpe.file_hash(staging / "src/config.json")
            == tt_axpe.file_hash(workdir / "src/config.json"),
            "export physical settings differ",
        )
        for relative, source in copies.items():
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        timing_proof = None
        if args.timing_proof:
            timing_proof = bundle_timing_proof(
                staging, args.timing_proof.resolve(), manifest["parameters"]
            )
        record = {
            "schema": "org.atomix.axpe-candidate-package.v1",
            "scope": "local review candidate; no publication, review approval or physical-operation claim",
            "candidate": lock["candidate"],
            "hardware_sources": manifest["sources"],
            "netlist_sha256": nl_hash,
            "gds_sha256": tt_axpe.file_hash(Path(state["gds"])),
            "functional_model_sha256": receipt["functional_model_sha256"],
            "signoff_state_sha256": tt_axpe.file_hash(state_path),
            "replay_receipt_sha256": tt_axpe.file_hash(receipt_path),
            "firmware_sha256": receipt["firmware_sha256"],
            "rate_profiles": rate_profiles,
            "recipe_sha256": tt_axpe.file_hash(Path(__file__)),
            "input_sha256": input_hashes,
            "checks": {key: metrics[key] for key in physical_checks},
            "startup_seeds": receipt["startup_seeds"],
            "eco_parent": {
                "original_state_sha256": tt_axpe.file_hash(parent_path),
                "files": parent_files,
                "scope": "exact pre-ECO checkpoint; original absolute paths must be relocated before replay",
            },
            "timing_proof": timing_proof,
            "precheck": precheck,
            "limits": [
                "4 ns external IO delay remains provisional",
                "only 25 ps fast-corner hold margin",
                "flow KLayout DRC/XOR and Yosys EQY skipped; separate TT precheck is recorded when supplied",
                "Tiny Tapeout precheck not supplied" if not precheck
                else "Tiny Tapeout precheck does not establish ECO flow reproduction",
                "no package supply/IR-drop contract",
                "two-state zero-delay functional replay; no SDF",
                "maintainer commit-pinned reviews owed",
                "program-memory/data correctness and non-default architecture are outside the timing proof"
                if timing_proof
                else "complete instruction-retirement proof remains open",
                "no FPGA or measured silicon evidence",
            ],
            "files_sha256": {
                str(p.relative_to(staging)): tt_axpe.file_hash(p)
                for p in sorted(staging.rglob("*"))
                if p.is_file()
            },
        }
        (staging / ".atomix-candidate.json").write_text(json.dumps(record, indent=2) + "\n")
        for path, digest in input_hashes.items():
            require(tt_axpe.file_hash(Path(path)) == digest, f"input drift while packaging: {path}")
        flow.validate_export(workdir, lock_path, profile, lock)
        if timing_proof:
            for path, digest in timing_proof["input_sha256"].items():
                require(
                    tt_axpe.file_hash(Path(path)) == digest,
                    f"formal input drift while packaging: {path}",
                )
        for path in functional:
            require(
                receipt["input_sha256"].get(str(path)) == tt_axpe.file_hash(path),
                f"functional input drift while packaging: {path}",
            )
        require(not output.exists(), "output appeared while packaging; refusing replacement")
        staging.rename(output)
    print(f"axpe candidate package: PASS: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workdir", "replay", "profile", "flow-lock", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--precheck", type=Path,
                        help="accepted exact-GDS Tiny Tapeout precheck directory")
    parser.add_argument(
        "--timing-proof",
        type=Path,
        help="accepted complete core timing proof directory; includes portable SAT jobs",
    )
    args = parser.parse_args()
    try:
        package(args)
    except (ValueError, KeyError, OSError, tt_axpe.ExportError, flow.FlowError) as exc:
        parser.exit(1, f"axpe candidate package: FAIL: {exc}\n")


if __name__ == "__main__":
    main()
