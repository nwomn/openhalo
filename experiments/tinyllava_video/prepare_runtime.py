"""Create an inference-only copy of the pinned upstream source on Jetson."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

SOURCE_REVISION = "44e162fa0ce6ea5f166cbfc6c1130465f82fd81a"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    revision = subprocess.check_output(
        ["git", "-C", str(args.source), "rev-parse", "HEAD"], text=True).strip()
    if revision != SOURCE_REVISION:
        raise ValueError(f"unexpected source revision: {revision}")
    if args.output.exists():
        raise FileExistsError("Use a fresh runtime directory; do not overwrite experiments")
    shutil.copytree(args.source / "tinyllava", args.output / "tinyllava")
    # Upstream eager imports require training-only deepspeed/PEFT and video
    # dataset dependencies. Keep actual model, connector, prompt and processor.
    (args.output / "tinyllava/utils/__init__.py").write_text(
        "from .constants import *\nfrom .import_module import *\n"
        "from .message import *\nfrom .eval_utils import *\n", encoding="utf-8")
    (args.output / "tinyllava/data/__init__.py").write_text(
        "from .template import *\nfrom .text_preprocess import *\n"
        "from .video_preprocess import *\n", encoding="utf-8")
    (args.output / "runtime-manifest.json").write_text(json.dumps({
        "source_revision": revision,
        "changes": ["omit eager training/dataset imports"],
        "model_math": "upstream; optional frame microbatching occurs in benchmark wrapper",
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
