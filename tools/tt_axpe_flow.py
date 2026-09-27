#!/usr/bin/env python3
"""Prepare, run, and summarize a pinned local CMOS5L axpe experiment.

The large PDK and LibreLane checkouts live under build/asic. Each candidate
gets its own export and runs directory; this tool never replaces a run tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import tt_axpe


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build" / "asic"
DEFAULT_LOCK = ROOT / "asic" / "axpe" / "flow-lock-25ns.json"
DEFAULT_PROFILE = ROOT / "configs" / "tt-axpe-6x4-25ns.json"
DEFAULT_WORKDIR = BUILD / "tt-axpe-25ns"
FOSSI_CACHE = "https://nix-cache.fossi-foundation.org"
FOSSI_KEY = "nix-cache.fossi-foundation.org:3+K59iFwXqKsL7BNu6Guy0v+uTlwsxYQxjspXzqLYQs="


class FlowError(Exception):
    pass


def absolute(path: Path) -> Path:
    return path.resolve()


def require_workdir(path: Path) -> Path:
    path = absolute(path)
    if path == BUILD or BUILD not in path.parents:
        raise FlowError(f"flow workspace must be a child of {BUILD}: {path}")
    return path


def git_head(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False)
    if result.returncode:
        raise FlowError(f"not a Git checkout: {path}: {result.stderr.strip()}")
    return result.stdout.strip()


def require_commit(path: Path, expected: str, label: str) -> None:
    actual = git_head(path)
    if actual != expected:
        raise FlowError(f"{label} commit mismatch: expected {expected}, found {actual}")
    dirty = subprocess.run(
        ["git", "-C", str(path), "diff", "--quiet", "HEAD", "--"],
        check=False)
    if dirty.returncode:
        raise FlowError(f"{label} has modified tracked files: {path}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inputs(args: argparse.Namespace) -> tuple[Path, Path, Path, dict[str, Any]]:
    workdir = require_workdir(args.workdir)
    lock_path = absolute(args.flow_lock)
    profile = absolute(args.profile)
    lock = tt_axpe.read_json(lock_path)
    if profile != (ROOT / lock["candidate"]["profile"]).resolve():
        raise FlowError("selected profile does not match the flow lock candidate")
    tt_axpe.validate_lock(lock)
    if not profile.is_file():
        raise FlowError(f"profile is missing: {profile}")
    return workdir, lock_path, profile, lock


def validate_export(workdir: Path, lock_path: Path, profile: Path,
                    lock: dict[str, Any]) -> None:
    marker = workdir / tt_axpe.MARKER
    if not marker.is_file():
        raise FlowError(f"unmarked or missing flow workspace: {workdir}")
    manifest = tt_axpe.read_json(marker)
    expected = {
        "profile": str(profile.relative_to(ROOT)),
        "profile_sha256": sha256(profile),
        "flow_lock_sha256": sha256(lock_path),
        "clock_period_ns": lock["candidate"]["clock_period_ns"],
        "io_delay_ns": lock["candidate"].get("io_delay_ns"),
        "cts_sink_clustering_size": lock["candidate"].get("cts_sink_clustering_size"),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise FlowError(f"stale export {marker}: {key} is not {value!r}")
    resolved = tt_axpe.configure.resolved_config(profile)
    component = resolved["components"]["pemu"]
    originals = {
        f"src/{Path(name).name}": tt_axpe.configure.resolve_source(component, name)
        for name in component.get("sources", [])
    }
    originals["src/axpe_isa.svh"] = ROOT / "sw/pemu/isa/axpe_isa.svh"
    originals["src/tt_um_shubhgau_atomix_axpe.sv"] = (
        ROOT / "asic/axpe/src/tt_um_shubhgau_atomix_axpe.sv")
    if set(manifest.get("sources", {})) != set(originals):
        raise FlowError(f"stale export {marker}: source list changed")
    for name, source in originals.items():
        digest = manifest["sources"][name]
        if not source.is_file() or sha256(source) != digest:
            raise FlowError(f"stale export {marker}: source changed: {source}")
        if not (workdir / name).is_file() or sha256(workdir / name) != digest:
            raise FlowError(f"export source changed: {workdir / name}")
    merged = workdir / "src" / "config_merged.json"
    if merged.is_file():
        config = tt_axpe.read_json(merged)
        if config.get("CLOCK_PERIOD") != expected["clock_period_ns"]:
            raise FlowError(f"{merged}: clock period disagrees with the lock")
        io_delay = expected["io_delay_ns"]
        if io_delay is not None:
            actual_delay = (config.get("IO_DELAY_CONSTRAINT", -1) *
                            config["CLOCK_PERIOD"] / 100)
            if abs(actual_delay - io_delay) > 1e-9:
                raise FlowError(f"{merged}: I/O delay disagrees with the lock")
        if config.get("CTS_SINK_CLUSTERING_SIZE") != expected["cts_sink_clustering_size"]:
            raise FlowError(f"{merged}: CTS sink-cluster size disagrees with the lock")


def prepare(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    workdir, lock_path, profile, lock = inputs(args)
    if workdir.exists():
        validate_export(workdir, lock_path, profile, lock)
    else:
        tt_axpe.export(profile, workdir, lock_path)

    support = workdir / "tt"
    if not support.exists():
        source = absolute(args.support_tools_source)
        if source.is_dir():
            require_commit(source, lock["flow"]["support_tools_commit"],
                           "support tools")
            support.symlink_to(source, target_is_directory=True)
        else:
            repository = lock["flow"]["support_tools_repository"]
            url = (repository if "://" in repository else
                   f"https://github.com/{repository}.git")
            subprocess.run(["git", "clone", url, str(support)], check=True)
            subprocess.run(["git", "-C", str(support), "checkout",
                            lock["flow"]["support_tools_commit"]], check=True)
    require_commit(support, lock["flow"]["support_tools_commit"], "support tools")

    merged = workdir / "src" / "config_merged.json"
    if not merged.is_file():
        # Keep the virtualenv symlink path: resolving it to the base interpreter
        # drops the virtualenv site-packages used by tt_tool.
        python = args.venv_python.absolute()
        if not python.is_file():
            raise FlowError(f"Tiny Tapeout virtualenv Python is missing: {python}")
        env = os.environ.copy()
        env["PATH"] = str(python.parent) + os.pathsep + env.get("PATH", "")
        subprocess.run([str(python), "tt/tt_tool.py", "--ihp",
                        "--create-user-config"], cwd=workdir, env=env, check=True)
    validate_export(workdir, lock_path, profile, lock)
    print(f"prepared {workdir} ({lock['candidate']['clock_period_ns']} ns, "
          f"{lock['candidate'].get('io_delay_ns')} ns I/O delay)")
    return workdir, lock


def require_toolchain(args: argparse.Namespace, lock: dict[str, Any]) -> None:
    require_commit(absolute(args.pdk_root), lock["flow"]["pdk_commit"], "PDK")
    librelane = absolute(args.librelane_source)
    expected = lock["flow"].get("librelane_source_commit")
    if expected is not None:
        require_commit(librelane, expected, "LibreLane")
    if not (librelane / "shell.nix").is_file():
        raise FlowError(f"LibreLane shell.nix is missing: {librelane}")
    portable = absolute(args.nix_portable)
    if not portable.is_file():
        raise FlowError(f"nix-portable is missing: {portable}")
    expected_hash = lock["flow"].get("nix_portable_sha256")
    if expected_hash is not None and sha256(portable) != expected_hash:
        raise FlowError(f"nix-portable SHA-256 mismatch: {portable}")


def summarize(workdir: Path, tag: str, lock: dict[str, Any]) -> dict[str, Any]:
    run_dir = workdir / "runs" / tag
    metrics_path = run_dir / "final" / "metrics.json"
    if not metrics_path.is_file():
        raise FlowError(f"post-route metrics are not available: {metrics_path}")
    metrics = tt_axpe.read_json(metrics_path)
    export_manifest = tt_axpe.read_json(workdir / tt_axpe.MARKER)
    required = ("design__instance__count__stdcell",
                "design__instance__area__stdcell", "design__core__area",
                "route__drc_errors", "antenna__violating__nets",
                "antenna__violating__pins",
                "timing__setup__ws__corner:nom_slow_1p08V_125C",
                "timing__setup_vio__count__corner:nom_slow_1p08V_125C")
    missing = [key for key in required if key not in metrics]
    if missing:
        raise FlowError(f"{metrics_path}: not a complete post-route report: {missing}")
    corners = {}
    for corner in ("nom_fast_1p32V_m40C", "nom_typ_1p20V_25C",
                   "nom_slow_1p08V_125C"):
        suffix = f"__corner:{corner}"
        corners[corner] = {
            "setup_worst_slack_ns": metrics.get("timing__setup__ws" + suffix),
            "setup_violations": metrics.get("timing__setup_vio__count" + suffix),
            "hold_worst_slack_ns": metrics.get("timing__hold__ws" + suffix),
            "hold_violations": metrics.get("timing__hold_vio__count" + suffix),
            "max_slew_violations": metrics.get("design__max_slew_violation__count" + suffix),
            "max_fanout_violations": metrics.get("design__max_fanout_violation__count" + suffix),
        }
    result = {
        "schema": "org.atomix.tt-axpe-flow-summary.v1",
        "candidate": lock["candidate"],
        "flow": lock["flow"],
        "export_manifest_sha256": sha256(workdir / tt_axpe.MARKER),
        "flow_lock_sha256": export_manifest["flow_lock_sha256"],
        "merged_config_sha256": sha256(workdir / "src/config_merged.json"),
        "metrics_sha256": sha256(metrics_path),
        "run": tag,
        "standard_cells": metrics.get("design__instance__count__stdcell"),
        "standard_cell_area_um2": metrics.get("design__instance__area__stdcell"),
        "core_area_um2": metrics.get("design__core__area"),
        "routing_drc_errors": metrics.get("route__drc_errors"),
        "antenna_net_violations": metrics.get("antenna__violating__nets"),
        "antenna_pin_violations": metrics.get("antenna__violating__pins"),
        "corners": corners,
    }
    summary = run_dir / "summary.json"
    summary.write_text(json.dumps(result, indent=2) + "\n")
    print(f"summary {summary}: route DRC={result['routing_drc_errors']}, "
          f"slow setup={corners['nom_slow_1p08V_125C']['setup_worst_slack_ns']} ns")
    return result


def status(workdir: Path, tag: str) -> None:
    run_dir = workdir / "runs" / tag
    if not run_dir.is_dir():
        raise FlowError(f"run does not exist: {run_dir}")
    steps = sorted(path for path in run_dir.iterdir()
                   if path.is_dir() and re.match(r"^\d+-", path.name))
    completed = [path for path in steps if (path / "state_out.json").is_file()]
    print(f"{tag}: {len(completed)} completed steps; "
          f"latest={steps[-1].name if steps else 'none'}; "
          f"last complete={completed[-1].name if completed else 'none'}")
    if (run_dir / "final" / "metrics.json").is_file():
        print(f"{tag}: final metrics available; use summarize for bounded results")


def latest_state(workdir: Path, tag: str) -> Path:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", tag) is None:
        raise FlowError(f"invalid resume run tag: {tag!r}")
    run_dir = workdir / "runs" / tag
    if not run_dir.is_dir():
        raise FlowError(f"resume run does not exist: {run_dir}")
    states = sorted(run_dir.glob("[0-9]*-*/state_out.json"))
    if not states:
        raise FlowError(f"no completed checkpoint in {run_dir}")
    return states[-1]


def run(args: argparse.Namespace) -> None:
    workdir, lock = prepare(args)
    require_toolchain(args, lock)
    tag = args.tag
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", tag) is None:
        raise FlowError(f"invalid run tag: {tag!r}")
    run_dir = workdir / "runs" / tag
    if run_dir.exists():
        raise FlowError(f"refusing to replace existing run: {run_dir}")
    portable = absolute(args.nix_portable)
    librelane = absolute(args.librelane_source)
    pdk_root = absolute(args.pdk_root)
    flow_command = [
        "python", "-m", "librelane", "--pdk-root", str(pdk_root),
        "--pdk", lock["flow"]["pdk"], "--manual-pdk",
        "--run-tag", tag, "--force-run-dir", f"runs/{tag}",
        "-c", f"OPENROAD_THREADS={args.threads}",
    ]
    if args.initial_state or args.resume_from_tag:
        state = (absolute(args.initial_state) if args.initial_state else
                 latest_state(workdir, args.resume_from_tag))
        if not state.is_file():
            raise FlowError(f"initial state is missing: {state}")
        flow_command += ["-i", str(state)]
    if args.from_step:
        flow_command += ["--from", args.from_step]
    if not args.full:
        flow_command += ["--to", "OpenROAD.STAPostPNR"]
    flow_command.append("src/config_merged.json")
    run_dir.mkdir(parents=True)
    inner = "PDK_ROOT=" + shlex.quote(str(pdk_root)) + " " + shlex.join(flow_command)
    command = [
        str(portable), "nix-shell", str(librelane / "shell.nix"),
        "--option", "extra-substituters", FOSSI_CACHE,
        "--option", "extra-trusted-public-keys", FOSSI_KEY,
        "--run", inner,
    ]
    env = os.environ.copy()
    env["NP_LOCATION"] = str(absolute(args.nix_state))
    log_path = workdir / f"{tag}.console.log"
    print(f"running {tag} in {workdir}; console: {log_path}", flush=True)
    with log_path.open("w") as log:
        completed = subprocess.run(command, cwd=workdir, env=env,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   check=False)
    if completed.returncode:
        raise FlowError(f"LibreLane exited {completed.returncode}; see {log_path}")
    summarize(workdir, tag, lock)


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "status", "summarize"))
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--flow-lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    parser.add_argument("--support-tools-source", type=Path,
                        default=BUILD / "tt-axpe-flow" / "tt")
    parser.add_argument("--venv-python", type=Path,
                        default=BUILD / "tt-flow-venv" / "bin" / "python")
    parser.add_argument("--pdk-root", type=Path, default=BUILD / "pdk-cmos5l")
    parser.add_argument("--librelane-source", type=Path,
                        default=BUILD / "librelane-src")
    parser.add_argument("--nix-portable", type=Path, default=BUILD / "nix-portable")
    parser.add_argument("--nix-state", type=Path,
                        default=BUILD / "nix-portable-state")
    parser.add_argument("--tag", default="pe10-25ns")
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--initial-state", type=Path)
    parser.add_argument("--resume-from-tag",
                        help="use the last completed state from this run tag")
    parser.add_argument("--from", dest="from_step")
    parser.add_argument("--full", action="store_true",
                        help="continue through GDS, DRC and LVS instead of stopping at post-route STA")
    args = parser.parse_args()
    try:
        if args.threads < 1 or args.threads > 64:
            raise FlowError("--threads must be between 1 and 64")
        if args.initial_state and args.resume_from_tag:
            raise FlowError("choose --initial-state or --resume-from-tag, not both")
        if args.resume_from_tag and not args.from_step:
            raise FlowError("--resume-from-tag requires --from")
        if args.command == "run":
            run(args)
        else:
            workdir, lock_path, profile, lock = inputs(args)
            if args.command == "prepare":
                prepare(args)
            else:
                validate_export(workdir, lock_path, profile, lock)
                if args.command == "status":
                    status(workdir, args.tag)
                else:
                    summarize(workdir, args.tag, lock)
    except (FlowError, tt_axpe.ExportError, subprocess.CalledProcessError,
            KeyError, ValueError) as exc:
        print(f"tt axpe flow: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()
