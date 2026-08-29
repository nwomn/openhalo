import hashlib
import json
import os
import sys
import types
import unittest

# The production Runtime runs on POSIX.  Keep this pure in-process protocol
# test runnable on the Windows development host without changing its pairing
# implementation or touching pairing storage.
if os.name == "nt" and "fcntl" not in sys.modules:
    sys.modules["fcntl"] = types.SimpleNamespace(
        LOCK_EX=0,
        LOCK_UN=0,
        flock=lambda *_args, **_kwargs: None,
    )

from device_edge.proxy.adapter import AdapterProbe
from device_edge.proxy.contracts import CapabilityAvailability
from device_edge.proxy.contracts import CapturedFrame
from device_edge.proxy.edge import ProxyInteractionEdge
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.proxy_screen_governance import ProxyScreenEvidenceService
from personal_runtime.runtime_state import RuntimeState


class BytesProxyAdapter:
    adapter_id = "bytes-proxy"
    adapter_kind = "test"
    requirements = ()
    supported_target_classes = frozenset({"desktop"})

    def __init__(self) -> None:
        self.body = b"bounded-private-jpeg"
        self.digest = hashlib.sha256(self.body).hexdigest()
        self.calls = []
        self.ref = f"proxy-evidence://bytes-proxy/screen/{self.digest[:24]}"

    def probe(self) -> AdapterProbe:
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

    def capture_frame(self) -> CapturedFrame:
        return CapturedFrame(
            evidence_ref=self.ref,
            captured_at="2026-08-29T13:00:00Z",
            width=1280,
            height=720,
            mime_type="image/jpeg",
            size_bytes=len(self.body),
            sha256=self.digest,
        )

    def read_evidence(self, evidence_ref: str, max_bytes: int) -> bytes:
        if evidence_ref != self.ref or len(self.body) > max_bytes:
            raise RuntimeError("evidence_unavailable")
        return self.body

    def execute_keyboard(self, payload: dict) -> dict:
        self.calls.append(("keyboard", payload))
        return {"ok": True}

    def execute_pointer(self, payload: dict) -> dict:
        self.calls.append(("pointer", payload))
        return {"ok": True}


def build_edge() -> tuple[ProxyInteractionEdge, BytesProxyAdapter]:
    adapter = BytesProxyAdapter()
    return (
        ProxyInteractionEdge(
            device_id="proxy-edge-1",
            audience="ws://runtime.example.test:8765",
            target_id="desktop-1",
            surface_id="main",
            target_class="desktop",
            adapter=adapter,
            observed_at="2026-08-29T13:00:00Z",
        ),
        adapter,
    )


def profile_request() -> dict:
    return {
        "type": "action_request",
        "device_id": "proxy-edge-1",
        "request_id": "profile-1",
        "action": {
            "capability": "proxy.screen.profile.configure",
            "payload": {
                "target_id": "desktop-1",
                "surface_id": "main",
                "profile_id": "desktop-control-v1",
                "revision": 1,
                "features": [
                    "proxy.screen.capture_health.v1",
                    "proxy.screen.change.v1",
                    "proxy.screen.action_effect.v1",
                ],
                "expires_at": "2099-08-29T13:00:00Z",
                "max_evidence_bytes": 1024,
                "visual_action_policy": "require_understanding",
            },
        },
    }


