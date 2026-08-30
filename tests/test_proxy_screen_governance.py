import hashlib
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

from device_edge.proxy.adapter import AdapterProbe
from device_edge.proxy.adapter import ProxyAdapterError
from device_edge.proxy.contracts import CapabilityAvailability
from device_edge.proxy.contracts import CapturedFrame
from device_edge.proxy.edge import ProxyInteractionEdge
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.runtime_state import RuntimeState


class BytesProxyAdapter:
    adapter_id = "bytes-proxy"
    adapter_kind = "test"
    requirements = ()
    supported_target_classes = frozenset({"desktop"})

    def __init__(self, body=b"bounded-private-jpeg"):
        self.body = body
        self.digest = hashlib.sha256(body).hexdigest()
        self.ref = f"proxy-evidence://bytes-proxy/screen/{self.digest[:24]}"
        self.capture_count = 0

    def probe(self):
        return AdapterProbe(
            {
                "screen": CapabilityAvailability("available"),
                "audio": CapabilityAvailability("unavailable", "not_supported"),
                "keyboard": CapabilityAvailability("available"),
                "pointer": CapabilityAvailability("available"),
                "virtual_media": CapabilityAvailability("unavailable", "not_supported"),
                "power": CapabilityAvailability("unavailable", "not_supported"),
            },
            {},
        )

    def capture_frame(self):
        self.capture_count += 1
        return CapturedFrame(
            evidence_ref=self.ref,
            captured_at="2026-08-30T08:30:00Z",
            width=1280,
            height=720,
            mime_type="image/jpeg",
            size_bytes=len(self.body),
            sha256=self.digest,
        )

    def read_evidence(self, evidence_ref, max_bytes):
        if evidence_ref != self.ref or len(self.body) > max_bytes:
            raise ProxyAdapterError("evidence_unavailable")
        return self.body

    def execute_keyboard(self, payload):
        return {"ok": True}

    def execute_pointer(self, payload):
        return {"ok": True}


def build_edge(body=b"bounded-private-jpeg"):
    adapter = BytesProxyAdapter(body)
    return ProxyInteractionEdge(
        device_id="proxy-edge-1",
        audience="ws://runtime.example.test:8765",
        target_id="desktop-1",
        surface_id="main",
        target_class="desktop",
        adapter=adapter,
        observed_at="2026-08-30T08:30:00Z",
    ), adapter


def read_request(max_bytes=98_304):
    return {
        "type": "action_request",
        "device_id": "proxy-edge-1",
        "request_id": "screen-read-1",
        "action": {
            "capability": "proxy.screen.read",
            "payload": {
                "target_id": "desktop-1",
                "surface_id": "main",
                "freshness": "latest",
                "max_bytes": max_bytes,
            },
        },
    }


