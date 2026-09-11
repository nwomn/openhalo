"""Run bounded tracking and temporal-feature validation on the Isaac ROS stream."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import threading
import time
from typing import Any

import rclpy

from temporal_features import TemporalTracker
from visual_features import LatestImageNode
from visual_features import TegrastatsCapture
from visual_features import VisualFeatureEngine
from visual_features import _feature_snapshot
from visual_features import _parse_regions
from visual_features import _terminate_process
from visual_live import _infer_with_geometry


def _pose_items(engine: VisualFeatureEngine, keypoints: Any) -> list[dict[str, Any]]:
    return [
        {"keypoints": item, "posture": engine._posture(item)}
        for item in keypoints
    ]


def _track_sample(snapshot: dict[str, Any]) -> dict[str, Any]:
    tracks = []
    for track in snapshot["tracks"]:
        tracks.append(
            {
                key: track[key]
                for key in (
                    "track_id",
                    "label",
                    "status",
                    "center",
                    "dwell_s",
                    "continuity",
                    "max_gap_s",
                    "reacquired",
                    "motion",
                    "region",
                    "pose",
                    "relationships",
                )
                if key in track
            }
        )
    return {
        "active_track_count": snapshot["active_track_count"],
        "active_person_count": snapshot["active_person_count"],
        "window": snapshot["window"],
        "tracks": tracks,
    }


def build_parser() -> argparse.ArgumentParser:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--image-topic", default="/left/image_raw")
    parser.add_argument("--ros2", default="ros2")
    parser.add_argument("--launch-file", type=Path, default=here / "argus_imx219_mono.launch.py")
    parser.add_argument("--camera-info-url", default=f"file://{here / 'imx219_1280x720.yaml'}")
    parser.add_argument("--camera-id", default="0")
    parser.add_argument("--module-id", default="0")
    parser.add_argument("--mode", default="4")
    parser.add_argument("--framerate", default="60")
    parser.add_argument("--detector", default="/home/jetson/ultralytics/yolo26n.engine")
    parser.add_argument("--pose-model", default="/home/jetson/ultralytics/yolo26n-pose.engine")
    parser.add_argument("--no-pose", action="store_true")
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument(
        "--objects",
        default="person,laptop,chair,cup,cell phone,keyboard,mouse,couch,potted plant",
    )
    parser.add_argument(
        "--regions",
        default="left=0:0:0.333:1,center=0.333:0:0.667:1,right=0.667:0:1:1",
    )
    parser.add_argument("--window-seconds", type=float, default=5.0)
    parser.add_argument("--track-max-distance", type=float, default=0.18)
    parser.add_argument("--max-lost-seconds", type=float, default=0.8)
    parser.add_argument(
        "--dropout-every",
        type=int,
        default=30,
        help="force a short person-detection dropout in the tracker-only probe",
    )
    parser.add_argument("--dropout-length", type=int, default=2)
    parser.add_argument("--wait-seconds", type=float, default=12.0)
    parser.add_argument("--case-name", default="live_temporal_camera_case")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=here / "results-visual-temporal",
    )
    parser.add_argument("--no-launch", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    regions = _parse_regions(args.regions)
    objects = tuple(dict.fromkeys(value.strip() for value in args.objects.split(",") if value.strip()))
    launch_process: subprocess.Popen[str] | None = None
    launch_log = args.output_dir / "launch.log"
    launch_handle = None
    stats = TegrastatsCapture(args.output_dir / "tegrastats.log")
    node: LatestImageNode | None = None
    spin_thread: threading.Thread | None = None
    rclpy_started = False
    engine: VisualFeatureEngine | None = None
    tracker: TemporalTracker | None = None
    dropout_tracker: TemporalTracker | None = None
    samples: list[dict[str, Any]] = []
    motion_states: Counter[str] = Counter()
    pose_change_samples = 0
    status = "ok"
    error_text: str | None = None
    last_sequence = -1
    last_detections: list[dict[str, Any]] = []
    last_timestamp_s: float | None = None
    warmup_complete = False
    process_start = time.monotonic()

    try:
        if not args.no_launch:
            launch_handle = launch_log.open("w", encoding="utf-8")
            launch_process = subprocess.Popen(
                [
                    args.ros2,
                    "launch",
                    str(args.launch_file),
                    f"camera_id:={args.camera_id}",
                    f"module_id:={args.module_id}",
                    f"mode:={args.mode}",
                    f"framerate:={args.framerate}",
                    f"camera_info_url:={args.camera_info_url}",
                ],
                stdout=launch_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                text=True,
            )
        rclpy.init()
        rclpy_started = True
        node = LatestImageNode(args.image_topic)
        spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
        spin_thread.start()

        deadline = time.monotonic() + args.wait_seconds
        first_frame = None
        while time.monotonic() < deadline:
            if launch_process is not None and launch_process.poll() is not None:
                raise RuntimeError("Isaac ROS launch exited before the first image")
            first_frame, _, _ = node.latest()
            if first_frame is not None:
                break
            time.sleep(0.02)
        if first_frame is None:
            raise RuntimeError("no ROS image arrived before timeout")

        engine = VisualFeatureEngine(
            detector_path=args.detector,
            pose_path=args.pose_model,
            confidence=args.confidence,
            image_size=args.image_size,
            regions=regions,
            object_labels=objects,
            use_pose=not args.no_pose,
        )
        engine.warmup(first_frame)
        tracker = TemporalTracker(
            regions=regions,
            window_seconds=args.window_seconds,
            max_distance=args.track_max_distance,
            max_lost_seconds=args.max_lost_seconds,
        )
        dropout_tracker = TemporalTracker(
            regions=regions,
            window_seconds=args.window_seconds,
            max_distance=args.track_max_distance,
            max_lost_seconds=args.max_lost_seconds,
        )
        warmup_complete = True
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline and rclpy.ok():
            if launch_process is not None and launch_process.poll() is not None:
                status = "launch_exited_early"
                break
            frame, stamp_ns, sequence = node.latest()
            if frame is None or sequence == last_sequence:
                time.sleep(0.005)
                continue
            last_sequence = sequence
            result, _, keypoints = _infer_with_geometry(engine, frame)
            timestamp_s = stamp_ns / 1_000_000_000.0 if stamp_ns else time.time()
            pose_items = _pose_items(engine, keypoints)
            temporal = tracker.update(
                result["detections"],
                timestamp_s,
                pose_items=pose_items,
                frame_size=(int(frame.shape[1]), int(frame.shape[0])),
            )
            for track in temporal["tracks"]:
                if track["label"] == "person":
                    motion_states[track["motion"]["state"]] += 1
                    if track["pose"]["change_state"] == "changing":
                        pose_change_samples += 1

            forced_dropout = (
                args.dropout_every > 0
                and len(samples) > 0
                and len(samples) % args.dropout_every in range(args.dropout_length)
            )
            probe_detections = [
                item
                for item in result["detections"]
                if not (forced_dropout and item["label"] == "person")
            ]
            probe_pose_items = [] if forced_dropout else pose_items
            probe_temporal = dropout_tracker.update(
                probe_detections,
                timestamp_s,
                pose_items=probe_pose_items,
                frame_size=(int(frame.shape[1]), int(frame.shape[0])),
            )
            samples.append(
                {
                    "sample_index": len(samples),
                    "ros_stamp_ns": stamp_ns,
                    "features": _feature_snapshot(result),
                    "temporal": _track_sample(temporal),
                    "synthetic_dropout": forced_dropout,
                    "synthetic_dropout_temporal": _track_sample(probe_temporal),
                }
            )
            last_detections = list(result["detections"])
            last_timestamp_s = timestamp_s
    except Exception as exc:
        status = "error"
        error_text = f"{type(exc).__name__}: {exc}"
    finally:
        observed_duration = time.monotonic() - process_start
        if rclpy_started and rclpy.ok():
            rclpy.shutdown()
        if spin_thread is not None:
            spin_thread.join(timeout=3.0)
        if node is not None:
            node.destroy_node()
        stats.stop()
        launch_exit_code = _terminate_process(launch_process)
        if launch_handle is not None:
            launch_handle.close()

    real_report = tracker.report(last_timestamp_s) if tracker is not None else {}
    synthetic_report = dropout_tracker.report(last_timestamp_s) if dropout_tracker is not None else {}
    long_gap_probe: dict[str, Any] = {"status": "not_run"}
    if dropout_tracker is not None and last_detections and last_timestamp_s is not None:
        before = [
            track["track_id"]
            for track in dropout_tracker.snapshot(last_timestamp_s)["tracks"]
            if track["label"] == "person"
        ]
        gap_timestamp = last_timestamp_s + args.max_lost_seconds + 0.2
        dropout_tracker.update([], gap_timestamp)
        after_snapshot = dropout_tracker.update(last_detections, gap_timestamp + 0.01)
        after = [
            track["track_id"]
            for track in after_snapshot["tracks"]
            if track["label"] == "person"
        ]
        long_gap_probe = {
            "status": "measured",
            "previous_person_track_ids": before,
            "new_person_track_ids": after,
            "new_id_after_long_gap": bool(before and after and not set(before) & set(after)),
            "gap_s": round(args.max_lost_seconds + 0.2, 3),
        }

    report = {
        "schema_version": "openhalo.isaac_ros.visual_temporal.v1",
        "created_at_epoch_s": round(time.time(), 3),
        "status": status,
        "error": error_text,
        "case": {
            "name": args.case_name,
            "raw_frames_retained": False,
            "synthetic_dropout_is_tracker_robustness": True,
            "accuracy_requires_owner_labeled_tracks": True,
        },
        "configuration": {
            "image_topic": args.image_topic,
            "sensor_mode": args.mode,
            "target_framerate": float(args.framerate),
            "detector": args.detector,
            "pose_model": None if args.no_pose else args.pose_model,
            "confidence": args.confidence,
            "image_size": args.image_size,
            "objects": list(objects),
            "regions": {name: list(bounds) for name, bounds in regions.items()},
            "window_seconds": args.window_seconds,
            "track_max_distance": args.track_max_distance,
            "max_lost_seconds": args.max_lost_seconds,
        },
        "stream": {
            "requested_duration_s": args.duration,
            "observed_duration_s": round(observed_duration, 3),
            "ros_images_received": node.received_count if node is not None else 0,
            "temporal_samples": len(samples),
            "temporal_rate_hz": round(len(samples) / observed_duration, 3)
            if observed_duration > 0
            else None,
            "encodings": sorted(node.encodings) if node is not None else [],
            "shapes": [list(shape) for shape in sorted(node.shapes)] if node is not None else [],
        },
        "temporal": {
            "real_camera": real_report,
            "synthetic_dropout_probe": {
                **synthetic_report,
                "forced_dropout_every": args.dropout_every,
                "forced_dropout_length": args.dropout_length,
                "long_gap": long_gap_probe,
            },
            "motion_state_samples": dict(motion_states),
            "pose_change_samples": pose_change_samples,
        },
        "resources": stats.summary(),
        "process": {
            "launch_exit_code": launch_exit_code,
            "launch_log": str(launch_log),
        },
        "samples": samples,
    }
    report_path = args.output_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "stream": report["stream"],
                "real_camera": real_report,
                "synthetic_dropout_probe": report["temporal"]["synthetic_dropout_probe"],
                "resources": report["resources"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"report: {report_path}")
    return 0 if status == "ok" and warmup_complete and len(samples) > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
