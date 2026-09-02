"""Single-process Camera Edge data-plane service.

``CameraEdgeService`` is the only owner of live camera frames.  Its one
asyncio event loop fans a frame out to an encoder/segmenter and a sampled local
Feature worker, while a separate bounded action queue waits for slow media
understanding providers.  No raw frame or encoded segment is put on the Edge
Session Link by this service.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Awaitable
from typing import Callable

try:
    from device_edge.media_memory import InMemoryMediaProviderCredentials
    from device_edge.media_memory import LocalHotRing
    from device_edge.media_memory import MediaMemoryActionExecutor
    from device_edge.media_memory import MEDIA_PROVIDER_CONFIGURE_CAPABILITY
except ImportError:  # pragma: no cover - copied MaixCAM files.
    from media_memory import InMemoryMediaProviderCredentials
    from media_memory import LocalHotRing
    from media_memory import MediaMemoryActionExecutor
    from media_memory import MEDIA_PROVIDER_CONFIGURE_CAPABILITY


@dataclass(frozen=True, slots=True)
class CapturedCameraFrame:
    """Opaque frame retained only for one capture-loop iteration."""

    captured_at: str
    frame: object
    encoded_body: bytes | None = None


@dataclass(frozen=True, slots=True)
class EncodedMediaSegment:
    start_at: str
    end_at: str
    body: bytes
    mime_type: str = "video/mp4"


class CameraEdgeService:
    """Coordinate local capture, Features, Hot Ring, and media-query jobs.

    ``capture_owner.read_frame`` is the sole point that may access a physical
    camera. ``segment_recorder.consume`` and ``feature_worker.observe`` receive
    the same ephemeral frame. They must return promptly or cooperatively await;
    slow cloud understanding is deliberately isolated in ``_action_worker``.
    """

    def __init__(
        self,
        *,
        capture_owner,
        segment_recorder,
        hot_ring: LocalHotRing,
        media_query_executor: MediaMemoryActionExecutor,
        feature_worker=None,
        observation_sink: Callable[[list[dict]], Awaitable[None] | None] | None = None,
        action_result_sink: Callable[[dict], Awaitable[None] | None] | None = None,
        feature_interval_seconds: float = 1.0,
        capture_interval_seconds: float = 0.0,
        action_queue_size: int = 4,
        provider_credentials: InMemoryMediaProviderCredentials | None = None,
    ) -> None:
        if feature_interval_seconds <= 0 or capture_interval_seconds < 0:
            raise ValueError("CameraEdgeService intervals are invalid.")
        if action_queue_size < 1:
            raise ValueError("CameraEdgeService action_queue_size must be positive.")
        if media_query_executor.hot_ring is not hot_ring:
            raise ValueError("Media query executor must use this service Hot Ring.")
        self.capture_owner = capture_owner
        self.segment_recorder = segment_recorder
        self.hot_ring = hot_ring
        self.media_query_executor = media_query_executor
        self.feature_worker = feature_worker
        self.observation_sink = observation_sink
        self.action_result_sink = action_result_sink
        self.feature_interval_seconds = feature_interval_seconds
        self.capture_interval_seconds = capture_interval_seconds
        self._action_queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=action_queue_size)
        self.provider_credentials = provider_credentials or InMemoryMediaProviderCredentials()
        self._action_worker_task: asyncio.Task | None = None
        self._segment_worker_task: asyncio.Task | None = None
        self._next_feature_at = 0.0
        self._closed = False

    async def start(self) -> None:
        if self._action_worker_task is None:
            self._action_worker_task = asyncio.create_task(self._action_worker())
        if self._segment_worker_task is None and hasattr(self.segment_recorder, "pop_pending_segment"):
            self._segment_worker_task = asyncio.create_task(self._segment_worker())

    async def stop(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._action_worker_task is not None:
            await self._action_queue.put(None)
            await self._action_worker_task
            self._action_worker_task = None
        if self._segment_worker_task is not None:
            await self._segment_worker_task
            self._segment_worker_task = None
        close = getattr(self.capture_owner, "close", None)
        if callable(close):
            await _maybe_await(close())
        close_recorder = getattr(self.segment_recorder, "close", None)
        if callable(close_recorder):
            await _maybe_await(close_recorder())
        close_feature_worker = getattr(self.feature_worker, "close", None)
        if callable(close_feature_worker):
            await _maybe_await(close_feature_worker())

    async def capture_once(self) -> int:
        """Capture exactly one frame and fan it out locally.

        Returns the number of sealed encoded segments admitted to the Hot Ring.
        The opaque frame is released before this coroutine returns.
        """

        if self._closed:
            raise RuntimeError("CameraEdgeService is closed.")
        captured = await _maybe_await(self.capture_owner.read_frame())
        if not isinstance(captured, CapturedCameraFrame):
            raise ValueError("Capture owner must return CapturedCameraFrame.")
        try:
            segments = await _maybe_await(self.segment_recorder.consume(captured))
            if not isinstance(segments, list) or not all(isinstance(item, EncodedMediaSegment) for item in segments):
                raise ValueError("Segment recorder must return EncodedMediaSegment items.")
            for segment in segments:
                self.hot_ring.append_segment(
                    start_at=segment.start_at,
                    end_at=segment.end_at,
                    body=segment.body,
                    mime_type=segment.mime_type,
                )
            now = asyncio.get_running_loop().time()
            if self.feature_worker is not None and now >= self._next_feature_at:
                observations = await _maybe_await(self.feature_worker.observe(captured))
                if not isinstance(observations, list) or not all(isinstance(item, dict) for item in observations):
                    raise ValueError("Feature worker must return Observation dictionaries.")
                await self._emit_observations(observations)
                self._next_feature_at = now + self.feature_interval_seconds
            return len(segments)
        finally:
            # Neither queue nor service state owns raw frame references.
            del captured

    async def run(self, stop_event: asyncio.Event, *, max_frames: int | None = None) -> int:
        """Run capture until asked to stop, in this one process/event loop."""

        await self.start()
        captured_frames = 0
        try:
            while not stop_event.is_set() and (max_frames is None or captured_frames < max_frames):
                await self.capture_once()
                captured_frames += 1
                if self.capture_interval_seconds:
                    await asyncio.sleep(self.capture_interval_seconds)
                else:
                    await asyncio.sleep(0)
            return captured_frames
        finally:
            await self.stop()

    async def submit_action_request(self, frame: dict) -> bool:
        """Queue a Gateway-delivered action without blocking camera capture."""

        if self._closed or self._action_worker_task is None:
            raise RuntimeError("CameraEdgeService must be started before actions are submitted.")
        try:
            self._action_queue.put_nowait(dict(frame))
            return True
        except asyncio.QueueFull:
            return False

    async def _action_worker(self) -> None:
        while True:
            frame = await self._action_queue.get()
            if frame is None:
                return
            action = frame.get("action", {})
            try:
                if action.get("capability") == MEDIA_PROVIDER_CONFIGURE_CAPABILITY:
                    result = self.provider_credentials.handle_action_request(frame)
                else:
                    result = await self.media_query_executor.handle_action_request_async(frame)
            except Exception:
                result = {
                    "api_version": "edge.runtime.v2",
                    "type": "action_result",
                    "device_id": frame.get("device_id"),
                    "result": {
                        "status": "error",
                        "capability": action.get("capability", "unknown"),
                        "reason": "media_action_failed",
                    },
                }
            if self.action_result_sink is not None:
                await _maybe_await(self.action_result_sink(result))

    async def _segment_worker(self) -> None:
        """Package closed H.264 chunks without stalling Camera capture."""

        while True:
            pending = self.segment_recorder.pop_pending_segment()
            if pending is None:
                if self._closed:
                    return
                await asyncio.sleep(0.02)
                continue
            try:
                segment = await asyncio.to_thread(
                    self.segment_recorder.package_pending_segment,
                    pending,
                )
                self.hot_ring.append_segment(
                    start_at=segment.start_at,
                    end_at=segment.end_at,
                    body=segment.body,
                    mime_type=segment.mime_type,
                )
            except Exception:
                # Segment loss must not crash Camera capture or its Gateway
                # control link; the next IDR still starts a fresh candidate.
                continue

    async def _emit_observations(self, observations: list[dict]) -> None:
        if observations and self.observation_sink is not None:
            await _maybe_await(self.observation_sink(observations))


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value
