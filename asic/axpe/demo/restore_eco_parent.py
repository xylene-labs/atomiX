#!/usr/bin/env python3
"""Restore the bundled pre-ECO checkpoint into a fresh atomiX build location."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PACKAGE = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atomix-root", type=Path, required=True)
    args = parser.parse_args()
    subprocess.run([sys.executable, str(PACKAGE / "verification/check_package.py")], check=True)
    manifest = json.loads((PACKAGE / ".atomix-candidate.json").read_text())
    evidence = json.loads((PACKAGE / "verification/candidate/physical-evidence.json").read_text())
    recipe = evidence["post_grt_max_wire_200_fanout_eco_trial"]["recipe_record"]
    root = args.atomix_root.resolve()
    if sha(root / "asic/axpe/experiments/wire200-fanout-eco.py") != recipe["recipe_sha256"]:
        raise ValueError("maintained ECO recipe differs from the accepted candidate")
    state_path = (root / recipe["parent_state"]).resolve()
    if not state_path.is_relative_to(root / "build/asic"):
        raise ValueError("checkpoint destination must stay under the atomiX build/asic directory")
    destination = state_path.parent
    if destination.exists():
        raise ValueError(f"refusing to replace existing checkpoint directory: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".eco-parent-", dir=destination.parent) as tmp:
        staging = Path(tmp) / "checkpoint"
        staging.mkdir()
        state = {"metrics": {}}
        for key, item in manifest["eco_parent"]["files"].items():
            source = PACKAGE / item["path"]
            if sha(source) != item["sha256"]:
                raise ValueError(f"checkpoint asset changed: {key}")
            shutil.copy2(source, staging / source.name)
            state[key] = str(destination / source.name)
        (staging / state_path.name).write_text(json.dumps(state, indent=2) + "\n")
        if destination.exists():
            raise ValueError("checkpoint destination appeared during restoration")
        staging.rename(destination)
    print(f"ECO parent restored with local paths and empty inherited metrics: {state_path}")


if __name__ == "__main__":
    main()
