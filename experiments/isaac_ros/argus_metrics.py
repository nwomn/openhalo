"""ROS image and camera-info metrics for the OpenHalo Argus experiment."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image


def _stamp_ns(message: Any) -> int:
    return int(message.header.stamp.sec) * 1_000_000_000 + int(
        message.header.stamp.nanosec
    )


class ArgusMetricsNode(Node):
    """Collect bounded, transport-level metrics without retaining image data."""

    def __init__(
        self,
        image_topic: str = "/left/image_raw",
        camera_info_topic: str = "/left/camera_info",
        target_fps: float = 60.0,
        gap_threshold_s: float = 0.2,
    ) -> None:
        super().__init__("openhalo_argus_metrics")
        self.image_topic = image_topic
        self.camera_info_topic = camera_info_topic
        self.target_fps = target_fps
        self.gap_threshold_s = gap_threshold_s
        self.started_monotonic = time.monotonic()
        self.last_received_monotonic: float | None = None
        self.first_stamp_ns: int | None = None
        self.last_stamp_ns: int | None = None
        self.previous_stamp_ns: int | None = None
        self.image_count = 0
        self.camera_info_count = 0
        self.zero_timestamp_count = 0
        self.backward_timestamp_count = 0
        self.abnormal_gap_count = 0
        self.intervals_s: list[float] = []
        self.abnormal_gaps_s: list[float] = []
        self.image_shapes: set[tuple[int, int, str]] = set()
        self.camera_info_shapes: set[tuple[int, int, str, int]] = set()
        self.camera_info_frames: set[str] = set()
        self._image_subscription = self.create_subscription(
            Image,
            image_topic,
            self._on_image,
            qos_profile_sensor_data,
        )
        self._camera_info_subscription = self.create_subscription(
            CameraInfo,
            camera_info_topic,
            self._on_camera_info,
            qos_profile_sensor_data,
        )

    def _on_image(self, message: Image) -> None:
        received = time.monotonic()
        stamp = _stamp_ns(message)
        self.image_count += 1
        self.last_received_monotonic = received
        self.image_shapes.add((int(message.width), int(message.height), message.encoding))

        if stamp <= 0:
            self.zero_timestamp_count += 1
            return
        if self.first_stamp_ns is None:
            self.first_stamp_ns = stamp
        if self.previous_stamp_ns is not None:
            interval_s = (stamp - self.previous_stamp_ns) / 1_000_000_000.0
            if interval_s <= 0:
                self.backward_timestamp_count += 1
            else:
                self.intervals_s.append(interval_s)
                if interval_s > self.gap_threshold_s:
                    self.abnormal_gap_count += 1
                    self.abnormal_gaps_s.append(interval_s)
        self.previous_stamp_ns = stamp
        self.last_stamp_ns = stamp

    def _on_camera_info(self, message: CameraInfo) -> None:
        self.camera_info_count += 1
        self.camera_info_shapes.add(
            (
                int(message.width),
                int(message.height),
                message.distortion_model,
                len(message.d),
            )
        )
        self.camera_info_frames.add(message.header.frame_id)

    def summary(self, wall_duration_s: float) -> dict[str, Any]:
        stamp_duration_s = None
        header_fps = None
        if self.first_stamp_ns is not None and self.last_stamp_ns is not None:
            stamp_duration_s = (self.last_stamp_ns - self.first_stamp_ns) / 1_000_000_000.0
            if stamp_duration_s > 0 and self.image_count > 1:
                header_fps = (self.image_count - 1) / stamp_duration_s

        wall_fps = None
        if self.last_received_monotonic is not None:
            received_duration_s = self.last_received_monotonic - self.started_monotonic
            if received_duration_s > 0:
                wall_fps = self.image_count / received_duration_s

        dropped_estimate = 0
        for interval_s in self.intervals_s:
            if self.target_fps > 0:
                dropped_estimate += max(round(interval_s * self.target_fps) - 1, 0)
        drop_ratio = None
        if self.image_count > 1 and dropped_estimate >= 0:
            total_estimated_frames = self.image_count + dropped_estimate
            if total_estimated_frames > 0:
                drop_ratio = dropped_estimate / total_estimated_frames

        return {
            "topics": {
                "image": self.image_topic,
                "camera_info": self.camera_info_topic,
            },
            "image_count": self.image_count,
            "camera_info_count": self.camera_info_count,
            "wall_duration_s": round(wall_duration_s, 3),
            "header_duration_s": (
                round(stamp_duration_s, 3) if stamp_duration_s is not None else None
            ),
            "effective_fps": round(header_fps, 3) if header_fps is not None else None,
            "wall_fps": round(wall_fps, 3) if wall_fps is not None else None,
            "interval_mean_ms": (
                round(sum(self.intervals_s) / len(self.intervals_s) * 1000.0, 3)
                if self.intervals_s
                else None
            ),
            "interval_max_ms": (
                round(max(self.intervals_s) * 1000.0, 3) if self.intervals_s else None
            ),
            "zero_timestamp_count": self.zero_timestamp_count,
            "backward_timestamp_count": self.backward_timestamp_count,
            "abnormal_gap_count": self.abnormal_gap_count,
            "abnormal_gaps_ms": [round(value * 1000.0, 3) for value in self.abnormal_gaps_s],
            "estimated_dropped_frames": dropped_estimate,
            "estimated_drop_ratio": round(drop_ratio, 5) if drop_ratio is not None else None,
            "image_shapes": [list(value) for value in sorted(self.image_shapes)],
            "camera_info_shapes": [
                {
                    "width": value[0],
                    "height": value[1],
                    "distortion_model": value[2],
                    "d_length": value[3],
                }
                for value in sorted(self.camera_info_shapes)
            ],
            "camera_info_frame_ids": sorted(self.camera_info_frames),
        }


def collect_for_duration(duration_s: float, **kwargs: Any) -> dict[str, Any]:
    """Run the collector as a standalone ROS Python process."""
    rclpy.init()
    node = ArgusMetricsNode(**kwargs)
    started = time.monotonic()
    try:
        deadline = started + duration_s
        while time.monotonic() < deadline and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)
        return node.summary(time.monotonic() - started)
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--image-topic", default="/left/image_raw")
    parser.add_argument("--camera-info-topic", default="/left/camera_info")
    parser.add_argument("--target-fps", type=float, default=60.0)
    parser.add_argument("--gap-threshold", type=float, default=0.2)
    parser.add_argument("--output", type=str)
    args = parser.parse_args()
    result = collect_for_duration(
        args.duration,
        image_topic=args.image_topic,
        camera_info_topic=args.camera_info_topic,
        target_fps=args.target_fps,
        gap_threshold_s=args.gap_threshold,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as output_file:
            output_file.write(rendered)
            output_file.write("\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
