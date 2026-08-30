from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from device_edge.camera import health_daemon
from device_edge.camera.person_presence import MaixPersonPresenceFeature
from device_edge.camera.person_presence import PersonPresenceSample
from device_edge.camera.person_presence import RegionOccupancy
from device_edge.camera.person_presence import VisualFeatureSample


class _Detection:
    def __init__(self, class_id: int, score: float, x: int, y: int, w: int, h: int) -> None:
        self.class_id = class_id
        self.score = score
        self.x = x
        self.y = y
        self.w = w
        self.h = h


class _Detector:
    labels = ["person", "chair", "cup"]

    def __init__(self, **kwargs) -> None:
        assert kwargs == {"model": "/tmp/yolo11.mud", "dual_buff": True}

    def input_width(self) -> int:
        return 320

    def input_height(self) -> int:
        return 240

    def input_format(self) -> str:
        return "rgb"

    def detect(self, frame, **kwargs):
        assert frame == "private-frame"
        assert kwargs == {"conf_th": 0.6, "iou_th": 0.45}
        return [
            _Detection(0, 0.91, 32, 32, 64, 64),
            _Detection(1, 0.83, 100, 100, 40, 40),
            _Detection(2, 0.40, 10, 10, 20, 20),
        ]


class _Camera:
    def __init__(self, *args) -> None:
        assert args == (320, 240, "rgb")
        self.closed = False

    def read(self, **kwargs):
        assert kwargs == {"block": True, "block_ms": 3000}
        return "private-frame"

    def close(self) -> None:
        self.closed = True


def test_shared_visual_pipeline_derives_allowlisted_objects_and_regions() -> None:
    feature = MaixPersonPresenceFeature(
        model_path="/tmp/yolo11.mud",
        confidence_threshold=0.6,
        object_labels=["chair", "cup"],
        regions={"desk": [0.1, 0.1, 0.5, 0.5]},
        detector_factory=_Detector,
        camera_factory=_Camera,
    )

    assert feature.sample() == PersonPresenceSample("present", 1, 0.91)
    visual = feature.last_visual_sample
    assert visual == VisualFeatureSample(
        state="ready",
        person_state="present",
        person_count=1,
        person_confidence=0.91,
        object_counts={"chair": 1, "cup": 0},
        regions={"desk": RegionOccupancy(occupied=True, count=1)},
        width=320,
        height=240,
    )
    assert not hasattr(visual, "frame")
    assert not hasattr(visual, "detections")
    feature.close()


def test_visual_pipeline_keeps_camera_failure_distinct_from_empty_room() -> None:
    class EmptyCamera(_Camera):
        def read(self, **kwargs):
            return None

    feature = MaixPersonPresenceFeature(
        detector_factory=_Detector,
        camera_factory=EmptyCamera,
        object_labels=["chair"],
        regions={"desk": [0.1, 0.1, 0.5, 0.5]},
    )

    assert feature.sample() == PersonPresenceSample("unavailable", None, 0.0)
    visual = feature.last_visual_sample
    assert visual is not None
    assert visual.state == "unavailable"
    assert visual.person_state == "unavailable"
    assert visual.object_counts == {}
    assert visual.regions == {"desk": RegionOccupancy(None, None)}
    feature.close()


