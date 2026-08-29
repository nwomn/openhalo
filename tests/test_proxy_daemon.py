import asyncio
import json
import unittest
from unittest.mock import AsyncMock
from unittest.mock import patch

from device_edge.proxy.adapter import AdapterProbe
from device_edge.proxy.adapter import ProxyAdapterError
from device_edge.proxy.contracts import CapabilityAvailability
from device_edge.proxy.edge import ProxyInteractionEdge
from device_edge.proxy.proxy_daemon import ProxyEdgeDaemon


def _capabilities(*, available: bool = True) -> dict[str, CapabilityAvailability]:
    state = "available" if available else "unavailable"
    reason = None if available else "adapter_unreachable"
    return {
        "screen": CapabilityAvailability(state, reason),
        "audio": CapabilityAvailability("unavailable", "not_supported"),
        "keyboard": CapabilityAvailability(state, reason),
        "pointer": CapabilityAvailability(state, reason),
        "virtual_media": CapabilityAvailability("unavailable", "not_supported"),
        "power": CapabilityAvailability("unavailable", "not_supported"),
    }


class FakeProxyAdapter:
    adapter_id = "fake-adapter"
    adapter_kind = "fake"
    requirements = ()
    supported_target_classes = frozenset({"tablet"})

    def __init__(self) -> None:
        self.available = True
        self.calls: list[tuple[str, dict]] = []

    def probe(self) -> AdapterProbe:
        if not self.available:
            raise ProxyAdapterError("adapter_unreachable")
        return AdapterProbe(capabilities=_capabilities(), details={})

    def capture_frame(self):
        from device_edge.proxy.contracts import CapturedFrame

        return CapturedFrame(
            evidence_ref="proxy-evidence://fake-adapter/screen/one",
            captured_at="2026-08-29T08:00:00Z",
            width=1280,
            height=720,
            mime_type="image/jpeg",
            size_bytes=32,
            sha256="a" * 64,
        )

    def execute_keyboard(self, payload: dict) -> dict:
        self.calls.append(("keyboard", payload))
        return {"ok": True}

    def execute_pointer(self, payload: dict) -> dict:
        self.calls.append(("pointer", payload))
        return {"ok": True}


def build_edge(adapter: FakeProxyAdapter) -> ProxyInteractionEdge:
    return ProxyInteractionEdge(
        device_id="proxy-edge-1",
        audience="ws://127.0.0.1:18765",
        target_id="tablet-1",
        surface_id="main",
        target_class="tablet",
        adapter=adapter,
        observed_at="2026-08-29T08:00:00Z",
    )


class ProxyEdgeDaemonTests(unittest.TestCase):
    def test_pairing_connect_frame_carries_only_public_identity_material(self) -> None:
        edge = build_edge(FakeProxyAdapter())

        frame = edge.client.build_pairing_connect_frame("pair-once")

        self.assertEqual(frame["auth"]["kind"], "pairing")
        self.assertEqual(frame["auth"]["pairing_code"], "pair-once")
        self.assertEqual(frame["auth"]["public_key"], edge.client.identity.public_key)
        self.assertNotIn("private_key", json.dumps(frame))

    def test_refresh_marks_adapter_unavailable_and_withdraws_actions(self) -> None:
        adapter = FakeProxyAdapter()
        edge = build_edge(adapter)
        adapter.available = False

        attachment = edge.refresh_attachment("2026-08-29T08:01:00Z")
        capability_names = [
            item["name"] for item in edge.build_capability_announce_frame()["capabilities"]
        ]

        self.assertEqual(attachment.attachment_state, "detached")
        self.assertEqual(attachment.capability_state("pointer").reason, "adapter_unreachable")
        self.assertEqual(capability_names, ["proxy.interaction.observe"])

    def test_session_authenticates_publishes_and_binds_post_action_frame(self) -> None:
        edge = build_edge(FakeProxyAdapter())
        daemon = ProxyEdgeDaemon(edge, probe_interval_s=1)
        websocket = AsyncMock()
        websocket.recv = AsyncMock(
            side_effect=[
                json.dumps(
                    {
                        "type": "auth_challenge",
                        "device_id": edge.client.device_id,
                        "session_id": edge.client.session_id,
                        "audience": edge.client.audience,
                        "challenge": {
                            "challenge_id": "challenge-1",
                            "nonce": "nonce-1",
                            "expires_at": "2026-08-29T08:01:00Z",
                        },
                    }
                ),
                json.dumps({"type": "connect_ok"}),
                json.dumps({"type": "event_ack"}),
                json.dumps({"type": "event_ack"}),
                json.dumps(
                    {
                        "type": "action_request",
                        "device_id": "proxy-edge-1",
                        "request_id": "action-1",
                        "action": {
                            "capability": "proxy.keyboard.input",
                            "payload": {
                                "target_id": "tablet-1",
                                "surface_id": "main",
                                "operation": "type",
                                "text": "safe",
                            },
                        },
                    }
                ),
                json.dumps({"type": "event_ack"}),
                json.dumps({"type": "event_ack"}),
            ]
        )
        connect_cm = AsyncMock()
        connect_cm.__aenter__.return_value = websocket
        connect_cm.__aexit__.return_value = False

        with patch(
            "device_edge.proxy.proxy_daemon.websockets.connect",
            return_value=connect_cm,
        ):
            results = asyncio.run(
                daemon.run_websocket_session(
                    edge.client.audience,
                    pairing_code="pair-once",
                    max_action_requests=1,
                )
            )

        self.assertEqual(results[0]["result"]["status"], "ok")
        sent = [json.loads(call.args[0]) for call in websocket.send.await_args_list]
        self.assertEqual(sent[0]["auth"]["kind"], "pairing")
        self.assertEqual(sent[2]["type"], "capability_announce")
        self.assertEqual(sent[5]["type"], "action_result")
        post_action = sent[-1]["observations"][0]
        self.assertEqual(post_action["name"], "proxy.screen_frame.v1")
        self.assertEqual(post_action["value"]["action_request_id"], "action-1")

