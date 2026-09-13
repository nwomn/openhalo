"""Inspect the actual installed vLLM decoder and HF video processor, without an LLM."""
import argparse
import hashlib
import json
from pathlib import Path

import torch
from PIL import Image, ImageDraw
from transformers import AutoProcessor
from transformers.video_utils import VideoMetadata
from vllm.multimodal.video import OpenCVVideoBackend


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/work"))
    args = parser.parse_args()
    directory = args.root / "private/cases-v1"
    processor = AutoProcessor.from_pretrained(args.root / "assets/model", local_files_only=True)
    rows = []
    for case in json.loads((directory / "cases.json").read_text()):
        # Manifest contains host paths; the same private root is mounted at /work.
        path = directory / (case["id"] + ".mp4")
        data = path.read_bytes()
        frames, metadata = OpenCVVideoBackend.load_bytes(data, num_frames=12, fps=4)
        clean_metadata = {k: v for k, v in metadata.items() if k != "do_sample_frames"}
        with torch.inference_mode():
            processed = processor.video_processor(
                videos=[frames], video_metadata=[VideoMetadata(**clean_metadata)],
                do_sample_frames=False, return_tensors="pt")
        grid = processed["video_grid_thw"][0].tolist()
        indices = list(metadata["frames_indices"])
        if len(indices) % 2:
            indices.append(indices[-1])
        timestamps = [(indices[i] + indices[i + 1]) / (2 * metadata["fps"])
                      for i in range(0, len(indices), 2)]
        assert len(timestamps) == grid[0], (case["id"], grid, timestamps)
        row = dict(id=case["id"], sha256=hashlib.sha256(data).hexdigest(),
                   decoded_shape=list(frames.shape), metadata=metadata,
                   grid_thw=grid, pair_timestamps_s=timestamps)
        rows.append(row)
        canvas = Image.new("RGB", (4 * 320, 3 * 200), "white")
        draw = ImageDraw.Draw(canvas)
        for i, frame in enumerate(frames):
            x, y = (i % 4) * 320, (i // 4) * 200
            canvas.paste(Image.fromarray(frame).resize((320, 180)), (x, y))
            draw.text((x + 4, y + 182), f'{metadata["frames_indices"][i] / metadata["fps"]:.2f}s', fill="black")
        canvas.save(directory / (case["id"] + "-sampled.jpg"))
        print(json.dumps(row), flush=True)
    (directory / "input-check.json").write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
