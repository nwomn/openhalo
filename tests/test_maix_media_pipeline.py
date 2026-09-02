from __future__ import annotations

from datetime import UTC
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from device_edge.camera.camera_edge_service import CapturedCameraFrame
from device_edge.camera.maix_media_pipeline import MaixH264Mp4SegmentRecorder
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
