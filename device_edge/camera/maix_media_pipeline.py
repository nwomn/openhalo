"""MaixCAM adapters for the single-owner Camera Edge capture loop.

Only this module opens ``maix.camera.Camera``.  The service receives the image
once, then hands that same object to the H.264 encoder and local Feature worker.
The adapter is deliberately imported lazily so desktop contract tests do not
need MaixPy installed.
"""

from __future__ import annotations

import gc
import subprocess
from collections import deque
from dataclasses import dataclass
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


class MaixVideoRecorderCaptureOwner:
    """Use Maix's bound ``VideoRecorder`` as the camera/encoder owner.

    MaixCAM's media driver cannot reliably support an application calling
    ``Camera.read()`` while also pushing that image through a separately
    created encoder.  The vendor recorder instead owns the camera binding and
    exposes ``snapshot()`` for the sampled local Feature worker.  This keeps
    exactly one physical camera open in the Camera Edge process.
    """

    def __init__(
        self,
        *,
        directory: Path,
        width: int,
        height: int,
        fps: int,
        bitrate: int,
        recording_enabled: bool,
        snapshot_width: int | None = None,
        snapshot_height: int | None = None,
        buffer_count: int = 2,
    ) -> None:
        if width <= 0 or height <= 0 or fps <= 0 or bitrate <= 0 or buffer_count < 1:
            raise ValueError("invalid Maix VideoRecorder capture configuration")
        self.directory = Path(directory)
        self.width = width
        self.height = height
        self.fps = fps
        self.bitrate = bitrate
        self.recording_enabled = recording_enabled
        self.snapshot_width = snapshot_width
        self.snapshot_height = snapshot_height
        self.buffer_count = buffer_count
        self._camera = None
        self._recorder = None
        self._active_path = self.directory / "active-recording.mp4"

    def _start_camera(self) -> None:
        if self._camera is not None:
            return
        from maix import camera, image

        self.directory.mkdir(parents=True, exist_ok=True)
        self._camera = camera.Camera(
            self.width,
            self.height,
            image.Format.FMT_YVU420SP,
            fps=self.fps,
            buff_num=self.buffer_count,
        )
        if self.recording_enabled:
            self._open_recorder()

    def _open_recorder(self) -> None:
        """Create one vendor recorder, binding its Camera *before* config.

        The MaixPy binding explicitly requires this order.  Keeping it here
        prevents a harmless configuration typo from wedging the native media
        stack before the Edge has connected to Runtime.
        """

        from maix import image, video

        self._active_path.unlink(missing_ok=True)
        recorder = video.VideoRecorder(open=False)
        recorder.bind_camera(self._camera)
        recorder.config_resolution([self.width, self.height])
        recorder.config_fps(self.fps)
        recorder.config_bitrate(self.bitrate)
        recorder.config_path(str(self._active_path))
        if self.snapshot_width is not None and self.snapshot_height is not None:
            recorder.config_snapshot(
                True,
                [self.snapshot_width, self.snapshot_height],
                image.Format.FMT_RGB888,
            )
        recorder.open()
        recorder.record_start()
        self._recorder = recorder

    def read_frame(self) -> CapturedCameraFrame:
        self._start_camera()
        if self._recorder is not None:
            frame = self._recorder.snapshot()
        else:
            frame = self._camera.read(block=True, block_ms=3000)
        if frame is None:
            raise RuntimeError("MaixCAM capture timed out")
        return CapturedCameraFrame(captured_at=_utc_timestamp(), frame=frame)

    def seal_recording(self, *, start_at: str, end_at: str) -> EncodedMediaSegment:
        if self._recorder is None:
            raise RuntimeError("Maix VideoRecorder is not enabled")
        self._recorder.record_finish()
        try:
            body = self._active_path.read_bytes()
        finally:
            self._active_path.unlink(missing_ok=True)
        # A fresh recorder keeps the already-bound Camera as the only sensor
        # owner while giving every Hot Ring segment a finalized MP4 container.
        self._recorder.close()
        self._recorder = None
        self._open_recorder()
        return EncodedMediaSegment(
            start_at=start_at,
            end_at=end_at,
            body=body,
            mime_type="video/mp4",
        )

    def close(self) -> None:
        if self._recorder is not None:
            try:
                self._recorder.record_finish()
            except Exception:
                pass
            try:
                self._recorder.close()
            finally:
                self._recorder = None
        self._active_path.unlink(missing_ok=True)
        if self._camera is not None:
            try:
                self._camera.close()
            finally:
                self._camera = None


