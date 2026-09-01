import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import types
import unittest

if os.name == "nt" and "fcntl" not in sys.modules:
    sys.modules["fcntl"] = types.SimpleNamespace(
        LOCK_EX=0, LOCK_UN=0, flock=lambda *_args, **_kwargs: None
    )

from device_edge.camera.health_daemon import CameraHealthDaemon
from device_edge.media_memory import LocalHotRing
from device_edge.media_memory import MEDIA_MEMORY_QUERY_CAPABILITY
from device_edge.media_memory import MediaMemoryActionExecutor
from device_edge.media_memory import InMemoryMediaProviderCredentials
from device_edge.media_memory import MEDIA_PROVIDER_CONFIGURE_CAPABILITY
from personal_runtime.gateway_server import RuntimeGateway


SOURCE_REF = "camera-edge-1/camera.main/camera.capture/video"


class _Client:
    device_id = "camera-edge-1"


class EdgeMediaMemoryTests(unittest.TestCase):
    def test_query_contract_exposes_canonical_source_ref(self):
        from device_edge.media_memory import media_memory_query_capability

        contract = media_memory_query_capability(SOURCE_REF)
        self.assertEqual(contract["source_ref"], SOURCE_REF)

    def _executor(self, directory: Path):
        ring = LocalHotRing(
            source_ref=SOURCE_REF,
            directory=directory,
            retention_seconds=86_400,
            max_bytes=128,
        )
        ring.append_segment(
            start_at="2026-09-01T10:00:00Z",
            end_at="2026-09-01T10:00:10Z",
            body=b"local-video-a",
            mime_type="video/mp4",
        )
        observed = {}

        def provider(selection, question, local_ring):
            observed["selection"] = selection
            observed["question"] = question
            observed["body"] = local_ring.read_segment(selection.segments[0])
            return {
                "markdown": "## Understanding\nA person entered the room.",
                "model": "test-video-model",
                "limitations": ["single short segment"],
            }

        return MediaMemoryActionExecutor(
            device_id="camera-edge-1", hot_ring=ring, understanding_provider=provider
        ), observed

    @staticmethod
    def _request(**payload):
        return {
            "type": "action_request",
            "device_id": "camera-edge-1",
            "request_id": "memory-1",
            "action": {"capability": MEDIA_MEMORY_QUERY_CAPABILITY, "payload": payload},
        }

    def test_query_reads_local_segment_and_returns_only_textual_understanding(self):
        with TemporaryDirectory() as directory:
            executor, observed = self._executor(Path(directory))
            result = executor.handle_action_request(self._request(
                source_ref=SOURCE_REF,
                start_at="2026-09-01T10:00:00Z",
                end_at="2026-09-01T10:00:10Z",
                question="Who entered?",
            ))

        payload = result["result"]["payload"]
        self.assertEqual(result["result"]["status"], "ok")
        self.assertEqual(observed["body"], b"local-video-a")
        self.assertEqual(observed["question"], "Who entered?")
        self.assertEqual(payload["understanding"]["model"], "test-video-model")
        self.assertNotIn("local-video-a", json.dumps(result))
        self.assertNotIn("media_bytes", payload)

    def test_query_reports_missing_local_interval_without_calling_provider(self):
        with TemporaryDirectory() as directory:
            executor, observed = self._executor(Path(directory))
            result = executor.handle_action_request(self._request(
                source_ref=SOURCE_REF,
                start_at="2026-09-01T11:00:00Z",
                end_at="2026-09-01T11:00:10Z",
                question="What happened?",
            ))
        self.assertEqual(result["result"]["reason"], "media_interval_unavailable")
        self.assertEqual(observed, {})

    def test_hot_ring_rotates_oldest_segment_by_capacity(self):
        with TemporaryDirectory() as directory:
            ring = LocalHotRing(source_ref=SOURCE_REF, directory=Path(directory), retention_seconds=86_400, max_bytes=20)
            first = ring.append_segment(start_at="2026-09-01T10:00:00Z", end_at="2026-09-01T10:00:10Z", body=b"a" * 12, mime_type="video/mp4")
            ring.append_segment(start_at="2026-09-01T10:00:10Z", end_at="2026-09-01T10:00:20Z", body=b"b" * 12, mime_type="video/mp4")
            selection = ring.select(start_at="2026-09-01T10:00:00Z", end_at="2026-09-01T10:00:20Z")
            self.assertEqual([item.segment_id for item in selection.segments], [ring._segments[0].segment_id])
            self.assertFalse((Path(directory) / first.path).exists())

    def test_camera_advertises_and_executes_media_query_only_when_configured(self):
        with TemporaryDirectory() as directory:
            executor, _ = self._executor(Path(directory))
            daemon = CameraHealthDaemon(
                client=_Client(), status_store=_StatusStore(), interval_seconds=60, min_free_mib=0,
                media_memory_executor=executor,
            )
            registrations = {item["name"] for item in daemon.capabilities}
            self.assertIn(MEDIA_MEMORY_QUERY_CAPABILITY, registrations)
            response = daemon.handle_action_request(self._request(
                source_ref=SOURCE_REF, start_at="2026-09-01T10:00:00Z", end_at="2026-09-01T10:00:10Z", question="What happened?",
            ))
        self.assertEqual(response["result"]["status"], "ok")

    def test_runtime_persists_understanding_but_never_a_local_media_body(self):
        with TemporaryDirectory() as directory:
            executor, _ = self._executor(Path(directory))
            result = executor.handle_action_request(self._request(
                source_ref=SOURCE_REF,
                start_at="2026-09-01T10:00:00Z",
                end_at="2026-09-01T10:00:10Z",
                question="What happened?",
            ))
            gateway = RuntimeGateway(persist_state=False)
            gateway.run_roundtrip([result])
        stored = json.dumps(gateway.state.action_results)
        self.assertIn("A person entered the room.", stored)
        self.assertNotIn("local-video-a", stored)

    def test_provider_key_action_is_kept_only_locally_and_not_echoed(self):
        credentials = InMemoryMediaProviderCredentials()
        key = "provider-key-keep-private"
        result = credentials.handle_action_request({
            "type": "action_request", "device_id": "camera-edge-1", "request_id": "provider-1",
            "action": {"capability": MEDIA_PROVIDER_CONFIGURE_CAPABILITY, "payload": {"provider": {"name": "gemini", "adapter_type": "gemini", "base_url": "https://example.test", "wire_api": "generateContent", "api_key": key, "timeout_seconds": 30, "default_headers": {}}, "model": {"name": "video-test", "model_id": "video-test", "supports_vision": True, "supports_video": True}}},
        })
        profile = credentials.profile_for(provider="gemini", model="video-test")
        self.assertEqual(profile["provider"]["api_key"], key)
        self.assertEqual(result["result"]["details"]["state"], "configured")
        self.assertNotIn(key, json.dumps(result))


class _StatusStore:
    def write(self, _status):
        pass
