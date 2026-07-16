import json
import unittest
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosedOK
from websockets.frames import Close

from device_edge.shared.session_client import SessionClient
from edge_api.protocol import API_VERSION
from personal_runtime.agent_executor import InterventionProposal
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.runtime_state import RuntimeState

ROOT = Path(__file__).resolve().parents[1]
TEST_LLM_CONFIG = ROOT / "tests" / "fixtures" / "llm-config-test.toml"
RUNTIME_TEST_DIR = ROOT / ".worktrees" / "v0-single-edge-loop" / ".runtime-test"


def _last_action_request(replies: list[dict]) -> dict | None:
    return next(
        (item for item in reversed(replies) if item["type"] == "action_request"),
        None,
    )


def _last_interaction_update(replies: list[dict]) -> dict | None:
    return next(
        (item for item in reversed(replies) if item["type"] == "interaction_update"),
        None,
    )


def _last_error(replies: list[dict]) -> dict | None:
    return next(
        (item for item in reversed(replies) if item["type"] == "error"),
        None,
    )


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_to_source_uses_current_connection_after_reconnect(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        class FakeWebSocket:
            def __init__(self) -> None:
                self.sent_frames = []

            async def send(self, frame: str) -> None:
                self.sent_frames.append(json.loads(frame))

        old_websocket = FakeWebSocket()
        current_websocket = FakeWebSocket()
        gateway.live_connections["android-edge-1"] = current_websocket

        await gateway._dispatch_websocket_replies(
            "android-edge-1",
            old_websocket,
            [{"type": "event_ack"}],
        )

        self.assertEqual(old_websocket.sent_frames, [])
        self.assertEqual(current_websocket.sent_frames[-1]["type"], "event_ack")

    async def test_replaced_websocket_close_does_not_clear_current_connection(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        class ReplacementWebSocket:
            def __init__(self) -> None:
                self.sent_frames = []

            async def send(self, frame: str) -> None:
                self.sent_frames.append(json.loads(frame))

        replacement_websocket = ReplacementWebSocket()

        class ReplacedDisconnectWebSocket:
            def __init__(self) -> None:
                self.sent_frames = []

            def __aiter__(self):
                async def frames():
                    yield json.dumps(
                        {
                            "api_version": API_VERSION,
                            "type": "connect",
                            "device": {
                                "device_id": "android-edge-1",
                                "device_type": "android-phone",
                            },
                            "auth": {"token": "dev-token"},
                        }
                    )
                    gateway.live_connections["android-edge-1"] = replacement_websocket
                    gateway.online_device_ids.add("android-edge-1")
                    raise ConnectionClosedOK(Close(1000, "normal close"), None)

                return frames()

            async def send(self, frame: str) -> None:
                self.sent_frames.append(json.loads(frame))

        websocket = ReplacedDisconnectWebSocket()

        await gateway._websocket_handler(websocket)

        self.assertEqual(websocket.sent_frames[-1]["type"], "connect_ok")
        self.assertIs(gateway.live_connections["android-edge-1"], replacement_websocket)
        self.assertIn("android-edge-1", gateway.online_device_ids)

    async def test_websocket_handler_treats_disconnect_as_closed_session(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        class DisconnectWebSocket:
            def __init__(self) -> None:
                self.sent_frames = []

            def __aiter__(self):
                async def frames():
                    yield json.dumps(
                        {
                            "api_version": API_VERSION,
                            "type": "connect",
                            "device": {
                                "device_id": "android-edge-1",
                                "device_type": "android-phone",
                            },
                            "auth": {"token": "dev-token"},
                        }
                    )
                    raise ConnectionClosedOK(Close(1000, "normal close"), None)

                return frames()

            async def send(self, frame: str) -> None:
                self.sent_frames.append(json.loads(frame))

        websocket = DisconnectWebSocket()

        await gateway._websocket_handler(websocket)

        self.assertEqual(websocket.sent_frames[-1]["type"], "connect_ok")
        self.assertNotIn("android-edge-1", gateway.online_device_ids)
        self.assertNotIn("android-edge-1", gateway.live_connections)

    async def test_capability_announce_registers_rich_capabilities_and_observations(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        await gateway.handle_test_frames(
            [
                {
                    "api_version": API_VERSION,
                    "type": "connect",
                    "device": {
                        "device_id": "phone-edge-1",
                        "device_type": "mobile",
                        "role": "interactive_surface",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "api_version": API_VERSION,
                    "type": "capability_announce",
                    "device_id": "phone-edge-1",
                    "capabilities": [
                        {
                            "name": "notification.show",
                            "direction": "runtime_to_edge",
                            "kind": "action",
                            "affordances": [
                                "notify_user",
                                "deliver_private_text",
                            ],
                            "modality": "visual_text",
                            "content_capacity": "short_text",
                            "privacy": "personal",
                            "interruptiveness": "medium",
                            "side_effect": "user_visible",
                            "input_schema": {
                                "type": "object",
                                "required": ["body"],
                                "properties": {
                                    "title": {"type": "string"},
                                    "body": {"type": "string"},
                                },
                            },
                        },
                        {
                            "name": "mobile.context",
                            "direction": "edge_to_runtime",
                            "kind": "observation_provider",
                            "observations": [
                                {
                                    "name": "mobile.screen_state",
                                    "schema": {
                                        "type": "string",
                                        "enum": [
                                            "locked",
                                            "unlocked",
                                            "unknown",
                                        ],
                                    },
                                    "semantics": ["device_activity"],
                                    "privacy": "personal_device_state",
                                    "freshness_seconds": 120,
                                }
                            ],
                        },
                    ],
                },
            ]
        )

        self.assertEqual(
            gateway.state.device_registry["phone-edge-1"]["role"],
            "interactive_surface",
        )
        self.assertIn(
            "notification.show",
            gateway.state.devices["phone-edge-1"]["capabilities"],
        )
        self.assertEqual(
            gateway.state.capability_registry["phone-edge-1"][
                "notification.show"
            ]["privacy"],
            "personal",
        )
        self.assertEqual(
            gateway.state.observation_registry["phone-edge-1"]["mobile.context"][
                "mobile.screen_state"
            ]["schema"]["type"],
            "string",
        )

    async def test_legacy_capability_announce_keeps_name_set_compatibility(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "terminal-edge-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "terminal-edge-1",
                    "capabilities": ["text.input", "notification.show"],
                },
            ]
        )

        self.assertEqual(
            gateway.state.devices["terminal-edge-1"]["capabilities"],
            {"text.input", "notification.show"},
        )

    async def test_rejects_unregistered_observation_push(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        replies = await gateway.handle_test_frames(
            [
                {
                    "api_version": API_VERSION,
                    "type": "connect",
                    "device": {
                        "device_id": "phone-edge-1",
                        "device_type": "mobile",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "api_version": API_VERSION,
                    "type": "capability_announce",
                    "device_id": "phone-edge-1",
                    "capabilities": [
                        {
                            "name": "mobile.context",
                            "direction": "edge_to_runtime",
                            "kind": "observation_provider",
                        }
                    ],
                },
                {
                    "api_version": API_VERSION,
                    "type": "observation_push",
                    "device_id": "phone-edge-1",
                    "capability": "mobile.context",
                    "observations": [
                        {
                            "name": "mobile.screen_state",
                            "value": "locked",
                            "observed_at": "2026-06-30T10:00:00Z",
                            "confidence": 1.0,
                        }
                    ],
                },
            ]
        )

        self.assertEqual(replies[-1]["type"], "error")
        self.assertEqual(replies[-1]["code"], "unregistered_observation")
        self.assertEqual(gateway.state.observations, [])

    async def test_rejects_schema_mismatched_observation_push(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        replies = await gateway.handle_test_frames(
            [
                {
                    "api_version": API_VERSION,
                    "type": "connect",
                    "device": {
                        "device_id": "phone-edge-1",
                        "device_type": "mobile",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "api_version": API_VERSION,
                    "type": "capability_announce",
                    "device_id": "phone-edge-1",
                    "capabilities": [
                        {
                            "name": "mobile.context",
                            "direction": "edge_to_runtime",
                            "kind": "observation_provider",
                            "observations": [
                                {
                                    "name": "mobile.screen_state",
                                    "schema": {
                                        "type": "string",
                                        "enum": [
                                            "locked",
                                            "unlocked",
                                            "unknown",
                                        ],
                                    },
                                }
                            ],
                        }
                    ],
                },
                {
                    "api_version": API_VERSION,
                    "type": "observation_push",
                    "device_id": "phone-edge-1",
                    "capability": "mobile.context",
                    "observations": [
                        {
                            "name": "mobile.screen_state",
                            "value": "charging",
                            "observed_at": "2026-06-30T10:00:00Z",
                            "confidence": 1.0,
                        }
                    ],
                },
            ]
        )

        self.assertEqual(replies[-1]["type"], "error")
        self.assertEqual(replies[-1]["code"], "schema_mismatch")
        self.assertEqual(gateway.state.observations, [])

    async def test_accepts_compat_runtime_health_with_null_started_at(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "host-edge-1",
                        "device_type": "server",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "host-edge-1",
                    "capabilities": [
                        "host.metrics",
                        "runtime.health",
                        "runtime.control",
                    ],
                },
                {
                    "type": "observation_push",
                    "device_id": "host-edge-1",
                    "capability": "runtime.health",
                    "observations": [
                        {
                            "name": "runtime.process_started_at",
                            "value": None,
                            "observed_at": "2026-06-19T09:30:00Z",
                            "confidence": 1.0,
                        }
                    ],
                    "payload": {
                        "observations": [
                            {
                                "name": "runtime.process_started_at",
                                "value": None,
                                "observed_at": "2026-06-19T09:30:00Z",
                                "confidence": 1.0,
                            }
                        ]
                    },
                },
            ]
        )

        self.assertEqual(replies[-1]["type"], "event_ack")
        self.assertEqual(
            gateway.state.observations[-1].name,
            "runtime.process_started_at",
        )
        self.assertIsNone(gateway.state.observations[-1].value)

    async def test_accepts_registered_observation_push(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        await gateway.handle_test_frames(
            [
                {
                    "api_version": API_VERSION,
                    "type": "connect",
                    "device": {
                        "device_id": "phone-edge-1",
                        "device_type": "mobile",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "api_version": API_VERSION,
                    "type": "capability_announce",
                    "device_id": "phone-edge-1",
                    "capabilities": [
                        {
                            "name": "mobile.context",
                            "direction": "edge_to_runtime",
                            "kind": "observation_provider",
                            "observations": [
                                {
                                    "name": "mobile.screen_state",
                                    "schema": {
                                        "type": "string",
                                        "enum": [
                                            "locked",
                                            "unlocked",
                                            "unknown",
                                        ],
                                    },
                                }
                            ],
                        }
                    ],
                },
                {
                    "api_version": API_VERSION,
                    "type": "observation_push",
                    "device_id": "phone-edge-1",
                    "capability": "mobile.context",
                    "observations": [
                        {
                            "name": "mobile.screen_state",
                            "value": "locked",
                            "observed_at": "2026-06-30T10:00:00Z",
                            "confidence": 1.0,
                        }
                    ],
                },
            ]
        )

        self.assertEqual(gateway.state.observations[-1].name, "mobile.screen_state")

    async def test_mobile_screen_context_observation_is_passive_evidence(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        replies = await gateway.handle_test_frames(
            [
                {
                    "api_version": API_VERSION,
                    "type": "connect",
                    "device": {
                        "device_id": "android-edge-1",
                        "device_type": "android-phone",
                        "role": "interactive_surface",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "api_version": API_VERSION,
                    "type": "capability_announce",
                    "device_id": "android-edge-1",
                    "capabilities": [
                        {
                            "name": "mobile.screen_context",
                            "direction": "edge_to_runtime",
                            "kind": "observation_provider",
                            "observations": [
                                {
                                    "name": "mobile.screen_context",
                                    "schema": {
                                        "type": "object",
                                        "required": [
                                            "trigger",
                                            "event_kind",
                                            "source",
                                            "capture_mode",
                                            "screen_state",
                                            "sensitivity",
                                            "raw_screenshot_uploaded",
                                        ],
                                        "properties": {
                                            "trigger": {"type": "string"},
                                            "event_kind": {"type": "string"},
                                            "source": {"type": "string"},
                                            "capture_mode": {"type": "string"},
                                            "screen_state": {"type": "string"},
                                            "sensitivity": {"type": "string"},
                                            "raw_screenshot_uploaded": {
                                                "type": "boolean"
                                            },
                                        },
                                    },
                                }
                            ],
                        }
                    ],
                },
                {
                    "api_version": API_VERSION,
                    "type": "observation_push",
                    "device_id": "android-edge-1",
                    "capability": "mobile.screen_context",
                    "observations": [
                        {
                            "name": "mobile.screen_context",
                            "value": {
                                "trigger": "accessibility_event",
                                "event_kind": "view_clicked",
                                "source": "accessibility",
                                "capture_mode": "accessibility_tree",
                                "screen_state": "unlocked",
                                "sensitivity": "normal",
                                "raw_screenshot_uploaded": False,
                                "visible_text_summary": "Chat screen with reply box.",
                            },
                            "observed_at": "2026-07-05T14:24:53Z",
                            "confidence": 0.76,
                        }
                    ],
                },
            ]
        )

        self.assertEqual(replies[0], {"api_version": API_VERSION, "type": "connect_ok"})
        self.assertEqual(replies[-1], {"api_version": API_VERSION, "type": "event_ack"})
        self.assertEqual(len(gateway.state.observations), 2)
        self.assertEqual(gateway.state.observations[0].name, "mobile.screen_context")
        self.assertEqual(gateway.state.observations[-1].name, "mobile.observation_liveness")
        self.assertEqual(gateway.state.interventions, [])
        self.assertEqual(
            gateway.state.mobile_liveness["android-edge-1"]["last_session"]["status"],
            "connected",
        )
        self.assertEqual(
            gateway.state.mobile_liveness["android-edge-1"]["last_view"]["state"],
            "fresh",
        )

    async def test_external_edge_uses_public_api_frames_for_full_turn(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        replies = await gateway.handle_test_frames(
            [
                {
                    "api_version": API_VERSION,
                    "type": "connect",
                    "device": {
                        "device_id": "external-display-1",
                        "device_type": "external-display",
                        "role": "interactive_surface",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "api_version": API_VERSION,
                    "type": "capability_announce",
                    "device_id": "external-display-1",
                    "capabilities": [
                        {
                            "name": "text.input",
                            "direction": "edge_to_runtime",
                        },
                        {
                            "name": "notification.show",
                            "direction": "runtime_to_edge",
                        },
                        {
                            "name": "surface.activity",
                            "direction": "edge_to_runtime",
                            "kind": "observation_provider",
                            "observations": [
                                {
                                    "name": "surface.activity_state",
                                    "schema": {
                                        "type": "string",
                                        "enum": ["active", "idle", "unknown"],
                                    },
                                    "semantics": ["device_activity"],
                                    "privacy": "personal_device_state",
                                    "freshness_seconds": 120,
                                }
                            ],
                        },
                    ],
                },
                {
                    "api_version": API_VERSION,
                    "type": "observation_push",
                    "device_id": "external-display-1",
                    "capability": "surface.activity",
                    "observations": [
                        {
                            "name": "surface.activity_state",
                            "value": "active",
                            "observed_at": "2026-06-29T10:00:00Z",
                            "confidence": 1.0,
                        }
                    ],
                },
                {
                    "api_version": API_VERSION,
                    "type": "event_push",
                    "trace_id": "trace-external-display-1-1",
                    "session_id": "session-external-display-1",
                    "turn_id": "turn-external-display-1-1",
                    "event_id": "external-display-1-evt-2",
                    "device_id": "external-display-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "hello from an external edge",
                        "observed_at": "2026-06-29T10:00:01Z",
                    },
                },
            ]
        )

        action_request = _last_action_request(replies)
        self.assertIsNotNone(action_request)
        self.assertEqual(action_request["api_version"], API_VERSION)
        self.assertEqual(action_request["trace_id"], "trace-external-display-1-1")
        self.assertEqual(action_request["session_id"], "session-external-display-1")
        self.assertEqual(action_request["turn_id"], "turn-external-display-1-1")
        self.assertRegex(action_request["request_id"], r"^action-\d+$")
        self.assertRegex(action_request["interaction_id"], r"^interaction-\d+$")
        self.assertEqual(action_request["device_id"], "external-display-1")
        self.assertEqual(
            gateway.state.observations[-1].name,
            "surface.activity_state",
        )
        self.assertEqual(
            gateway.state.interventions[-1]["correlation"]["trace_id"],
            "trace-external-display-1-1",
        )

        result_replies = await gateway.handle_test_frames(
            [
                {
                    "api_version": API_VERSION,
                    "type": "action_result",
                    "trace_id": action_request["trace_id"],
                    "session_id": action_request["session_id"],
                    "turn_id": action_request["turn_id"],
                    "request_id": action_request["request_id"],
                    "interaction_id": action_request["interaction_id"],
                    "interaction_turn_id": action_request["interaction_turn_id"],
                    "device_id": "external-display-1",
                    "result": {
                        "status": "ok",
                        "capability": "notification.show",
                        "observed_at": "2026-06-29T10:00:02Z",
                        "details": {
                            "title": action_request["action"]["payload"]["title"],
                            "body": action_request["action"]["payload"]["body"],
                        },
                    },
                }
            ]
        )

        interaction_update = _last_interaction_update(result_replies)
        self.assertIsNotNone(interaction_update)
        self.assertEqual(interaction_update["api_version"], API_VERSION)
        self.assertEqual(
            interaction_update["interaction"]["interaction_id"],
            action_request["interaction_id"],
        )

    async def test_connect_event_and_action_roundtrip(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        gateway.state.upsert_goal(
            goal_id="goal-1",
            title="Keep runtime healthy",
            status="active",
            summary="Watch runtime health signals.",
            updated_at="2026-06-22T10:00:00Z",
        )
        reply = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "hello"},
                },
            ]
        )

        action_request = next(
            (item for item in reversed(reply) if item["type"] == "action_request"),
            None,
        )

        self.assertIsNotNone(action_request)
        self.assertEqual(action_request["action"]["capability"], "notification.show")
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["metadata"]["llm_profile"],
            "proposal_formation",
        )
        self.assertIn(
            gateway.state.interventions[-1]["proposal"]["metadata"][
                "used_deterministic_fallback"
            ],
            {True, False},
        )
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["metadata"][
                "grounding_bundle_version"
            ],
            "m10.v1",
        )
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["metadata"][
                "grounding_active_goal_count"
            ],
            1,
        )
        self.assertIn(
            "grounding_recent_user_inputs",
            gateway.state.interventions[-1]["proposal"]["metadata"],
        )
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["proposal_type"],
            "action",
        )
        self.assertIn(
            "proposal_rationale",
            gateway.state.interventions[-1]["proposal"]["metadata"],
        )

    async def test_sync_roundtrip_wrapper_returns_replies(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        replies = gateway.run_roundtrip(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "hello"},
                },
            ]
        )

        self.assertIsNotNone(_last_action_request(replies))

    async def test_persists_state_after_connect_event_and_action_result(self) -> None:
        state_path = RUNTIME_TEST_DIR / "gateway-state.json"
        gateway = RuntimeGateway(
            shared_token="dev-token",
            state_path=state_path,
            llm_config_path=TEST_LLM_CONFIG,
        )
        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "hello"},
                },
                {
                    "type": "action_result",
                    "device_id": "desktop-dev-1",
                    "result": {"status": "ok"},
                },
            ]
        )

        persisted = json.loads(state_path.read_text(encoding="utf-8"))

        action_request = _last_action_request(replies)
        self.assertIsNotNone(action_request)
        self.assertEqual(
            persisted["devices"]["desktop-dev-1"]["capabilities"],
            ["notification.show", "text.input"],
        )
        self.assertEqual(persisted["events"][-1]["payload"]["text"], "hello")
        self.assertEqual(persisted["action_results"][-1]["status"], "ok")

    async def test_websocket_server_emits_connect_ack_and_action_request(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        async with gateway.run_test_server() as server_info:
            async with websockets.connect(server_info["url"]) as websocket:
                await websocket.send(
                    json.dumps(
                        {
                            "type": "connect",
                            "device": {
                                "device_id": "desktop-dev-1",
                                "device_type": "desktop-cli",
                            },
                            "auth": {"token": "dev-token"},
                        }
                    )
                )
                await websocket.send(
                    json.dumps(
                        {
                            "type": "capability_announce",
                            "device_id": "desktop-dev-1",
                            "capabilities": ["text.input", "notification.show"],
                        }
                    )
                )
                await websocket.send(
                    json.dumps(
                        {
                            "type": "event_push",
                            "device_id": "desktop-dev-1",
                            "capability": "text.input",
                            "payload": {"text": "hello"},
                        }
                    )
                )

                connect_ok = json.loads(await websocket.recv())
                event_ack = json.loads(await websocket.recv())
                action_request = json.loads(await websocket.recv())

        self.assertEqual(connect_ok["type"], "connect_ok")
        self.assertEqual(event_ack["type"], "event_ack")
        self.assertEqual(action_request["type"], "action_request")

    async def test_websocket_server_surfaces_missing_runtime_config_without_closing_connection(
        self,
    ) -> None:
        missing_config_path = ROOT / "tests" / "fixtures" / "llm-config-does-not-exist.toml"
        self.assertFalse(missing_config_path.exists())
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=missing_config_path,
        )

        async with gateway.run_test_server() as server_info:
            async with websockets.connect(server_info["url"]) as websocket:
                await websocket.send(
                    json.dumps(
                        {
                            "type": "connect",
                            "device": {
                                "device_id": "desktop-dev-1",
                                "device_type": "desktop-cli",
                            },
                            "auth": {"token": "dev-token"},
                        }
                    )
                )
                await websocket.send(
                    json.dumps(
                        {
                            "type": "capability_announce",
                            "device_id": "desktop-dev-1",
                            "capabilities": ["text.input", "notification.show"],
                        }
                    )
                )
                await websocket.send(
                    json.dumps(
                        {
                            "type": "event_push",
                            "device_id": "desktop-dev-1",
                            "capability": "text.input",
                            "payload": {"text": "hello"},
                        }
                    )
                )

                connect_ok = json.loads(await websocket.recv())
                event_ack = json.loads(await websocket.recv())
                interaction_update = json.loads(await websocket.recv())

        self.assertEqual(connect_ok["type"], "connect_ok")
        self.assertEqual(event_ack["type"], "event_ack")
        self.assertEqual(interaction_update["type"], "interaction_update")
        self.assertEqual(interaction_update["interaction"]["status"], "completed")
        self.assertEqual(interaction_update["interaction"]["visibility"], "visible")
        self.assertIn(
            "Real model reply unavailable",
            interaction_update["interaction"]["summary"],
        )
        proposal = gateway.state.interventions[-1]["proposal"]
        self.assertEqual(proposal["proposal_type"], "provider_failure")
        self.assertIsNone(proposal["action_capability"])
        self.assertEqual(
            proposal["metadata"]["runtime_message_channel"],
            "provider_failure",
        )
        self.assertEqual(
            proposal["metadata"]["provider_failure_type"],
            "FileNotFoundError",
        )

    async def test_protocol_accepts_interaction_update_frame_type(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "terminal-edge-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "interaction_update",
                    "device_id": "terminal-edge-1",
                    "interaction": {
                        "interaction_id": "interaction-1",
                        "status": "completed",
                        "summary": "Runtime status is healthy.",
                    },
                },
            ]
        )

        self.assertEqual(replies[-1]["type"], "connect_ok")

    async def test_direct_action_event_bypasses_router_but_is_still_persisted(self) -> None:
        state_path = RUNTIME_TEST_DIR / "direct-action-state.json"
        gateway = RuntimeGateway(
            shared_token="dev-token",
            state_path=state_path,
            llm_config_path=TEST_LLM_CONFIG,
        )
        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "urgent ping",
                        "direct_action": {
                            "capability": "notification.show",
                            "payload": {
                                "title": "OpenHalo",
                                "body": "urgent ping",
                            },
                        },
                    },
                },
            ]
        )

        persisted = json.loads(state_path.read_text(encoding="utf-8"))

        action_request = _last_action_request(replies)

        self.assertEqual(replies[-2]["type"], "event_ack")
        self.assertIsNotNone(action_request)
        self.assertEqual(
            action_request["action"]["payload"],
            {"title": "OpenHalo", "body": "urgent ping"},
        )
        self.assertEqual(
            persisted["events"][-1]["payload"]["direct_action"]["payload"],
            {"title": "OpenHalo", "body": "urgent ping"},
        )

    async def test_direct_notification_action_normalizes_title_before_dispatch(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )

        replies = await gateway.handle_test_frames(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "urgent ping",
                        "direct_action": {
                            "capability": "notification.show",
                            "payload": {
                                "title": "Hermes",
                                "body": "urgent ping",
                            },
                        },
                    },
                },
            ]
        )

        action_request = _last_action_request(replies)

        self.assertIsNotNone(action_request)
        self.assertEqual(
            action_request["action"]["payload"],
            {"title": "OpenHalo", "body": "urgent ping"},
        )

    async def test_direct_notification_action_rejects_legacy_and_blank_payloads(
        self,
    ) -> None:
        for payload in (
            {"message": "urgent ping"},
            {"title": "OpenHalo", "body": "   "},
        ):
            with self.subTest(payload=payload):
                gateway = RuntimeGateway(
                    shared_token="dev-token",
                    persist_state=False,
                    llm_config_path=TEST_LLM_CONFIG,
                )
                client = SessionClient(
                    device_id="desktop-dev-1",
                    device_type="desktop-cli",
                    token="dev-token",
                )

                replies = await gateway.handle_test_frames(
                    [
                        client.build_connect_frame(),
                        client.build_capability_announce_frame(),
                        {
                            "type": "event_push",
                            "device_id": "desktop-dev-1",
                            "capability": "text.input",
                            "payload": {
                                "text": "urgent ping",
                                "direct_action": {
                                    "capability": "notification.show",
                                    "payload": payload,
                                },
                            },
                        },
                    ]
                )

                self.assertIsNone(_last_action_request(replies))
                self.assertEqual(_last_error(replies)["code"], "direct_action_rejected")

    async def test_direct_action_rejects_unknown_capability(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )

        replies = await gateway.handle_test_frames(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "urgent ping",
                        "direct_action": {
                            "capability": "unknown.action",
                            "payload": {
                                "title": "OpenHalo",
                                "body": "urgent ping",
                            },
                        },
                    },
                },
            ]
        )

        self.assertIsNone(_last_action_request(replies))
        self.assertEqual(_last_error(replies)["code"], "direct_action_rejected")

    async def test_direct_action_rejects_non_object_input(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )

        replies = await gateway.handle_test_frames(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "urgent ping",
                        "direct_action": "not-an-object",
                    },
                },
            ]
        )

        self.assertIsNone(_last_action_request(replies))
        self.assertEqual(_last_error(replies)["code"], "direct_action_rejected")

    async def test_direct_action_rejects_invalid_capability_variants(self) -> None:
        for direct_action in (
            {"capability": {"name": "notification.show"}, "payload": {}},
            {"capability": "runtime.evil", "payload": {}},
        ):
            with self.subTest(direct_action=direct_action):
                gateway = RuntimeGateway(
                    shared_token="dev-token",
                    persist_state=False,
                    llm_config_path=TEST_LLM_CONFIG,
                )
                client = SessionClient(
                    device_id="desktop-dev-1",
                    device_type="desktop-cli",
                    token="dev-token",
                )
                host = SessionClient(
                    device_id="host-edge-1",
                    device_type="server",
                    token="dev-token",
                    capabilities=["runtime.control"],
                )
                direct_action = dict(direct_action)
                direct_action["target_device_id"] = "host-edge-1"

                replies = await gateway.handle_test_frames(
                    [
                        client.build_connect_frame(),
                        client.build_capability_announce_frame(),
                        host.build_connect_frame(),
                        host.build_capability_announce_frame(),
                        {
                            "type": "event_push",
                            "device_id": "desktop-dev-1",
                            "capability": "text.input",
                            "payload": {
                                "text": "urgent ping",
                                "direct_action": direct_action,
                            },
                        },
                    ]
                )

                self.assertIsNone(_last_action_request(replies))
                error = _last_error(replies)
                self.assertEqual(error["code"], "direct_action_rejected")
                if not isinstance(direct_action["capability"], str):
                    self.assertNotIn("capability", error)

    async def test_normal_path_can_target_other_registered_device(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-2",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-2",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "hello routed runtime"},
                },
            ]
        )

        action_request = _last_action_request(replies)

        self.assertIsNotNone(action_request)
        self.assertEqual(action_request["device_id"], "desktop-dev-2")
        self.assertEqual(action_request["action"]["capability"], "notification.show")
        self.assertEqual(gateway.state.interventions[-1]["decision"], "allow")
        self.assertEqual(gateway.state.interventions[-1]["target_device_id"], "desktop-dev-2")
        self.assertEqual(gateway.state.interventions[-1]["proposal"]["action_capability"], "notification.show")
        self.assertEqual(gateway.state.interventions[-1]["proposal"]["kind"], "notify")
        self.assertEqual(gateway.state.interventions[-1]["proposal"]["proposal_type"], "action")

    async def test_normal_text_can_form_runtime_status_action_proposal(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        replies = await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "check runtime status"},
                },
            ]
        )

        proposal = gateway.state.interventions[-1]["proposal"]
        action_request = _last_action_request(replies)

        self.assertIsNotNone(action_request)
        self.assertEqual(action_request["device_id"], "host-edge-1")
        self.assertEqual(action_request["action"]["capability"], "runtime.status")
        self.assertEqual(proposal["proposal_type"], "action")
        self.assertEqual(proposal["action_capability"], "runtime.status")
        self.assertIn("proposal_rationale", proposal["metadata"])

    async def test_local_reply_interaction_completion_is_silent_after_visible_notification(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )

        replies = await gateway.handle_test_frames(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "hello runtime"},
                },
            ]
        )
        action_request = _last_action_request(replies)
        self.assertIsNotNone(action_request)

        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "action_result",
                    "device_id": "desktop-dev-1",
                    "interaction_id": action_request["interaction_id"],
                    "interaction_turn_id": action_request["interaction_turn_id"],
                    "request_id": action_request["request_id"],
                    "result": {
                        "status": "ok",
                        "capability": action_request["action"]["capability"],
                        "details": {
                            "delivered_via": "terminal.stdout",
                            "title": "OpenHalo",
                            "body": "Hello! Runtime here.",
                        },
                    },
                },
            ]
        )

        interaction_update = _last_interaction_update(replies)
        self.assertIsNotNone(interaction_update)
        self.assertEqual(interaction_update["interaction"]["visibility"], "silent")
        self.assertEqual(interaction_update["interaction"]["summary"], "Hello! Runtime here.")

    async def test_runtime_status_reentry_records_visible_summary_after_delivery(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        replies = await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "check runtime status"},
                },
            ]
        )
        action_request = _last_action_request(replies)
        self.assertIsNotNone(action_request)

        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "action_result",
                    "device_id": "host-edge-1",
                    "interaction_id": action_request["interaction_id"],
                    "interaction_turn_id": action_request["interaction_turn_id"],
                    "request_id": action_request["request_id"],
                    "result": {
                        "status": "ok",
                        "capability": "runtime.status",
                        "details": {"state": "running", "pid": 42137},
                    },
                }
            ]
        )

        follow_up = _last_action_request(replies)
        self.assertIsNotNone(follow_up)
        self.assertEqual(
            follow_up["action"]["payload"],
            {
                "title": "OpenHalo",
                "body": "Runtime status: running (pid 42137).",
            },
        )

        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "action_result",
                    "device_id": "desktop-dev-1",
                    "interaction_id": follow_up["interaction_id"],
                    "interaction_turn_id": follow_up["interaction_turn_id"],
                    "request_id": follow_up["request_id"],
                    "result": {
                        "status": "ok",
                        "capability": "notification.show",
                        "details": {
                            "delivered_via": "terminal.stdout",
                            "title": "OpenHalo",
                            "body": "Runtime status: running (pid 42137).",
                        },
                    },
                }
            ]
        )

        interaction_update = _last_interaction_update(replies)
        self.assertIsNotNone(interaction_update)
        self.assertEqual(
            interaction_update["interaction"]["summary"],
            "Runtime status: running (pid 42137).",
        )

    async def test_action_result_reenters_agent_runtime_for_runtime_status_reply(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        replies = await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "check runtime status",
                        "observed_at": "2026-06-21T10:10:00Z",
                    },
                },
            ]
        )
        first_action = _last_action_request(replies)
        self.assertIsNotNone(first_action)

        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "action_result",
                    "device_id": "host-edge-1",
                    "interaction_id": first_action["interaction_id"],
                    "interaction_turn_id": first_action["interaction_turn_id"],
                    "request_id": first_action["request_id"],
                    "result": {
                        "status": "ok",
                        "capability": "runtime.status",
                        "observed_at": "2026-06-21T10:11:00Z",
                        "details": {"state": "running", "pid": 42137},
                    },
                }
            ]
        )

        follow_up = _last_action_request(replies)
        self.assertIsNotNone(follow_up)
        self.assertEqual(follow_up["interaction_id"], first_action["interaction_id"])
        self.assertEqual(follow_up["device_id"], "desktop-dev-1")
        self.assertEqual(follow_up["action"]["capability"], "notification.show")
        self.assertEqual(
            follow_up["action"]["payload"],
            {
                "title": "OpenHalo",
                "body": "Runtime status: running (pid 42137).",
            },
        )
        self.assertEqual(gateway.state.interventions[-1]["decision"], "allow")
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["source"],
            "post_action",
        )
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["metadata"]["interaction_id"],
            first_action["interaction_id"],
        )
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["metadata"]["turn_index"],
            2,
        )

    async def test_action_result_reentry_can_emit_follow_up_action_with_same_interaction(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        replies = await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "check runtime status",
                        "observed_at": "2026-06-21T10:10:00Z",
                    },
                },
            ]
        )
        first_action = _last_action_request(replies)
        self.assertIsNotNone(first_action)

        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "action_result",
                    "device_id": "host-edge-1",
                    "interaction_id": first_action["interaction_id"],
                    "interaction_turn_id": first_action["interaction_turn_id"],
                    "request_id": first_action["request_id"],
                    "result": {
                        "status": "ok",
                        "capability": "runtime.status",
                        "observed_at": "2026-06-21T10:11:00Z",
                        "details": {
                            "state": "degraded",
                            "needs_follow_up": True,
                        },
                    },
                }
            ]
        )

        follow_up = _last_action_request(replies)
        self.assertIsNotNone(follow_up)
        self.assertEqual(follow_up["interaction_id"], first_action["interaction_id"])
        self.assertEqual(follow_up["device_id"], "host-edge-1")
        self.assertEqual(follow_up["action"]["capability"], "runtime.status")
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["proposal_type"],
            "action",
        )
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["metadata"][
                "parent_action_capability"
            ],
            "runtime.status",
        )

    async def test_relevant_observation_reenters_open_interaction_with_same_interaction(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        replies = await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "check runtime status",
                        "observed_at": "2026-06-21T10:10:00Z",
                    },
                },
            ]
        )
        first_action = _last_action_request(replies)
        self.assertIsNotNone(first_action)

        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "event_push",
                    "device_id": "host-edge-1",
                    "capability": "runtime.health",
                    "event_id": "host-edge-1-health-1",
                    "reentry_parent": {
                        "interaction_id": first_action["interaction_id"],
                        "interaction_turn_id": first_action["interaction_turn_id"],
                        "request_id": first_action["request_id"],
                    },
                    "payload": {
                        "observations": [
                            {
                                "name": "runtime.health_state",
                                "value": "degraded",
                                "observed_at": "2026-06-21T10:10:30Z",
                                "confidence": 1.0,
                            }
                        ]
                    },
                }
            ]
        )

        follow_up = _last_action_request(replies)
        self.assertIsNotNone(follow_up)
        self.assertEqual(follow_up["interaction_id"], first_action["interaction_id"])
        self.assertEqual(follow_up["device_id"], "host-edge-1")
        self.assertEqual(follow_up["action"]["capability"], "runtime.status")
        proposal = gateway.state.interventions[-1]["proposal"]
        self.assertEqual(proposal["source"], "post_observation")
        self.assertEqual(proposal["metadata"]["trigger"], "observation")
        self.assertEqual(proposal["metadata"]["turn_index"], 2)
        self.assertEqual(
            proposal["metadata"]["observation_names"],
            ["runtime.health_state"],
        )

    async def test_observation_without_open_interaction_only_updates_context(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        replies = await gateway.handle_test_frames(
            [
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                {
                    "type": "event_push",
                    "device_id": "host-edge-1",
                    "capability": "runtime.health",
                    "event_id": "host-edge-1-health-1",
                    "payload": {
                        "observations": [
                            {
                                "name": "runtime.health_state",
                                "value": "healthy",
                                "observed_at": "2026-06-21T10:10:30Z",
                                "confidence": 1.0,
                            }
                        ]
                    },
                },
            ]
        )

        self.assertEqual(
            replies,
            [
                {"api_version": API_VERSION, "type": "connect_ok"},
                {"api_version": API_VERSION, "type": "event_ack"},
            ],
        )
        self.assertEqual(gateway.state.interventions, [])
        self.assertEqual(gateway.state.observations[-1].name, "runtime.health_state")

    async def test_action_result_reentry_can_finish_silently_after_visible_notification(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )

        replies = await gateway.handle_test_frames(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "hello runtime",
                        "observed_at": "2026-06-21T10:10:00Z",
                    },
                },
            ]
        )
        first_action = _last_action_request(replies)
        self.assertIsNotNone(first_action)

        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "action_result",
                    "device_id": "desktop-dev-1",
                    "interaction_id": first_action["interaction_id"],
                    "interaction_turn_id": first_action["interaction_turn_id"],
                    "request_id": first_action["request_id"],
                    "result": {
                        "status": "ok",
                        "capability": "notification.show",
                        "observed_at": "2026-06-21T10:11:00Z",
                        "details": {
                            "delivered_via": "terminal.stdout",
                            "title": "OpenHalo",
                            "body": "Hello! Runtime here.",
                        },
                    },
                },
            ]
        )

        interaction_update = _last_interaction_update(replies)
        self.assertIsNotNone(interaction_update)
        self.assertEqual(
            len([reply for reply in replies if reply["type"] == "action_request"]),
            0,
        )
        self.assertEqual(interaction_update["interaction"]["visibility"], "silent")
        self.assertEqual(
            interaction_update["interaction"]["summary"],
            "Hello! Runtime here.",
        )
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["source"],
            "post_action",
        )
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["proposal_type"],
            "no_intervention",
        )

    async def test_normal_text_can_form_visible_action_proposal(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )

        replies = await gateway.handle_test_frames(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "help"},
                },
            ]
        )

        proposal = gateway.state.interventions[-1]["proposal"]
        action_request = _last_action_request(replies)

        self.assertIsNotNone(action_request)
        self.assertEqual(action_request["action"]["capability"], "notification.show")
        self.assertEqual(proposal["proposal_type"], "action")
        self.assertEqual(proposal["action_capability"], "notification.show")
        self.assertIn("proposal_rationale", proposal["metadata"])

    async def test_normal_text_can_form_no_intervention_proposal(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )

        replies = await gateway.handle_test_frames(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "thanks"},
                },
            ]
        )

        proposal = gateway.state.interventions[-1]["proposal"]
        interaction_update = _last_interaction_update(replies)
        self.assertIsNotNone(interaction_update)
        self.assertEqual(proposal["proposal_type"], "no_intervention")
        self.assertIsNone(proposal["action_capability"])
        self.assertEqual(gateway.state.interventions[-1]["decision"], "allow")
        self.assertIn("proposal_rationale", proposal["metadata"])

    async def test_normal_path_falls_back_to_source_when_peer_is_not_online(self) -> None:
        state = RuntimeState()
        state.register_device("desktop-dev-2", "desktop-cli")
        state.register_capability("desktop-dev-2", "notification.show")
        state.register_capability("desktop-dev-2", "text.input")
        gateway = RuntimeGateway(
            shared_token="dev-token",
            state=state,
            llm_config_path=TEST_LLM_CONFIG,
        )

        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "stay local"},
                },
            ]
        )

        action_request = _last_action_request(replies)

        self.assertIsNotNone(action_request)
        self.assertEqual(action_request["device_id"], "desktop-dev-1")

    async def test_normal_path_suppresses_user_facing_action_when_location_context_is_ambiguous(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show", "desktop_context"],
        )

        replies = await gateway.handle_test_frames(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
                client.build_observation_event(
                    capability="desktop_context",
                    observations=[
                        {
                            "name": "user.location",
                            "value": "office",
                            "observed_at": "2026-06-19T10:30:00Z",
                            "confidence": 0.81,
                        }
                    ],
                ),
                {
                    "type": "event_push",
                    "device_id": "phone-1",
                    "capability": "mobile_context",
                    "event_id": "evt-mobile-1",
                    "payload": {
                        "observations": [
                            {
                                "name": "user.location",
                                "value": "train",
                                "observed_at": "2026-06-19T10:29:00Z",
                                "confidence": 0.80,
                            }
                        ]
                    },
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "should be suppressed"},
                },
            ]
        )

        interaction_update = _last_interaction_update(replies)
        self.assertIsNotNone(interaction_update)
        self.assertEqual(len([reply for reply in replies if reply["type"] == "action_request"]), 0)
        self.assertEqual(gateway.state.interventions[-1]["decision"], "suppress")
        self.assertEqual(gateway.state.interventions[-1]["reason"], "context_ambiguous")

    async def test_normal_path_uses_latest_known_observation_time_when_event_timestamp_is_missing(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show", "desktop_context"],
        )

        replies = await gateway.handle_test_frames(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
                client.build_observation_event(
                    capability="desktop_context",
                    observations=[
                        {
                            "name": "user.location",
                            "value": "office",
                            "observed_at": "2026-06-19T10:30:00Z",
                            "confidence": 0.81,
                        }
                    ],
                ),
                {
                    "type": "event_push",
                    "device_id": "phone-1",
                    "capability": "mobile_context",
                    "event_id": "evt-mobile-1",
                    "payload": {
                        "observations": [
                            {
                                "name": "user.location",
                                "value": "train",
                                "observed_at": "2026-06-19T10:29:00Z",
                                "confidence": 0.80,
                            }
                        ]
                    },
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "should use latest known context time"},
                },
            ]
        )

        interaction_update = _last_interaction_update(replies)
        self.assertIsNotNone(interaction_update)
        self.assertEqual(
            gateway.state.interventions[-1]["snapshot_contract"]["snapshot_time"],
            "2026-06-19T10:30:00Z",
        )
        self.assertEqual(gateway.state.interventions[-1]["decision"], "suppress")
        self.assertEqual(gateway.state.interventions[-1]["reason"], "context_ambiguous")

    async def test_normal_path_ignores_stale_conflicting_location_evidence(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show", "desktop_context"],
        )

        replies = await gateway.handle_test_frames(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
                client.build_observation_event(
                    capability="desktop_context",
                    observations=[
                        {
                            "name": "user.location",
                            "value": "office",
                            "observed_at": "2026-06-19T10:30:00Z",
                            "confidence": 0.81,
                        }
                    ],
                ),
                {
                    "type": "event_push",
                    "device_id": "phone-1",
                    "capability": "mobile_context",
                    "event_id": "evt-mobile-1",
                    "payload": {
                        "observations": [
                            {
                                "name": "user.location",
                                "value": "train",
                                "observed_at": "2026-06-19T10:29:00Z",
                                "confidence": 0.80,
                            }
                        ]
                    },
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "fresh enough to notify",
                        "observed_at": "2026-06-19T10:36:00Z",
                    },
                },
            ]
        )

        action_request = _last_action_request(replies)

        self.assertIsNotNone(action_request)
        self.assertEqual(action_request["action"]["capability"], "notification.show")
        self.assertEqual(gateway.state.interventions[-1]["decision"], "allow")
        self.assertEqual(gateway.state.interventions[-1]["reason"], "context_clear")
        self.assertEqual(
            gateway.state.interventions[-1]["snapshot_contract"]["fields"][
                "user.current_location"
            ]["status"],
            "stale",
        )

    async def test_normal_path_records_fresh_runtime_health_contract_for_intervention(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        replies = await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                host.build_observation_event(
                    capability="runtime.health",
                    observations=[
                        {
                            "name": "runtime.health_state",
                            "value": "healthy",
                            "observed_at": "2026-06-21T10:08:00Z",
                            "confidence": 1.0,
                        },
                        {
                            "name": "runtime.process_pid",
                            "value": 4242,
                            "observed_at": "2026-06-21T10:08:00Z",
                            "confidence": 1.0,
                        },
                    ],
                ),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "notify me",
                        "observed_at": "2026-06-21T10:10:00Z",
                    },
                },
            ]
        )

        self.assertIsNotNone(_last_action_request(replies))
        snapshot_contract = gateway.state.interventions[-1]["snapshot_contract"]
        self.assertEqual(snapshot_contract["snapshot_time"], "2026-06-21T10:10:00Z")
        self.assertEqual(
            snapshot_contract["fields"]["runtime.current_health_state"]["value"],
            "healthy",
        )
        self.assertEqual(
            snapshot_contract["fields"]["runtime.current_health_state"]["status"],
            "fresh",
        )
        self.assertEqual(
            snapshot_contract["fields"]["runtime.current_process_pid"]["value"],
            4242,
        )
        self.assertEqual(
            snapshot_contract["fields"]["runtime.current_process_pid"]["status"],
            "fresh",
        )

    async def test_normal_path_records_stale_runtime_health_contract_for_intervention(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        replies = await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                host.build_observation_event(
                    capability="runtime.health",
                    observations=[
                        {
                            "name": "runtime.health_state",
                            "value": "healthy",
                            "observed_at": "2026-06-21T10:00:00Z",
                            "confidence": 1.0,
                        }
                    ],
                ),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "notify me anyway",
                        "observed_at": "2026-06-21T10:10:00Z",
                    },
                },
            ]
        )

        self.assertIsNotNone(_last_action_request(replies))
        snapshot_contract = gateway.state.interventions[-1]["snapshot_contract"]
        self.assertEqual(
            snapshot_contract["fields"]["runtime.current_health_state"]["value"],
            "unknown",
        )
        self.assertEqual(
            snapshot_contract["fields"]["runtime.current_health_state"]["status"],
            "stale",
        )
        self.assertEqual(
            snapshot_contract["fields"]["runtime.current_health_state"]["evidence"][0][
                "name"
            ],
            "runtime.health_state",
        )

    async def test_agent_initiative_path_routes_runtime_status_through_presence_and_records_source(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        replies = await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                host.build_observation_event(
                    capability="runtime.health",
                    observations=[
                        {
                            "name": "runtime.health_state",
                            "value": "healthy",
                            "observed_at": "2026-06-21T10:08:00Z",
                            "confidence": 1.0,
                        }
                    ],
                ),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "observed_at": "2026-06-21T10:10:00Z",
                        "agent_initiative": {
                            "action_capability": "runtime.status",
                            "action_payload": {},
                            "reason": "runtime_health_check",
                            "target_device_hint": "host-edge-1",
                        },
                    },
                },
            ]
        )

        action_request = _last_action_request(replies)

        self.assertIsNotNone(action_request)
        self.assertEqual(action_request["device_id"], "host-edge-1")
        self.assertEqual(action_request["action"]["capability"], "runtime.status")
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["source"],
            "agent_initiative",
        )
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["action_capability"],
            "runtime.status",
        )
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["metadata"]["reason"],
            "runtime_health_check",
        )
        self.assertEqual(
            gateway.state.interventions[-1]["snapshot_contract"]["snapshot_time"],
            "2026-06-21T10:10:00Z",
        )

    async def test_agent_initiative_path_is_not_suppressed_by_global_cooldown(self) -> None:
        state = RuntimeState()
        state.record_intervention(
            {
                "target_device_id": "host-edge-1",
                "action_capability": "runtime.status",
                "decision": "allow",
                "reason": "context_clear",
                "proposal": {
                    "source": "agent_initiative",
                    "action_capability": "runtime.status",
                },
                "recorded_at": "2026-06-21T10:06:00Z",
            }
        )
        gateway = RuntimeGateway(
            shared_token="dev-token",
            state=state,
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        replies = await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "observed_at": "2026-06-21T10:10:00Z",
                        "agent_initiative": {
                            "action_capability": "runtime.status",
                            "action_payload": {},
                            "reason": "runtime_health_check",
                            "target_device_hint": "host-edge-1",
                        },
                    },
                },
            ]
        )

        action_request = _last_action_request(replies)
        self.assertIsNotNone(action_request)
        self.assertEqual(action_request["device_id"], "host-edge-1")
        self.assertEqual(action_request["action"]["capability"], "runtime.status")
        self.assertEqual(gateway.state.interventions[-1]["decision"], "allow")
        self.assertEqual(gateway.state.interventions[-1]["reason"], "context_clear")
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["source"],
            "agent_initiative",
        )

    async def test_runtime_can_trigger_agent_initiative_without_edge_text_event(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
            ]
        )

        replies = gateway.trigger_agent_initiative(
            source_device_id="desktop-dev-1",
            initiative_request={
                "action_capability": "runtime.status",
                "action_payload": {},
                "reason": "runtime_health_check",
                "target_device_hint": "host-edge-1",
            },
            observed_at="2026-06-21T10:10:00Z",
        )

        self.assertEqual(replies[-1]["type"], "action_request")
        self.assertEqual(replies[-1]["device_id"], "host-edge-1")
        self.assertEqual(replies[-1]["action"]["capability"], "runtime.status")
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["source"],
            "agent_initiative",
        )

    async def test_agent_initiative_notification_to_terminal_edge_is_suppressed_when_terminal_is_idle(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        terminal = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show", "terminal.context"],
        )

        replies = await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                terminal.build_connect_frame(),
                terminal.build_capability_announce_frame(),
                terminal.build_observation_event(
                    capability="terminal.context",
                    observations=[
                        {
                            "name": "terminal.activity_state",
                            "value": "idle",
                            "observed_at": "2026-06-22T10:09:00Z",
                            "confidence": 1.0,
                        }
                    ],
                ),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "agent.initiative",
                    "payload": {
                        "observed_at": "2026-06-22T10:10:00Z",
                        "agent_initiative": {
                            "action_capability": "notification.show",
                            "action_payload": {
                                "title": "OpenHalo",
                                "body": "runtime push",
                            },
                            "reason": "manual_terminal_push",
                            "target_device_hint": "terminal-edge-1",
                        },
                    },
                },
            ]
        )

        interaction_update = _last_interaction_update(replies)
        self.assertIsNone(interaction_update)
        self.assertEqual(
            len([reply for reply in replies if reply["type"] == "action_request"]),
            0,
        )
        self.assertEqual(gateway.state.interventions[-1]["decision"], "suppress")
        self.assertEqual(
            gateway.state.interventions[-1]["reason"],
            "terminal_inactive",
        )

    async def test_agent_initiative_notification_to_active_terminal_normalizes_title(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        terminal = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show", "terminal.context"],
        )

        replies = await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                terminal.build_connect_frame(),
                terminal.build_capability_announce_frame(),
                terminal.build_observation_event(
                    capability="terminal.context",
                    observations=[
                        {
                            "name": "terminal.activity_state",
                            "value": "active",
                            "observed_at": "2026-06-22T10:09:00Z",
                            "confidence": 1.0,
                        }
                    ],
                ),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "agent.initiative",
                    "payload": {
                        "observed_at": "2026-06-22T10:10:00Z",
                        "agent_initiative": {
                            "action_capability": "notification.show",
                            "action_payload": {
                                "title": "Hermes",
                                "body": "runtime push",
                            },
                            "reason": "manual_terminal_push",
                            "target_device_hint": "terminal-edge-1",
                        },
                    },
                },
            ]
        )

        action_request = _last_action_request(replies)

        self.assertIsNotNone(action_request)
        self.assertEqual(action_request["device_id"], "terminal-edge-1")
        self.assertEqual(action_request["action"]["capability"], "notification.show")
        self.assertEqual(
            action_request["action"]["payload"],
            {"title": "OpenHalo", "body": "runtime push"},
        )
        self.assertEqual(gateway.state.interventions[-1]["decision"], "allow")

    async def test_agent_initiative_notification_to_offline_idle_terminal_is_suppressed_instead_of_falling_back(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        source = SessionClient(
            device_id="desktop-dev-verify",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )

        await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                {
                    "type": "connect",
                    "device": {
                        "device_id": "terminal-edge-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "terminal-edge-1",
                    "capabilities": ["text.input", "notification.show", "terminal.context"],
                },
                {
                    "type": "event_push",
                    "device_id": "terminal-edge-1",
                    "capability": "terminal.context",
                    "event_id": "terminal-idle-1",
                    "payload": {
                        "observations": [
                            {
                                "name": "terminal.activity_state",
                                "value": "idle",
                                "observed_at": "2026-06-22T10:12:00Z",
                                "confidence": 1.0,
                            }
                        ]
                    },
                },
            ]
        )
        gateway.online_device_ids.discard("terminal-edge-1")

        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-verify",
                    "capability": "agent.initiative",
                    "payload": {
                        "observed_at": "2026-06-22T10:13:00Z",
                        "agent_initiative": {
                            "action_capability": "notification.show",
                            "action_payload": {
                                "title": "OpenHalo",
                                "body": "runtime push idle",
                            },
                            "reason": "terminal_push_idle",
                            "target_device_hint": "terminal-edge-1",
                        },
                    },
                },
            ]
        )

        interaction_update = _last_interaction_update(replies)
        self.assertIsNone(interaction_update)
        self.assertEqual(
            len([reply for reply in replies if reply["type"] == "action_request"]),
            0,
        )
        self.assertEqual(gateway.state.interventions[-1]["decision"], "suppress")
        self.assertEqual(
            gateway.state.interventions[-1]["reason"],
            "terminal_inactive",
        )

    async def test_agent_initiative_notification_is_not_suppressed_by_global_cooldown(self) -> None:
        state = RuntimeState()
        state.record_intervention(
            {
                "target_device_id": "desktop-dev-1",
                "action_capability": "notification.show",
                "decision": "allow",
                "reason": "context_clear",
                "recorded_at": "2026-06-19T10:30:00Z",
            }
        )
        gateway = RuntimeGateway(
            shared_token="dev-token",
            state=state,
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "connect",
                    "device": {
                        "device_id": "phone-1",
                        "device_type": "mobile",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "phone-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "phone-1",
                    "capability": "agent.initiative",
                    "payload": {
                        "observed_at": "2026-06-19T10:32:00Z",
                        "agent_initiative": {
                            "action_capability": "notification.show",
                            "action_payload": {
                                "title": "OpenHalo",
                                "body": "repeat too soon",
                            },
                            "reason": "repeat_too_soon",
                            "target_device_hint": "desktop-dev-1",
                        },
                    },
                },
            ]
        )

        action_request = _last_action_request(replies)
        self.assertIsNotNone(action_request)
        self.assertEqual(action_request["device_id"], "desktop-dev-1")
        self.assertEqual(action_request["action"]["capability"], "notification.show")
        self.assertEqual(gateway.state.interventions[-1]["decision"], "allow")
        self.assertEqual(gateway.state.interventions[-1]["reason"], "context_clear")

    async def test_normal_path_allows_repeated_explicit_user_text_during_cooldown(self) -> None:
        state = RuntimeState()
        state.record_intervention(
            {
                "target_device_id": "desktop-dev-1",
                "action_capability": "notification.show",
                "decision": "allow",
                "reason": "context_clear",
                "recorded_at": "2026-06-19T10:30:00Z",
                "proposal": {
                    "source": "sense_first",
                    "metadata": {"trigger": "text.input"},
                },
            }
        )
        gateway = RuntimeGateway(
            shared_token="dev-token",
            state=state,
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "second explicit request",
                        "observed_at": "2026-06-19T10:32:00Z",
                    },
                },
            ]
        )

        self.assertEqual(gateway.state.interventions[-1]["decision"], "allow")
        self.assertEqual(gateway.state.interventions[-1]["reason"], "context_clear")
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["proposal_type"],
            "action",
        )

    async def test_records_host_observations_with_runtime_provenance(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        replies = await gateway.handle_test_frames(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
                client.build_observation_event(
                    capability="runtime.health",
                    observations=[
                        {
                            "name": "runtime.health_state",
                            "value": "healthy",
                            "observed_at": "2026-06-19T09:30:00Z",
                            "confidence": 0.9,
                        }
                    ],
                ),
            ]
        )

        self.assertEqual(replies[-1]["type"], "event_ack")
        self.assertEqual(gateway.state.events[-1]["capability"], "runtime.health")
        self.assertEqual(gateway.state.observations[-1].name, "runtime.health_state")
        self.assertEqual(
            gateway.state.observations[-1].source_device_id,
            "host-edge-1",
        )
        self.assertEqual(
            gateway.state.observations[-1].source_capability,
            "runtime.health",
        )
        self.assertTrue(gateway.state.observations[-1].source_event_id)

    async def test_m17_mobile_edge_routes_terminal_interaction_and_preserves_lineage(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        replies = await gateway.handle_test_frames(
            [
                {
                    "api_version": API_VERSION,
                    "type": "connect",
                    "device": {
                        "device_id": "terminal-edge-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "api_version": API_VERSION,
                    "type": "capability_announce",
                    "device_id": "terminal-edge-1",
                    "capabilities": ["text.input"],
                },
                {
                    "api_version": API_VERSION,
                    "type": "connect",
                    "device": {
                        "device_id": "android-edge-1",
                        "device_type": "android-phone",
                        "role": "interactive_surface",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "api_version": API_VERSION,
                    "type": "capability_announce",
                    "device_id": "android-edge-1",
                    "capabilities": [
                        {
                            "name": "notification.show",
                            "direction": "runtime_to_edge",
                            "kind": "action",
                            "affordances": [
                                "notify_user",
                                "deliver_private_text",
                            ],
                            "modality": "visual_text",
                            "content_capacity": "short_text",
                            "privacy": "personal",
                            "interruptiveness": "medium",
                            "side_effect": "user_visible",
                            "input_schema": {
                                "type": "object",
                                "required": ["body"],
                                "properties": {
                                    "title": {"type": "string"},
                                    "body": {"type": "string"},
                                },
                            },
                        },
                        {
                            "name": "mobile.context",
                            "direction": "edge_to_runtime",
                            "kind": "observation_provider",
                            "observations": [
                                {
                                    "name": "mobile.app_visibility",
                                    "schema": {
                                        "type": "string",
                                        "enum": [
                                            "foreground",
                                            "background",
                                            "unknown",
                                        ],
                                    },
                                    "semantics": ["device_activity"],
                                    "privacy": "personal_device_state",
                                    "freshness_seconds": 120,
                                },
                                {
                                    "name": "mobile.notification_permission",
                                    "schema": {
                                        "type": "string",
                                        "enum": ["granted", "denied", "unknown"],
                                    },
                                    "semantics": ["permission_state"],
                                    "privacy": "personal_device_state",
                                    "freshness_seconds": 300,
                                },
                            ],
                        },
                    ],
                },
                {
                    "api_version": API_VERSION,
                    "type": "connect",
                    "device": {
                        "device_id": "speaker-edge-1",
                        "device_type": "speaker",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "api_version": API_VERSION,
                    "type": "capability_announce",
                    "device_id": "speaker-edge-1",
                    "capabilities": [
                        {
                            "name": "speaker.play_audio",
                            "direction": "runtime_to_edge",
                            "kind": "action",
                            "affordances": ["notify_user"],
                            "modality": "public_audio",
                            "content_capacity": "spoken_text",
                            "privacy": "public",
                            "interruptiveness": "high",
                            "side_effect": "user_visible",
                            "input_schema": {
                                "type": "object",
                                "required": ["message"],
                                "properties": {"message": {"type": "string"}},
                            },
                        }
                    ],
                },
                {
                    "api_version": API_VERSION,
                    "type": "connect",
                    "device": {
                        "device_id": "desk-light-edge-1",
                        "device_type": "ambient-light",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "api_version": API_VERSION,
                    "type": "capability_announce",
                    "device_id": "desk-light-edge-1",
                    "capabilities": [
                        {
                            "name": "light.pulse",
                            "direction": "runtime_to_edge",
                            "kind": "action",
                            "affordances": ["ambient_signal"],
                            "modality": "ambient_light",
                            "content_capacity": "none",
                            "privacy": "public",
                            "interruptiveness": "low",
                            "side_effect": "environment_visible",
                            "input_schema": {"type": "object"},
                        }
                    ],
                },
                {
                    "api_version": API_VERSION,
                    "type": "observation_push",
                    "device_id": "android-edge-1",
                    "capability": "mobile.context",
                    "observations": [
                        {
                            "name": "mobile.app_visibility",
                            "value": "foreground",
                            "observed_at": "2026-07-01T03:56:04Z",
                            "confidence": 1.0,
                        },
                        {
                            "name": "mobile.notification_permission",
                            "value": "granted",
                            "observed_at": "2026-07-01T03:56:04Z",
                            "confidence": 1.0,
                        },
                    ],
                },
                {
                    "api_version": API_VERSION,
                    "type": "event_push",
                    "device_id": "terminal-edge-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "send me a private reminder",
                        "observed_at": "2026-07-01T03:57:00Z",
                    },
                },
            ]
        )

        action_request = _last_action_request(replies)
        self.assertIsNotNone(action_request)
        self.assertEqual(action_request["api_version"], API_VERSION)
        self.assertEqual(action_request["device_id"], "android-edge-1")
        self.assertEqual(action_request["action"]["capability"], "notification.show")

        interaction = gateway.state.interactions[-1]
        self.assertEqual(interaction["source_device_id"], "terminal-edge-1")
        self.assertEqual(
            interaction["participant_device_ids"],
            ["terminal-edge-1", "android-edge-1"],
        )
        self.assertEqual(
            interaction["primary_action"]["target_device_id"],
            "android-edge-1",
        )

        intervention = gateway.state.interventions[-1]
        self.assertEqual(intervention["source_device_id"], "terminal-edge-1")
        self.assertEqual(intervention["target_device_id"], "android-edge-1")
        planning_record = intervention["planning_record"]
        self.assertEqual(
            planning_record["chosen_candidate"]["device_id"],
            "android-edge-1",
        )
        filtered = {
            item["device_id"]: item["reasons"]
            for item in planning_record["filtered_candidates"]
        }
        self.assertIn("target_mismatch:android-edge-1", filtered["speaker-edge-1"])
        self.assertIn("privacy:public", filtered["speaker-edge-1"])
        self.assertIn("target_mismatch:android-edge-1", filtered["desk-light-edge-1"])
        self.assertIn("content_capacity:none", filtered["desk-light-edge-1"])

        result_replies = await gateway.handle_test_frames(
            [
                {
                    "api_version": API_VERSION,
                    "type": "action_result",
                    "request_id": action_request["request_id"],
                    "interaction_id": action_request["interaction_id"],
                    "interaction_turn_id": action_request["interaction_turn_id"],
                    "device_id": "android-edge-1",
                    "result": {
                        "status": "ok",
                        "capability": "notification.show",
                        "observed_at": "2026-07-01T03:57:02Z",
                        "details": {
                            "title": action_request["action"]["payload"]["title"],
                            "body": action_request["action"]["payload"]["body"],
                        },
                    },
                }
            ]
        )

        self.assertEqual(gateway.state.action_results[-1]["status"], "ok")
        self.assertEqual(
            gateway.state.action_results[-1]["capability"],
            "notification.show",
        )
        self.assertEqual(
            gateway.state.interactions[-1]["interaction_id"],
            action_request["interaction_id"],
        )
        self.assertIn("android-edge-1", gateway.state.interactions[-1]["participant_device_ids"])
        self.assertTrue(
            any(
                reply["type"] in {"action_request", "interaction_update"}
                for reply in result_replies
            )
        )

    async def test_m17_6_cross_edge_notification_result_acknowledges_source_edge(
        self,
    ) -> None:
        class SourceAckProposalFormation:
            def build_post_action_proposal(
                self,
                interaction: dict,
                prior_proposal: dict,
                result: dict,
                turn_index: int,
                snapshot: dict,
                grounding_bundle: dict | None = None,
                correlation: dict | None = None,
            ) -> InterventionProposal:
                return InterventionProposal(
                    kind="notify",
                    proposal_type="action",
                    source="post_action",
                    action_capability="notification.show",
                    required_capability="notification.show",
                    action_payload={
                        "title": "OpenHalo",
                        "body": "Sent to your phone.",
                    },
                    message="Sent to your phone.",
                    metadata={
                        "trigger": "action_result",
                        "interaction_id": interaction["interaction_id"],
                        "post_action_semantics": "source_ack",
                        "loop_decision": "continue",
                        "source_device_id": interaction.get("source_device_id"),
                        "previous_target_device_id": (
                            interaction.get("primary_action") or {}
                        ).get("target_device_id"),
                        "participant_device_ids": list(
                            interaction.get("participant_device_ids", [])
                        ),
                    },
                    target_device_hint=interaction.get("source_device_id"),
                    interaction_type=interaction.get("interaction_type", "pull"),
                    visibility_intent="visible",
                    candidate_surface_hints=["source_device"],
                )

        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        terminal = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )

        replies = await gateway.handle_test_frames(
            [
                terminal.build_connect_frame(),
                terminal.build_capability_announce_frame(),
                {
                    "api_version": API_VERSION,
                    "type": "connect",
                    "device": {
                        "device_id": "android-edge-1",
                        "device_type": "android-phone",
                        "role": "interactive_surface",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "api_version": API_VERSION,
                    "type": "capability_announce",
                    "device_id": "android-edge-1",
                    "capabilities": ["notification.show"],
                },
                {
                    "api_version": API_VERSION,
                    "type": "event_push",
                    "device_id": "terminal-edge-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "send hello to my phone",
                        "observed_at": "2026-07-06T09:00:00Z",
                    },
                },
            ]
        )
        phone_action = _last_action_request(replies)
        self.assertIsNotNone(phone_action)
        self.assertEqual(phone_action["device_id"], "android-edge-1")

        gateway.proposal_formation = SourceAckProposalFormation()
        result_replies = await gateway.handle_test_frames(
            [
                {
                    "api_version": API_VERSION,
                    "type": "action_result",
                    "request_id": phone_action["request_id"],
                    "interaction_id": phone_action["interaction_id"],
                    "interaction_turn_id": phone_action["interaction_turn_id"],
                    "device_id": "android-edge-1",
                    "result": {
                        "status": "ok",
                        "capability": "notification.show",
                        "observed_at": "2026-07-06T09:00:02Z",
                        "details": {
                            "title": phone_action["action"]["payload"]["title"],
                            "body": phone_action["action"]["payload"]["body"],
                            "delivered_via": "android.urgent_alert",
                        },
                    },
                }
            ]
        )

        source_ack = _last_action_request(result_replies)
        self.assertIsNotNone(source_ack)
        self.assertEqual(source_ack["interaction_id"], phone_action["interaction_id"])
        self.assertEqual(source_ack["device_id"], "terminal-edge-1")
        self.assertEqual(source_ack["action"]["capability"], "notification.show")
        self.assertNotIn("notification.show", source_ack["action"]["payload"]["body"])
        self.assertNotIn("android-edge-1", source_ack["action"]["payload"]["body"])
        proposal = gateway.state.interventions[-1]["proposal"]
        self.assertEqual(proposal["source"], "post_action")
        self.assertEqual(proposal["metadata"]["post_action_semantics"], "source_ack")
        self.assertEqual(
            proposal["metadata"]["source_device_id"],
            "terminal-edge-1",
        )
        self.assertEqual(
            proposal["metadata"]["previous_target_device_id"],
            "android-edge-1",
        )
        self.assertEqual(
            proposal["metadata"]["participant_device_ids"],
            ["terminal-edge-1", "android-edge-1"],
        )

    async def test_m17_6_action_result_loop_reenters_proposal_until_model_stops(
        self,
    ) -> None:
        class HarnessProposalFormation:
            def __init__(self) -> None:
                self.calls = []

            def build_post_action_proposal(
                self,
                interaction: dict,
                prior_proposal: dict,
                result: dict,
                turn_index: int,
                snapshot: dict,
                grounding_bundle: dict | None = None,
                correlation: dict | None = None,
            ) -> InterventionProposal:
                self.calls.append(
                    {
                        "interaction": dict(interaction),
                        "prior_proposal": dict(prior_proposal),
                        "result": dict(result),
                        "turn_index": turn_index,
                    }
                )
                if len(self.calls) == 1:
                    return InterventionProposal(
                        kind="notify",
                        proposal_type="action",
                        source="post_action",
                        action_capability="notification.show",
                        required_capability="notification.show",
                        action_payload={
                            "title": "OpenHalo",
                            "body": "Sent to your phone.",
                        },
                        message="Sent to your phone.",
                        metadata={
                            "trigger": "action_result",
                            "interaction_id": interaction["interaction_id"],
                            "post_action_semantics": "source_ack",
                            "loop_decision": "continue",
                        },
                        target_device_hint=interaction.get("source_device_id"),
                        interaction_type=interaction.get("interaction_type", "pull"),
                        visibility_intent="visible",
                        candidate_surface_hints=["source_device"],
                    )
                return InterventionProposal(
                    kind="no_intervention",
                    proposal_type="no_intervention",
                    source="post_action",
                    action_capability=None,
                    required_capability=None,
                    action_payload={},
                    message="",
                    metadata={
                        "trigger": "action_result",
                        "interaction_id": interaction["interaction_id"],
                        "post_action_semantics": "model_stopped_action_loop",
                        "loop_decision": "complete",
                    },
                    interaction_type=interaction.get("interaction_type", "pull"),
                    visibility_intent="silent",
                    candidate_surface_hints=["background"],
                )

        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        terminal = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )

        replies = await gateway.handle_test_frames(
            [
                terminal.build_connect_frame(),
                terminal.build_capability_announce_frame(),
                {
                    "api_version": API_VERSION,
                    "type": "connect",
                    "device": {
                        "device_id": "android-edge-1",
                        "device_type": "android-phone",
                        "role": "interactive_surface",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "api_version": API_VERSION,
                    "type": "capability_announce",
                    "device_id": "android-edge-1",
                    "capabilities": ["notification.show"],
                },
                {
                    "api_version": API_VERSION,
                    "type": "event_push",
                    "device_id": "terminal-edge-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "send hello to my phone",
                        "observed_at": "2026-07-06T09:00:00Z",
                    },
                },
            ]
        )
        phone_action = _last_action_request(replies)
        self.assertIsNotNone(phone_action)
        self.assertEqual(phone_action["device_id"], "android-edge-1")

        harness = HarnessProposalFormation()
        gateway.proposal_formation = harness

        phone_result_replies = await gateway.handle_test_frames(
            [
                {
                    "api_version": API_VERSION,
                    "type": "action_result",
                    "request_id": phone_action["request_id"],
                    "interaction_id": phone_action["interaction_id"],
                    "interaction_turn_id": phone_action["interaction_turn_id"],
                    "device_id": "android-edge-1",
                    "result": {
                        "status": "ok",
                        "capability": "notification.show",
                        "observed_at": "2026-07-06T09:00:02Z",
                        "details": {
                            "title": phone_action["action"]["payload"]["title"],
                            "body": phone_action["action"]["payload"]["body"],
                            "delivered_via": "android.urgent_alert",
                        },
                    },
                }
            ]
        )
        source_ack = _last_action_request(phone_result_replies)
        self.assertIsNotNone(source_ack)
        self.assertNotEqual(source_ack["request_id"], phone_action["request_id"])
        self.assertEqual(source_ack["device_id"], "terminal-edge-1")
        self.assertEqual(
            source_ack["action"]["payload"],
            {"title": "OpenHalo", "body": "Sent to your phone."},
        )

        terminal_result_replies = await gateway.handle_test_frames(
            [
                {
                    "api_version": API_VERSION,
                    "type": "action_result",
                    "request_id": source_ack["request_id"],
                    "interaction_id": source_ack["interaction_id"],
                    "interaction_turn_id": source_ack["interaction_turn_id"],
                    "device_id": "terminal-edge-1",
                    "result": {
                        "status": "ok",
                        "capability": "notification.show",
                        "observed_at": "2026-07-06T09:00:03Z",
                        "details": {
                            "title": source_ack["action"]["payload"]["title"],
                            "body": source_ack["action"]["payload"]["body"],
                            "delivered_via": "terminal.stdout",
                        },
                    },
                }
            ]
        )

        self.assertIsNone(_last_action_request(terminal_result_replies))
        interaction_update = _last_interaction_update(terminal_result_replies)
        self.assertIsNotNone(interaction_update)
        self.assertEqual(interaction_update["interaction"]["status"], "completed")
        self.assertEqual(len(harness.calls), 2)
        self.assertEqual(harness.calls[0]["result"]["device_id"], "android-edge-1")
        self.assertEqual(harness.calls[1]["result"]["device_id"], "terminal-edge-1")
        self.assertEqual(harness.calls[0]["result"]["details"]["delivered_via"], "android.urgent_alert")
        self.assertEqual(harness.calls[1]["result"]["details"]["delivered_via"], "terminal.stdout")
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["metadata"]["loop_decision"],
            "complete",
        )

    async def test_m17_6_unknown_action_result_lineage_returns_public_error(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        replies = await gateway.handle_test_frames(
            [
                {
                    "api_version": API_VERSION,
                    "type": "connect",
                    "device": {
                        "device_id": "android-edge-1",
                        "device_type": "android-phone",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "api_version": API_VERSION,
                    "type": "action_result",
                    "request_id": "action-missing",
                    "interaction_id": "interaction-missing",
                    "interaction_turn_id": "interaction-turn-missing",
                    "device_id": "android-edge-1",
                    "result": {
                        "status": "ok",
                        "capability": "notification.show",
                        "observed_at": "2026-07-06T09:00:02Z",
                        "details": {"title": "OpenHalo", "body": "hello"},
                    },
                },
            ]
        )

        error = _last_error(replies)
        self.assertIsNotNone(error)
        self.assertEqual(error["code"], "lineage_missing")
        self.assertEqual(error["interaction_id"], "interaction-missing")
        self.assertEqual(error["device_id"], "android-edge-1")
        self.assertEqual(gateway.state.action_results, [])

    async def test_unknown_capability_announce_returns_public_error(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        replies = await gateway.handle_test_frames(
            [
                {
                    "api_version": API_VERSION,
                    "type": "capability_announce",
                    "device_id": "android-edge-1",
                    "capabilities": ["notification.show"],
                }
            ]
        )

        error = _last_error(replies)
        self.assertIsNotNone(error)
        self.assertEqual(error["code"], "unknown_device")
        self.assertEqual(error["device_id"], "android-edge-1")


if __name__ == "__main__":
    unittest.main()
