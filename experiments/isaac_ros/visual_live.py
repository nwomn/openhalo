"""Serve a browser-based live annotated preview for the Isaac ROS camera stream."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import signal
import subprocess
import threading
import time
from typing import Any
import urllib.parse

import cv2
import numpy as np
import rclpy

from visual_features import LatestImageNode
from visual_features import VisualFeatureEngine
from visual_features import _parse_regions
from visual_features import _terminate_process
from visual_preview import _draw_detections
from visual_preview import _draw_info
from visual_preview import _draw_pose
from visual_preview import _draw_regions


def _infer_with_geometry(
    engine: VisualFeatureEngine, frame: np.ndarray
) -> tuple[dict[str, Any], Any, np.ndarray]:
    """Run the same bounded features as the report runner and retain draw data."""
    height, width = frame.shape[:2]
    started = time.perf_counter()
    detector_started = time.perf_counter()
    detection = engine.detector.predict(
        frame, device=0, imgsz=engine.image_size, conf=engine.confidence, verbose=False
    )[0]
    detector_ms = (time.perf_counter() - detector_started) * 1000.0
    detections = engine._detections(detection, width, height)

    pose_ms = 0.0
    if engine.pose is None:
        keypoints = np.empty((0, 17, 3), dtype=np.float32)
        pose = {
            "available": False,
            "person_count": 0,
            "postures": {},
            "body_coverage": {},
            "visible_keypoints_mean": 0.0,
            "visible_keypoints_min": 0,
        }
    else:
        pose_started = time.perf_counter()
        pose_result = engine.pose.predict(
            frame, device=0, imgsz=engine.image_size, conf=engine.confidence, verbose=False
        )[0]
        pose_ms = (time.perf_counter() - pose_started) * 1000.0
        keypoints = (
            pose_result.keypoints.data.detach().cpu().numpy()
            if pose_result.keypoints is not None
            else np.empty((0, 17, 3), dtype=np.float32)
        )
        postures = [engine._posture(item) for item in keypoints]
        visible_counts = [int(np.count_nonzero(item[:, 2] >= 0.35)) for item in keypoints]
        posture_counts: dict[str, int] = {}
        coverage_counts: dict[str, int] = {}
        for posture in postures:
            posture_counts[posture] = posture_counts.get(posture, 0) + 1
        for visible_count in visible_counts:
            coverage = engine._body_coverage(visible_count)
            coverage_counts[coverage] = coverage_counts.get(coverage, 0) + 1
        pose = {
            "available": True,
            "person_count": int(len(keypoints)),
            "postures": posture_counts,
            "body_coverage": coverage_counts,
            "visible_keypoints_mean": round(float(np.mean(visible_counts)), 3)
            if visible_counts
            else 0.0,
            "visible_keypoints_min": min(visible_counts) if visible_counts else 0,
        }

    result = {
        "width": width,
        "height": height,
        "person_count": int(detections["counts"].get("person", 0)),
        "person_confidence": round(
            max(detections["confidence"].get("person", []), default=0.0), 5
        ),
        "object_counts": detections["counts"],
        "regions": engine._regions(detections["persons"]),
        "pose": pose,
        "latency_ms": {
            "detector": round(detector_ms, 3),
            "pose": round(pose_ms, 3),
            "total": round((time.perf_counter() - started) * 1000.0, 3),
        },
    }
    return result, detection, keypoints


def _annotate(
    frame: np.ndarray,
    detection: Any,
    keypoints: np.ndarray,
    result: dict[str, Any],
    regions: dict[str, tuple[float, float, float, float]],
    allowed_objects: set[str],
    confidence: float,
) -> np.ndarray:
    annotated = frame.copy()
    object_counts = _draw_detections(annotated, detection, allowed_objects, confidence)
    _draw_pose(annotated, keypoints)
    _draw_regions(annotated, regions, result["regions"])
    postures = [
        posture
        for posture, count in result["pose"]["postures"].items()
        for _ in range(count)
    ]
    coverage = [
        coverage_name
        for coverage_name, count in result["pose"]["body_coverage"].items()
        for _ in range(count)
    ]
    region_text = ", ".join(
        f"{name}={'on' if value['occupied'] else 'off'}"
        for name, value in result["regions"].items()
    )
    _draw_info(
        annotated,
        [
            "OpenHalo Isaac ROS | LIVE RECOGNITION",
            "detector %.1f ms | pose %.1f ms | total %.1f ms"
            % (
                result["latency_ms"]["detector"],
                result["latency_ms"]["pose"],
                result["latency_ms"]["total"],
            ),
            "objects: "
            + (", ".join(f"{name}={count}" for name, count in object_counts.items() if count) or "none"),
            "pose: %s | body: %s" % (",".join(postures) or "none", ",".join(coverage) or "none"),
            "regions: " + (region_text or "none"),
        ],
    )
    return annotated


class LivePreview:
    """Own the ROS subscription, inference worker, and latest in-memory JPEG."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.stop = threading.Event()
        self.enabled = threading.Event()
        self.enabled.set()
        self.condition = threading.Condition()
        self.annotated_jpeg: bytes | None = None
        self.generation = 0
        self.node: LatestImageNode | None = None
        self.engine: VisualFeatureEngine | None = None
        self.launch_process: subprocess.Popen[str] | None = None
        self.launch_log_handle: Any = None
        self.rclpy_started = False
        self.spin_thread: threading.Thread | None = None
        self.worker: threading.Thread | None = None
        self.inference_times: list[float] = []
        self.first_frame_monotonic: float | None = None
        self.state: dict[str, Any] = {
            "status": "starting",
            "error": None,
            "processed_frames": 0,
            "camera_frames": 0,
            "result": None,
        }

    def _set_state(self, **values: Any) -> None:
        with self.condition:
            self.state.update(values)
            self.condition.notify_all()

    def start(self) -> None:
        args = self.args
        if not args.no_launch:
            args.launch_log.parent.mkdir(parents=True, exist_ok=True)
            self.launch_log_handle = args.launch_log.open("w", encoding="utf-8")
            self.launch_process = subprocess.Popen(
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
                stdout=self.launch_log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                text=True,
            )
        rclpy.init()
        self.rclpy_started = True
        self.node = LatestImageNode(args.image_topic)
        self.spin_thread = threading.Thread(target=rclpy.spin, args=(self.node,), daemon=True)
        self.spin_thread.start()

        deadline = time.monotonic() + args.wait_seconds
        frame: np.ndarray | None = None
        while time.monotonic() < deadline:
            if self.launch_process is not None and self.launch_process.poll() is not None:
                raise RuntimeError("Isaac ROS launch exited before the first image")
            frame, _, _ = self.node.latest()
            if frame is not None:
                break
            time.sleep(0.02)
        if frame is None:
            raise RuntimeError("no ROS image arrived before timeout")

        self._set_state(status="warming_up")
        regions = _parse_regions(args.regions)
        objects = tuple(dict.fromkeys(value.strip() for value in args.objects.split(",") if value.strip()))
        self.engine = VisualFeatureEngine(
            detector_path=args.detector,
            pose_path=args.pose_model,
            confidence=args.confidence,
            image_size=args.image_size,
            regions=regions,
            object_labels=objects,
            use_pose=not args.no_pose,
        )
        self.engine.warmup(frame)
        self.first_frame_monotonic = time.monotonic()
        self.worker = threading.Thread(target=self._work, name="isaac-live-inference", daemon=True)
        self.worker.start()

    def _work(self) -> None:
        assert self.node is not None
        assert self.engine is not None
        args = self.args
        regions = _parse_regions(args.regions)
        allowed_objects = set(value.strip() for value in args.objects.split(",") if value.strip())
        last_sequence = -1
        while not self.stop.is_set():
            if not self.enabled.wait(timeout=0.2):
                continue
            frame, stamp_ns, sequence = self.node.latest()
            if frame is None or sequence == last_sequence:
                time.sleep(0.004)
                continue
            last_sequence = sequence
            try:
                result, detection, keypoints = _infer_with_geometry(self.engine, frame)
                annotated = _annotate(
                    frame,
                    detection,
                    keypoints,
                    result,
                    regions,
                    allowed_objects,
                    args.confidence,
                )
                ok, encoded = cv2.imencode(
                    ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, args.jpeg_quality]
                )
                if not ok:
                    raise RuntimeError("failed to encode annotated preview")
                now = time.time()
                self.inference_times.append(now)
                self.inference_times = [value for value in self.inference_times if now - value <= 5.0]
                elapsed = max(time.monotonic() - (self.first_frame_monotonic or time.monotonic()), 0.001)
                camera_fps = self.node.received_count / elapsed
                frame_age_ms = None
                if stamp_ns:
                    candidate = (time.time_ns() - stamp_ns) / 1_000_000.0
                    if 0 <= candidate < 600_000:
                        frame_age_ms = round(candidate, 1)
                live_result = {
                    **result,
                    "sequence": sequence,
                    "ros_stamp_ns": stamp_ns,
                    "processed_at_epoch_s": round(now, 3),
                    "frame_age_ms": frame_age_ms,
                }
                with self.condition:
                    self.annotated_jpeg = encoded.tobytes()
                    self.generation += 1
                    self.state.update(
                        status="ready",
                        error=None,
                        processed_frames=int(self.state["processed_frames"]) + 1,
                        camera_frames=self.node.received_count,
                        camera_fps=round(camera_fps, 2),
                        inference_fps=round(len(self.inference_times) / 5.0, 2),
                        enabled=self.enabled.is_set(),
                        result=live_result,
                    )
                    self.condition.notify_all()
            except Exception as exc:
                self.enabled.clear()
                self._set_state(status="error", error=f"{type(exc).__name__}: {exc}", enabled=False)

    def snapshot(self) -> dict[str, Any]:
        with self.condition:
            state = dict(self.state)
            state["enabled"] = self.enabled.is_set()
            state["server_time"] = time.time()
            state["configuration"] = {
                "image_topic": self.args.image_topic,
                "sensor_mode": self.args.mode,
                "target_framerate": float(self.args.framerate),
                "detector": self.args.detector,
                "pose_model": None if self.args.no_pose else self.args.pose_model,
                "confidence": self.args.confidence,
                "image_size": self.args.image_size,
                "objects": [value.strip() for value in self.args.objects.split(",") if value.strip()],
                "regions": self.args.regions,
            }
            return state

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.enabled.set()
            self._set_state(status="ready" if self.annotated_jpeg else "warming_up", error=None)
        else:
            self.enabled.clear()
            self._set_state(status="paused")

    def wait_frame(self, after_generation: int, timeout: float) -> tuple[bytes | None, int]:
        with self.condition:
            self.condition.wait_for(
                lambda: self.stop.is_set()
                or self.generation > after_generation,
                timeout=timeout,
            )
            return self.annotated_jpeg, self.generation

    def close(self) -> None:
        self.stop.set()
        self.enabled.set()
        with self.condition:
            self.condition.notify_all()
        if self.worker is not None:
            self.worker.join(timeout=3.0)
        if self.rclpy_started and rclpy.ok():
            rclpy.shutdown()
        if self.spin_thread is not None:
            self.spin_thread.join(timeout=3.0)
        if self.node is not None:
            self.node.destroy_node()
        _terminate_process(self.launch_process)
        if self.launch_log_handle is not None:
            self.launch_log_handle.close()


