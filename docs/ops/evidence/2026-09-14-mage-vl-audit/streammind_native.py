#!/usr/bin/env python3
"""Feed MP4, RTSP or HLS into the native llama.cpp StreamMind runtime.

FFmpeg and codec-video-prep only decode/rearrange pixels. Mage-ViT, Mamba EPFE,
the gate classifier, and optional language generation stay in native llama.cpp.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import resource
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("source", help="local video, RTSP URL, HLS URL, or other FFmpeg input")
    p.add_argument("--runner", required=True, type=Path)
    p.add_argument("--backbone", required=True, type=Path)
    p.add_argument("--mmproj", required=True, type=Path)
    p.add_argument("--epfe", required=True, type=Path)
    p.add_argument("--classifier", required=True, type=Path)
    p.add_argument("--packer", type=Path, default=Path(__file__).with_name("pack_mage_codec.py"))
    p.add_argument("--codec-prep", default="codec-video-prep")
    p.add_argument("--incremental-producer", type=Path,
                   help="use continuous readiness producer instead of transport MP4 segments")
    p.add_argument("--sample-fps", type=float, default=8.0)
    p.add_argument("--min-group-frames", type=int, default=8)
    p.add_argument("--readiness-threshold", type=float, default=25000.0)
    p.add_argument("--segment-seconds", type=float, default=4.0)
    p.add_argument("--max-pixels", type=int, default=1024 * 1024)
    p.add_argument("--sampled-frames", type=int, default=32)
    # codec-video-prep currently gains little from decoder parallelism and its
    # libavcodec path can SIGBUS under repeated segmented-video loads at >1.
    # Keep the safe default; advanced users may benchmark a larger value.
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("--vulkan-device", default="0")
    p.add_argument("--keep-workdir", action="store_true")
    p.add_argument("--startup-timeout", type=float, default=30.0)
    p.add_argument("--rtsp-transport", choices=("tcp", "udp"), default="tcp")
    p.add_argument("--realtime", action="store_true", help="pace local files at their native rate")
    p.add_argument("--prompt", default="", help="generate a response when StreamMind triggers")
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--max-tokens", type=int, default=128)
    p.add_argument("--interval-segments", type=int, default=0,
                   help="also generate periodically; 0 disables periodic generation")
    p.add_argument("--drop-stale", action=argparse.BooleanOptionalAction, default=True,
                   help="drop closed transport segments when the consumer falls behind")
    p.add_argument("--max-pending-segments", type=int, default=1,
                   help="maximum closed segments retained before stale ones are dropped")
    return p.parse_args()


def run_checked(command: list[str], timeout: float | None = None) -> None:
    def enlarge_stack() -> None:
        soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
        target = min(hard, 64 * 1024 * 1024) if hard != resource.RLIM_INFINITY else 64 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_STACK, (max(soft, target), hard))
    result = subprocess.run(command, text=True, capture_output=True, timeout=timeout,
                            preexec_fn=enlarge_stack)
    if result.returncode:
        detail = result.stderr or result.stdout or "no child-process diagnostics"
        raise RuntimeError(f"command exited {result.returncode}: {command!r}\n{detail[-4000:]}")


def complete_file(path: Path) -> bool:
    """A segment is consumable once its size is unchanged across two polls."""
    try:
        first = path.stat().st_size
        if first <= 0:
            return False
        time.sleep(0.08)
        return path.stat().st_size == first
    except FileNotFoundError:
        return False


def duration(path: Path) -> float:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ], text=True, capture_output=True)
    try:
        return float(result.stdout.strip()) if result.returncode == 0 else 0.0
    except ValueError:
        return 0.0


def video_info(path: Path) -> dict:
    result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate", "-of", "json", str(path)],
        text=True, capture_output=True)
    try:
        stream = json.loads(result.stdout)["streams"][0]
        numerator, denominator = map(float, stream.get("avg_frame_rate", "0/1").split("/"))
        return {"source_width": int(stream["width"]), "source_height": int(stream["height"]),
                "source_fps": numerator / denominator if denominator else 0}
    except (ValueError, KeyError, IndexError, json.JSONDecodeError):
        return {"source_width": 0, "source_height": 0, "source_fps": 0}


def emit_runner_line(line: str, stream_started: float,
                     submitted: dict[int, dict] | None = None) -> dict | None:
    """Forward native JSON while attaching observable transport latency."""
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        print(line, end="", flush=True)
        return None
    elapsed = time.monotonic() - stream_started
    if "event" not in payload:
        payload["stream_elapsed_seconds"] = elapsed
    if payload.get("event") in {"response", "suppressed"} and submitted is not None:
        segment = int(payload.get("segment", -1))
        metadata = submitted.pop(segment, {})
        payload.update({key: metadata[key] for key in (
            "preprocess_seconds", "source_duration_seconds", "source_end_seconds",
            "submitted_elapsed_seconds", "pending_segments", "source_width", "source_height",
            "source_fps", "readiness_stop_reason", "sampled_frames") if key in metadata})
        payload["stream_elapsed_seconds"] = elapsed
        source_end = float(metadata.get("source_end_seconds", 0))
        payload["live_delay_seconds"] = max(0.0, elapsed - source_end)
        payload["segment_rtf"] = ((elapsed - float(metadata.get("segment_started_elapsed", elapsed))) /
                                  max(0.001, float(metadata.get("source_duration_seconds", 0.001))))
    print(json.dumps(payload, separators=(",", ":")), flush=True)
    return payload


def prepare(segment: Path, output: Path, asset: Path, args: argparse.Namespace) -> None:
    decoder_threads = max(1, args.threads)
    command = [
        args.codec_prep, "--video", str(segment), "--out_dir", str(asset),
        "--num_sampled_frames", str(args.sampled_frames),
        "--grouping_mode", "readiness", "--group_size", "32",
        "--images_per_group", "4", "--patch", "16",
        "--max_pixels", str(args.max_pixels), "--readiness_sum_threshold", "0",
        "--min_group_frames", "8", "--max_group_frames", "64",
        "--avoid_keyframes", "--canvas_format", "jpg",
        "--thread_count", str(decoder_threads),
    ]
    # A newly closed fragmented MP4 can briefly race filesystem visibility on
    # network/overlay filesystems. Retry once from a clean output directory.
    # On SIGBUS (-7), also fall back to one decoder worker; this avoids a known
    # libavcodec failure without hiding persistent corrupt-input errors.
    try:
        run_checked(command)
    except RuntimeError as error:
        shutil.rmtree(asset, ignore_errors=True)
        time.sleep(0.2)
        if "command exited -7:" in str(error):
            command[-1] = "1"
        run_checked(command)
    run_checked([sys.executable, str(args.packer), str(asset), str(output)], 120)


def incremental_main(args: argparse.Namespace) -> int:
    """Connect a continuous readiness producer to the persistent native runner."""
    work = Path(tempfile.mkdtemp(prefix="mage-streammind-live-"))
    env = os.environ.copy()
    env["GGML_VK_VISIBLE_DEVICES"] = args.vulkan_device
    env["STREAMMIND_PROMPT"] = args.prompt
    env["STREAMMIND_THRESHOLD"] = str(args.threshold)
    env["STREAMMIND_MAX_TOKENS"] = str(args.max_tokens)
    env["STREAMMIND_INTERVAL_SEGMENTS"] = str(args.interval_segments)
    runner = subprocess.Popen(
        [str(args.runner), str(args.backbone), str(args.mmproj), str(args.epfe),
         str(args.classifier), "-"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr,
        text=True, bufsize=1, env=env,
    )
    assert runner.stdin and runner.stdout
    output_lines: queue.Queue[str | None] = queue.Queue()
    def read_runner() -> None:
        for line in runner.stdout:
            output_lines.put(line)
        output_lines.put(None)
    threading.Thread(target=read_runner, daemon=True).start()
    deadline = time.monotonic() + args.startup_timeout
    while time.monotonic() < deadline:
        try:
            line = output_lines.get(timeout=0.2)
        except queue.Empty:
            if runner.poll() is not None:
                raise RuntimeError(f"native runner exited with {runner.returncode}")
            continue
        if line is None:
            raise RuntimeError("native runner closed before readiness")
        payload = emit_runner_line(line, time.monotonic())
        if payload and payload.get("event") == "ready":
            break
    else:
        raise RuntimeError("native runner did not become ready")

    producer_command = [
        sys.executable, str(args.incremental_producer), args.source,
        "--output-dir", str(work), "--sample-fps", str(args.sample_fps),
        "--max-pixels", str(args.max_pixels),
        "--min-group-frames", str(args.min_group_frames),
        "--max-group-frames", str(max(args.min_group_frames, args.sampled_frames)),
        "--readiness-threshold", str(args.readiness_threshold),
        "--rtsp-transport", args.rtsp_transport,
    ]
    if args.realtime:
        producer_command.append("--realtime")
    producer = subprocess.Popen(producer_command, stdout=subprocess.PIPE,
                                stderr=sys.stderr, text=True, bufsize=1)
    assert producer.stdout
    stream_started = time.monotonic()
    submitted: dict[int, dict] = {}
    try:
        for producer_line in producer.stdout:
            event = json.loads(producer_line)
            if event.get("event") != "readiness_group":
                continue
            segment = int(event["group"])
            source_start = float(event["start_seconds"])
            source_end = float(event["end_seconds"])
            submitted[segment] = {
                "source_duration_seconds": source_end - source_start,
                "source_end_seconds": source_end,
                "submitted_elapsed_seconds": time.monotonic() - stream_started,
                "segment_started_elapsed": time.monotonic() - stream_started,
                "pending_segments": 0,
                "readiness_stop_reason": event.get("stop_reason"),
                "sampled_frames": int(event.get("frames", 0)),
            }
            runner.stdin.write(str(event["path"]) + "\n")
            runner.stdin.flush()
            print(json.dumps({"event": "group_submitted", "segment": segment,
                              **submitted[segment]}, separators=(",", ":")), flush=True)
            # Preserve ordering and bounded memory: one adaptive group in flight.
            while segment in submitted:
                line = output_lines.get(timeout=max(1.0, args.startup_timeout))
                if line is None:
                    raise RuntimeError("native runner closed during stream")
                emit_runner_line(line, stream_started, submitted)
            Path(event["path"]).unlink(missing_ok=True)
        producer_code = producer.wait()
        runner.stdin.close()
        runner_code = runner.wait()
        if producer_code or runner_code:
            raise RuntimeError(f"live pipeline exited producer={producer_code} runner={runner_code}")
        return 0
    finally:
        for process in (producer, runner):
            if process.poll() is None:
                process.terminate()
        if not args.keep_workdir:
            shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    args = arguments()
    if args.incremental_producer:
        return incremental_main(args)
    if args.segment_seconds <= 0:
        raise ValueError("--segment-seconds must be positive")
    if args.max_pending_segments < 1:
        raise ValueError("--max-pending-segments must be positive")
    work = Path(tempfile.mkdtemp(prefix="mage-streammind-"))
    segments = work / "segments"
    segments.mkdir()
    env = os.environ.copy()
    env["GGML_VK_VISIBLE_DEVICES"] = args.vulkan_device
    env["STREAMMIND_PROMPT"] = args.prompt
    env["STREAMMIND_THRESHOLD"] = str(args.threshold)
    env["STREAMMIND_MAX_TOKENS"] = str(args.max_tokens)
    env["STREAMMIND_INTERVAL_SEGMENTS"] = str(args.interval_segments)
    runner = subprocess.Popen(
        [str(args.runner), str(args.backbone), str(args.mmproj), str(args.epfe),
         str(args.classifier), "-"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr,
        text=True, bufsize=1, env=env,
    )
    # Reset timestamps in each transport segment. StreamMind continuity is held
    # by EPFE state, while each JSON row also carries a global timeline_index.
    input_options: list[str] = []
    if args.source.lower().startswith("rtsp://"):
        input_options += ["-rtsp_transport", args.rtsp_transport]
    if args.source.lower().startswith(("http://", "https://")):
        input_options += ["-re", "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_on_network_error", "1",
                          "-reconnect_on_http_error", "4xx,5xx", "-reconnect_delay_max", "5"]
    if args.realtime and not args.source.lower().startswith(("rtsp://", "http://", "https://")):
        input_options += ["-re"]
    ffmpeg_command = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "warning", *input_options, "-i", args.source,
        "-map", "0:v:0", "-an", "-c:v", "libx264", "-preset", "veryfast",
        "-tune", "zerolatency", "-pix_fmt", "yuv420p", "-force_key_frames",
        f"expr:gte(t,n_forced*{args.segment_seconds})", "-f", "segment",
        "-segment_time", str(args.segment_seconds), "-reset_timestamps", "1",
        str(segments / "%09d.mp4"),
    ]
    ffmpeg: subprocess.Popen | None = None
    processed: set[Path] = set()
    submitted: dict[int, dict] = {}
    submission_index = 0
    dropped_segments = 0
    process_started = time.monotonic()
    stream_started = process_started
    assert runner.stdout and runner.stdin
    output_lines: queue.Queue[str | None] = queue.Queue()

    def read_runner() -> None:
        for output_line in runner.stdout:
            output_lines.put(output_line)
        output_lines.put(None)

    threading.Thread(target=read_runner, daemon=True).start()

    def drain_runner(wait: float = 0.0) -> None:
        first = True
        while True:
            try:
                line = output_lines.get(timeout=wait if first else 0)
            except queue.Empty:
                return
            first = False
            if line is None:
                return
            emit_runner_line(line, stream_started, submitted)
    try:
        deadline = time.monotonic() + args.startup_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("native StreamMind runner did not become ready")
            try:
                line = output_lines.get(timeout=min(0.2, remaining))
            except queue.Empty:
                if runner.poll() is not None:
                    raise RuntimeError(f"native StreamMind runner exited with {runner.returncode}")
                continue
            if line is not None:
                payload = emit_runner_line(line, stream_started, submitted)
                try:
                    if payload and payload.get("event") == "ready":
                        print(json.dumps({"event": "runner_ready",
                                          "startup_seconds": time.monotonic() - process_started}),
                              flush=True)
                        break
                except json.JSONDecodeError:
                    pass
        # Transport latency starts when capture starts, not while the models
        # are loading. Cold-start remains available in runner_ready above.
        stream_started = time.monotonic()
        ffmpeg = subprocess.Popen(ffmpeg_command)
        while True:
            candidates = sorted(segments.glob("*.mp4"))
            # FFmpeg is still writing the last visible file. When it exits, the
            # last file also becomes eligible.
            eligible = candidates if ffmpeg.poll() is not None else candidates[:-1]
            pending = [item for item in eligible if item not in processed]
            if args.drop_stale and len(pending) > args.max_pending_segments:
                stale = pending[:-args.max_pending_segments]
                for segment in stale:
                    index = int(segment.stem)
                    processed.add(segment)
                    segment.unlink(missing_ok=True)
                    dropped_segments += 1
                    print(json.dumps({"event": "segment_dropped", "segment": index,
                                      "reason": "stale_backlog", "dropped_segments": dropped_segments,
                                      "pending_segments": len(pending)}), flush=True)
            for segment in eligible:
                if segment in processed or not complete_file(segment):
                    continue
                # codec-video-prep requires enough frames to form a readiness
                # group. A tiny EOF tail carries no useful standalone window.
                if duration(segment) < 0.5:
                    print(json.dumps({"event": "segment_skipped", "segment": segment.name,
                                      "reason": "short_eof_tail"}), flush=True)
                    processed.add(segment)
                    segment.unlink(missing_ok=True)
                    continue
                asset = work / f"codec-{segment.stem}"
                bundle = work / f"{segment.stem}.mcv"
                started = time.monotonic()
                segment_index = int(segment.stem)
                segment_duration = duration(segment)
                dimensions = video_info(segment)
                prepare(segment, bundle, asset, args)
                runner.stdin.write(str(bundle) + "\n")
                runner.stdin.flush()
                processed.add(segment)
                elapsed = time.monotonic() - stream_started
                metadata = {"preprocess_seconds": time.monotonic() - started,
                            "source_duration_seconds": segment_duration,
                            "source_end_seconds": (segment_index + 1) * args.segment_seconds,
                            "segment_started_elapsed": started - stream_started,
                            "submitted_elapsed_seconds": elapsed,
                            "pending_segments": len([item for item in eligible if item not in processed])}
                metadata.update(dimensions)
                submitted[submission_index] = metadata
                submission_index += 1
                print(json.dumps({"event": "segment_submitted", "segment": segment.name,
                                  **metadata, "stream_elapsed_seconds": elapsed,
                                  "dropped_segments": dropped_segments}), flush=True)
                shutil.rmtree(asset, ignore_errors=True)
                segment.unlink(missing_ok=True)
                # Bound producer lead. The runner emits one or more rows per
                # submitted segment; draining stdout here prevents pipe growth
                # and naturally slows FFmpeg/file ingestion when inference is
                # behind real time.
                drain_runner()
            drain_runner(0.1)
            if runner.poll() is not None:
                raise RuntimeError(f"native StreamMind runner exited with {runner.returncode}")
            if ffmpeg.poll() is not None and not set(segments.glob("*.mp4")) - processed:
                break
        runner.stdin.close()
        code = ffmpeg.returncode or runner.wait()
        drain_runner()
        print(json.dumps({"event": "stream_complete",
                          "wall_seconds": time.monotonic() - stream_started,
                          "dropped_segments": dropped_segments}), flush=True)
        return code
    finally:
        if ffmpeg is not None and ffmpeg.poll() is None:
            ffmpeg.terminate()
        if runner.poll() is None:
            runner.terminate()
        if args.keep_workdir:
            print(f"workdir={work}", file=sys.stderr)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
