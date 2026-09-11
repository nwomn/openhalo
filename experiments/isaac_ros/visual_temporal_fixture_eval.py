"""Validate temporal features against known multi-person TensorRT fixtures."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import time
from typing import Any

import cv2
import numpy as np

from temporal_features import TemporalTracker
from visual_features import VisualFeatureEngine
from visual_live import _infer_with_geometry


FIXTURES = (
    {
        "name": "ultralytics_bus",
        "path": "/home/jetson/ultralytics/bus.jpg",
        "expected_person_count": 4,
        "object_labels": ("person", "bus", "tie"),
    },
    {
        "name": "ultralytics_zidane",
        "path": "/home/jetson/ultralytics/assets/zidane.jpg",
        "expected_person_count": 2,
        "object_labels": ("person", "bus", "tie"),
    },
)


def _jitter_detections(
    detections: list[dict[str, Any]], sample_index: int
) -> list[dict[str, Any]]:
    shift = 0.003 if sample_index % 2 else -0.003
    result: list[dict[str, Any]] = []
    for detection in detections:
        item = copy.deepcopy(detection)
        x1, y1, x2, y2 = item["bbox"]
        item["bbox"] = [
            max(0.0, min(1.0, x1 + shift)),
            max(0.0, min(1.0, y1)),
            max(0.0, min(1.0, x2 + shift)),
            max(0.0, min(1.0, y2)),
        ]
        result.append(item)
    return result


def _jitter_pose(keypoints: np.ndarray, sample_index: int) -> np.ndarray:
    output = np.asarray(keypoints, dtype=np.float32).copy()
    output[:, 0] += 2.0 if sample_index % 2 else -2.0
    return output


def _pose_items(engine: VisualFeatureEngine, keypoints: np.ndarray, sample_index: int) -> list[dict[str, Any]]:
    return [
        {
            "keypoints": _jitter_pose(item, sample_index),
            "posture": engine._posture(item),
        }
        for item in keypoints
    ]


def _run_fixture(
    engine: VisualFeatureEngine,
    fixture: dict[str, Any],
    *,
    repeats: int,
    dropout_start: int,
    dropout_length: int,
    max_lost_seconds: float,
) -> dict[str, Any]:
    frame = cv2.imread(fixture["path"])
    if frame is None:
        return {"name": fixture["name"], "passed": False, "error": "image_not_found"}
    result, _, keypoints = _infer_with_geometry(engine, frame)
    regions = {
        "left": (0.0, 0.0, 0.333, 1.0),
        "center": (0.333, 0.0, 0.667, 1.0),
        "right": (0.667, 0.0, 1.0, 1.0),
    }
    tracker = TemporalTracker(
        regions=regions,
        window_seconds=1.0,
        max_distance=0.22,
        max_lost_seconds=max_lost_seconds,
    )
    last_detections: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    for sample_index in range(repeats):
        timestamp = sample_index * 0.1
        dropout = dropout_start <= sample_index < dropout_start + dropout_length
        detections = _jitter_detections(result["detections"], sample_index)
        if dropout:
            detections = [item for item in detections if item["label"] != "person"]
            pose_items: list[dict[str, Any]] = []
        else:
            pose_items = _pose_items(engine, keypoints, sample_index)
        snapshot = tracker.update(
            detections,
            timestamp,
            pose_items=pose_items,
            frame_size=(int(frame.shape[1]), int(frame.shape[0])),
        )
        snapshots.append(
            {
                "sample_index": sample_index,
                "dropout": dropout,
                "person_track_ids": [
                    track["track_id"]
                    for track in snapshot["tracks"]
                    if track["label"] == "person"
                ],
                "person_states": [
                    {
                        "track_id": track["track_id"],
                        "status": track["status"],
                        "motion": track["motion"],
                        "region": track["region"],
                        "pose": track["pose"],
                        "relationships": track["relationships"],
                    }
                    for track in snapshot["tracks"]
                    if track["label"] == "person"
                ],
                "window": snapshot["window"],
            }
        )
        if not dropout:
            last_detections = detections

    report = tracker.report((repeats - 1) * 0.1)
    before = [
        track["track_id"]
        for track in tracker.snapshot((repeats - 1) * 0.1)["tracks"]
        if track["label"] == "person"
    ]
    tracker.update([], repeats * 0.1 + max_lost_seconds + 0.2)
    after_snapshot = tracker.update(last_detections, repeats * 0.1 + max_lost_seconds + 0.3)
    after = [
        track["track_id"]
        for track in after_snapshot["tracks"]
        if track["label"] == "person"
    ]
    real_ids = [
        track_id
        for snapshot in snapshots
        for track_id in snapshot["person_track_ids"]
        if not snapshot["dropout"]
    ]
    unique_real_ids = sorted(set(real_ids))
    expected_count = int(fixture["expected_person_count"])
    passed = (
        result["person_count"] == expected_count
        and report["unique_person_tracks"] == expected_count
        and report["reacquired_tracks"] >= expected_count
        and len(unique_real_ids) == expected_count
        and bool(before and after and not set(before) & set(after))
    )
    return {
        "name": fixture["name"],
        "path": fixture["path"],
        "passed": passed,
        "expected_person_count": expected_count,
        "observed_person_count": result["person_count"],
        "observed_object_counts": result["object_counts"],
        "unique_person_track_ids": unique_real_ids,
        "repeats": repeats,
        "dropout": {"start": dropout_start, "length": dropout_length},
        "tracking": report,
        "long_gap": {
            "previous_ids": before,
            "new_ids": after,
            "new_id_after_long_gap": bool(before and after and not set(before) & set(after)),
        },
        "sample_tail": snapshots[-3:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detector", default="/home/jetson/ultralytics/yolo26n.engine")
    parser.add_argument("--pose-model", default="/home/jetson/ultralytics/yolo26n-pose.engine")
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--repeats", type=int, default=12)
    parser.add_argument("--dropout-start", type=int, default=4)
    parser.add_argument("--dropout-length", type=int, default=2)
    parser.add_argument("--max-lost-seconds", type=float, default=0.8)
    parser.add_argument("--output", type=Path, default=Path("visual-temporal-fixtures.json"))
    args = parser.parse_args()

    labels = tuple(sorted({label for fixture in FIXTURES for label in fixture["object_labels"]}))
    engine = VisualFeatureEngine(
        detector_path=args.detector,
        pose_path=args.pose_model,
        confidence=args.confidence,
        image_size=args.image_size,
        regions={
            "left": (0.0, 0.0, 0.333, 1.0),
            "center": (0.333, 0.0, 0.667, 1.0),
            "right": (0.667, 0.0, 1.0, 1.0),
        },
        object_labels=labels,
        use_pose=True,
    )
    first_frame = cv2.imread(FIXTURES[0]["path"])
    if first_frame is None:
        report = {"passed": False, "error": "fixture_not_found"}
    else:
        engine.warmup(first_frame)
        started = time.perf_counter()
        results = [
            _run_fixture(
                engine,
                fixture,
                repeats=args.repeats,
                dropout_start=args.dropout_start,
                dropout_length=args.dropout_length,
                max_lost_seconds=args.max_lost_seconds,
            )
            for fixture in FIXTURES
        ]
        report = {
            "schema_version": "openhalo.isaac_ros.visual_temporal_fixture.v1",
            "detector": args.detector,
            "pose_model": args.pose_model,
            "repeats": args.repeats,
            "results": results,
            "passed": bool(results) and all(item["passed"] for item in results),
            "wall_s": round(time.perf_counter() - started, 3),
            "limitations": [
                "Repeated known-image geometry validates tracker behavior, not camera-domain tracking accuracy.",
                "Forced dropout is a tracker robustness probe, not physical occlusion accuracy.",
                "No raw frames are written by this evaluator.",
            ],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report: {args.output}")
    return 0 if report.get("passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