class ProxyScreenReadTests(unittest.TestCase):
    def test_base_observations_reach_context_facts_without_profile(self):
        edge, _ = build_edge()
        state = RuntimeState()
        state.register_device("proxy-edge-1", "proxy-interaction")
        for capability in edge.build_capability_announce_frame()["capabilities"]:
            state.register_capability("proxy-edge-1", capability)
        gateway = RuntimeGateway(state=state, persist_state=False)

        replies = gateway.run_roundtrip([edge.build_screen_base_observation_frame()])

        self.assertEqual(replies[0]["type"], "event_ack")
        self.assertIn("proxy-edge-1/proxy.screen.capture_health.v1", gateway.state.context_facts)

    def test_screen_read_registration_advertises_latest_and_cached_evidence(self):
        edge, _ = build_edge()
        registration = next(
            item
            for item in edge.build_capability_announce_frame()["capabilities"]
            if item["name"] == "proxy.screen.read"
        )

        self.assertEqual(
            registration["input_schema"]["properties"]["freshness"]["enum"],
            ["latest", "cached"],
        )
        self.assertEqual(
            registration["input_schema"]["properties"]["evidence_id"]["maxLength"],
            256,
        )

    def test_screen_read_is_one_normal_action_result_and_runtime_never_persists_jpeg(self):
        edge, adapter = build_edge()
        action_result = edge.handle_action_request(read_request())
        payload = action_result["result"]["payload"]
        self.assertEqual(action_result["result"]["capability"], "proxy.screen.read")
        self.assertEqual(payload["mime_type"], "image/jpeg")
        self.assertIn("jpeg_bytes", payload)

        gateway = RuntimeGateway(
            persist_state=False,
            proxy_screen_vision_evaluator=lambda _body, _attachment: {
                "summary": "A desktop is visible.",
                "labels": ["desktop"],
                "confidence": 0.9,
            },
        )
        gateway.run_roundtrip([action_result])

        recorded = gateway.state.action_results[-1]
        serialized = json.dumps({"results": gateway.state.action_results, "events": gateway.state.events})
        self.assertNotIn("jpeg_bytes", recorded["payload"])
        self.assertEqual(
            recorded["payload"]["evidence_id"],
            payload["evidence_id"],
        )
        self.assertEqual(
            recorded["payload"]["attachment"]["evidence_id"],
            payload["evidence_id"],
        )
        self.assertEqual(recorded["payload"]["visual_understanding"]["summary"], "A desktop is visible.")
        self.assertNotIn(adapter.body.decode("ascii"), serialized)

    def test_screen_read_enforces_edge_byte_bound(self):
        edge, _ = build_edge(b"x" * 98_305)
        result = edge.handle_action_request(read_request())
        self.assertEqual(result["result"]["status"], "error")
        self.assertEqual(result["result"]["reason"], "evidence_unavailable")

    def test_screen_read_rejects_non_latest_request(self):
        edge, _ = build_edge()
        request = read_request()
        request["action"]["payload"]["freshness"] = "cached"
        result = edge.handle_action_request(request)
        self.assertEqual(result["result"]["reason"], "invalid_evidence_id")

    def test_screen_read_cached_replays_the_same_edge_frame_without_capture(self):
        edge, adapter = build_edge()
        latest = edge.handle_action_request(read_request())
        evidence_id = latest["result"]["payload"]["evidence_id"]

        request = read_request()
        request["request_id"] = "screen-read-cached"
        request["action"]["payload"].update(
            {"freshness": "cached", "evidence_id": evidence_id}
        )
        cached = edge.handle_action_request(request)

        self.assertEqual(adapter.capture_count, 1)
        self.assertEqual(cached["result"]["status"], "ok")
        self.assertEqual(cached["result"]["payload"]["evidence_id"], evidence_id)
        self.assertEqual(
            cached["result"]["payload"]["jpeg_bytes"],
            latest["result"]["payload"]["jpeg_bytes"],
        )

    def test_cached_read_fails_closed_on_edge_sha_mismatch(self):
        edge, adapter = build_edge()
        latest = edge.handle_action_request(read_request())

        adapter.body = b"x" * len(adapter.body)
        request = read_request()
        request["action"]["payload"].update(
            {
                "freshness": "cached",
                "evidence_id": latest["result"]["payload"]["evidence_id"],
            }
        )

        result = edge.handle_action_request(request)

        self.assertEqual(result["result"]["status"], "error")
        self.assertEqual(result["result"]["reason"], "evidence_integrity_mismatch")
        self.assertEqual(adapter.capture_count, 1)

    def test_persisted_runtime_state_never_contains_screen_jpeg(self):
        edge, adapter = build_edge()
        action_result = edge.handle_action_request(read_request())

        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.sqlite3"
            gateway = RuntimeGateway(
                state_path=state_path,
                persist_state=True,
                proxy_screen_vision_evaluator=lambda _body, _attachment: {
                    "summary": "A desktop is visible.",
                    "labels": ["desktop"],
                    "confidence": 0.9,
                },
            )
            try:
                gateway.run_roundtrip([action_result])
                persisted_bytes = b"".join(
                    path.read_bytes()
                    for path in Path(directory).glob("state.sqlite3*")
                )
            finally:
                gateway.state_store.close()

            self.assertNotIn(adapter.body, persisted_bytes)
