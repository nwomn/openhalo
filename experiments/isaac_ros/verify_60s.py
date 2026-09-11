"""Run a bounded IMX219 Argus stream test and a restart smoke test."""

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

import rclpy

from argus_metrics import ArgusMetricsNode


FRAME_DROP_RE = re.compile(r"\bframe\s+drop(?:ped)?\b", re.IGNORECASE)
UNSUPPORTED_RE = re.compile(r"unsupported|distortion model|nitros.*error", re.IGNORECASE)
CRASH_RE = re.compile(
    r"segmentation fault|abort|fatal|core dumped|exit code [1-9]|backtrace",
    re.IGNORECASE,
)
RAM_RE = re.compile(r"RAM\s+(\d+)/(\d+)MB")
GR3D_RE = re.compile(r"GR3D_FREQ[^0-9]*(\d+)%")
TEMP_RE = re.compile(r"([A-Za-z0-9_]+)@(-?\d+(?:\.\d+)?)C")


class LogCapture:
    def __init__(self, process: subprocess.Popen[str], path: Path) -> None:
        self.process = process
        self.path = path
        self.frame_drop_count = 0
        self.unsupported_count = 0
        self.crash_count = 0
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self) -> None:
        with self.path.open("w", encoding="utf-8", errors="replace") as log_file:
            assert self.process.stdout is not None
            for line in self.process.stdout:
                log_file.write(line)
                log_file.flush()
                if FRAME_DROP_RE.search(line):
                    self.frame_drop_count += 1
                if UNSUPPORTED_RE.search(line):
                    self.unsupported_count += 1
                if CRASH_RE.search(line):
                    self.crash_count += 1

    def join(self) -> None:
        self._thread.join(timeout=5.0)


class TegrastatsCapture:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self.ram_used_mb: list[int] = []
        self.ram_total_mb: list[int] = []
        self.gr3d_utilization_pct: list[int] = []
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
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self) -> None:
        if self.process is None or self.process.stdout is None:
            return
        with self.path.open("w", encoding="utf-8", errors="replace") as log_file:
            for line in self.process.stdout:
                log_file.write(line)
                log_file.flush()
                ram_match = RAM_RE.search(line)
                if ram_match:
                    self.ram_used_mb.append(int(ram_match.group(1)))
                    self.ram_total_mb.append(int(ram_match.group(2)))
                gr3d_match = GR3D_RE.search(line)
                if gr3d_match:
                    self.gr3d_utilization_pct.append(int(gr3d_match.group(1)))
                for name, value in TEMP_RE.findall(line):
                    self.temperatures_c.setdefault(name, []).append(float(value))

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                self.process.terminate()
            try:
                self.process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    def summary(self) -> dict[str, Any]:
        return {
            "available": self.process is not None,
            "sample_count": len(self.ram_used_mb),
            "ram_used_max_mb": max(self.ram_used_mb) if self.ram_used_mb else None,
            "ram_total_mb": max(self.ram_total_mb) if self.ram_total_mb else None,
            "gr3d_utilization_max_pct": (
                max(self.gr3d_utilization_pct) if self.gr3d_utilization_pct else None
            ),
            "temperatures_max_c": {
                name: max(values) for name, values in self.temperatures_c.items()
            },
            "log_path": str(self.path),
        }


def _process_rss_mb(pid: int) -> float | None:
    status_path = Path(f"/proc/{pid}/status")
    try:
        content = status_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r"^VmRSS:\s+(\d+)\s+kB$", content, re.MULTILINE)
    return int(match.group(1)) / 1024.0 if match else None


def _stop_process(process: subprocess.Popen[str]) -> int | None:
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


def _acceptance(
    metrics: dict[str, Any],
    log: LogCapture,
    launch_survived: bool,
    requested_duration_s: float,
    target_width: int,
    target_height: int,
    target_fps: float,
    min_fps: float,
    max_drop_ratio: float,
    expected_model: str,
) -> dict[str, Any]:
    image_shapes = metrics["image_shapes"]
    camera_info_shapes = metrics["camera_info_shapes"]
    effective_fps = metrics["effective_fps"]
    checks = {
        "launch_survived_requested_duration": launch_survived,
        "received_images": metrics["image_count"] > 1,
        "received_camera_info": metrics["camera_info_count"] > 0,
        "image_dimensions_match": image_shapes == [[target_width, target_height, "rgb8"]]
        or image_shapes == [[target_width, target_height, "bgr8"]],
        "camera_info_dimensions_match": any(
            item["width"] == target_width and item["height"] == target_height
            for item in camera_info_shapes
        ),
        "camera_info_distortion_model_match": any(
            item["distortion_model"] == expected_model and item["d_length"] == 8
            for item in camera_info_shapes
        ),
        "header_timestamps_monotonic": (
            metrics["zero_timestamp_count"] == 0
            and metrics["backward_timestamp_count"] == 0
        ),
        "no_abnormal_timestamp_gap": metrics["abnormal_gap_count"] == 0,
        "minimum_effective_fps": effective_fps is not None and effective_fps >= min_fps,
        "estimated_drop_ratio_within_limit": (
            metrics["estimated_drop_ratio"] is not None
            and metrics["estimated_drop_ratio"] <= max_drop_ratio
        ),
        "no_frame_drop_log": log.frame_drop_count == 0,
        "no_unsupported_camera_info_log": log.unsupported_count == 0,
        "no_crash_log": log.crash_count == 0,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "requested_duration_s": requested_duration_s,
        "target": {
            "width": target_width,
            "height": target_height,
            "fps": target_fps,
            "minimum_fps": min_fps,
            "maximum_estimated_drop_ratio": max_drop_ratio,
            "distortion_model": expected_model,
        },
    }


