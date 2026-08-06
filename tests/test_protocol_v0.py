import importlib
import tomllib
import unittest
from pathlib import Path

from edge_api.auth import build_challenge_payload
from edge_api.auth import generate_private_key
from edge_api.auth import public_key_spki_der
from edge_api.auth import sign_challenge
from edge_api.auth import verify_challenge_signature
from edge_api.protocol import API_VERSION
from edge_api.protocol import build_capability_announce_frame
from edge_api.protocol import build_connect_frame
from edge_api.protocol import build_observation_push_frame
from edge_api.protocol import validate_frame


class ImportSmokeTests(unittest.TestCase):
    def test_runtime_package_imports(self) -> None:
        self.assertEqual(
            importlib.import_module("personal_runtime").__doc__,
            "Personal runtime v0 package.",
        )
        self.assertEqual(
            importlib.import_module("device_edge").__doc__,
            "Device edge v0 package.",
        )

    def test_pyproject_declares_explicit_package_discovery(self) -> None:
        payload = tomllib.loads(
            Path("pyproject.toml").read_text(encoding="utf-8")
        )

        self.assertEqual(
            payload["tool"]["setuptools"]["packages"]["find"]["include"],
            [
                "agent_guard",
                "device_edge",
                "device_edge.*",
                "edge_api",
                "openhalo",
                "openhalo_common",
                "personal_runtime",
            ],
        )
        self.assertIn("cryptography>=46,<47", payload["project"]["dependencies"])


