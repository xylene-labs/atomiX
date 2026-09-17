#!/usr/bin/env python3
"""Validate and recompute deterministic Live FPGA fitness records."""

from __future__ import annotations

import argparse
import copy
import hashlib
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import personality_contract as pc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "research" / "live-fpga" / "fitness-example.json"
DECLINED_ROOT = ROOT / "research" / "live-fpga" / "fitness-cases" / "declined.json"
MISSING_ROOT = ROOT / "research" / "live-fpga" / "fitness-cases" / "missing-observation.json"
U32_MAX = (1 << 32) - 1
U64_MAX = (1 << 64) - 1
OBJECTIVE = "org.atomix.fitness.cycles-per-work-q10"
REASONS = (
    (1 << 1, "org.atomix.fitness.reject.sequence"),
    (1 << 2, "org.atomix.fitness.reject.oracle"),
    (1 << 3, "org.atomix.fitness.reject.work"),
    (1 << 4, "org.atomix.fitness.reject.descriptor"),
    (1 << 5, "org.atomix.fitness.reject.watchdog"),
    (1 << 6, "org.atomix.fitness.reject.generation"),
    (1 << 7, "org.atomix.fitness.reject.counters"),
    (1 << 8, "org.atomix.fitness.reject.score-range"),
    (1 << 9, "org.atomix.fitness.reject.descriptor-observation-unavailable"),
    (1 << 10, "org.atomix.fitness.reject.watchdog-observation-unavailable"),
)
COUNTERS = (
    "cycles",
    "work_completed",
    "memory_stalls",
    "configuration_generation",
)
SAFETY_COUNTERS = (
    "descriptor_rejections",
    "watchdog_events",
)