def _run_phase(
    label: str,
    duration_s: float,
    args: argparse.Namespace,
    output_dir: Path,
) -> dict[str, Any]:
    phase_dir = output_dir / label
    phase_dir.mkdir(parents=True, exist_ok=True)
    launch_log_path = phase_dir / "launch.log"
    tegrastats_path = phase_dir / "tegrastats.log"
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
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    log = LogCapture(process, launch_log_path)
    stats = TegrastatsCapture(tegrastats_path)
    node = ArgusMetricsNode(
        target_fps=args.target_fps,
        gap_threshold_s=args.gap_threshold,
    )
    started = time.monotonic()
    early_exit_s: float | None = None
    rss_samples_mb: list[float] = []
    try:
        deadline = started + duration_s
        while time.monotonic() < deadline and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)
            rss = _process_rss_mb(process.pid)
            if rss is not None:
                rss_samples_mb.append(rss)
            if process.poll() is not None:
                early_exit_s = time.monotonic() - started
                break
    finally:
        observed_duration_s = time.monotonic() - started
        final_exit_code = _stop_process(process)
        stats.stop()
        log.join()
        metrics = node.summary(observed_duration_s)
        node.destroy_node()

    launch_survived = early_exit_s is None and observed_duration_s >= duration_s * 0.95
    acceptance = _acceptance(
        metrics,
        log,
        launch_survived,
        duration_s,
        args.target_width,
        args.target_height,
        args.target_fps,
        args.min_fps,
        args.max_drop_ratio,
        args.expected_distortion_model,
    )
    return {
        "label": label,
        "command": command,
        "requested_duration_s": duration_s,
        "observed_duration_s": round(observed_duration_s, 3),
        "early_exit_s": round(early_exit_s, 3) if early_exit_s is not None else None,
        "launch_exit_code": final_exit_code,
        "metrics": metrics,
        "process_rss_max_mb": round(max(rss_samples_mb), 3) if rss_samples_mb else None,
        "system": stats.summary(),
        "log": {
            "path": str(launch_log_path),
            "frame_drop_count": log.frame_drop_count,
            "unsupported_count": log.unsupported_count,
            "crash_count": log.crash_count,
        },
        "acceptance": acceptance,
    }


def parse_args() -> argparse.Namespace:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--restart-duration", type=float, default=10.0)
    parser.add_argument("--output-dir", type=Path, default=here / "results")
    parser.add_argument(
        "--launch-file", type=Path, default=here / "argus_imx219_mono.launch.py"
    )
    parser.add_argument(
        "--camera-info-url", default=f"file://{here / 'imx219_1280x720.yaml'}"
    )
    parser.add_argument("--ros2", default="ros2")
    parser.add_argument("--camera-id", default="0")
    parser.add_argument("--module-id", default="0")
    parser.add_argument("--mode", default="4")
    parser.add_argument("--framerate", default="60")
    parser.add_argument("--target-width", type=int, default=1280)
    parser.add_argument("--target-height", type=int, default=720)
    parser.add_argument("--target-fps", type=float, default=60.0)
    parser.add_argument("--min-fps", type=float, default=45.0)
    parser.add_argument("--max-drop-ratio", type=float, default=0.05)
    parser.add_argument("--gap-threshold", type=float, default=0.2)
    parser.add_argument("--expected-distortion-model", default="rational_polynomial")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if not args.launch_file.is_file():
        raise SystemExit(f"launch file does not exist: {args.launch_file}")
    if shutil.which(args.ros2) is None and not Path(args.ros2).is_file():
        raise SystemExit(f"ros2 executable was not found: {args.ros2}")

    rclpy.init()
    started = time.time()
    try:
        main_phase = _run_phase("main", args.duration, args, args.output_dir)
        time.sleep(2.0)
        restart_phase = _run_phase("restart", args.restart_duration, args, args.output_dir)
    finally:
        rclpy.shutdown()

    report = {
        "schema_version": "openhalo.isaac_ros.argus_validation.v1",
        "created_at_epoch_s": round(started, 3),
        "configuration": {
            "camera_id": args.camera_id,
            "module_id": args.module_id,
            "mode": args.mode,
            "framerate": args.framerate,
            "camera_info_url": args.camera_info_url,
            "image_topic": "/left/image_raw",
            "camera_info_topic": "/left/camera_info",
            "calibration_status": "experimental_estimate_requires_measured_calibration",
        },
        "main": main_phase,
        "restart": restart_phase,
        "accepted": main_phase["acceptance"]["passed"]
        and restart_phase["acceptance"]["passed"],
    }
    report_path = args.output_dir / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report: {report_path}")
    return 0 if report["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
