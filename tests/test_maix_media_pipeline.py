from __future__ import annotations

from datetime import UTC
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from device_edge.camera.camera_edge_service import CapturedCameraFrame
from device_edge.camera.maix_media_pipeline import MaixH264Mp4SegmentRecorder


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
        image=SimpleNamespace(Format=SimpleNamespace(FMT_YVU420SP="yvu420sp")),
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

