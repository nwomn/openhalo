from __future__ import annotations

import json
import subprocess
from datetime import UTC
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from device_edge.camera.camera_edge_service import CapturedCameraFrame
from device_edge.camera.maix_media_pipeline import MaixH264Mp4SegmentRecorder
from device_edge.camera.maix_media_pipeline import MaixBoundEncoderCaptureOwner
from device_edge.camera.maix_media_pipeline import MaixBoundEncoderSegmentRecorder
from device_edge.camera.maix_media_pipeline import MaixVideoRecorderCaptureOwner
from device_edge.camera.maix_media_pipeline import MaixVideoRecorderSegmentRecorder


def test_maix_recorder_writes_encoder_frames_then_packages_mp4(monkeypatch, tmp_path: Path) -> None:
    class _Frame:
        def to_bytes(self, include_config: bool) -> bytes:
            assert include_config is False
            return b"h264-frame"

    class _Encoder:
        calls: list[dict] = []

        def __init__(self, **kwargs) -> None:
            self.calls.append(kwargs)

        def encode(self, image) -> _Frame:
            assert image == "camera-frame"
            return _Frame()

    fake_maix = SimpleNamespace(
        image=SimpleNamespace(Format=SimpleNamespace(FMT_YVU420SP="yvu420sp", FMT_RGB888="rgb888")),
        video=SimpleNamespace(Encoder=_Encoder, VideoType=SimpleNamespace(VIDEO_H264_CBR="h264")),
    )
    monkeypatch.setitem(__import__("sys").modules, "maix", fake_maix)

    def _ffmpeg(command, **kwargs) -> None:
        raw_path = Path(command[command.index("-i") + 1])
        mp4_path = Path(command[-1])
        assert raw_path.read_bytes() == b"h264-frameh264-frame"
        mp4_path.write_bytes(b"packaged-mp4")

    monkeypatch.setattr("device_edge.camera.maix_media_pipeline.subprocess.run", _ffmpeg)
    recorder = MaixH264Mp4SegmentRecorder(
        directory=tmp_path, width=640, height=480, fps=10, bitrate=1_000_000, segment_seconds=2,
    )
    first = CapturedCameraFrame("2026-09-01T00:00:00Z", "camera-frame")
    second = CapturedCameraFrame("2026-09-01T00:00:02Z", "camera-frame")

    assert recorder.consume(first) == []
    segments = recorder.consume(second)

    assert _Encoder.calls == [{"width": 640, "height": 480, "format": "yvu420sp", "type": "h264", "framerate": 10, "gop": 10, "bitrate": 1_000_000}]
    assert len(segments) == 1
    assert segments[0].body == b"packaged-mp4"
    assert segments[0].mime_type == "video/mp4"
    assert list(tmp_path.iterdir()) == []


def test_video_recorder_binds_camera_before_config_and_seals_mp4(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple] = []

    class _Camera:
        def __init__(self, *args, **kwargs) -> None:
            calls.append(("camera", args, kwargs))

        def close(self) -> None:
            calls.append(("camera.close",))

    class _VideoRecorder:
        def __init__(self, *, open: bool) -> None:
            assert open is False
            self.path: Path | None = None
            self.bound = False

        def bind_camera(self, camera) -> None:
            self.bound = True
            calls.append(("bind_camera", camera))

        def config_resolution(self, value) -> None:
            assert self.bound
            calls.append(("resolution", value))

        def config_fps(self, value) -> None:
            assert self.bound
            calls.append(("fps", value))

        def config_bitrate(self, value) -> None:
            assert self.bound
            calls.append(("bitrate", value))

        def config_path(self, value) -> None:
            assert self.bound
            self.path = Path(value)
            calls.append(("path", value))

        def config_snapshot(self, enabled, resolution, format) -> None:
            assert self.bound
            calls.append(("snapshot_config", enabled, resolution, format))

        def open(self) -> None:
            calls.append(("open",))

        def record_start(self) -> None:
            calls.append(("start",))

        def snapshot(self):
            calls.append(("snapshot",))
            return "local-feature-frame"

        def record_finish(self) -> None:
            calls.append(("finish",))
            assert self.path is not None
            self.path.write_bytes(b"finalized-mp4")

        def close(self) -> None:
            calls.append(("close",))

    fake_maix = SimpleNamespace(
        image=SimpleNamespace(Format=SimpleNamespace(FMT_YVU420SP="yvu420sp", FMT_RGB888="rgb888")),
        camera=SimpleNamespace(Camera=_Camera),
        video=SimpleNamespace(VideoRecorder=_VideoRecorder),
    )
    monkeypatch.setitem(__import__("sys").modules, "maix", fake_maix)
    owner = MaixVideoRecorderCaptureOwner(
        directory=tmp_path,
        width=320,
        height=224,
        fps=5,
        bitrate=500_000,
        recording_enabled=True,
        snapshot_width=160,
        snapshot_height=112,
    )
    recorder = MaixVideoRecorderSegmentRecorder(capture_owner=owner, segment_seconds=2)

    first_read = owner.read_frame()
    assert first_read.frame == "local-feature-frame"
    first = CapturedCameraFrame("2026-09-01T00:00:00Z", first_read.frame)
    assert recorder.consume(first) == []
    second = owner.read_frame()
    second = CapturedCameraFrame("2026-09-01T00:00:02Z", second.frame)
    segments = recorder.consume(second)

    assert len(segments) == 1
    assert segments[0].body == b"finalized-mp4"
    assert calls.index(next(item for item in calls if item[0] == "bind_camera")) < calls.index(("resolution", [320, 224]))
    assert ("snapshot_config", True, [160, 112], "rgb888") in calls
    owner.close()


