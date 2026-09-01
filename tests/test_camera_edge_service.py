import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from device_edge.camera.camera_edge_service import CameraEdgeService
from device_edge.camera.camera_edge_service import CapturedCameraFrame
from device_edge.camera.camera_edge_service import EncodedMediaSegment
from device_edge.media_memory import LocalHotRing
from device_edge.media_memory import MEDIA_MEMORY_QUERY_CAPABILITY
from device_edge.media_memory import MediaMemoryActionExecutor
from device_edge.media_memory import MEDIA_PROVIDER_CONFIGURE_CAPABILITY


SOURCE = "camera-edge-1/camera.main/camera.capture/video"


class _CaptureOwner:
    def __init__(self):
        self.calls = 0
        self.closed = False

    async def read_frame(self):
        self.calls += 1
        return CapturedCameraFrame("2026-09-01T10:00:00Z", f"raw-frame-{self.calls}")

    def close(self):
        self.closed = True


class _SegmentRecorder:
    def __init__(self):
        self.frames = []

    def consume(self, captured):
        self.frames.append(captured.frame)
        return [EncodedMediaSegment("2026-09-01T10:00:00Z", "2026-09-01T10:00:02Z", b"encoded-local-video")]


class _FeatureWorker:
    def __init__(self):
        self.frames = []

    async def observe(self, captured):
        self.frames.append(captured.frame)
        return [{"name": "camera.person_presence.v1", "value": {"state": "present"}}]


def test_single_process_service_fans_one_capture_to_local_encoder_and_features():
    async def scenario():
        with TemporaryDirectory() as directory:
            capture = _CaptureOwner()
            recorder = _SegmentRecorder()
            feature = _FeatureWorker()
            observations = []
            ring = LocalHotRing(source_ref=SOURCE, directory=Path(directory), retention_seconds=86_400, max_bytes=1024)
            executor = MediaMemoryActionExecutor(device_id="camera-edge-1", hot_ring=ring, understanding_provider=lambda *_args: {"markdown": "ok", "model": "test", "limitations": []})
            service = CameraEdgeService(capture_owner=capture, segment_recorder=recorder, hot_ring=ring, media_query_executor=executor, feature_worker=feature, observation_sink=lambda values: observations.extend(values))
            await service.capture_once()
            selection = ring.select(start_at="2026-09-01T10:00:00Z", end_at="2026-09-01T10:00:02Z")
            await service.stop()
            return capture, recorder, feature, observations, selection

    capture, recorder, feature, observations, selection = asyncio.run(scenario())
    assert recorder.frames == ["raw-frame-1"]
    assert feature.frames == ["raw-frame-1"]
    assert observations == [{"name": "camera.person_presence.v1", "value": {"state": "present"}}]
    assert selection is not None
    assert capture.closed is True


def test_media_query_waits_in_separate_queue_while_capture_keeps_progressing():
    async def scenario():
        with TemporaryDirectory() as directory:
            results = []
            started = asyncio.Event()
            release = asyncio.Event()

            async def provider(_selection, _question, _ring):
                started.set()
                await release.wait()
                return {"markdown": "## Answer\nLocal result", "model": "async-test", "limitations": []}

            ring = LocalHotRing(source_ref=SOURCE, directory=Path(directory), retention_seconds=86_400, max_bytes=1024)
            service = CameraEdgeService(
                capture_owner=_CaptureOwner(), segment_recorder=_SegmentRecorder(), hot_ring=ring,
                media_query_executor=MediaMemoryActionExecutor(device_id="camera-edge-1", hot_ring=ring, understanding_provider=provider),
                action_result_sink=results.append,
            )
            await service.start()
            await service.capture_once()
            accepted = await service.submit_action_request({"type": "action_request", "device_id": "camera-edge-1", "request_id": "q1", "action": {"capability": MEDIA_MEMORY_QUERY_CAPABILITY, "payload": {"source_ref": SOURCE, "start_at": "2026-09-01T10:00:00Z", "end_at": "2026-09-01T10:00:02Z", "question": "What happened?"}}})
            await started.wait()
            await service.capture_once()
            release.set()
            for _ in range(10):
                if results:
                    break
                await asyncio.sleep(0)
            await service.stop()
            return accepted, results

    accepted, results = asyncio.run(scenario())
    assert accepted is True
    assert results[0]["result"]["payload"]["understanding"]["markdown"] == "## Answer\nLocal result"
    assert "encoded-local-video" not in str(results)


def test_service_routes_provider_key_action_without_returning_the_key():
    async def scenario():
        with TemporaryDirectory() as directory:
            results = []
            ring = LocalHotRing(source_ref=SOURCE, directory=Path(directory), retention_seconds=86_400, max_bytes=1024)
            service = CameraEdgeService(
                capture_owner=_CaptureOwner(), segment_recorder=_SegmentRecorder(), hot_ring=ring,
                media_query_executor=MediaMemoryActionExecutor(device_id="camera-edge-1", hot_ring=ring, understanding_provider=lambda *_args: {"markdown": "ok", "model": "test", "limitations": []}),
                action_result_sink=results.append,
            )
            await service.start()
            await service.submit_action_request({"type": "action_request", "device_id": "camera-edge-1", "action": {"capability": MEDIA_PROVIDER_CONFIGURE_CAPABILITY, "payload": {"provider": {"name": "gemini", "adapter_type": "gemini", "base_url": "https://example.test", "wire_api": "generateContent", "api_key": "private-key", "timeout_seconds": 30, "default_headers": {}}, "model": {"name": "video-test", "model_id": "video-test", "supports_vision": True, "supports_video": True}}}})
            for _ in range(10):
                if results:
                    break
                await asyncio.sleep(0)
            configured = service.provider_credentials.profile_for(provider="gemini", model="video-test")["provider"]["api_key"]
            await service.stop()
            return results, configured

    results, configured = asyncio.run(scenario())
    assert configured == "private-key"
    assert results[0]["result"]["details"]["state"] == "configured"
    assert "private-key" not in str(results)


def test_service_returns_diagnostic_result_when_media_worker_raises():
    async def scenario():
        with TemporaryDirectory() as directory:
            results = []
            ring = LocalHotRing(source_ref=SOURCE, directory=Path(directory), retention_seconds=86_400, max_bytes=1024)

            class FailingExecutor:
                hot_ring = ring

                async def handle_action_request_async(self, _frame):
                    raise RuntimeError("provider exploded")

            service = CameraEdgeService(
                capture_owner=_CaptureOwner(), segment_recorder=_SegmentRecorder(), hot_ring=ring,
                media_query_executor=FailingExecutor(), action_result_sink=results.append,
            )
            await service.start()
            await service.submit_action_request({"type": "action_request", "device_id": "camera-edge-1", "request_id": "q2", "action": {"capability": MEDIA_MEMORY_QUERY_CAPABILITY, "payload": {}}})
            for _ in range(10):
                if results:
                    break
                await asyncio.sleep(0)
            await service.stop()
            return results

    results = asyncio.run(scenario())
    assert results[0]["result"]["reason"] == "media_action_failed"
