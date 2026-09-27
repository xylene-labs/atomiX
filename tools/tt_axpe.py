#!/usr/bin/env python3
"""Build a reproducible Tiny Tapeout axpe repository from source inputs.

The official template stays byte-for-byte pristine under asic/tt-axpe.  This
tool verifies that baseline, resolves the component profile, and combines both
with the small axpe-specific overlay.  Generated flow trees belong under build/
and carry a marker before this tool will replace them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

import configure


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "asic" / "tt-axpe"
OVERLAY = ROOT / "asic" / "axpe"
DEFAULT_PROFILE = ROOT / "configs" / "tt-axpe-6x4.json"
DEFAULT_OUTPUT = ROOT / "build" / "asic" / "tt-axpe-export"
DEFAULT_LOCK = OVERLAY / "flow-lock.json"
MARKER = ".atomix-export.json"


class ExportError(Exception):
    pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ExportError(f"{path}: expected a JSON object")
    return value


def canonical_tree_hash(root: Path) -> str:
    """Hash relative name, Unix permission bits and bytes of every file."""
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        mode = stat.S_IMODE(path.stat().st_mode)
        relative = path.relative_to(root).as_posix()
        digest.update(f"{mode:o} {relative}\0".encode())
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_overlay_file(staging: Path, relative: str) -> None:
    source = OVERLAY / relative
    destination = staging / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def component_parameters(resolved: dict[str, Any], kind: str) -> dict[str, int]:
    component = resolved["components"][kind]
    given = resolved["parameters"].get(kind, {})
    return {
        name: given.get(name, spec["default"])
        for name, spec in sorted(component.get("parameters", {}).items())
    }


def profile_defines(resolved: dict[str, Any], kind: str) -> list[str]:
    component = resolved["components"][kind]
    values = component_parameters(resolved, kind)
    return [
        f"{spec['define']}={values[name]}"
        for name, spec in sorted(component.get("parameters", {}).items())
        if not (values[name] == 0 and spec.get("omit_when_zero"))
    ]


def validate_lock(lock: dict[str, Any]) -> None:
    try:
        expected = lock["template"]["canonical_sha256"]
        candidate = lock["candidate"]
    except KeyError as exc:
        raise ExportError(f"flow lock is missing {exc}") from exc
    actual = canonical_tree_hash(TEMPLATE)
    if actual != expected:
        raise ExportError(
            "official template baseline drifted: "
            f"expected {expected}, found {actual}")
    period = candidate.get("clock_period_ns")
    if (candidate.get("tiles") != "6x4" or isinstance(period, bool) or
            not isinstance(period, (int, float)) or not 5 <= period <= 1000):
        raise ExportError("flow lock must declare a 6x4 candidate and a 5..1000 ns clock period")
    io_delay = candidate.get("io_delay_ns")
    if io_delay is not None and (isinstance(io_delay, bool) or
                                 not isinstance(io_delay, (int, float)) or
                                 not 0 <= io_delay < period):
        raise ExportError("flow lock io_delay_ns must be nonnegative and less than the clock period")
    cts_size = candidate.get("cts_sink_clustering_size")
    if cts_size is not None and (isinstance(cts_size, bool) or
                                 not isinstance(cts_size, int) or
                                 not 1 <= cts_size <= 64):
        raise ExportError("flow lock cts_sink_clustering_size must be 1..64")


def populate(staging: Path, profile: Path, lock: dict[str, Any],
             lock_path: Path) -> dict[str, Any]:
    shutil.copytree(TEMPLATE, staging)

    resolved = configure.resolved_config(profile)
    if set(resolved["components"]) != {"pemu"}:
        raise ExportError(f"{profile}: ASIC profile must select only a pemu component")
    component = resolved["components"]["pemu"]
    if component["id"] != "pemu.axpe":
        raise ExportError(f"{profile}: expected pemu.axpe, found {component['id']}")

    parameters = component_parameters(resolved, "pemu")
    defines = profile_defines(resolved, "pemu")
    locked_profile = (ROOT / lock["candidate"]["profile"]).resolve()
    if profile.resolve() == locked_profile and parameters["imem_words"] != 64:
        raise ExportError("the locked early-flow profile must use 64 instruction words")

    # Replace every template file that describes or tests the example project.
    for relative in (
        "README.md", "info.yaml", "docs/info.md", "src/tt_um_shubhgau_atomix_axpe.sv",
        ".github/workflows/gds.yaml", ".github/workflows/test.yaml",
        "test/Makefile", "test/tb.v", "test/test.py",
    ):
        copy_overlay_file(staging, relative)
    (staging / "src" / "project.v").unlink()

    template_config = read_json(TEMPLATE / "src" / "config.json")
    template_config.update(read_json(OVERLAY / "src" / "config.json"))
    settings = resolved["settings"]
    period = settings.get("asic_clock_period_ns", template_config["CLOCK_PERIOD"])
    if "asic_clock_period_ns" in settings:
        configure.check_setting(profile, "asic_clock_period_ns", period)
    if period != lock["candidate"]["clock_period_ns"]:
        raise ExportError(
            f"{profile}: clock period {period} ns disagrees with flow lock "
            f"{lock['candidate']['clock_period_ns']} ns")
    template_config["CLOCK_PERIOD"] = period
    io_delay = lock["candidate"].get("io_delay_ns")
    if io_delay is not None:
        # LibreLane's base SDC interprets this as a percentage. Keep the
        # declared I/O budget absolute when the profile clock changes.
        template_config["IO_DELAY_CONSTRAINT"] = 100 * io_delay / period
    cts_size = settings.get("asic_cts_sink_clustering_size")
    if cts_size != lock["candidate"].get("cts_sink_clustering_size"):
        raise ExportError(f"{profile}: CTS sink-cluster size disagrees with flow lock")
    if cts_size is not None:
        configure.check_setting(profile, "asic_cts_sink_clustering_size", cts_size)
        template_config["CTS_SINK_CLUSTERING_SIZE"] = cts_size
    template_config["VERILOG_DEFINES"] = defines
    (staging / "src" / "config.json").write_text(
        json.dumps(template_config, indent=2) + "\n")

    source_hashes: dict[str, str] = {}
    seen_names = {"tt_um_shubhgau_atomix_axpe.sv"}
    for source_name in component.get("sources", []):
        source = configure.resolve_source(component, source_name).resolve()
        if not source.is_file():
            raise ExportError(f"component source is missing: {source}")
        if source.name in seen_names:
            raise ExportError(f"source basename collision in export: {source.name}")
        seen_names.add(source.name)
        destination = staging / "src" / source.name
        shutil.copy2(source, destination)
        source_hashes[f"src/{source.name}"] = file_hash(destination)

    # axpe_isa.svh is generated from the normative ISA JSON and included by
    # axpe.sv; it is not a compilation unit, so it deliberately does not
    # appear in the component's `sources` or Tiny Tapeout's `source_files`.
    # It must still be present beside the RTL in a standalone export.
    isa_include = ROOT / "sw" / "pemu" / "isa" / "axpe_isa.svh"
    isa_destination = staging / "src" / isa_include.name
    shutil.copy2(isa_include, isa_destination)
    source_hashes[f"src/{isa_include.name}"] = file_hash(isa_destination)

    info_text = (staging / "info.yaml").read_text()
    for source_name in sorted(seen_names):
        if f'- "{source_name}"' not in info_text:
            raise ExportError(f"info.yaml does not list exported source {source_name}")

    (staging / "test" / "profile.mk").write_text(
        "# Generated by tools/tt_axpe.py; do not edit.\n"
        + "PROFILE_DEFINES := "
        + " ".join(f"-D{item}" for item in defines)
        + "\n")

    source_hashes["src/tt_um_shubhgau_atomix_axpe.sv"] = file_hash(
        staging / "src" / "tt_um_shubhgau_atomix_axpe.sv")
    manifest = {
        "schema": "org.atomix.tt-export.v1",
        "profile": str(profile.resolve().relative_to(ROOT)),
        "component": component["id"],
        "parameters": parameters,
        "defines": defines,
        "profile_sha256": file_hash(profile),
        "flow_lock_sha256": file_hash(lock_path),
        "clock_period_ns": period,
        "io_delay_ns": io_delay,
        "cts_sink_clustering_size": cts_size,
        "template_canonical_sha256": canonical_tree_hash(TEMPLATE),
        "sources": dict(sorted(source_hashes.items())),
    }
    (staging / MARKER).write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def safe_replace(staging: Path, output: Path) -> None:
    if output.exists():
        if not (output / MARKER).is_file():
            raise ExportError(
                f"refusing to replace unmarked output directory: {output}")
        runs = output / "runs"
        if runs.exists() or runs.is_symlink():
            raise ExportError(
                f"refusing to replace flow workspace with a runs directory: {output}")
        shutil.rmtree(output)
    staging.rename(output)


def export(profile: Path, output: Path,
           lock_path: Path = DEFAULT_LOCK) -> dict[str, Any]:
    lock_path = lock_path.resolve()
    lock = read_json(lock_path)
    validate_lock(lock)
    output = output.resolve()
    profile = profile.resolve()
    sources = (TEMPLATE.resolve(), OVERLAY.resolve())
    root = ROOT.resolve()
    if (output == root or output in root.parents or
            any(output == path or output in path.parents or path in output.parents
                for path in sources)):
        raise ExportError(f"refusing unsafe output path: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".tt-axpe-", dir=output.parent) as temporary:
        staging = Path(temporary) / "export"
        manifest = populate(staging, profile, lock, lock_path)
        safe_replace(staging, output)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("export", "check"))
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--flow-lock", type=Path, default=DEFAULT_LOCK)
    args = parser.parse_args()
    try:
        manifest = export(args.profile, args.output, args.flow_lock)
        if args.command == "check":
            # A second export proves replacement is limited to our marker and
            # that generated bytes are deterministic.
            first = canonical_tree_hash(args.output.resolve())
            export(args.profile, args.output, args.flow_lock)
            second = canonical_tree_hash(args.output.resolve())
            if first != second:
                raise ExportError("two identical exports produced different trees")
            # A hardening run may add a large `runs/` tree beneath an export.
            # Never let a later verification/export command erase it.
            runs = args.output.resolve() / "runs"
            runs.mkdir()
            try:
                try:
                    export(args.profile, args.output, args.flow_lock)
                except ExportError as exc:
                    if "flow workspace" not in str(exc):
                        raise
                else:
                    raise ExportError("export replaced a flow workspace")
            finally:
                runs.rmdir()
        print(
            f"tt axpe {args.command}: PASS: {args.output.resolve()} "
            f"({manifest['parameters']['imem_words']} words)")
        return 0
    except (ExportError, configure.ConfigError) as exc:
        print(f"tt axpe {args.command}: FAIL: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