class MaixVideoRecorderSegmentRecorder:
    """Seal bounded Hot Ring MP4s from a bound ``VideoRecorder``."""

    def __init__(
        self,
        *,
        capture_owner: MaixVideoRecorderCaptureOwner,
        segment_seconds: float = 2.0,
        enabled: bool = True,
    ) -> None:
        if segment_seconds < 2:
            raise ValueError("segment_seconds must be at least two seconds")
        self.capture_owner = capture_owner
        self.segment_seconds = segment_seconds
        self.enabled = enabled
        self._segment_started_at: str | None = None

    def consume(self, captured: CapturedCameraFrame) -> list[EncodedMediaSegment]:
        if not self.enabled:
            return []
        if self._segment_started_at is None:
            self._segment_started_at = captured.captured_at
            return []
        started = datetime.fromisoformat(self._segment_started_at.replace("Z", "+00:00"))
        current = datetime.fromisoformat(captured.captured_at.replace("Z", "+00:00"))
        if (current - started).total_seconds() < self.segment_seconds:
            return []
        segment = self.capture_owner.seal_recording(
            start_at=self._segment_started_at,
            end_at=captured.captured_at,
        )
        self._segment_started_at = captured.captured_at
        return [segment]

    def close(self) -> None:
        self._segment_started_at = None


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


class MaixBoundEncoderCaptureOwner:
    """One Camera bound to Maix's hardware Encoder.

    The Encoder becomes the only component that reads from the physical Camera:
    ``encode()`` yields the H.264 stream and ``capture()`` yields the locally
    consumed image.  This is the vendor-supported alternative to asking
    ``Camera.read()`` and a separate Encoder to compete for the same buffers.
    """

    def __init__(
        self,
        *,
        width: int = 640,
        height: int = 480,
        fps: int = 5,
        bitrate: int = 1_000_000,
        buffer_count: int = 2,
    ) -> None:
        if width <= 0 or height <= 0 or fps <= 0 or bitrate <= 0 or buffer_count < 1:
            raise ValueError("invalid Maix bound-encoder capture configuration")
        self.width = width
        self.height = height
        self.fps = fps
        self.bitrate = bitrate
        self.buffer_count = buffer_count
        self._camera = None
        self._encoder = None

    def _start(self) -> None:
        if self._encoder is not None:
            return
        from maix import camera, image, video

        self._camera = camera.Camera(
            self.width,
            self.height,
            image.Format.FMT_YVU420SP,
            fps=self.fps,
            buff_num=self.buffer_count,
        )
        self._encoder = video.Encoder(
            width=self.width,
            height=self.height,
            format=image.Format.FMT_YVU420SP,
            type=video.VideoType.VIDEO_H264_CBR,
            framerate=self.fps,
            gop=self.fps,
            bitrate=self.bitrate,
            capture=True,
        )
        self._encoder.bind_camera(self._camera)

    def read_frame(self) -> CapturedCameraFrame:
        self._start()
        encoded = self._encoder.encode()
        frame = self._encoder.capture()
        if encoded is None or frame is None:
            raise RuntimeError("Maix bound encoder produced no frame")
        return CapturedCameraFrame(
            captured_at=_utc_timestamp(),
            frame=frame,
            # Copy native packet bytes before the next Encoder call may reuse
            # its backing buffer.  Codec-parameter admission is handled by the
            # segmenter, not by this Frame copy flag.
            encoded_body=encoded.to_bytes(True),
        )

    def close(self) -> None:
        self._encoder = None
        gc.collect()
        if self._camera is not None:
            try:
                self._camera.close()
            finally:
                self._camera = None