def test_bound_encoder_reads_camera_once_and_exposes_encoded_and_feature_frames(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple] = []

    class _Camera:
        def __init__(self, *args, **kwargs) -> None:
            calls.append(("camera", args, kwargs))

        def close(self) -> None:
            calls.append(("camera.close",))

    class _Encoded:
        def to_bytes(self, include_config: bool) -> bytes:
            assert include_config is True
            return b"h264-with-config"

    class _Encoder:
        def __init__(self, **kwargs) -> None:
            calls.append(("encoder", kwargs))

        def bind_camera(self, camera) -> None:
            calls.append(("bind_camera", camera))

        def encode(self):
            calls.append(("encode",))
            return _Encoded()

        def capture(self):
            calls.append(("capture",))
            return "yolo-image"

    fake_maix = SimpleNamespace(
        image=SimpleNamespace(Format=SimpleNamespace(FMT_YVU420SP="yvu420sp")),
        camera=SimpleNamespace(Camera=_Camera),
        video=SimpleNamespace(
            Encoder=_Encoder,
            VideoType=SimpleNamespace(VIDEO_H264_CBR="h264"),
        ),
    )
    monkeypatch.setitem(__import__("sys").modules, "maix", fake_maix)
    owner = MaixBoundEncoderCaptureOwner(width=640, height=480, fps=5, bitrate=500_000)
    frame = owner.read_frame()

    assert frame.frame == "yolo-image"
    assert frame.encoded_body == b"h264-with-config"
    assert calls.index(next(item for item in calls if item[0] == "bind_camera")) < calls.index(("encode",))
    assert calls.index(("encode",)) < calls.index(("capture",))

    recorder = MaixBoundEncoderSegmentRecorder(directory=tmp_path, fps=5, segment_seconds=2)
    def nal(nal_type: int, payload: bytes = b"x") -> bytes:
        return b"\0\0\0\1" + bytes([nal_type]) + payload

    first_payload = nal(7, b"sps") + nal(8, b"pps") + nal(5, b"idr-0")
    p_payload = nal(1, b"p-frame")
    second_payload = nal(5, b"idr-1")
    first = CapturedCameraFrame("2026-09-01T00:00:00Z", "yolo-image", first_payload)
    middle = CapturedCameraFrame("2026-09-01T00:00:01Z", "yolo-image", p_payload)
    second = CapturedCameraFrame("2026-09-01T00:00:02Z", "yolo-image", second_payload)
    assert recorder.consume(first) == []
    assert recorder.consume(middle) == []

    def _ffmpeg(command, **kwargs) -> None:
        raw_path = Path(command[command.index("-i") + 1])
        mp4_path = Path(command[-1])
        assert command[command.index("-framerate") + 1] == "1"
        raw_body = raw_path.read_bytes()
        assert raw_body.startswith(nal(7, b"sps") + nal(8, b"pps") + first_payload)
        assert raw_body.endswith(p_payload)
        mp4_path.write_bytes(b"bound-encoder-mp4")

    monkeypatch.setattr("device_edge.camera.maix_media_pipeline.subprocess.run", _ffmpeg)
    assert recorder.consume(second) == []
    pending = recorder.pop_pending_segment()
    assert pending is not None
    segment = recorder.package_pending_segment(pending)
    assert segment.body == b"bound-encoder-mp4"
    assert pending.timing == {"wall_clock_seconds": 2.0, "access_unit_packets": 2, "configured_fps": 5, "container_fps": 1.0}
    owner.close()


def test_bound_encoder_segment_records_h264_and_ffmpeg_failure_diagnostics(monkeypatch, tmp_path: Path) -> None:
    recorder = MaixBoundEncoderSegmentRecorder(directory=tmp_path, fps=5, segment_seconds=2)

    def nal(nal_type: int, payload: bytes = b"x") -> bytes:
        return b"\0\0\0\1" + bytes([nal_type]) + payload

    recorder.consume(CapturedCameraFrame("2026-09-01T00:00:00Z", "frame", nal(7, b"sps") + nal(8, b"pps") + nal(5, b"idr-0")))
    recorder.consume(CapturedCameraFrame("2026-09-01T00:00:01Z", "frame", nal(1, b"p")))
    recorder.consume(CapturedCameraFrame("2026-09-01T00:00:02Z", "frame", nal(5, b"idr-1")))
    pending = recorder.pop_pending_segment()
    assert pending is not None

    def _ffmpeg(command, **_kwargs) -> None:
        raise subprocess.CalledProcessError(1, command, stderr="[h264] non-existing PPS 0 referenced")

    monkeypatch.setattr("device_edge.camera.maix_media_pipeline.subprocess.run", _ffmpeg)
    try:
        recorder.package_pending_segment(pending)
    except subprocess.CalledProcessError:
        pass
    else:  # pragma: no cover - guards the expected package failure.
        raise AssertionError("ffmpeg packaging must fail in this test")

    events = [json.loads(line) for line in (tmp_path / "media-diagnostics.jsonl").read_text(encoding="utf-8").splitlines()]
    sealed = next(event for event in events if event["event"] == "h264_segment_sealed")
    failed = next(event for event in events if event["event"] == "h264_segment_package" and event["status"] == "failed")
    assert sealed["h264"] == {"access_unit_packets": 2, "idr_count": 1, "opening_idr": True, "pps_bytes": 8, "pps_cached": True, "sps_bytes": 8, "sps_cached": True}
    assert sealed["timing"] == {"wall_clock_seconds": 2.0, "access_unit_packets": 2, "configured_fps": 5, "container_fps": 1.0}
    assert failed["h264"]["idr_count"] == 1
    assert failed["ffmpeg"]["stderr"] == "[h264] non-existing PPS 0 referenced"
    assert failed["end_at"] == "2026-09-01T00:00:02Z"
