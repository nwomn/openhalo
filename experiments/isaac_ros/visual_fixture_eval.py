"""Run deterministic known-image sanity fixtures for the visual feature stack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

import cv2

from visual_features import VisualFeatureEngine
from visual_features import _feature_snapshot


FIXTURES = (
    {
        "name": "ultralytics_bus",
        "path": "/home/jetson/ultralytics/bus.jpg",
        "expected_object_counts": {"person": 4, "bus": 1},
        "minimum_pose_person_count": 1,
    },
    {
        "name": "ultralytics_zidane",
        "path": "/home/jetson/ultralytics/assets/zidane.jpg",
        "expected_object_counts": {"person": 2, "tie": 1},
        "minimum_pose_person_count": 1,
    },
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detector", default="/home/jetson/ultralytics/yolo26n.engine")
    parser.add_argument("--pose-model", default="/home/jetson/ultralytics/yolo26n-pose.engine")
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--output", type=Path, default=Path("fixture-report.json"))
    args = parser.parse_args()

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
        object_labels=("person", "bus", "stop sign", "tie"),
        use_pose=True,
    )
    results: list[dict[str, Any]] = []
    warmed_up = False
    for fixture in FIXTURES:
        frame = cv2.imread(fixture["path"])
        if frame is None:
            results.append(
                {
                    "name": fixture["name"],
                    "path": fixture["path"],
                    "passed": False,
                    "error": "image_not_found",
                }
            )
            continue
        if not warmed_up:
            engine.warmup(frame)
            warmed_up = True
        started = time.perf_counter()
        actual = engine.infer(frame)
        observed = _feature_snapshot(actual)
        expected = fixture["expected_object_counts"]
        object_checks = {
            label: observed["object_counts"].get(label, 0) == count
            for label, count in expected.items()
        }
        pose_check = observed["pose_person_count"] >= fixture["minimum_pose_person_count"]
        results.append(
            {
                "name": fixture["name"],
                "path": fixture["path"],
                "passed": all(object_checks.values()) and pose_check,
                "expected_object_counts": expected,
                "observed_object_counts": observed["object_counts"],
                "object_checks": object_checks,
                "minimum_pose_person_count": fixture["minimum_pose_person_count"],
                "observed_pose_person_count": observed["pose_person_count"],
                "postures": observed["postures"],
                "body_coverage": observed["body_coverage"],
                "latency_ms": observed["latency_ms"],
                "wall_ms": round((time.perf_counter() - started) * 1000.0, 3),
            }
        )

    report = {
        "schema_version": "openhalo.isaac_ros.visual_fixture.v1",
        "detector": args.detector,
        "pose_model": args.pose_model,
        "confidence": args.confidence,
        "results": results,
        "passed": bool(results) and all(item["passed"] for item in results),
        "limitations": [
            "Known-image sanity only; this is not a camera-domain accuracy benchmark.",
            "Pose minimum-count checks do not measure keypoint AP or posture accuracy.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report: {args.output}")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
