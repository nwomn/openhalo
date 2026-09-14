#!/usr/bin/env python3
"""Continuous StreamMind canvas producer for FFmpeg-compatible live inputs.

Unlike the compatibility path this process never creates transport MP4 files.
One FFmpeg demux/decode session stays open, sampled BGR frames are scored
incrementally, and each closed readiness group is emitted as a MAGECV1 bundle.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from codec_selector.core.frame_ops import resolve_prepared_frame_geometry
from codec_selector.plugins.selectors.topk_2x2_bitcost import process_group_topk_2x2

from incremental_readiness import IncrementalReadiness, ReadyGroup
from pack_mage_codec import MAGIC, block_order


def probe(source: str) -> tuple[int, int]:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", source,
    ], text=True, capture_output=True, timeout=30, check=True)
    stream = json.loads(result.stdout)["streams"][0]
    return int(stream["width"]), int(stream["height"])


def change_score(frame: np.ndarray, previous: np.ndarray | None) -> np.ndarray:
    """Open temporal residual proxy for codec bit-cost readiness.

    It intentionally uses only decoded pixels, so it works for cameras, HLS,
    pipes and every codec supported by the system FFmpeg. The first frame is an
    anchor and receives a zero residual, just like the reference selector which
    excludes the first frame from readiness candidates.
    """
    if previous is None:
        return np.zeros(frame.shape[:2], dtype=np.float32)
    current = frame.astype(np.int16, copy=False)
    old = previous.astype(np.int16, copy=False)
    return np.abs(current - old).mean(axis=2, dtype=np.float32)


def write_bundle(group: ReadyGroup, output: Path, sample_fps: float, group_index: int) -> None:
    meta, _mask, canvases, patch_pos, src_pos, _ptr = process_group_topk_2x2(
        group_idx=group_index,
        group_frame_ids=list(group.frame_ids),
        group_frames_bgr=[item.copy() for item in group.frames_bgr],
        group_scores=[item.copy() for item in group.score_maps],
        images_per_group=4,
        patch=16,
        block_size=2,
        group_block_scores=[item.copy() for item in group.block_scores],
    )
    height, width = canvases.shape[1:3]
    grid_w = width // 16
    patches_per_canvas = (height // 16) * grid_w
    raster = np.empty_like(src_pos)
    indices = (patch_pos[:, 0].astype(np.int64) * patches_per_canvas
               + patch_pos[:, 1].astype(np.int64) * grid_w
               + patch_pos[:, 2].astype(np.int64))
    raster[indices] = src_pos
    encoded: list[bytes] = []
    ordered: list[np.ndarray] = []
    for index, canvas in enumerate(canvases):
        positions = raster[index * patches_per_canvas:(index + 1) * patches_per_canvas]
        # The selector should fill all four canvases for a valid readiness group.
        if not np.all(positions[:, 0] >= 0):
            raise RuntimeError("readiness group produced a partially padded canvas")
        buffer = io.BytesIO()
        Image.fromarray(canvas).save(buffer, format="JPEG", quality=95)
        encoded.append(buffer.getvalue())
        ordered.append(block_order(positions, height, width))
    positions = np.concatenate(ordered).astype("<i4", copy=False)
    header = MAGIC + struct.pack("<fIII", float(sample_fps), len(encoded), len(positions), 0)
    temporary = output.with_suffix(".tmp")
    with temporary.open("wb") as handle:
        handle.write(header)
        handle.write(positions.tobytes(order="C"))
        for jpeg in encoded:
            handle.write(struct.pack("<I", len(jpeg)))
            handle.write(jpeg)
    temporary.replace(output)
    print(json.dumps({
        "event": "readiness_group", "path": str(output), "group": group_index,
        "frames": len(group.frame_ids), "start_seconds": group.frame_ids[0] / sample_fps,
        "end_seconds": (group.frame_ids[-1] + 1) / sample_fps,
        "stop_reason": group.stop_reason, "readiness": group.readiness,
        "selector": meta,
    }, separators=(",", ":")), flush=True)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--sample-fps", type=float, default=8.0)
    parser.add_argument("--max-pixels", type=int, default=1024 * 1024)
    parser.add_argument("--min-group-frames", type=int, default=8)
    parser.add_argument("--max-group-frames", type=int, default=32)
    parser.add_argument("--readiness-threshold", type=float, default=25000.0)
    parser.add_argument("--reference-close", action="store_true",
                        help="wait for reference low-gain close instead of low-latency first readiness")
    parser.add_argument("--rtsp-transport", choices=("tcp", "udp"), default="tcp")
    parser.add_argument("--realtime", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    if not math.isfinite(args.sample_fps) or args.sample_fps <= 0:
        raise ValueError("sample-fps must be positive")
    width, height = probe(args.source)
    resize_h, resize_w, pad_bottom, pad_right, out_h, out_w = resolve_prepared_frame_geometry(
        height, width, patch=16, max_dim=max(width, height), block_size=2,
        max_pixels=args.max_pixels,
    )
    options: list[str] = []
    if args.source.lower().startswith("rtsp://"):
        options += ["-rtsp_transport", args.rtsp_transport]
    if args.realtime and not args.source.lower().startswith(("rtsp://", "http://", "https://")):
        options += ["-re"]
    vf = (f"fps={args.sample_fps},scale={resize_w}:{resize_h}:flags=bilinear,"
          f"pad={out_w}:{out_h}:0:0:black")
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "warning", *options,
               "-i", args.source, "-map", "0:v:0", "-an", "-vf", vf,
               "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1"]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    state = IncrementalReadiness(
        patch=16, images_per_group=4, min_group_frames=args.min_group_frames,
        max_group_frames=args.max_group_frames, threshold=args.readiness_threshold,
        eager=not args.reference_close,
    )
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    assert process.stdout
    frame_bytes = out_h * out_w * 3
    previous = None
    frame_id = group_index = 0
    try:
        while data := process.stdout.read(frame_bytes):
            if len(data) != frame_bytes:
                raise RuntimeError(f"truncated raw frame: {len(data)}/{frame_bytes}")
            frame = np.frombuffer(data, dtype=np.uint8).reshape(out_h, out_w, 3).copy()
            score = change_score(frame, previous)
            previous = frame
            group = state.push(frame_id, frame, score)
            frame_id += 1
            if group:
                write_bundle(group, args.output_dir / f"{group_index:09d}.mcv",
                             args.sample_fps, group_index)
                group_index += 1
        if group := state.flush():
            write_bundle(group, args.output_dir / f"{group_index:09d}.mcv",
                         args.sample_fps, group_index)
    finally:
        if process.poll() is None:
            process.terminate()
    return process.wait()


if __name__ == "__main__":
    sys.exit(main())