def _handler_for(preview: LivePreview):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:
            pass

        def send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            path = urllib.parse.urlsplit(self.path).path
            if path == "/":
                self.send_bytes(
                    Path(__file__).with_name("visual_live.html").read_bytes(),
                    "text/html; charset=utf-8",
                )
                return
            if path == "/api/state":
                self.send_bytes(json.dumps(preview.snapshot(), ensure_ascii=False).encode(), "application/json")
                return
            if path == "/frame.jpg":
                with preview.condition:
                    jpeg = preview.annotated_jpeg
                self.send_bytes(jpeg or b"", "image/jpeg", 200 if jpeg else 503)
                return
            if path == "/stream.mjpg":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                generation = 0
                try:
                    while not preview.stop.is_set():
                        jpeg, generation = preview.wait_frame(generation, 2.0)
                        if not jpeg:
                            continue
                        self.wfile.write(
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            + f"Content-Length: {len(jpeg)}\r\n\r\n".encode()
                            + jpeg
                            + b"\r\n"
                        )
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            self.send_bytes(b"Not found", "text/plain; charset=utf-8", 404)

        def do_POST(self) -> None:
            origin = self.headers.get("Origin")
            host = self.headers.get("Host", "")
            if origin and urllib.parse.urlsplit(origin).netloc != host:
                self.send_bytes(b"Forbidden", "text/plain; charset=utf-8", 403)
                return
            path = urllib.parse.urlsplit(self.path).path
            if path == "/api/pause":
                preview.set_enabled(False)
            elif path == "/api/resume":
                preview.set_enabled(True)
            else:
                self.send_bytes(b"Not found", "text/plain; charset=utf-8", 404)
                return
            self.send_bytes(b"{}", "application/json")

    return Handler


def build_parser() -> argparse.ArgumentParser:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8876)
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
    parser.add_argument(
        "--objects",
        default="person,laptop,chair,cup,cell phone,keyboard,mouse,couch,potted plant",
    )
    parser.add_argument(
        "--regions",
        default="left=0:0:0.333:1,center=0.333:0:0.667:1,right=0.667:0:1:1",
    )
    parser.add_argument("--wait-seconds", type=float, default=12.0)
    parser.add_argument("--jpeg-quality", type=int, default=86)
    parser.add_argument(
        "--launch-log",
        type=Path,
        default=Path("/tmp/openhalo-isaac-ros/live-preview-launch.log"),
    )
    parser.add_argument("--no-launch", action="store_true")
    parser.add_argument("--no-pose", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    preview = LivePreview(args)
    server: ThreadingHTTPServer | None = None
    try:
        preview.start()
        server = ThreadingHTTPServer((args.host, args.port), _handler_for(preview))
        server.daemon_threads = True
        print(f"Live preview http://{args.host}:{args.port}", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"live preview failed: {type(exc).__name__}: {exc}", flush=True)
        return 2
    finally:
        if server is not None:
            server.server_close()
        preview.close()
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    raise SystemExit(main())
