#!/usr/bin/env python3
"""Run the accepted core-timing SAT jobs from a relocated candidate package."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yosys", default=os.environ.get("YOSYS", "yosys"))
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument(
        "--induction-only",
        action="store_true",
        help="rerun induction only; does not repeat witness and mutation checks",
    )
    args = parser.parse_args()
    if not 1 <= args.timeout_seconds <= 3600:
        parser.error("timeout must be 1..3600 seconds per job")
    subprocess.run([sys.executable, str(ROOT / "verification/check_package.py")], check=True)
    manifest = json.loads((ROOT / ".atomix-candidate.json").read_text())
    proof = manifest.get("timing_proof")
    if not proof:
        parser.error("this package contains no completed core timing proof")
    build = ROOT / "demo/build"
    build.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="formal-", dir=build))
    record = {
        "scope": "induction only" if args.induction_only else "induction, witnesses and mutations",
        "status": "running",
        "jobs": [],
    }
    try:
        for job in proof["jobs"]:
            if args.induction_only and job["kind"] != "induction":
                continue
            script = ROOT / job["path"]
            if hashlib.sha256(script.read_bytes()).hexdigest() != job["sha256"]:
                raise ValueError(f"SAT job changed: {script}")
            log = output / (
                "-".join(script.relative_to(ROOT / "verification/formal").parts) + ".log"
            )
            with log.open("w") as stream:
                result = subprocess.run(
                    [args.yosys, "-Q", "-T", "-s", str(script)],
                    cwd=ROOT,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=args.timeout_seconds,
                )
            text = log.read_text()
            expected = {
                "induction": "Induction step proven: SUCCESS!",
                "cover": "SAT solving finished - model found:",
                "counterexample": "model found for base case: FAIL!",
            }[job["kind"]]
            correct_exit = (
                result.returncode != 0
                if job["kind"] == "counterexample"
                else result.returncode == 0
            )
            if not correct_exit or expected not in text:
                raise ValueError(f"formal job failed its expected outcome: {log}")
            record["jobs"].append(
                {
                    "job": job["path"],
                    "kind": job["kind"],
                    "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
                }
            )
            print(f"PASS {job['path']} ({job['kind']})", flush=True)
        subprocess.run([sys.executable, str(ROOT / "verification/check_package.py")], check=True)
        record["yosys"] = subprocess.check_output([args.yosys, "-V"], text=True).strip()
        record["status"] = "passed"
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        record["status"] = "failed"
        record["failure"] = str(exc)
        raise
    finally:
        (output / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"axpe packaged timing proof: PASS; {output}")


if __name__ == "__main__":
    main()