def bounded_int(path: Path, value: Any, name: str, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= maximum:
        raise pc.error(path, f"{name} must be an integer in [0, {maximum}]")
    return value


def positive(path: Path, value: Any, name: str) -> int:
    result = bounded_int(path, value, name, U32_MAX)
    if result == 0:
        raise pc.error(path, f"{name} must be positive")
    return result


def validate_snapshot(path: Path, value: Any, name: str,
                      producers: dict[str, Any]) -> dict[str, int | None]:
    snapshot = pc.object_value(path, value, name)
    pc.exact_keys(path, snapshot, name,
                  {"sequence", *COUNTERS, *SAFETY_COUNTERS})
    bounded_int(path, snapshot["sequence"], f"{name}.sequence", U32_MAX)
    for counter in COUNTERS:
        bounded_int(path, snapshot[counter], f"{name}.{counter}", U64_MAX)
    for counter in SAFETY_COUNTERS:
        if producers[counter]["observed"]:
            bounded_int(path, snapshot[counter], f"{name}.{counter}", U64_MAX)
        elif snapshot[counter] is not None:
            raise pc.error(path, f"{name}.{counter} must be null when unobserved")
    return snapshot


def validate_producers(path: Path, value: Any) -> dict[str, dict[str, bool]]:
    producers = pc.object_value(path, value, "telemetry.producers")
    pc.exact_keys(path, producers, "telemetry.producers", set(SAFETY_COUNTERS))
    for counter in SAFETY_COUNTERS:
        state = pc.object_value(
            path, producers[counter], f"telemetry.producers.{counter}")
        pc.exact_keys(path, state, f"telemetry.producers.{counter}",
                      {"present", "observed"})
        if not isinstance(state["present"], bool) or \
                not isinstance(state["observed"], bool):
            raise pc.error(path, f"telemetry.producers.{counter} states must be boolean")
        if state["observed"] and not state["present"]:
            raise pc.error(path, f"telemetry.producers.{counter} cannot be observed "
                           "without a producer")
    return producers


def validate_profile(path: Path, value: Any, producers: dict[str, Any]) -> None:
    profile = pc.object_value(path, value, "telemetry.profile")
    pc.exact_keys(path, profile, "telemetry.profile", {"path", "sha256"})
    relative = profile["path"]
    if not isinstance(relative, str) or not relative:
        raise pc.error(path, "telemetry.profile.path must be non-empty")
    profile_path = (ROOT / relative).resolve()
    try:
        profile_path.relative_to(ROOT)
    except ValueError as exc:
        raise pc.error(path, "telemetry.profile.path must stay inside the checkout") from exc
    if not profile_path.is_file():
        raise pc.error(path, f"telemetry profile does not exist: {relative}")
    digest = hashlib.sha256(profile_path.read_bytes()).hexdigest()
    if profile["sha256"] != digest:
        raise pc.error(path, "telemetry.profile.sha256 does not match the profile")
    resolved = subprocess.run(
        [sys.executable, str(ROOT / "tools/configure.py"), "resolve",
         "--config", str(profile_path)], cwd=ROOT, capture_output=True, text=True)
    if resolved.returncode != 0:
        raise pc.error(path, "telemetry profile does not resolve: " +
                       (resolved.stderr.strip() or "unknown resolver failure"))
    present = "+define+AX_LIVE_ROLE_EVENTS=1" in resolved.stdout.split()
    for counter in SAFETY_COUNTERS:
        if producers[counter]["present"] != present:
            raise pc.error(
                path, f"telemetry.producers.{counter}.present disagrees with "
                f"resolved profile {relative}")


def delta(before: int, after: int, bits: int) -> int:
    return (after - before) & ((1 << bits) - 1)


def validate_input(path: Path, document: dict[str, Any]) -> None:
    required = {
        "schema", "kind", "id", "revision", "summary", "candidate",
        "workload", "telemetry", "oracle", "energy", "objective", "result",
        "extensions",
    }
    pc.exact_keys(path, document, "fitness record", required)
    if document["kind"] != "live-fitness":
        raise pc.error(path, "kind must be 'live-fitness'")
    pc.common(path, document, "org.atomix.live-fitness")
    if document["schema"]["minor"] != 1:
        raise pc.error(path, "live-fitness schema must be version 1.1")

    candidate = pc.object_value(path, document["candidate"], "candidate")
    pc.exact_keys(path, candidate, "candidate", {"id", "numeric_id"})
    pc.namespaced(path, candidate["id"], "candidate.id")
    positive(path, candidate["numeric_id"], "candidate.numeric_id")

    workload = pc.object_value(path, document["workload"], "workload")
    pc.exact_keys(
        path, workload, "workload", {"id", "revision", "case", "expected_work"}
    )
    pc.namespaced(path, workload["id"], "workload.id")
    positive(path, workload["revision"], "workload.revision")
    if not isinstance(workload["case"], str) or not workload["case"].strip():
        raise pc.error(path, "workload.case must be a non-empty string")
    positive(path, workload["expected_work"], "workload.expected_work")

    telemetry = pc.object_value(path, document["telemetry"], "telemetry")
    pc.exact_keys(path, telemetry, "telemetry",
                  {"schema", "profile", "producers", "before", "after"})
    version = pc.object_value(path, telemetry["schema"], "telemetry.schema")
    pc.exact_keys(path, version, "telemetry.schema", {"major", "minor"})
    if version != {"major": 1, "minor": 0}:
        raise pc.error(path, "telemetry.schema must be Live FPGA L0 version 1.0")
    producers = validate_producers(path, telemetry["producers"])
    validate_profile(path, telemetry["profile"], producers)
    validate_snapshot(path, telemetry["before"], "telemetry.before", producers)
    validate_snapshot(path, telemetry["after"], "telemetry.after", producers)

    oracle = pc.object_value(path, document["oracle"], "oracle")
    pc.exact_keys(
        path, oracle, "oracle", {"status", "cases", "output_sha256", "method"}
    )
    status = pc.namespaced(path, oracle["status"], "oracle.status")
    if status not in {"org.atomix.pass", "org.atomix.fail"}:
        raise pc.error(path, "oracle.status must be org.atomix.pass or org.atomix.fail")
    cases = bounded_int(path, oracle["cases"], "oracle.cases", U32_MAX)
    digest = oracle["output_sha256"]
    if digest is not None and (
        not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
    ):
        raise pc.error(path, "oracle.output_sha256 must be null or lowercase SHA-256")
    if status == "org.atomix.pass" and (cases == 0 or digest is None):
        raise pc.error(path, "a passing oracle needs cases and output SHA-256")
    if not isinstance(oracle["method"], str) or not oracle["method"].strip():
        raise pc.error(path, "oracle.method must be non-empty")

    energy = pc.object_value(path, document["energy"], "energy")
    pc.exact_keys(path, energy, "energy", {"picojoules", "method"})
    if energy["picojoules"] is not None:
        bounded_int(path, energy["picojoules"], "energy.picojoules", U64_MAX)
    if not isinstance(energy["method"], str) or not energy["method"].strip():
        raise pc.error(path, "energy.method must be non-empty")

    objective = pc.object_value(path, document["objective"], "objective")
    pc.exact_keys(
        path, objective, "objective", {"id", "scale", "rounding", "direction"}
    )
    if objective != {
        "id": OBJECTIVE,
        "scale": 1024,
        "rounding": "org.atomix.round-up",
        "direction": "org.atomix.lower-is-better",
    }:
        raise pc.error(path, "unsupported or non-canonical fitness objective")
    pc.extensions(path, document["extensions"])


def derive(document: dict[str, Any]) -> dict[str, Any]:
    telemetry = document["telemetry"]
    before, after = telemetry["before"], telemetry["after"]
    deltas = {name: delta(before[name], after[name], 64) for name in COUNTERS}
    for name in SAFETY_COUNTERS:
        state = telemetry["producers"][name]
        deltas[name] = delta(before[name], after[name], 64) \
            if state["present"] and state["observed"] else None
    mask = 0
    if delta(before["sequence"], after["sequence"], 32) != 1:
        mask |= 1 << 1
    oracle = document["oracle"]
    if oracle["status"] != "org.atomix.pass" or oracle["cases"] == 0:
        mask |= 1 << 2
    if deltas["work_completed"] != document["workload"]["expected_work"]:
        mask |= 1 << 3
    if deltas["descriptor_rejections"] not in (0, None):
        mask |= 1 << 4
    if deltas["watchdog_events"] not in (0, None):
        mask |= 1 << 5
    if deltas["descriptor_rejections"] is None:
        mask |= 1 << 9
    if deltas["watchdog_events"] is None:
        mask |= 1 << 10
    if deltas["configuration_generation"] != 0:
        mask |= 1 << 6
    if deltas["cycles"] == 0 or deltas["memory_stalls"] > deltas["cycles"]:
        mask |= 1 << 7

    score = U32_MAX
    if mask == 0:
        numerator = deltas["cycles"] * 1024
        score = numerator // deltas["work_completed"]
        if numerator % deltas["work_completed"]:
            score += 1
        if score > U32_MAX:
            score = U32_MAX
            mask |= 1 << 8

    return {
        "eligible": mask == 0,
        "rejection_mask": mask,
        "rejection_reasons": [name for bit, name in REASONS if mask & bit],
        "deltas": deltas,
        "ratios": {
            "cycles_per_work": {
                "numerator": deltas["cycles"],
                "denominator": deltas["work_completed"],
            },
            "stall_fraction": {
                "numerator": deltas["memory_stalls"],
                "denominator": deltas["cycles"],
            },
        },
        "evolution_record": {
            "candidate_id": document["candidate"]["numeric_id"],
            "fitness": score,
            "evidence_generation": document["revision"],
            "objective_id": 1,
            "flags": 1 if mask == 0 else 0,
        },
    }


def validate_document(path: Path, document: dict[str, Any]) -> None:
    validate_input(path, document)
    result = pc.object_value(path, document["result"], "result")
    expected = derive(document)
    if result != expected:
        raise pc.error(path, "result does not exactly match deterministic derivation")


def load(path: Path) -> dict[str, Any]:
    return pc.load_document(path)


def check(paths: list[Path]) -> int:
    files = pc.collect(paths)
    if not files:
        raise pc.ContractError("no Live FPGA fitness JSON documents found")
    identities: set[tuple[str, int]] = set()
    for path in files:
        document = load(path)
        validate_document(path, document)
        identity = (document["id"], document["revision"])
        if identity in identities:
            raise pc.error(path, f"duplicate fitness identity {identity!r}")
        identities.add(identity)
    print(f"live fitness: PASS ({len(files)} deterministic records)")
    return 0


def self_test() -> int:
    path = DEFAULT_ROOT
    record = load(path)
    validate_document(path, record)

    tampered = copy.deepcopy(record)
    tampered["result"]["evolution_record"]["fitness"] -= 1
    try:
        validate_document(Path("<tampered-result>"), tampered)
    except pc.ContractError:
        pass
    else:
        raise pc.ContractError("self-test accepted a tampered fitness score")

    wrong = copy.deepcopy(record)
    wrong["oracle"]["status"] = "org.atomix.fail"
    wrong["oracle"]["cases"] = 1
    wrong["oracle"]["output_sha256"] = None
    wrong["telemetry"]["after"]["cycles"] = 1010
    wrong["result"] = derive(wrong)
    validate_document(Path("<oracle-failure>"), wrong)
    if wrong["result"]["eligible"] or wrong["result"]["evolution_record"]["flags"]:
        raise pc.ContractError("self-test let performance override oracle failure")

    unsafe = copy.deepcopy(record)
    unsafe["telemetry"]["after"]["watchdog_events"] += 1
    unsafe["result"] = derive(unsafe)
    validate_document(Path("<watchdog-failure>"), unsafe)
    if unsafe["result"]["eligible"]:
        raise pc.ContractError("self-test accepted a watchdog event")

    wrapped = copy.deepcopy(record)
    wrapped["telemetry"]["before"].update({
        "sequence": U32_MAX,
        "cycles": U64_MAX - 9,
        "work_completed": U64_MAX - 1,
        "memory_stalls": U64_MAX - 2,
    })
    wrapped["telemetry"]["after"].update({
        "sequence": 0,
        "cycles": 10,
        "work_completed": 2,
        "memory_stalls": 1,
    })
    wrapped["result"] = derive(wrapped)
    validate_document(Path("<counter-wrap>"), wrapped)
    if wrapped["result"]["evolution_record"]["fitness"] != 5120:
        raise pc.ContractError("self-test computed the wrong wrapped score")

    declined = load(DECLINED_ROOT)
    validate_document(DECLINED_ROOT, declined)
    unavailable = (1 << 9) | (1 << 10)
    if declined["result"]["eligible"] or \
            declined["result"]["rejection_mask"] & unavailable != unavailable:
        raise pc.ContractError("self-test let a declined producer satisfy zero events")

    missing = load(MISSING_ROOT)
    validate_document(MISSING_ROOT, missing)
    if missing["result"]["eligible"] or \
            missing["result"]["rejection_mask"] != 1 << 9:
        raise pc.ContractError("self-test let a missing observation satisfy zero events")

    impossible = copy.deepcopy(missing)
    state = impossible["telemetry"]["producers"]["descriptor_rejections"]
    state.update({"present": False, "observed": True})
    try:
        validate_document(Path("<observed-without-producer>"), impossible)
    except pc.ContractError:
        pass
    else:
        raise pc.ContractError("self-test accepted an observation without a producer")

    disguised = copy.deepcopy(missing)
    disguised["telemetry"]["before"]["descriptor_rejections"] = 0
    disguised["telemetry"]["after"]["descriptor_rejections"] = 0
    try:
        validate_document(Path("<unobserved-zero>"), disguised)
    except pc.ContractError:
        pass
    else:
        raise pc.ContractError("self-test accepted zero values for an unobserved counter")

    fabricated = copy.deepcopy(record)
    fabricated["telemetry"]["producers"]["descriptor_rejections"]["present"] = False
    fabricated["telemetry"]["producers"]["descriptor_rejections"]["observed"] = False
    fabricated["telemetry"]["before"]["descriptor_rejections"] = None
    fabricated["telemetry"]["after"]["descriptor_rejections"] = None
    fabricated["result"] = derive(fabricated)
    try:
        validate_document(Path("<profile-presence-mismatch>"), fabricated)
    except pc.ContractError:
        pass
    else:
        raise pc.ContractError("self-test accepted producer state that disagrees "
                               "with the resolved profile")

    print("live fitness: SELF-TEST PASS (hard gates, availability, exact score, "
          "counter wrap)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check", help="validate fitness records")
    check_parser.add_argument("paths", nargs="*", type=Path, default=[DEFAULT_ROOT])
    subparsers.add_parser("self-test", help="exercise deterministic derivation")
    args = parser.parse_args()
    try:
        return self_test() if args.command == "self-test" else check(args.paths)
    except pc.ContractError as exc:
        print(f"live fitness: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
