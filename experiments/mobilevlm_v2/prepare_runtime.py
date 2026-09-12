"""Prepare an isolated copy; preserve the upstream model and parameter layout."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

REVISION = "688fdec914810485c8766da96c63d9d2ce15f750"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    revision = subprocess.check_output(["git", "-C", str(a.source), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION or a.output.exists():
        raise ValueError("Require the pinned source and a fresh output directory")
    shutil.copytree(a.source / "mobilevlm", a.output / "mobilevlm")
    path = a.output / "mobilevlm/model/vision_encoder.py"
    src = path.read_text()
    old = "CLIPVisionModel.from_pretrained(self.vision_tower_name)  # dummy-load"
    if src.count(old) != 1:
        raise ValueError("Unexpected upstream dummy-load implementation")
    path.write_text(src.replace(old, "CLIPVisionModel(self.cfg_only)  # outer V2 checkpoint supplies weights"))
    (a.output / "runtime-manifest.json").write_text(json.dumps({
        "source_revision": revision,
        "changes": ["Construct dummy vision tower from config; require complete outer checkpoint key match"],
        "model_math": "unchanged upstream FP16 inference",
    }, indent=2))


if __name__ == "__main__":
    main()
