"""Write one annotated preview frame from the OpenHalo Isaac ROS image topic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import threading
import time
from typing import Any

import cv2
import numpy as np
import rclpy

from visual_features import LatestImageNode
from visual_features import VisualFeatureEngine
from visual_features import _parse_regions
from visual_features import _terminate_process


SKELETON = (
    (0, 1),
    (0, 2),
    (1, 3),
    (2, 4),
    (5, 6),
    (5, 7),
    (7, 9),
    (6, 8),
    (8, 10),
    (5, 11),
    (6, 12),
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
)


def _draw_label(image: np.ndarray, text: str, origin: tuple[int, int], color: tuple[int, int, int]) -> None:
    x, y = origin
    cv2.putText(image, text, (x, max(18, y)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(image, text, (x, max(18, y)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)


def _draw_info(image: np.ndarray, lines: list[str]) -> None:
    height = 28 + 24 * len(lines)
    overlay = image.copy()
    cv2.rectangle(overlay, (0, 0), (image.shape[1], height), (15, 22, 30), -1)
    cv2.addWeighted(overlay, 0.82, image, 0.18, 0.0, image)
    for index, line in enumerate(lines):
        _draw_label(image, line, (14, 24 + index * 24), (235, 245, 250))


def _draw_regions(
    image: np.ndarray,
    regions: dict[str, tuple[float, float, float, float]],
    values: dict[str, dict[str, Any]],
) -> None:
    height, width = image.shape[:2]
    colors = {
        "occupied": (60, 220, 90),
        "clear": (170, 180, 190),
    }
    for name, (x1, y1, x2, y2) in regions.items():
        occupied = bool(values.get(name, {}).get("occupied"))
        count = int(values.get(name, {}).get("count", 0))
        point1 = (round(x1 * width), round(y1 * height))
        point2 = (round(x2 * width), round(y2 * height))
        state = "occupied" if occupied else "clear"
        color = colors[state]
        cv2.rectangle(image, point1, point2, color, 2)
        _draw_label(image, f"{name}: {state} ({count})", (point1[0] + 6, point1[1] + 24), color)


def _draw_detections(image: np.ndarray, result: Any, allowed: set[str], confidence: float) -> dict[str, int]:
    counts = {label: 0 for label in allowed}
    if result.boxes is None:
        return counts
    boxes = result.boxes.xyxy.detach().cpu().numpy()
    scores = result.boxes.conf.detach().cpu().numpy()
    classes = result.boxes.cls.detach().cpu().numpy().astype(int)
    for box, score, class_id in zip(boxes, scores, classes):
        label = str(result.names[int(class_id)])
        if label not in allowed or float(score) < confidence:
            continue
        counts[label] += 1
        x1, y1, x2, y2 = [round(float(value)) for value in box]
        color = (70, 220, 90) if label == "person" else (255, 175, 60)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        _draw_label(image, f"{label} {float(score):.2f}", (x1 + 4, y1 - 8), color)
    return counts


def _draw_pose(image: np.ndarray, keypoints: np.ndarray) -> None:
    for person in keypoints:
        visible = person[:, 2] >= 0.35
        for start, end in SKELETON:
            if not visible[start] or not visible[end]:
                continue
            start_point = tuple(round(float(value)) for value in person[start, :2])
            end_point = tuple(round(float(value)) for value in person[end, :2])
            cv2.line(image, start_point, end_point, (255, 210, 50), 2, cv2.LINE_AA)
        for point, is_visible in zip(person, visible):
            if is_visible:
                center = tuple(round(float(value)) for value in point[:2])
                cv2.circle(image, center, 4, (40, 230, 255), -1, cv2.LINE_AA)


def build_parser() -> argparse.ArgumentParser:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=here / "visual-preview.jpg")
    parser.add_argument("--image-topic", default="/left/image_raw")
    parser.add_argument("--launch-file", type=Path, default=here / "argus_imx219_mono.launch.py")
    parser.add_argument("--camera-info-url", default=f"file://{here / 'imx219_1280x720.yaml'}")
    parser.add_argument("--camera-id", default="0")
    parser.add_argument("--module-id", default="0")
    parser.add_argument("--mode", default="4")
    parser.add_argument("--framerate", default="60")
    parser.add_argument("--ros2", default="ros2")
    parser.add_argument("--detector", default="/home/jetson/ultralytics/yolo26n.engine")
    parser.add_argument("--pose-model", default="/home/jetson/ultralytics/yolo26n-pose.engine")
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--objects", default="person,laptop,chair,cup,cell phone,keyboard,mouse,couch,potted plant")
    parser.add_argument("--regions", default="left=0:0:0.333:1,center=0.333:0:0.667:1,right=0.667:0:1:1")
    parser.add_argument("--wait-seconds", type=float, default=12.0)
    parser.add_argument("--no-launch", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    regions = _parse_regions(args.regions)
    objects = tuple(dict.fromkeys(value.strip() for value in args.objects.split(",") if value.strip()))
    launch_process: subprocess.Popen[str] | None = None
    node: LatestImageNode | None = None
    spin_thread: threading.Thread | None = None
    error: str | None = None
    report: dict[str, Any] = {"schema_version": "openhalo.isaac_ros.visual_preview.v1"}
    try:
        if not args.no_launch:
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
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                text=True,
            )
        rclpy.init()
        node = LatestImageNode(args.image_topic)
        spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
        spin_thread.start()
        deadline = time.monotonic() + args.wait_seconds
        frame: np.ndarray | None = None
        stamp_ns = 0
        while time.monotonic() < deadline:
            frame, stamp_ns, _ = node.latest()
            if frame is not None:
                break
            time.sleep(0.01)
        if frame is None:
            raise RuntimeError("no ROS image arrived before timeout")

        engine = VisualFeatureEngine(
            detector_path=args.detector,
            pose_path=args.pose_model,
            confidence=args.confidence,
            image_size=args.image_size,
            regions=regions,
            object_labels=objects,
            use_pose=True,
        )
        engine.warmup(frame)
        frame, stamp_ns, _ = node.latest()
        assert frame is not None
        started = time.perf_counter()
        detection = engine.detector.predict(
            frame, device=0, imgsz=args.image_size, conf=args.confidence, verbose=False
        )[0]
        detector_ms = (time.perf_counter() - started) * 1000.0
        detections = engine._detections(detection, frame.shape[1], frame.shape[0])
        pose_started = time.perf_counter()
        pose_result = engine.pose.predict(
            frame, device=0, imgsz=args.image_size, conf=args.confidence, verbose=False
        )[0]
        pose_ms = (time.perf_counter() - pose_started) * 1000.0
        keypoints = (
            pose_result.keypoints.data.detach().cpu().numpy()
            if pose_result.keypoints is not None
            else np.empty((0, 17, 3), dtype=np.float32)
        )
        annotated = frame.copy()
        object_counts = _draw_detections(annotated, detection, set(objects), args.confidence)
        _draw_pose(annotated, keypoints)
        region_values = engine._regions(detections["persons"])
        _draw_regions(annotated, regions, region_values)
        postures = [engine._posture(person) for person in keypoints]
        coverage = [engine._body_coverage(int(np.count_nonzero(person[:, 2] >= 0.35))) for person in keypoints]
        posture = ",".join(postures) if postures else "none"
        coverage_text = ",".join(coverage) if coverage else "none"
        region_text = ", ".join(
            f"{name}={'on' if value['occupied'] else 'off'}" for name, value in region_values.items()
        )
        _draw_info(
            annotated,
            [
                "OpenHalo Isaac ROS visual preview",
                f"detector {detector_ms:.1f} ms | pose {pose_ms:.1f} ms | total {detector_ms + pose_ms:.1f} ms",
                f"objects: {', '.join(f'{name}={count}' for name, count in object_counts.items() if count) or 'none'}",
                f"pose: {posture} | coverage: {coverage_text} | regions: {region_text}",
            ],
        )
        if not cv2.imwrite(str(args.output), annotated, [cv2.IMWRITE_JPEG_QUALITY, 92]):
            raise RuntimeError(f"failed to write {args.output}")
        report.update(
            {
                "status": "ok",
                "output": str(args.output),
                "ros_stamp_ns": stamp_ns,
                "image_shape": [int(frame.shape[1]), int(frame.shape[0])],
                "object_counts": object_counts,
                "pose_person_count": int(len(keypoints)),
                "postures": postures,
                "body_coverage": coverage,
                "regions": region_values,
                "latency_ms": {
                    "detector": round(detector_ms, 3),
                    "pose": round(pose_ms, 3),
                    "total": round(detector_ms + pose_ms, 3),
                },
            }
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        report.update({"status": "error", "error": error})
    finally:
        if rclpy.ok():
            rclpy.shutdown()
        if spin_thread is not None:
            spin_thread.join(timeout=3.0)
        if node is not None:
            node.destroy_node()
        _terminate_process(launch_process)

    report_path = args.output.with_suffix(".json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report: {report_path}")
    return 0 if error is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