class MaixBoundEncoderSegmentRecorder:
    """Seal independently decodable MP4s from bound-Encoder H.264 output.

    A continuous H.264 stream may begin a time-based chunk on a P-frame.  The
    segmenter therefore caches SPS/PPS and admits a new file only at an IDR;
    it closes the prior file only when a later IDR arrives after the requested
    duration.  Every file starts with the cached parameters plus an IDR.
    """

    def __init__(
        self,
        *,
        directory: Path,
        fps: int,
        segment_seconds: float = 2.0,
        enabled: bool = True,
    ) -> None:
        if fps <= 0 or segment_seconds < 2:
            raise ValueError("invalid bound-encoder segment configuration")
        self.directory = Path(directory)
        self.fps = fps
        self.segment_seconds = segment_seconds
        self.enabled = enabled
        self._encoded_file = None
        self._segment_path: Path | None = None
        self._segment_started_at: str | None = None
        self._parameter_sets: dict[int, bytes] = {}
        self._pending: deque[_PendingH264Segment] = deque()
        self.directory.mkdir(parents=True, exist_ok=True)

    def consume(self, captured: CapturedCameraFrame) -> list[EncodedMediaSegment]:
        if not self.enabled:
            return []
        if captured.encoded_body is None:
            raise RuntimeError("bound encoder capture did not supply H.264 bytes")
        access_units = _h264_annex_b_units(captured.encoded_body)
        for nal_type, unit in access_units:
            if nal_type in (7, 8):  # SPS / PPS
                self._parameter_sets[nal_type] = unit
        has_idr = any(nal_type == 5 for nal_type, _unit in access_units)

        # Without SPS/PPS an H.264 slice cannot be independently decoded. Do
        # not create a misleading Hot Ring candidate from a P-frame stream.
        if self._encoded_file is None:
            if not has_idr or not self._has_parameter_sets():
                return []
            self._open_segment(captured.captured_at)
            self._write_segment_start(captured.encoded_body)
            return []

        started = datetime.fromisoformat(self._segment_started_at.replace("Z", "+00:00"))
        current = datetime.fromisoformat(captured.captured_at.replace("Z", "+00:00"))
        if has_idr and (current - started).total_seconds() >= self.segment_seconds:
            self._queue_segment(captured.captured_at)
            self._open_segment(captured.captured_at)
            self._write_segment_start(captured.encoded_body)
            return []

        self._encoded_file.write(captured.encoded_body)
        return []

    def _has_parameter_sets(self) -> bool:
        return 7 in self._parameter_sets and 8 in self._parameter_sets

    def _write_segment_start(self, body: bytes) -> None:
        assert self._encoded_file is not None
        # Keep deterministic SPS/PPS order ahead of the IDR.  The packet may
        # also contain them; duplicate sequence parameters are valid Annex-B.
        self._encoded_file.write(self._parameter_sets[7])
        self._encoded_file.write(self._parameter_sets[8])
        self._encoded_file.write(body)

    def _open_segment(self, captured_at: str) -> None:
        filename = f"bound-{captured_at.replace(':', '').replace('+', '').replace('.', '')}.h264"
        self._segment_path = self.directory / filename
        self._encoded_file = self._segment_path.open("wb")
        self._segment_started_at = captured_at

    def _queue_segment(self, ended_at: str) -> None:
        assert self._encoded_file is not None and self._segment_path is not None
        self._encoded_file.close()
        self._pending.append(
            _PendingH264Segment(
                start_at=self._segment_started_at,
                end_at=ended_at,
                raw_path=self._segment_path,
            )
        )
        self._encoded_file = None
        self._segment_path = None
        self._segment_started_at = None

    def pop_pending_segment(self):
        return self._pending.popleft() if self._pending else None

    def package_pending_segment(self, pending) -> EncodedMediaSegment:
        """Run ffmpeg only on a previously closed raw segment."""

        raw_path = pending.raw_path
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
        return EncodedMediaSegment(start_at=pending.start_at, end_at=pending.end_at, body=body)

    def close(self) -> None:
        if self._encoded_file is not None:
            self._encoded_file.close()
            self._encoded_file = None
        if self._segment_path is not None:
            self._segment_path.unlink(missing_ok=True)
            self._segment_path = None
        while self._pending:
            self._pending.popleft().raw_path.unlink(missing_ok=True)
        self._segment_started_at = None


@dataclass(frozen=True, slots=True)
class _PendingH264Segment:
    start_at: str
    end_at: str
    raw_path: Path


def _h264_annex_b_units(body: bytes) -> list[tuple[int, bytes]]:
    """Return ``(NAL type, complete Annex-B unit)`` entries from one packet."""

    starts: list[tuple[int, int]] = []
    index = 0
    while index + 3 < len(body):
        if body[index:index + 4] == b"\x00\x00\x00\x01":
            starts.append((index, 4))
            index += 4
        elif body[index:index + 3] == b"\x00\x00\x01":
            starts.append((index, 3))
            index += 3
        else:
            index += 1
    units: list[tuple[int, bytes]] = []
    for position, (start, prefix_length) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(body)
        unit = body[start:end]
        if len(unit) > prefix_length:
            units.append((unit[prefix_length] & 0x1F, unit))
    return units
