"""Launch the isolated local-only vLLM probe inside the pinned Jetson image."""
import argparse
import json
import os
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/work"))
    parser.add_argument("--gpu-memory-utilization", default="0.65")
    parser.add_argument("--enforce-eager", action="store_true")
    args = parser.parse_args()
    command = [
        "vllm", "serve", str(args.root / "assets/model"),
        "--served-model-name", "embedl/Cosmos-Reason2-2B-W4A16-Edge2-FlashHead",
        "--host", "127.0.0.1", "--port", "18081",
        "--max-model-len", "8192", "--max-num-seqs", "1",
        "--gpu-memory-utilization", args.gpu_memory_utilization,
        "--dtype", "half", "--no-enable-prefix-caching",
        "--mm-processor-cache-gb", "0",
        "--limit-mm-per-prompt", json.dumps({
            "video": {"count": 1, "num_frames": 12, "width": 1280, "height": 720},
            "image": 0, "audio": 0}),
        "--media-io-kwargs", json.dumps({"video": {"num_frames": 12, "fps": 4}}),
        # The loader samples uniformly across each whole clip and retains original
        # frame indices/fps. Prevent HF from sampling the already sampled array.
        "--mm-processor-kwargs", json.dumps({"truncation": False, "do_sample_frames": False}),
    ]
    if args.enforce_eager:
        command.append("--enforce-eager")
    env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
               VLLM_VIDEO_LOADER_BACKEND="opencv")
    print(json.dumps({"command": command, "offline": True}), flush=True)
    subprocess.run(command, env=env, check=True)


if __name__ == "__main__":
    main()