class ProxyScreenGovernanceTests(unittest.TestCase):
    def test_profile_selects_features_and_blocks_blind_hid(self) -> None:
        edge, adapter = build_edge()

        configured = edge.handle_action_request(profile_request())
        self.assertEqual(configured["result"]["status"], "ok")
        feature_frame = edge.build_screen_feature_observation_frame()
        self.assertIsNotNone(feature_frame)
        assert feature_frame is not None
        self.assertEqual(feature_frame["capability"], "proxy.screen.features")
        self.assertEqual(
            [item["name"] for item in feature_frame["observations"]],
            [
                "proxy.screen.capture_health.v1",
                "proxy.screen.change.v1",
            ],
        )
        blind = edge.handle_action_request(
            {
                "type": "action_request",
                "device_id": "proxy-edge-1",
                "request_id": "key-1",
                "action": {
                    "capability": "proxy.keyboard.input",
                    "payload": {
                        "target_id": "desktop-1",
                        "surface_id": "main",
                        "operation": "type",
                        "text": "blocked",
                    },
                },
            }
        )
        self.assertEqual(blind["result"]["reason"], "visual_understanding_required")
        self.assertEqual(adapter.calls, [])

    def test_bounded_transfer_becomes_expiring_understanding_without_media_persistence(self) -> None:
        edge, adapter = build_edge()
        edge.handle_action_request(profile_request())
        feature_frame = edge.build_screen_feature_observation_frame()
        assert feature_frame is not None
        evidence_ref = feature_frame["observations"][1]["evidence_ref"]
        evidence_result = edge.handle_action_request(
            {
                "type": "action_request",
                "device_id": "proxy-edge-1",
                "request_id": "evidence-1",
                "action": {
                    "capability": "proxy.screen.evidence.read",
                    "payload": {
                        "target_id": "desktop-1",
                        "surface_id": "main",
                        "evidence_ref": evidence_ref,
                        "purpose": "owner_inspection",
                        "max_bytes": 1024,
                        "understanding_ttl_seconds": 60,
                    },
                },
            }
        )
        transfer = edge.drain_evidence_transfers()[0]
        self.assertEqual(evidence_result["result"]["details"]["understanding_state"], "pending_understanding")
        self.assertNotIn("data_base64", json.dumps(evidence_result))

        service = ProxyScreenEvidenceService(
            vision_evaluator=lambda _body, _metadata: {
                "summary": "A configured desktop control surface is visible.",
                "labels": ["desktop"],
                "confidence": 0.9,
            },
        )
        update = service.ingest(transfer)
        self.assertEqual(update["understanding"]["state"], "understanding_ready")
        self.assertEqual(update["understanding"]["valid_for_seconds"], 60)
        audit = service.audit_event(transfer, update)
        self.assertNotIn("data_base64", json.dumps(audit))
        self.assertNotIn(adapter.body.decode("ascii"), json.dumps(audit))

        edge.handle_understanding_update(update)
        authorized = edge.handle_action_request(
            {
                "type": "action_request",
                "device_id": "proxy-edge-1",
                "request_id": "key-2",
                "action": {
                    "capability": "proxy.keyboard.input",
                    "payload": {
                        "target_id": "desktop-1",
                        "surface_id": "main",
                        "operation": "type",
                        "text": "allowed",
                        "visual_authorization": {
                            "understanding_id": update["understanding"]["understanding_id"],
                        },
                    },
                },
            }
        )
        self.assertEqual(authorized["result"]["status"], "ok")
        self.assertEqual(adapter.calls[0][0], "keyboard")

    def test_edge_rejects_unknown_evidence_reference(self) -> None:
        edge, _adapter = build_edge()
        edge.handle_action_request(profile_request())
        edge.build_screen_feature_observation_frame()
        transfer = edge.handle_action_request(
            {
                "type": "action_request",
                "device_id": "proxy-edge-1",
                "request_id": "evidence-2",
                "action": {
                    "capability": "proxy.screen.evidence.read",
                    "payload": {
                        "target_id": "desktop-1",
                        "surface_id": "main",
                        "evidence_ref": "proxy-evidence://missing",
                    },
                },
            }
        )
        self.assertEqual(transfer["result"]["reason"], "evidence_unavailable")

    def test_gateway_accepts_only_result_authorized_transfer_and_persists_no_jpeg(self) -> None:
        edge, adapter = build_edge()
        configured = edge.handle_action_request(profile_request())
        feature_frame = edge.build_screen_feature_observation_frame()
        assert feature_frame is not None
        evidence_ref = feature_frame["observations"][1]["evidence_ref"]
        evidence_result = edge.handle_action_request(
            {
                "type": "action_request",
                "device_id": "proxy-edge-1",
                "request_id": "evidence-3",
                "action": {
                    "capability": "proxy.screen.evidence.read",
                    "payload": {
                        "target_id": "desktop-1",
                        "surface_id": "main",
                        "evidence_ref": evidence_ref,
                        "purpose": "candidate_review",
                        "max_bytes": 1024,
                    },
                },
            }
        )
        transfer = edge.drain_evidence_transfers()[0]
        state = RuntimeState()
        state.register_device("proxy-edge-1", "proxy-interaction")
        for capability in edge.build_capability_announce_frame()["capabilities"]:
            state.register_capability("proxy-edge-1", capability)
        gateway = RuntimeGateway(
            state=state,
            persist_state=False,
            proxy_screen_vision_evaluator=lambda _body, _metadata: {
                "summary": "Desktop is available for review.",
                "labels": ["desktop"],
                "confidence": 0.8,
            },
        )
        replies = gateway.run_roundtrip([configured, evidence_result, transfer])
        update = next(reply for reply in replies if reply["type"] == "understanding_update")
        self.assertEqual(update["understanding"]["state"], "understanding_ready")
        self.assertEqual(
            gateway.state.proxy_screen_profiles["proxy-edge-1"]["profile_id"],
            "desktop-control-v1",
        )
        self.assertNotIn("data_base64", json.dumps(gateway.state.events))
        self.assertNotIn(adapter.body.decode("ascii"), json.dumps(gateway.state.events))

        unapproved_state = RuntimeState()
        unapproved_state.register_device("proxy-edge-1", "proxy-interaction")
        for capability in edge.build_capability_announce_frame()["capabilities"]:
            unapproved_state.register_capability("proxy-edge-1", capability)
        unapproved = RuntimeGateway(state=unapproved_state, persist_state=False)
        rejected = unapproved.run_roundtrip([transfer])
        self.assertEqual(rejected[0]["code"], "unauthorized_evidence_transfer")