class ProtocolTests(unittest.TestCase):
    def test_uses_the_v2_public_protocol_only(self) -> None:
        self.assertEqual(API_VERSION, "edge.runtime.v2")
        with self.assertRaisesRegex(ValueError, "Unsupported api_version"):
            validate_frame({"api_version": "edge.runtime.v1", "type": "connect"})

    def test_p256_authentication_signature_binds_all_challenge_fields(self) -> None:
        private_key = generate_private_key()
        payload = build_challenge_payload(
            audience="wss://runtime.example/openhalo/edge",
            device_id="terminal-edge-1",
            session_id="session-1",
            challenge_id="challenge-1",
            nonce="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY",
            expires_at="2030-01-01T12:01:00Z",
        )
        signature = sign_challenge(private_key, payload)

        self.assertTrue(
            verify_challenge_signature(
                public_key_spki_der(private_key.public_key()), payload, signature
            )
        )
        self.assertFalse(
            verify_challenge_signature(
                public_key_spki_der(private_key.public_key()),
                build_challenge_payload(
                    audience="wss://other.example/openhalo/edge",
                    device_id="terminal-edge-1",
                    session_id="session-1",
                    challenge_id="challenge-1",
                    nonce="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY",
                    expires_at="2030-01-01T12:01:00Z",
                ),
                signature,
            )
        )

    def test_accepts_versioned_interaction_progress_frame(self) -> None:
        frame = {
            "api_version": API_VERSION,
            "type": "interaction_progress",
            "device_id": "terminal-edge-1",
            "progress": {
                "version": 1,
                "interaction_id": "interaction-1",
                "interaction_turn_id": "interaction-turn-1",
                "sequence": 1,
                "phase": "deliberating",
                "state": "active",
                "occurred_at": "2026-07-18T10:00:00Z",
                "presentation_hint": "working",
            },
        }

        self.assertEqual(validate_frame(frame), frame)

    def test_builds_pairing_connect_frame_without_a_bearer_token(self) -> None:
        frame = build_connect_frame(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            audience="wss://runtime.example/openhalo/edge",
            pairing_code="pairing-code",
            public_key="cHVibGljLWtleQ",
            display_name="Maya's Terminal",
        )

        self.assertEqual(frame["type"], "connect")
        self.assertEqual(frame["api_version"], API_VERSION)
        self.assertEqual(frame["device"]["device_id"], "desktop-dev-1")
        self.assertEqual(frame["auth"]["kind"], "pairing")
        self.assertEqual(frame["auth"]["pairing_code"], "pairing-code")
        self.assertNotIn("token", frame["auth"])

    def test_builds_object_capability_announce_frame(self) -> None:
        frame = build_capability_announce_frame(
            device_id="desktop-dev-1",
            capabilities=[
                {
                    "name": "notification.show",
                    "direction": "runtime_to_edge",
                }
            ],
        )

        self.assertEqual(frame["api_version"], API_VERSION)
        self.assertEqual(frame["type"], "capability_announce")
        self.assertEqual(
            frame["capabilities"][0],
            {
                "name": "notification.show",
                "direction": "runtime_to_edge",
            },
        )

    def test_builds_mobile_style_rich_capability_registration(self) -> None:
        notification_capability = {
            "name": "notification.show",
            "direction": "runtime_to_edge",
            "kind": "action",
            "affordances": ["notify_user", "deliver_private_text"],
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
        }
        observation_provider = {
            "name": "mobile.context",
            "direction": "edge_to_runtime",
            "kind": "observation_provider",
            "observations": [
                {
                    "name": "mobile.screen_state",
                    "schema": {
                        "type": "string",
                        "enum": ["locked", "unlocked", "unknown"],
                    },
                    "semantics": ["device_activity"],
                    "privacy": "personal_device_state",
                    "freshness_seconds": 120,
                    "confidence": {"type": "edge_reported"},
                }
            ],
        }

        frame = build_capability_announce_frame(
            "phone-edge-1",
            [notification_capability, observation_provider],
        )

        self.assertEqual(frame["type"], "capability_announce")
        self.assertEqual(frame["api_version"], API_VERSION)
        self.assertEqual(frame["device_id"], "phone-edge-1")
        self.assertEqual(frame["capabilities"][0], notification_capability)
        self.assertEqual(frame["capabilities"][1], observation_provider)

    def test_rejects_malformed_rich_capability_registration(self) -> None:
        with self.assertRaises(ValueError):
            build_capability_announce_frame(
                "phone-edge-1",
                [{"direction": "runtime_to_edge", "kind": "action"}],
            )

    def test_rejects_rich_action_registration_with_non_object_input_schema(self) -> None:
        with self.assertRaises(ValueError):
            build_capability_announce_frame(
                "terminal-edge-1",
                [
                    {
                        "name": "coding.turn.start",
                        "direction": "runtime_to_edge",
                        "kind": "action",
                        "input_schema": "not-a-schema",
                    }
                ],
            )

    def test_validates_generic_process_contracts_on_action_capabilities(self) -> None:
        frame = build_capability_announce_frame(
            "terminal-edge-1",
            [
                {
                    "name": "agent.run",
                    "direction": "runtime_to_edge",
                    "kind": "action",
                    "process_contract": {
                        "continuation_policy": "until_settled",
                        "watches": [
                            {
                                "watch_id": "completion",
                                "observation_names": ["process.activity.v1"],
                            }
                        ],
                    },
                }
            ],
        )

        self.assertEqual("until_settled", frame["capabilities"][0]["process_contract"]["continuation_policy"])
        with self.assertRaisesRegex(ValueError, "process_contract"):
            build_capability_announce_frame(
                "terminal-edge-1",
                [
                    {
                        "name": "agent.run",
                        "direction": "runtime_to_edge",
                        "process_contract": {"continuation_policy": "until_settled"},
                    }
                ],
            )

    def test_builds_observation_push_frame(self) -> None:
        frame = build_observation_push_frame(
            device_id="host-edge-1",
            capability="runtime.health",
            observations=[
                {
                    "name": "runtime.health_state",
                    "value": "healthy",
                    "observed_at": "2026-06-29T10:00:00Z",
                    "confidence": 1.0,
                }
            ],
        )

        self.assertEqual(frame["api_version"], API_VERSION)
        self.assertEqual(frame["type"], "observation_push")
        self.assertEqual(frame["capability"], "runtime.health")
        self.assertEqual(
            frame["observations"][0]["name"],
            "runtime.health_state",
        )

    def test_rejects_frame_without_type(self) -> None:
        with self.assertRaises(ValueError):
            validate_frame({"device": {}})


if __name__ == "__main__":
    unittest.main()
