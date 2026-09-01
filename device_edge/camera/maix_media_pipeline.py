"""MaixCAM adapters for the single-owner Camera Edge capture loop.

Only this module opens ``maix.camera.Camera``.  The service receives the image
once, then hands that same object to the H.264 encoder and local Feature worker.
The adapter is deliberately imported lazily so desktop contract tests do not
need MaixPy installed.
"""

from __future__ import annotations

import gc
import subprocess
from datetime import UTC
from datetime import datetime
from pathlib import Path

try:
    from device_edge.camera.camera_edge_service import CapturedCameraFrame
    from device_edge.camera.camera_edge_service import EncodedMediaSegment
except ImportError:  # pragma: no cover - copied MaixCAM files.
    from camera_edge_service import CapturedCameraFrame
    from camera_edge_service import EncodedMediaSegment


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class MaixCameraCaptureOwner:
    """The only Camera owner used by the production CameraEdgeService path."""

    def __init__(
        self,
        *,
        width: int = 640,
        height: int = 480,
        fps: int = 10,
        buffer_count: int = 2,
    ) -> None:
        if width <= 0 or height <= 0 or fps <= 0 or buffer_count < 1:
            raise ValueError("invalid Maix camera capture configuration")
        self.width = width
        self.height = height
        self.fps = fps
        self.buffer_count = buffer_count
        self._camera = None

    def _start(self) -> None:
        if self._camera is not None:
            return
        from maix import camera, image

        # Maix's hardware Encoder accepts NV21/YVU420SP input.
        self._camera = camera.Camera(
            self.width,
            self.height,
            image.Format.FMT_YVU420SP,
            fps=self.fps,
            buff_num=self.buffer_count,
        )

    def read_frame(self) -> CapturedCameraFrame:
        self._start()
        frame = self._camera.read(block=True, block_ms=3000)
        if frame is None:
            raise RuntimeError("MaixCAM capture timed out")
        return CapturedCameraFrame(captured_at=_utc_timestamp(), frame=frame)

    def close(self) -> None:
        if self._camera is not None:
            try:
                self._camera.close()
            finally:
                self._camera = None


class MaixH264Mp4SegmentRecorder:
    """Seal short H.264/MP4 files from shared Maix camera frames.

    MaixPy's Encoder emits encoded H.264 frames; it does not own or finalize an
    MP4 output file. We write those frames to a temporary elementary stream,
    then package the sealed stream with the board's ``ffmpeg`` binary. Each
    segment gets its own encoder, intentionally keeping only one encoder alive
    at a time (a MaixPy limitation).
    """

    def __init__(
        self,
        *,
        directory: Path,
        width: int,
        height: int,
        fps: int = 10,
        bitrate: int = 1_000_000,
        segment_seconds: float = 2.0,
        enabled: bool = True,
    ) -> None:
        if width <= 0 or height <= 0 or fps <= 0 or bitrate <= 0 or segment_seconds < 2:
            raise ValueError("invalid Maix video segment configuration")
        self.directory = Path(directory)
        self.width = width
        self.height = height
        self.fps = fps
        self.bitrate = bitrate
        self.segment_seconds = segment_seconds
        self.enabled = enabled
        self._encoder = None
        self._encoded_file = None
        self._segment_started_at: str | None = None
        self._segment_path: Path | None = None
        self.directory.mkdir(parents=True, exist_ok=True)

    def _open_segment(self, captured_at: str) -> None:
        from maix import image, video

        filename = f"recording-{captured_at.replace(':', '').replace('+', '').replace('.', '')}.h264"
        self._segment_path = self.directory / filename
        self._encoder = video.Encoder(
            width=self.width,
            height=self.height,
            format=image.Format.FMT_YVU420SP,
            type=video.VideoType.VIDEO_H264_CBR,
            framerate=self.fps,
            gop=self.fps,
            bitrate=self.bitrate,
        )
        self._encoded_file = self._segment_path.open("wb")
        self._segment_started_at = captured_at

    def consume(self, captured: CapturedCameraFrame) -> list[EncodedMediaSegment]:
        if not self.enabled:
            return []
        if self._encoder is None:
            self._open_segment(captured.captured_at)
        encoded = self._encoder.encode(captured.frame)
        if encoded is not None:
            self._encoded_file.write(encoded.to_bytes(False))
        assert self._segment_started_at is not None
        started = datetime.fromisoformat(self._segment_started_at.replace("Z", "+00:00"))
        current = datetime.fromisoformat(captured.captured_at.replace("Z", "+00:00"))
        if (current - started).total_seconds() < self.segment_seconds:
            return []
        return [self._seal_segment(captured.captured_at)]

    def _seal_segment(self, ended_at: str) -> EncodedMediaSegment:
        assert self._encoder is not None and self._segment_path is not None
        started_at = self._segment_started_at
        raw_path = self._segment_path
        self._release_encoder()
        mp4_path = raw_path.with_suffix(".mp4")
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error", "-framerate", str(self.fps),
                    "-i", str(raw_path), "-c:v", "copy", "-movflags", "+faststart", str(mp4_path),
                ],
                check=True,
                timeout=20,
            )
            body = mp4_path.read_bytes()
        finally:
            raw_path.unlink(missing_ok=True)
            mp4_path.unlink(missing_ok=True)
        segment = EncodedMediaSegment(
            start_at=started_at,
            end_at=ended_at,
            body=body,
            mime_type="video/mp4",
        )
        self._segment_started_at = None
        self._segment_path = None
        return segment

    def _release_encoder(self) -> None:
        """Release the native encoder before using its completed raw stream."""

        self._encoder = None
        if self._encoded_file is not None:
            self._encoded_file.close()
            self._encoded_file = None
        # MaixPy exposes no Encoder.close()/finish(); prompt destruction frees
        # its single native encoder instance before the next segment opens.
        gc.collect()

    def close(self) -> None:
        self._release_encoder()
        if self._segment_path is not None:
            self._segment_path.unlink(missing_ok=True)
            self._segment_path = None
        self._segment_started_at = None
