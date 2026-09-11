"""Bounded Jetson visual-feature validation for the OpenHalo Camera Edge.

This runner consumes the validated Argus ROS image topic, performs local
TensorRT detection and pose inference, and writes only structured feature and
benchmark data. It does not publish observations, retain frames, or connect to
Personal Runtime.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import threading
import time
from typing import Any

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from ultralytics import YOLO


RAM_RE = re.compile(r"RAM\s+(\d+)/(\d+)MB")
GR3D_RE = re.compile(r"GR3D_FREQ[^0-9]*(\d+)%")
TEMP_RE = re.compile(r"([A-Za-z0-9_]+)@(-?\d+(?:\.\d+)?)C")

POSE_KEYPOINT_NAMES = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=np.float64), percentile))


def _summary(values: list[float]) -> dict[str, float | None]:
    return {
        "count": len(values),
        "mean_ms": round(float(np.mean(values)), 3) if values else None,
        "p50_ms": round(_percentile(values, 50.0), 3)
        if _percentile(values, 50.0) is not None
        else None,
        "p95_ms": round(_percentile(values, 95.0), 3)
        if _percentile(values, 95.0) is not None
        else None,
        "max_ms": round(max(values), 3) if values else None,
    }


def _parse_regions(raw: str) -> dict[str, tuple[float, float, float, float]]:
    regions: dict[str, tuple[float, float, float, float]] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        name, separator, bounds = item.partition("=")
        if not separator:
            raise ValueError(f"region {item!r} must use name=x1:y1:x2:y2")
        values = tuple(float(value) for value in bounds.split(":"))
        if len(values) != 4:
            raise ValueError(f"region {name!r} must contain four values")
        x1, y1, x2, y2 = values
        if not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
            raise ValueError(f"region {name!r} must be ordered and normalized")
        regions[name.strip()] = (x1, y1, x2, y2)
    return regions


def _parse_expected_regions(raw: str) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        name, separator, value = item.partition("=")
        if not separator or value not in {"0", "1", "false", "true"}:
            raise ValueError(f"expected region {item!r} must use name=0|1")
        result[name.strip()] = value in {"1", "true"}
    return result


def _parse_occlusion_rectangles(raw: str) -> dict[str, tuple[float, float, float, float]]:
    return _parse_regions(raw)


def _terminate_process(process: subprocess.Popen[str] | None) -> int | None:
    if process is None:
        return None
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGINT)
        except (ProcessLookupError, PermissionError):
            process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=8.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                process.terminate()
            try:
                process.wait(timeout=4.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=4.0)
    return process.returncode


class TegrastatsCapture:
    """Collect bounded hardware samples without retaining image data."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.process: subprocess.Popen[str] | None = None
        self.thread: threading.Thread | None = None
        self.ram_used_mb: list[int] = []
        self.ram_total_mb: list[int] = []
        self.gr3d_pct: list[int] = []
        self.temperatures_c: dict[str, list[float]] = {}
        executable = shutil.which("tegrastats")
        if executable is None:
            return
        self.process = subprocess.Popen(
            [executable, "--interval", "1000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self) -> None:
        if self.process is None or self.process.stdout is None:
            return
        with self.path.open("w", encoding="utf-8", errors="replace") as output:
            for line in self.process.stdout:
                output.write(line)
                output.flush()
                ram = RAM_RE.search(line)
                if ram:
                    self.ram_used_mb.append(int(ram.group(1)))
                    self.ram_total_mb.append(int(ram.group(2)))
                gr3d = GR3D_RE.search(line)
                if gr3d:
                    self.gr3d_pct.append(int(gr3d.group(1)))
                for name, value in TEMP_RE.findall(line):
                    self.temperatures_c.setdefault(name, []).append(float(value))

    def stop(self) -> None:
        _terminate_process(self.process)
        if self.thread is not None:
            self.thread.join(timeout=3.0)

    def summary(self) -> dict[str, Any]:
        return {
            "available": self.process is not None,
            "sample_count": len(self.ram_used_mb),
            "ram_used_max_mb": max(self.ram_used_mb) if self.ram_used_mb else None,
            "ram_used_mean_mb": round(float(np.mean(self.ram_used_mb)), 3)
            if self.ram_used_mb
            else None,
            "ram_total_mb": max(self.ram_total_mb) if self.ram_total_mb else None,
            "gr3d_utilization_max_pct": max(self.gr3d_pct) if self.gr3d_pct else None,
            "gr3d_utilization_mean_pct": round(float(np.mean(self.gr3d_pct)), 3)
            if self.gr3d_pct
            else None,
            "temperatures_max_c": {
                name: max(values) for name, values in self.temperatures_c.items()
            },
            "temperatures_mean_c": {
                name: round(float(np.mean(values)), 3)
                for name, values in self.temperatures_c.items()
            },
            "log_path": str(self.path),
        }


class LatestImageNode(Node):
    """Keep only the newest ROS image so inference cannot build a backlog."""

    def __init__(self, topic: str) -> None:
        super().__init__("openhalo_visual_features")
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._stamp_ns = 0
        self._sequence = 0
        self.received_count = 0
        self.encodings: set[str] = set()
        self.shapes: set[tuple[int, int]] = set()
        self.subscription = self.create_subscription(
            Image, topic, self._on_image, qos_profile_sensor_data
        )

    def _on_image(self, message: Image) -> None:
        try:
            channels = 1 if message.encoding in {"mono8", "8UC1"} else 3
            raw = np.frombuffer(message.data, dtype=np.uint8)
            row_width = int(message.step) if message.step else int(message.width) * channels
            frame = raw.reshape(int(message.height), row_width)[:, : int(message.width) * channels]
            if channels == 1:
                frame = frame.reshape(int(message.height), int(message.width))
            else:
                frame = frame.reshape(int(message.height), int(message.width), channels)
                if message.encoding == "rgb8":
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                elif message.encoding != "bgr8":
                    return
            stamp_ns = int(message.header.stamp.sec) * 1_000_000_000 + int(
                message.header.stamp.nanosec
            )
        except (ValueError, cv2.error):
            return
        with self._lock:
            self._frame = frame.copy()
            self._stamp_ns = stamp_ns
            self._sequence += 1
            self.received_count += 1
            self.encodings.add(message.encoding)
            self.shapes.add((int(message.width), int(message.height)))

    def latest(self) -> tuple[np.ndarray | None, int, int]:
        with self._lock:
            if self._frame is None:
                return None, self._stamp_ns, self._sequence
            return self._frame.copy(), self._stamp_ns, self._sequence


class VisualFeatureEngine:
    """Run local detection, region projection, and coarse pose extraction."""

    def __init__(
        self,
        *,
        detector_path: str,
        pose_path: str,
        confidence: float,
        image_size: int,
        regions: dict[str, tuple[float, float, float, float]],
        object_labels: tuple[str, ...],
        use_pose: bool,
    ) -> None:
        self.confidence = confidence
        self.image_size = image_size
        self.regions = regions
        self.object_labels = object_labels
        self.use_pose = use_pose
        self.detector = YOLO(detector_path, task="detect")
        self.pose = YOLO(pose_path, task="pose") if use_pose else None

    def warmup(self, frame: np.ndarray) -> None:
        self.infer(frame)

    def _posture(self, keypoints: np.ndarray) -> str:
        if keypoints.shape[0] < 17:
            return "unknown"
        confidence = keypoints[:, 2]
        visible = confidence >= 0.35
        required = [5, 6, 11, 12]
        if not all(visible[index] for index in required):
            return "unknown"
        shoulder_y = float((keypoints[5, 1] + keypoints[6, 1]) / 2.0)
        hip_y = float((keypoints[11, 1] + keypoints[12, 1]) / 2.0)
        ankle_visible = visible[15] or visible[16]
        if ankle_visible:
            ankle_y = float(
                np.mean([keypoints[index, 1] for index in (15, 16) if visible[index]])
            )
            if ankle_y - shoulder_y > 0.30 * max(float(np.ptp(keypoints[:, 1])), 1.0):
                return "standing"
        knee_visible = visible[13] or visible[14]
        if knee_visible and hip_y - shoulder_y < 0.45 * max(float(np.ptp(keypoints[:, 1])), 1.0):
            return "sitting"
        return "unknown"

    @staticmethod
    def _body_coverage(visible_count: int) -> str:
        if visible_count >= 13:
            return "full_body"
        if visible_count >= 8:
            return "upper_body"
        if visible_count > 0:
            return "partial"
        return "none"

    def _detections(self, result: Any, width: int, height: int) -> dict[str, Any]:
        counts = {label: 0 for label in self.object_labels}
        persons: list[dict[str, float]] = []
        confidences: dict[str, list[float]] = {label: [] for label in self.object_labels}
        if result.boxes is None:
            return {"counts": counts, "persons": persons, "confidence": confidences}
        xyxy = result.boxes.xyxy.detach().cpu().numpy()
        scores = result.boxes.conf.detach().cpu().numpy()
        classes = result.boxes.cls.detach().cpu().numpy().astype(int)
        for box, score, class_id in zip(xyxy, scores, classes):
            label = str(result.names[int(class_id)])
            if label not in counts or float(score) < self.confidence:
                continue
            counts[label] += 1
            confidences[label].append(float(score))
            if label == "person":
                x1, y1, x2, y2 = [float(value) for value in box]
                persons.append(
                    {
                        "center_x": ((x1 + x2) / 2.0) / width,
                        "center_y": ((y1 + y2) / 2.0) / height,
                        "width": max(0.0, x2 - x1) / width,
                        "height": max(0.0, y2 - y1) / height,
                        "confidence": float(score),
                    }
                )
        return {"counts": counts, "persons": persons, "confidence": confidences}

    def _regions(self, persons: list[dict[str, float]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for name, (x1, y1, x2, y2) in self.regions.items():
            count = sum(
                x1 <= person["center_x"] <= x2 and y1 <= person["center_y"] <= y2
                for person in persons
            )
            result[name] = {"occupied": count > 0, "count": count}
        return result

    def _pose(self, frame: np.ndarray) -> tuple[dict[str, Any], float]:
        if self.pose is None:
            return {
                "available": False,
                "person_count": 0,
                "postures": {},
                "body_coverage": {},
                "visible_keypoints_mean": 0.0,
                "visible_keypoints_min": 0,
            }, 0.0
        started = time.perf_counter()
        results = self.pose.predict(
            frame, device=0, imgsz=self.image_size, conf=self.confidence, verbose=False
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        result = results[0]
        keypoints = (
            result.keypoints.data.detach().cpu().numpy()
            if result.keypoints is not None
            else np.empty((0, 17, 3), dtype=np.float32)
        )
        postures = [self._posture(item) for item in keypoints]
        visible_counts = [int(np.count_nonzero(item[:, 2] >= 0.35)) for item in keypoints]
        coverage: dict[str, int] = {}
        for visible_count in visible_counts:
            label = self._body_coverage(visible_count)
            coverage[label] = coverage.get(label, 0) + 1
        posture_counts: dict[str, int] = {}
        for posture in postures:
            posture_counts[posture] = posture_counts.get(posture, 0) + 1
        return (
            {
                "available": True,
                "person_count": int(len(keypoints)),
                "postures": posture_counts,
                "body_coverage": coverage,
                "visible_keypoints_mean": round(float(np.mean(visible_counts)), 3)
                if visible_counts
                else 0.0,
                "visible_keypoints_min": min(visible_counts) if visible_counts else 0,
            },
            elapsed_ms,
        )

    def infer(self, frame: np.ndarray) -> dict[str, Any]:
        height, width = frame.shape[:2]
        started = time.perf_counter()
        detector_started = time.perf_counter()
        results = self.detector.predict(
            frame, device=0, imgsz=self.image_size, conf=self.confidence, verbose=False
        )
        detector_ms = (time.perf_counter() - detector_started) * 1000.0
        detections = self._detections(results[0], width, height)
        pose, pose_ms = self._pose(frame)
        return {
            "width": width,
            "height": height,
            "person_count": int(detections["counts"].get("person", 0)),
            "person_confidence": round(
                max(detections["confidence"].get("person", []), default=0.0), 5
            ),
            "object_counts": detections["counts"],
            "regions": self._regions(detections["persons"]),
            "pose": pose,
            "latency_ms": {
                "detector": round(detector_ms, 3),
                "pose": round(pose_ms, 3),
                "total": round((time.perf_counter() - started) * 1000.0, 3),
            },
        }


def _mask(frame: np.ndarray, rectangle: tuple[float, float, float, float]) -> np.ndarray:
    output = frame.copy()
    height, width = output.shape[:2]
    x1, y1, x2, y2 = rectangle
    cv2.rectangle(
        output,
        (round(x1 * width), round(y1 * height)),
        (round(x2 * width), round(y2 * height)),
        (0, 0, 0),
        thickness=-1,
    )
    return output


def _feature_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    """Remove local geometry while retaining values needed for comparisons."""
    return {
        "person_count": result["person_count"],
        "object_counts": result["object_counts"],
        "regions": result["regions"],
        "pose_person_count": result["pose"]["person_count"],
        "postures": result["pose"]["postures"],
        "body_coverage": result["pose"]["body_coverage"],
        "visible_keypoints_mean": result["pose"]["visible_keypoints_mean"],
        "visible_keypoints_min": result["pose"]["visible_keypoints_min"],
        "latency_ms": result["latency_ms"],
    }


def _accuracy_summary(
    samples: list[dict[str, Any]],
    *,
    expected_person_count: int | None,
    expected_objects: set[str],
    expected_regions: dict[str, bool],
    expected_posture: str | None,
) -> dict[str, Any]:
    if not any(
        value is not None and value != set() and value != {}
        for value in (
            expected_person_count,
            expected_objects,
            expected_regions,
            expected_posture,
        )
    ):
        return {"status": "not_provided"}
    if not samples:
        return {"status": "no_samples"}
    person_matches = [
        sample["person_count"] == expected_person_count
        for sample in samples
        if expected_person_count is not None
    ]
    object_matches = [
        all((sample["object_counts"].get(label, 0) > 0) for label in expected_objects)
        for sample in samples
        if expected_objects
    ]
    region_matches = [
        all(sample["regions"].get(name, {}).get("occupied") == expected for name, expected in expected_regions.items())
        for sample in samples
        if expected_regions
    ]
    posture_matches = [
        sample["postures"].get(expected_posture, 0) > 0
        for sample in samples
        if expected_posture
    ]

    def rate(values: list[bool]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    return {
        "status": "measured",
        "expected": {
            "person_count": expected_person_count,
            "object_presence": sorted(expected_objects),
            "regions": expected_regions,
            "posture": expected_posture,
        },
        "person_count_accuracy": rate(person_matches),
        "object_presence_accuracy": rate(object_matches),
        "region_accuracy": rate(region_matches),
        "posture_accuracy": rate(posture_matches),
    }


def _occlusion_summary(trials: list[dict[str, Any]]) -> dict[str, Any]:
    if not trials:
        return {"status": "not_run"}
    valid = [trial for trial in trials if trial["baseline_person_count"] > 0]
    person_retained = [
        trial["occluded_person_count"] == trial["baseline_person_count"] for trial in valid
    ]
    pose_retained = [
        trial["occluded_pose_person_count"] > 0 and trial["baseline_pose_person_count"] > 0
        for trial in valid
    ]

    def rate(values: list[bool]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    return {
        "status": "measured" if valid else "insufficient_baseline_person",
        "trial_count": len(trials),
        "valid_person_trials": len(valid),
        "person_count_retention": rate(person_retained),
        "pose_person_retention": rate(pose_retained),
        "trials": trials,
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
        help="comma-separated normalized regions name=x1:y1:x2:y2",
    )
    parser.add_argument("--expected-person-count", type=int)
    parser.add_argument("--expected-objects", default="")
    parser.add_argument("--expected-regions", default="")
    parser.add_argument("--expected-posture", choices=["standing", "sitting", "unknown"])
    parser.add_argument("--case-name", default="live_camera_case")
    parser.add_argument(
        "--occlusion-rectangles",
        default="upper=0:0:1:0.28,center=0.2:0.25:0.8:0.75,lower=0:0.72:1:1",
        help="comma-separated synthetic in-memory occlusion rectangles",
    )
    parser.add_argument("--occlusion-every", type=int, default=30)
    parser.add_argument("--output-dir", type=Path, default=here / "results-visual-features")
    parser.add_argument("--no-launch", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    regions = _parse_regions(args.regions)
    occlusion_rectangles = _parse_occlusion_rectangles(args.occlusion_rectangles)
    objects = tuple(dict.fromkeys(value.strip() for value in args.objects.split(",") if value.strip()))
    expected_objects = {value.strip() for value in args.expected_objects.split(",") if value.strip()}
    expected_regions = _parse_expected_regions(args.expected_regions)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    launch_process: subprocess.Popen[str] | None = None
    launch_log = args.output_dir / "launch.log"
    stats = TegrastatsCapture(args.output_dir / "tegrastats.log")
    node: LatestImageNode | None = None
    spin_thread: threading.Thread | None = None
    engine: VisualFeatureEngine | None = None
    samples: list[dict[str, Any]] = []
    occlusion_trials: list[dict[str, Any]] = []
    detector_latency: list[float] = []
    pose_latency: list[float] = []
    total_latency: list[float] = []
    process_start = time.monotonic()
    last_sequence = -1
    warmup_complete = False
    status = "ok"
    try:
        if not args.no_launch:
            command = [
                args.ros2,
                "launch",
                str(args.launch_file),
                f"camera_id:={args.camera_id}",
                f"module_id:={args.module_id}",
                f"mode:={args.mode}",
                f"framerate:={args.framerate}",
                f"camera_info_url:={args.camera_info_url}",
            ]
            launch_file = launch_log.open("w", encoding="utf-8")
            launch_process = subprocess.Popen(
                command,
                stdout=launch_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                text=True,
            )
        rclpy.init()
        node = LatestImageNode(args.image_topic)
        spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
        spin_thread.start()
        engine = VisualFeatureEngine(
            detector_path=args.detector,
            pose_path=args.pose_model,
            confidence=args.confidence,
            image_size=args.image_size,
            regions=regions,
            object_labels=objects,
            use_pose=not args.no_pose,
        )
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
            if not warmup_complete:
                engine.warmup(frame)
                warmup_complete = True
                continue
            result = engine.infer(frame)
            latency = result["latency_ms"]
            detector_latency.append(float(latency["detector"]))
            pose_latency.append(float(latency["pose"]))
            total_latency.append(float(latency["total"]))
            sample = {
                "sample_index": len(samples),
                "ros_stamp_ns": stamp_ns,
                "features": _feature_snapshot(result),
            }
            samples.append(sample)
            if (
                occlusion_rectangles
                and args.occlusion_every > 0
                and len(samples) % args.occlusion_every == 0
            ):
                for name, rectangle in occlusion_rectangles.items():
                    masked = _mask(frame, rectangle)
                    masked_result = engine.infer(masked)
                    occlusion_trials.append(
                        {
                            "source_sample_index": sample["sample_index"],
                            "rectangle": list(rectangle),
                            "name": name,
                            "baseline_person_count": result["person_count"],
                            "occluded_person_count": masked_result["person_count"],
                            "baseline_pose_person_count": result["pose"]["person_count"],
                            "occluded_pose_person_count": masked_result["pose"]["person_count"],
                            "baseline_objects": result["object_counts"],
                            "occluded_objects": masked_result["object_counts"],
                            "occluded_latency_ms": masked_result["latency_ms"],
                        }
                    )
    except Exception as error:  # report a bounded failure instead of losing evidence
        status = "error"
        error_text = f"{type(error).__name__}: {error}"
    else:
        error_text = None
    finally:
        observed_duration = time.monotonic() - process_start
        if rclpy.ok():
            rclpy.shutdown()
        if spin_thread is not None:
            spin_thread.join(timeout=3.0)
        if node is not None:
            node.destroy_node()
        stats.stop()
        launch_exit_code = _terminate_process(launch_process)
        launch_file_handle = locals().get("launch_file")
        if launch_file_handle is not None:
            launch_file_handle.close()

    report = {
        "schema_version": "openhalo.isaac_ros.visual_features.v1",
        "created_at_epoch_s": round(time.time(), 3),
        "status": status,
        "error": error_text,
        "case": {
            "name": args.case_name,
            "accuracy_is_manual_ground_truth": True,
            "synthetic_occlusion_is_relative_robustness": True,
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
        },
        "stream": {
            "requested_duration_s": args.duration,
            "observed_duration_s": round(observed_duration, 3),
            "ros_images_received": node.received_count if node is not None else 0,
            "feature_samples": len(samples),
            "feature_rate_hz": round(len(samples) / observed_duration, 3)
            if observed_duration > 0
            else None,
            "encodings": sorted(node.encodings) if node is not None else [],
            "shapes": [list(shape) for shape in sorted(node.shapes)] if node is not None else [],
        },
        "latency": {
            "detector": _summary(detector_latency),
            "pose": _summary(pose_latency),
            "end_to_end": _summary(total_latency),
        },
        "feature_summary": {
            "person_count_distribution": {
                str(count): sum(sample["features"]["person_count"] == count for sample in samples)
                for count in sorted({sample["features"]["person_count"] for sample in samples})
            },
            "object_max_counts": {
                label: max((sample["features"]["object_counts"].get(label, 0) for sample in samples), default=0)
                for label in objects
            },
            "region_occupied_samples": {
                name: sum(sample["features"]["regions"].get(name, {}).get("occupied", False) for sample in samples)
                for name in regions
            },
            "postures": {
                posture: sum(sample["features"]["postures"].get(posture, 0) for sample in samples)
                for posture in ("standing", "sitting", "unknown")
            },
            "body_coverage": {
                coverage: sum(
                    sample["features"]["body_coverage"].get(coverage, 0)
                    for sample in samples
                )
                for coverage in ("full_body", "upper_body", "partial", "none")
            },
            "visible_keypoints_mean": round(
                float(
                    np.mean(
                        [
                            sample["features"]["visible_keypoints_mean"]
                            for sample in samples
                        ]
                    )
                ),
                3,
            )
            if samples
            else None,
        },
        "accuracy": _accuracy_summary(
            [sample["features"] for sample in samples],
            expected_person_count=args.expected_person_count,
            expected_objects=expected_objects,
            expected_regions=expected_regions,
            expected_posture=args.expected_posture,
        ),
        "occlusion": _occlusion_summary(occlusion_trials),
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
                "latency": report["latency"],
                "feature_summary": report["feature_summary"],
                "accuracy": report["accuracy"],
                "occlusion": {
                    key: value
                    for key, value in report["occlusion"].items()
                    if key != "trials"
                },
                "resources": report["resources"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"report: {report_path}")
    return 0 if status == "ok" and len(samples) > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