def test_visual_capabilities_and_frames_are_registered_without_raw_media() -> None:
    visual = VisualFeatureSample(
        state="ready",
        person_state="present",
        person_count=1,
        person_confidence=0.9,
        object_counts={"chair": 1},
        regions={"desk": RegionOccupancy(True, 1)},
        width=320,
        height=240,
    )

    class Client:
        audience = "ws://runtime.example.test:8765"
        device_id = "camera-edge-1"

        async def authenticate(self, websocket, capabilities):
            assert [item["name"] for item in capabilities] == [
                "camera.health",
                "camera.person_presence",
                "camera.object_presence",
                "camera.region_occupancy",
                "camera.region_occupancy_transition",
                "camera.scene_quality",
                "camera.person_presence_transition",
            ]
            websocket.authenticated = True

    class Feature:
        supports_visual_features = True
        last_visual_sample = None

        def sample(self):
            self.last_visual_sample = visual
            return PersonPresenceSample("present", 1, 0.9)

        def close(self):
            pass

    class WebSocket:
        authenticated = False

        def __init__(self):
            self.sent: list[dict] = []

        async def send(self, payload: str):
            assert self.authenticated
            self.sent.append(json.loads(payload))

    class Connect:
        def __init__(self, websocket):
            self.websocket = websocket

        async def __aenter__(self):
            return self.websocket

        async def __aexit__(self, *_args):
            return False

    with TemporaryDirectory() as directory:
        websocket = WebSocket()
        daemon = health_daemon.CameraHealthDaemon(
            client=Client(),
            status_store=health_daemon.LocalStatusStore(Path(directory) / "status.json"),
            interval_seconds=60,
            min_free_mib=0,
            person_presence_feature=Feature(),
            presence_confirm_samples=1,
        )
        with patch(
            "device_edge.camera.health_daemon.websockets.connect",
            return_value=Connect(websocket),
        ):
            asyncio.run(daemon.run_once())

    assert [frame["capability"] for frame in websocket.sent] == [
        "camera.health",
        "camera.person_presence",
        "camera.object_presence",
        "camera.region_occupancy",
        "camera.scene_quality",
    ]
    serialized = json.dumps(websocket.sent)
    assert "raw_media" not in serialized
    assert "bbox" not in serialized
    assert "private-frame" not in serialized


def test_presence_transition_frame_distinguishes_enter_leave_and_count_change() -> None:
    previous = type("Decision", (), {"state": "absent", "count": 0})()
    current = type("Decision", (), {"state": "present", "count": 1, "confidence": 0.9})()
    frame = health_daemon.build_presence_transition_frame(
        "camera-edge-1",
        previous,
        current,
        observed_at="2030-01-01T00:00:00Z",
    )
    assert frame["observations"][0]["value"] == {
        "from_state": "absent",
        "to_state": "present",
        "from_count": 0,
        "to_count": 1,
        "transition": "entered",
        "feature_version": "person_presence_transition.v1",
    }


def test_visual_change_publishes_transition_and_new_semantics_immediately() -> None:
    absent = VisualFeatureSample(
        state="ready",
        person_state="absent",
        person_count=0,
        person_confidence=0.0,
        object_counts={"chair": 0},
        regions={"desk": RegionOccupancy(False, 0)},
        width=320,
        height=240,
    )
    present = VisualFeatureSample(
        state="ready",
        person_state="present",
        person_count=1,
        person_confidence=0.88,
        object_counts={"chair": 1},
        regions={"desk": RegionOccupancy(True, 1)},
        width=320,
        height=240,
    )

    class Feature:
        supports_visual_features = True

        def __init__(self):
            self.last_visual_sample = None
            self.samples = iter((absent, present))

        def sample(self):
            self.last_visual_sample = next(self.samples)
            return PersonPresenceSample(
                self.last_visual_sample.person_state,
                self.last_visual_sample.person_count,
                self.last_visual_sample.person_confidence,
            )

        def close(self):
            pass

    class Client:
        device_id = "camera-edge-1"

    with TemporaryDirectory() as directory:
        daemon = health_daemon.CameraHealthDaemon(
            client=Client(),
            status_store=health_daemon.LocalStatusStore(Path(directory) / "status.json"),
            interval_seconds=60,
            min_free_mib=0,
            person_presence_feature=Feature(),
            presence_confirm_samples=1,
            presence_freshness_seconds=60,
        )
        first = daemon._next_visual_frames(force=True)
        second = daemon._next_visual_frames()

    assert [frame["capability"] for frame in first] == [
        "camera.person_presence",
        "camera.object_presence",
        "camera.region_occupancy",
        "camera.scene_quality",
    ]
    assert [frame["capability"] for frame in second] == [
        "camera.person_presence",
        "camera.person_presence_transition",
        "camera.object_presence",
        "camera.region_occupancy",
        "camera.region_occupancy_transition",
        "camera.scene_quality",
    ]
    assert (
        second[1]["observations"][0]["value"]["transition"]
        == "entered"
    )
    assert (
        second[4]["observations"][0]["value"]["transition"]
        == "entered"
    )
