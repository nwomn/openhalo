import asyncio
import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from device_edge.shared.session_client import SessionClient
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.runtime_orchestrator import RuntimeOrchestrator
from openhalo_common.diagnostics import InMemoryDiagnosticRecorder
from openhalo_common.diagnostics import JsonlDiagnosticRecorder
from personal_runtime.agent_executor import ProposalFormation
from personal_runtime.presence_router import PresenceRouter


TEST_LLM_CONFIG = Path("tests/fixtures/llm-config-test.toml")


class RuntimeOrchestratorTests(unittest.TestCase):
    def test_gateway_uses_runtime_orchestrator_for_event_frames(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        self.assertIsInstance(gateway.orchestrator, RuntimeOrchestrator)

    def test_orchestrator_handles_normal_turn_with_correlation(self) -> None:
        diagnostics = InMemoryDiagnosticRecorder(
            timestamp_provider=lambda: "2026-06-30T12:00:00Z"
        )
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
            diagnostic_recorder=diagnostics,
        )
        client = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
        )
        gateway.run_roundtrip(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
            ]
        )

        frame = client.build_text_event("hello runtime")
        replies = gateway.orchestrator.handle_event_frame(frame)

        action_request = next(
            reply for reply in replies if reply["type"] == "action_request"
        )
        self.assertEqual(action_request["trace_id"], frame["trace_id"])
        self.assertEqual(
            gateway.state.interventions[-1]["correlation"]["trace_id"],
            frame["trace_id"],
        )
        modules = [event.module for event in diagnostics.events]
        self.assertIn("State / Context", modules)
        self.assertIn("Grounding / Runtime Memory", modules)
        self.assertIn("Proposal Formation", modules)
        self.assertIn("Presence Router", modules)
        self.assertIn("Execution Planning", modules)
        self.assertIn("Action Layer", modules)

    def test_orchestrator_registers_user_and_initiative_origins_in_pool(self) -> None:
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
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["runtime.control"],
        )
        gateway.run_roundtrip(
            [
                terminal.build_connect_frame(),
                terminal.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
            ]
        )

        user_replies = gateway.run_roundtrip(
            [terminal.build_text_event("hello runtime")]
        )
        user_action = next(
            reply for reply in user_replies if reply["type"] == "action_request"
        )
        initiative_replies = gateway.trigger_agent_initiative(
            source_device_id="terminal-edge-1",
            initiative_request={
                "action_capability": "runtime.status",
                "action_payload": {},
                "reason": "runtime_health_check",
                "target_device_hint": "host-edge-1",
            },
            observed_at="2026-07-13T10:00:00Z",
        )
        initiative_action = next(
            reply
            for reply in initiative_replies
            if reply["type"] == "action_request"
        )

        user_interaction = next(
            interaction
            for interaction in gateway.state.interactions
            if interaction["interaction_id"] == user_action["interaction_id"]
        )
        initiative_interaction = next(
            interaction
            for interaction in gateway.state.interactions
            if interaction["interaction_id"] == initiative_action["interaction_id"]
        )
        self.assertEqual(user_interaction["origin"], "user_event")
        self.assertEqual(initiative_interaction["origin"], "agent_initiative")
        self.assertTrue(user_interaction["causal_scope"]["key"])
        self.assertTrue(initiative_interaction["causal_scope"]["key"])
        self.assertIn("interaction_turn_id", user_action)
        self.assertIn("interaction_turn_id", initiative_action)
        self.assertNotEqual(
            user_action["interaction_turn_id"],
            user_action.get("turn_id"),
        )

    def test_admitted_observation_uses_normal_interaction_proposal_chain(self) -> None:
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
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["runtime.health", "runtime.control"],
        )
        gateway.run_roundtrip(
            [
                terminal.build_connect_frame(),
                terminal.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
            ]
        )

        replies = gateway.run_roundtrip(
            [
                {
                    "type": "event_push",
                    "device_id": "host-edge-1",
                    "capability": "runtime.health",
                    "event_id": "runtime-health-degraded-1",
                    "payload": {
                        "observations": [
                            {
                                "name": "runtime.health_state",
                                "value": "degraded",
                                "observed_at": "2026-07-13T10:00:00Z",
                                "confidence": 1.0,
                            }
                        ]
                    },
                }
            ]
        )

        interaction = next(
            item
            for item in gateway.state.interactions
            if item["origin"] == "observation_driven"
        )
        intervention = next(
            item
            for item in gateway.state.interventions
            if item["interaction_id"] == interaction["interaction_id"]
        )
        self.assertEqual(
            interaction["causal_scope"]["key"],
            "proactive:runtime_health_failure:host-edge-1:runtime-health-degraded-1",
        )
        self.assertEqual(intervention["proposal"]["source"], "observation_driven")
        self.assertEqual(intervention["proposal"]["proposal_type"], "no_intervention")
        self.assertEqual(intervention["decision"], "allow")
        self.assertTrue(
            any(reply["type"] == "interaction_update" for reply in replies)
        )

    def test_admitted_observation_persists_interaction_before_proposal_formation(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        persisted_snapshots = []
        gateway._persist_state = lambda: persisted_snapshots.append(
            copy.deepcopy(gateway.state.to_dict())
        )

        class FailingProposalFormation:
            def build_observation_driven_proposal(
                self,
                interaction: dict,
                admission: dict,
                observations: list[dict],
                turn_index: int,
                snapshot: dict,
                grounding_bundle: dict | None = None,
                correlation: dict | None = None,
            ):
                raise RuntimeError("proposal formation stopped")

        gateway.proposal_formation = FailingProposalFormation()
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["runtime.health", "runtime.control"],
        )
        gateway.run_roundtrip(
            [host.build_connect_frame(), host.build_capability_announce_frame()]
        )
        persisted_snapshots.clear()

        with self.assertRaisesRegex(RuntimeError, "proposal formation stopped"):
            gateway.run_roundtrip(
                [
                    {
                        "type": "event_push",
                        "device_id": "host-edge-1",
                        "capability": "runtime.health",
                        "event_id": "runtime-health-degraded-persist-before-proposal",
                        "payload": {
                            "observations": [
                                {
                                    "name": "runtime.health_state",
                                    "value": "degraded",
                                    "observed_at": "2026-07-13T10:00:00Z",
                                    "confidence": 1.0,
                                }
                            ]
                        },
                    }
                ]
            )

        self.assertTrue(
            any(
                any(
                    interaction.get("origin") == "observation_driven"
                    for interaction in snapshot["interactions"]
                )
                for snapshot in persisted_snapshots
            )
        )

    def test_observation_driven_proposal_excludes_raw_edge_history(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
            grounding_edge_history_fetcher=lambda: {
                "history_kind": "observation_window",
                "entries": [{"visible_text": "secret screen text"}],
                "available_entries": 1,
                "returned_entries": 1,
            },
        )

        class CaptureProposalFormation:
            def __init__(self) -> None:
                self.grounding_bundle = None

            def build_observation_driven_proposal(
                self,
                interaction: dict,
                admission: dict,
                observations: list[dict],
                turn_index: int,
                snapshot: dict,
                grounding_bundle: dict | None = None,
                correlation: dict | None = None,
            ):
                from personal_runtime.agent_executor import InterventionProposal

                self.grounding_bundle = grounding_bundle
                return InterventionProposal(
                    kind="no_intervention",
                    proposal_type="no_intervention",
                    source="observation_driven",
                    action_capability=None,
                    required_capability=None,
                    action_payload={},
                    message="",
                    metadata={},
                    interaction_type="push",
                    visibility_intent="silent",
                )

        capture = CaptureProposalFormation()
        gateway.proposal_formation = capture
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["runtime.health", "runtime.control"],
        )
        gateway.run_roundtrip(
            [host.build_connect_frame(), host.build_capability_announce_frame()]
        )

        gateway.run_roundtrip(
            [
                {
                    "type": "event_push",
                    "device_id": "host-edge-1",
                    "capability": "runtime.health",
                    "event_id": "runtime-health-degraded-privacy",
                    "payload": {
                        "observations": [
                            {
                                "name": "runtime.health_state",
                                "value": "degraded",
                                "observed_at": "2026-07-13T10:00:00Z",
                                "confidence": 1.0,
                            }
                        ]
                    },
                }
            ]
        )

        self.assertIsNotNone(capture.grounding_bundle)
        self.assertNotIn("secret screen text", json.dumps(capture.grounding_bundle))

    def test_observation_driven_proposal_sanitizes_mobile_screen_context(
        self,
    ) -> None:
        from edge_api.protocol import build_capability_announce_frame

        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        class CaptureProposalFormation:
            def __init__(self) -> None:
                self.snapshot = None
                self.grounding_bundle = None

            def build_observation_driven_proposal(
                self,
                interaction: dict,
                admission: dict,
                observations: list[dict],
                turn_index: int,
                snapshot: dict,
                grounding_bundle: dict | None = None,
                correlation: dict | None = None,
            ):
                from personal_runtime.agent_executor import InterventionProposal

                self.snapshot = snapshot
                self.grounding_bundle = grounding_bundle
                return InterventionProposal(
                    kind="no_intervention",
                    proposal_type="no_intervention",
                    source="observation_driven",
                    action_capability=None,
                    required_capability=None,
                    action_payload={},
                    message="",
                    metadata={},
                    interaction_type="push",
                    visibility_intent="silent",
                )

        capture = CaptureProposalFormation()
        gateway.proposal_formation = capture
        phone = SessionClient(
            device_id="android-edge-1",
            device_type="android-phone",
            token="dev-token",
            capabilities=["mobile.screen_context"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["runtime.health", "runtime.control"],
        )
        gateway.run_roundtrip(
            [
                phone.build_connect_frame(),
                build_capability_announce_frame(
                    "android-edge-1",
                    [
                        {
                            "name": "mobile.screen_context",
                            "direction": "edge_to_runtime",
                            "kind": "observation_provider",
                            "observations": [
                                {
                                    "name": "mobile.screen_context",
                                    "schema": {"type": "object"},
                                }
                            ],
                        }
                    ],
                    session_id=phone.session_id,
                ),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                phone.build_observation_event(
                    capability="mobile.screen_context",
                    observations=[
                        {
                            "name": "mobile.screen_context",
                            "value": {
                                "screen_kind": "conversation_or_feed",
                                "screen_state": "unlocked",
                                "capture_mode": "accessibility_tree",
                                "sensitivity": "normal",
                                "package_name": "com.example.private",
                                "root_class_name": "PrivateRoot",
                                "visible_text_summary": "secret screen text",
                                "interactive_elements": [
                                    {"label": "secret button"}
                                ],
                            },
                            "observed_at": "2026-07-13T09:59:00Z",
                            "confidence": 1.0,
                        }
                    ],
                ),
            ]
        )

        gateway.run_roundtrip(
            [
                {
                    "type": "event_push",
                    "device_id": "host-edge-1",
                    "capability": "runtime.health",
                    "event_id": "runtime-health-degraded-screen-context",
                    "payload": {
                        "observations": [
                            {
                                "name": "runtime.health_state",
                                "value": "degraded",
                                "observed_at": "2026-07-13T10:00:00Z",
                                "confidence": 1.0,
                            }
                        ]
                    },
                }
            ]
        )

        self.assertIsNotNone(capture.snapshot)
        self.assertIsNotNone(capture.grounding_bundle)
        rendered_snapshot = json.dumps(capture.snapshot)
        rendered_grounding = json.dumps(capture.grounding_bundle)
        intervention = next(
            item
            for item in gateway.state.interventions
            if item["proposal"].get("source") == "observation_driven"
        )
        rendered_contract = json.dumps(intervention["snapshot_contract"])
        for rendered in (
            rendered_snapshot,
            rendered_grounding,
            rendered_contract,
        ):
            self.assertNotIn("com.example.private", rendered)
            self.assertNotIn("PrivateRoot", rendered)
            self.assertNotIn("secret screen text", rendered)
            self.assertNotIn("secret button", rendered)
        screen_context = capture.snapshot["mobile.current_screen_context"]
        self.assertEqual(screen_context["screen_kind"], "conversation_or_feed")
        self.assertEqual(screen_context["sensitivity"], "normal")

    def test_admitted_observation_does_not_block_on_unrelated_interaction(self) -> None:
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
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["runtime.health", "runtime.control"],
        )
        gateway.run_roundtrip(
            [
                terminal.build_connect_frame(),
                terminal.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
            ]
        )
        user_action = next(
            reply
            for reply in gateway.run_roundtrip(
                [terminal.build_text_event("hello runtime")]
            )
            if reply["type"] == "action_request"
        )

        gateway.run_roundtrip(
            [
                {
                    "type": "event_push",
                    "device_id": "host-edge-1",
                    "capability": "runtime.health",
                    "event_id": "runtime-health-degraded-2",
                    "payload": {
                        "observations": [
                            {
                                "name": "runtime.health_state",
                                "value": "degraded",
                                "observed_at": "2026-07-13T10:00:00Z",
                                "confidence": 1.0,
                            }
                        ]
                    },
                }
            ]
        )

        observation_interaction = next(
            item
            for item in gateway.state.interactions
            if item["origin"] == "observation_driven"
        )
        user_interaction = next(
            item
            for item in gateway.state.interactions
            if item["interaction_id"] == user_action["interaction_id"]
        )
        self.assertNotEqual(
            observation_interaction["interaction_id"],
            user_interaction["interaction_id"],
        )
        self.assertEqual(user_interaction["status"], "planned")

    def test_observation_driven_terminal_notification_without_hint_is_suppressed_when_idle(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        class ObservationProposalFormation:
            def build_observation_driven_proposal(
                self,
                interaction: dict,
                admission: dict,
                observations: list[dict],
                turn_index: int,
                snapshot: dict,
                grounding_bundle: dict | None = None,
                correlation: dict | None = None,
            ):
                from personal_runtime.agent_executor import InterventionProposal

                return InterventionProposal(
                    kind="notify",
                    proposal_type="action",
                    source="observation_driven",
                    action_capability="notification.show",
                    required_capability="notification.show",
                    action_payload={"message": "Runtime health changed."},
                    message="Runtime health changed.",
                    metadata={"reason_code": admission["reason_code"]},
                    target_device_hint=None,
                    interaction_type="push",
                    visibility_intent="visible",
                    candidate_surface_hints=["available_surface"],
                )

        gateway.proposal_formation = ObservationProposalFormation()
        terminal = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show", "terminal.context"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["runtime.health", "runtime.control"],
        )
        gateway.run_roundtrip(
            [
                terminal.build_connect_frame(),
                terminal.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                terminal.build_observation_event(
                    capability="terminal.context",
                    observations=[
                        {
                            "name": "terminal.activity_state",
                            "value": "idle",
                            "observed_at": "2026-07-13T09:59:00Z",
                            "confidence": 1.0,
                        }
                    ],
                ),
            ]
        )

        replies = gateway.run_roundtrip(
            [
                {
                    "type": "event_push",
                    "device_id": "host-edge-1",
                    "capability": "runtime.health",
                    "event_id": "runtime-health-degraded-3",
                    "payload": {
                        "observations": [
                            {
                                "name": "runtime.health_state",
                                "value": "degraded",
                                "observed_at": "2026-07-13T10:00:00Z",
                                "confidence": 1.0,
                            }
                        ]
                    },
                }
            ]
        )

        self.assertFalse(
            any(reply["type"] == "action_request" for reply in replies)
        )
        self.assertEqual(gateway.state.interventions[-1]["decision"], "suppress")
        self.assertEqual(
            gateway.state.interventions[-1]["reason"],
            "terminal_inactive",
        )

    def test_observation_driven_notification_completes_after_action_result(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        class ProactiveProposalFormation:
            def build_observation_driven_proposal(
                self,
                interaction: dict,
                admission: dict,
                observations: list[dict],
                turn_index: int,
                snapshot: dict,
                grounding_bundle: dict | None = None,
                correlation: dict | None = None,
            ):
                from personal_runtime.agent_executor import InterventionProposal

                return InterventionProposal(
                    kind="notify",
                    proposal_type="action",
                    source="observation_driven",
                    action_capability="notification.show",
                    required_capability="notification.show",
                    action_payload={"message": "Runtime health needs attention."},
                    message="Runtime health needs attention.",
                    metadata={"reason_code": admission["reason_code"]},
                    target_device_hint="terminal-edge-1",
                    interaction_type="push",
                    visibility_intent="visible",
                    candidate_surface_hints=["target_device"],
                )

            def build_post_action_proposal(
                self,
                interaction: dict,
                prior_proposal: dict,
                result: dict,
                turn_index: int,
                snapshot: dict,
                grounding_bundle: dict | None = None,
                correlation: dict | None = None,
            ):
                from personal_runtime.agent_executor import InterventionProposal

                return InterventionProposal(
                    kind="no_intervention",
                    proposal_type="no_intervention",
                    source="post_action",
                    action_capability=None,
                    required_capability=None,
                    action_payload={},
                    message="",
                    metadata={},
                    interaction_type="push",
                    visibility_intent="silent",
                )

        gateway.proposal_formation = ProactiveProposalFormation()
        terminal = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show", "terminal.context"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["runtime.health", "runtime.control"],
        )
        gateway.run_roundtrip(
            [
                terminal.build_connect_frame(),
                terminal.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                terminal.build_observation_event(
                    capability="terminal.context",
                    observations=[
                        {
                            "name": "terminal.activity_state",
                            "value": "active",
                            "observed_at": "2026-07-13T09:59:00Z",
                            "confidence": 1.0,
                        }
                    ],
                ),
            ]
        )

        replies = gateway.run_roundtrip(
            [
                {
                    "type": "event_push",
                    "device_id": "host-edge-1",
                    "capability": "runtime.health",
                    "event_id": "runtime-health-degraded-e2e-1",
                    "payload": {
                        "observations": [
                            {
                                "name": "runtime.health_state",
                                "value": "degraded",
                                "observed_at": "2026-07-13T10:00:00Z",
                                "confidence": 1.0,
                            }
                        ]
                    },
                }
            ]
        )

        action_request = next(
            reply for reply in replies if reply["type"] == "action_request"
        )
        self.assertEqual(action_request["device_id"], terminal.device_id)
        self.assertEqual(action_request["action"]["capability"], "notification.show")
        self.assertEqual(
            gateway.state.interventions[-1]["admission"]["reason_code"],
            "runtime_health_failure",
        )
        self.assertEqual(gateway.state.interventions[-1]["decision"], "allow")

        completion_replies = gateway.run_roundtrip(
            [
                {
                    "type": "action_result",
                    "device_id": terminal.device_id,
                    "interaction_id": action_request["interaction_id"],
                    "interaction_turn_id": action_request["interaction_turn_id"],
                    "request_id": action_request["request_id"],
                    "result": {
                        "status": "ok",
                        "capability": "notification.show",
                        "details": {"delivered_via": "terminal.stdout"},
                    },
                }
            ]
        )

        interaction = next(
            item
            for item in gateway.state.interactions
            if item["interaction_id"] == action_request["interaction_id"]
        )
        self.assertEqual(interaction["origin"], "observation_driven")
        self.assertEqual(interaction["status"], "completed")
        self.assertEqual(
            gateway.state.action_results[-1]["request_id"],
            action_request["request_id"],
        )
        self.assertEqual(
            gateway.state.action_results[-1]["interaction_turn_id"],
            action_request["interaction_turn_id"],
        )
        self.assertTrue(
            any(reply["type"] == "interaction_update" for reply in completion_replies)
        )

    def test_action_results_use_exact_pending_interaction_turn(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        first_terminal = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        second_terminal = SessionClient(
            device_id="terminal-edge-2",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        gateway.run_roundtrip(
            [
                first_terminal.build_connect_frame(),
                first_terminal.build_capability_announce_frame(),
                second_terminal.build_connect_frame(),
                second_terminal.build_capability_announce_frame(),
            ]
        )
        first_replies = gateway.run_roundtrip(
            [first_terminal.build_text_event("first request")]
        )
        second_replies = gateway.run_roundtrip(
            [second_terminal.build_text_event("second request")]
        )
        first_action = next(
            reply for reply in first_replies if reply["type"] == "action_request"
        )
        second_action = next(
            reply for reply in second_replies if reply["type"] == "action_request"
        )
        self.assertNotEqual(first_action["interaction_id"], second_action["interaction_id"])
        self.assertIn("interaction_turn_id", first_action)
        self.assertIn("interaction_turn_id", second_action)

        result_count_before_missing_correlation = len(gateway.state.action_results)
        missing_correlation_replies = gateway.run_roundtrip(
            [
                {
                    "type": "action_result",
                    "device_id": first_action["device_id"],
                    "interaction_id": first_action["interaction_id"],
                    "request_id": first_action["request_id"],
                    "result": {
                        "status": "ok",
                        "capability": "notification.show",
                        "details": {"message": "missing runtime turn"},
                    },
                }
            ]
        )
        self.assertEqual(missing_correlation_replies[-1]["type"], "error")
        self.assertEqual(
            missing_correlation_replies[-1]["code"],
            "action_result_correlation_missing",
        )
        self.assertEqual(
            len(gateway.state.action_results),
            result_count_before_missing_correlation,
        )

        def action_result(
            action: dict,
            device_id: str,
            interaction_turn_id: str,
            capability: str = "notification.show",
        ) -> dict:
            return {
                "type": "action_result",
                "device_id": device_id,
                "interaction_id": action["interaction_id"],
                "interaction_turn_id": interaction_turn_id,
                "request_id": action["request_id"],
                "result": {
                    "status": "ok",
                    "capability": capability,
                    "details": {"message": action["action"]["payload"]["message"]},
                },
            }

        wrong_device_id = (
            first_terminal.device_id
            if first_terminal.device_id != first_action["device_id"]
            else second_terminal.device_id
        )
        result_count_before_wrong_device = len(gateway.state.action_results)
        intervention_count_before_wrong_device = len(gateway.state.interventions)
        wrong_device_replies = gateway.run_roundtrip(
            [
                action_result(
                    first_action,
                    wrong_device_id,
                    first_action["interaction_turn_id"],
                )
            ]
        )
        self.assertEqual(wrong_device_replies[-1]["type"], "error")
        self.assertEqual(
            wrong_device_replies[-1]["code"],
            "action_result_target_mismatch",
        )
        self.assertEqual(
            len(gateway.state.action_results),
            result_count_before_wrong_device,
        )
        self.assertEqual(
            len(gateway.state.interventions),
            intervention_count_before_wrong_device,
        )
        self.assertIsNotNone(
            gateway.interaction_pool.get_for_action_result(
                first_action["interaction_id"],
                first_action["interaction_turn_id"],
                first_action["request_id"],
            )
        )

        result_count_before_wrong_capability = len(gateway.state.action_results)
        intervention_count_before_wrong_capability = len(gateway.state.interventions)
        wrong_capability_replies = gateway.run_roundtrip(
            [
                action_result(
                    first_action,
                    first_action["device_id"],
                    first_action["interaction_turn_id"],
                    capability="runtime.status",
                )
            ]
        )
        self.assertEqual(wrong_capability_replies[-1]["type"], "error")
        self.assertEqual(
            wrong_capability_replies[-1]["code"],
            "action_result_capability_mismatch",
        )
        self.assertEqual(
            len(gateway.state.action_results),
            result_count_before_wrong_capability,
        )
        self.assertEqual(
            len(gateway.state.interventions),
            intervention_count_before_wrong_capability,
        )
        self.assertIsNotNone(
            gateway.interaction_pool.get_for_action_result(
                first_action["interaction_id"],
                first_action["interaction_turn_id"],
                first_action["request_id"],
            )
        )

        initial_intervention_count = len(gateway.state.interventions)
        wrong_turn_replies = gateway.run_roundtrip(
            [
                action_result(
                    first_action,
                    first_action["device_id"],
                    "interaction-turn-mismatch",
                )
            ]
        )
        self.assertEqual(len(gateway.state.interventions), initial_intervention_count)
        self.assertEqual(wrong_turn_replies[-1]["type"], "error")

        gateway.run_roundtrip(
            [
                action_result(
                    second_action,
                    second_action["device_id"],
                    second_action["interaction_turn_id"],
                )
            ]
        )
        first_interaction = next(
            item
            for item in gateway.state.interactions
            if item["interaction_id"] == first_action["interaction_id"]
        )
        second_interaction = next(
            item
            for item in gateway.state.interactions
            if item["interaction_id"] == second_action["interaction_id"]
        )
        self.assertEqual(first_interaction["status"], "planned")
        self.assertEqual(second_interaction["status"], "completed")
        self.assertEqual(
            gateway.state.action_results[-1]["interaction_id"],
            second_action["interaction_id"],
        )
        self.assertEqual(
            gateway.state.action_results[-1]["interaction_turn_id"],
            second_action["interaction_turn_id"],
        )
        self.assertEqual(
            gateway.state.action_results[-1]["request_id"],
            second_action["request_id"],
        )

        gateway.run_roundtrip(
            [
                action_result(
                    first_action,
                    first_action["device_id"],
                    first_action["interaction_turn_id"],
                )
            ]
        )
        completed_first_interaction = next(
            item
            for item in gateway.state.interactions
            if item["interaction_id"] == first_action["interaction_id"]
        )
        self.assertEqual(completed_first_interaction["status"], "completed")
        completed_intervention_count = len(gateway.state.interventions)
        duplicate_replies = gateway.run_roundtrip(
            [
                action_result(
                    first_action,
                    first_action["device_id"],
                    first_action["interaction_turn_id"],
                )
            ]
        )
        self.assertEqual(len(gateway.state.interventions), completed_intervention_count)
        self.assertEqual(duplicate_replies[-1]["type"], "error")

    def test_pending_follow_up_keeps_interaction_open_after_first_result(self) -> None:
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
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["runtime.health", "runtime.control"],
        )
        gateway.run_roundtrip(
            [
                terminal.build_connect_frame(),
                terminal.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
            ]
        )
        first_replies = gateway.run_roundtrip(
            [terminal.build_text_event("check runtime status")]
        )
        first_action = next(
            reply for reply in first_replies if reply["type"] == "action_request"
        )
        follow_up_replies = gateway.run_roundtrip(
            [
                {
                    "type": "event_push",
                    "device_id": "host-edge-1",
                    "capability": "runtime.health",
                    "event_id": "host-health-1",
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
                                "observed_at": "2026-07-13T10:01:00Z",
                                "confidence": 1.0,
                            }
                        ]
                    },
                }
            ]
        )
        follow_up_action = next(
            reply
            for reply in follow_up_replies
            if reply["type"] == "action_request"
        )
        self.assertEqual(
            follow_up_action["interaction_id"],
            first_action["interaction_id"],
        )
        self.assertNotEqual(
            follow_up_action["interaction_turn_id"],
            first_action["interaction_turn_id"],
        )

        class NoInterventionProposalFormation:
            def build_post_action_proposal(
                self,
                interaction: dict,
                prior_proposal: dict,
                result: dict,
                turn_index: int,
                snapshot: dict,
                grounding_bundle: dict | None = None,
                correlation: dict | None = None,
            ):
                from personal_runtime.agent_executor import InterventionProposal

                return InterventionProposal(
                    kind="none",
                    proposal_type="no_intervention",
                    source="post_action",
                    action_capability=None,
                    required_capability=None,
                    action_payload={},
                    message="",
                    metadata={},
                    interaction_type=interaction["interaction_type"],
                    visibility_intent="silent",
                )

        gateway.proposal_formation = NoInterventionProposalFormation()

        gateway.run_roundtrip(
            [
                {
                    "type": "action_result",
                    "device_id": first_action["device_id"],
                    "interaction_id": first_action["interaction_id"],
                    "interaction_turn_id": first_action["interaction_turn_id"],
                    "request_id": first_action["request_id"],
                    "result": {
                        "status": "ok",
                        "capability": "runtime.status",
                        "details": {"state": "running"},
                    },
                }
            ]
        )
        interaction = next(
            item
            for item in gateway.state.interactions
            if item["interaction_id"] == first_action["interaction_id"]
        )
        self.assertEqual(interaction["status"], "planned")

    def test_persists_pending_action_correlation_before_dispatch(self) -> None:
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "runtime-state.json"
            gateway = RuntimeGateway(
                shared_token="dev-token",
                state_path=state_path,
                llm_config_path=TEST_LLM_CONFIG,
            )
            terminal = SessionClient(
                device_id="terminal-edge-1",
                device_type="desktop-cli",
                token="dev-token",
                capabilities=["text.input", "notification.show"],
            )
            gateway.run_roundtrip(
                [
                    terminal.build_connect_frame(),
                    terminal.build_capability_announce_frame(),
                ]
            )
            replies = gateway.run_roundtrip(
                [terminal.build_text_event("hello runtime")]
            )
            action_request = next(
                reply for reply in replies if reply["type"] == "action_request"
            )

            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            persisted_interaction = next(
                interaction
                for interaction in persisted["interactions"]
                if interaction["interaction_id"] == action_request["interaction_id"]
            )
            self.assertEqual(
                persisted_interaction["turns"][-1],
                {
                    "interaction_turn_id": action_request["interaction_turn_id"],
                    "request_id": action_request["request_id"],
                    "action_status": "pending",
                },
            )
            persisted_intervention = next(
                intervention
                for intervention in persisted["interventions"]
                if intervention["interaction_id"] == action_request["interaction_id"]
            )
            self.assertEqual(
                persisted_intervention["interaction_turn_id"],
                action_request["interaction_turn_id"],
            )
            self.assertEqual(
                persisted_intervention["request_id"], action_request["request_id"])

            restored_gateway = RuntimeGateway(
                shared_token="dev-token",
                state_path=state_path,
                llm_config_path=TEST_LLM_CONFIG,
            )
            self.assertIsNotNone(
                restored_gateway.interaction_pool.get_for_action_result(
                    action_request["interaction_id"],
                    action_request["interaction_turn_id"],
                    action_request["request_id"],
                )
            )
            self.assertEqual(
                restored_gateway._next_interaction_turn_id(),
                "interaction-turn-2",
            )

    def test_agent_initiative_reuses_explicit_causal_token(self) -> None:
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
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["runtime.control"],
        )
        gateway.run_roundtrip(
            [
                terminal.build_connect_frame(),
                terminal.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
            ]
        )
        initiative_request = {
            "action_capability": "runtime.status",
            "action_payload": {},
            "reason": "runtime_health_check",
            "target_device_hint": "host-edge-1",
        }
        first_replies = gateway.trigger_agent_initiative(
            source_device_id="terminal-edge-1",
            initiative_request=initiative_request,
            observed_at="2026-07-13T10:00:00Z",
            initiative_id="initiative-health-check-1",
        )
        second_replies = gateway.trigger_agent_initiative(
            source_device_id="terminal-edge-1",
            initiative_request=initiative_request,
            observed_at="2026-07-13T10:00:00Z",
            initiative_id="initiative-health-check-1",
        )

        self.assertTrue(
            any(reply["type"] == "action_request" for reply in first_replies)
        )
        self.assertFalse(
            any(reply["type"] == "action_request" for reply in second_replies)
        )
        initiatives = [
            interaction
            for interaction in gateway.state.interactions
            if interaction["origin"] == "agent_initiative"
        ]
        self.assertEqual(len(initiatives), 1)
        self.assertEqual(
            initiatives[0]["causal_scope"]["source_event_id"],
            "initiative-health-check-1",
        )

    def test_observation_reentry_uses_explicit_action_parent_without_crossing_scopes(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        first_terminal = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        second_terminal = SessionClient(
            device_id="terminal-edge-2",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["runtime.health", "runtime.control"],
        )
        gateway.run_roundtrip(
            [
                first_terminal.build_connect_frame(),
                first_terminal.build_capability_announce_frame(),
                second_terminal.build_connect_frame(),
                second_terminal.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
            ]
        )
        first_action = next(
            reply
            for reply in gateway.run_roundtrip(
                [first_terminal.build_text_event("check runtime status")]
            )
            if reply["type"] == "action_request"
        )
        second_action = next(
            reply
            for reply in gateway.run_roundtrip(
                [second_terminal.build_text_event("check runtime status")]
            )
            if reply["type"] == "action_request"
        )
        observation_frame = {
            "type": "event_push",
            "device_id": "host-edge-1",
            "capability": "runtime.health",
            "event_id": "host-health-follow-up-1",
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
                        "observed_at": "2026-07-13T10:01:00Z",
                        "confidence": 1.0,
                    }
                ]
            },
        }

        first_reentry = gateway.run_roundtrip([observation_frame])
        follow_up = next(
            reply for reply in first_reentry if reply["type"] == "action_request"
        )
        intervention_count = len(gateway.state.interventions)
        duplicate_reentry = gateway.run_roundtrip([observation_frame])

        self.assertEqual(follow_up["interaction_id"], first_action["interaction_id"])
        self.assertNotEqual(follow_up["interaction_id"], second_action["interaction_id"])
        self.assertFalse(
            any(reply["type"] == "action_request" for reply in duplicate_reentry)
        )
        self.assertEqual(len(gateway.state.interventions), intervention_count)

    def test_observation_with_mismatched_parent_stays_context_only(self) -> None:
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
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["runtime.health", "runtime.control"],
        )
        gateway.run_roundtrip(
            [
                terminal.build_connect_frame(),
                terminal.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
            ]
        )
        first_action = next(
            reply
            for reply in gateway.run_roundtrip(
                [terminal.build_text_event("check runtime status")]
            )
            if reply["type"] == "action_request"
        )
        intervention_count = len(gateway.state.interventions)

        replies = gateway.run_roundtrip(
            [
                {
                    "type": "event_push",
                    "device_id": "host-edge-1",
                    "capability": "runtime.health",
                    "event_id": "host-health-mismatched-parent",
                    "reentry_parent": {
                        "interaction_id": first_action["interaction_id"],
                        "interaction_turn_id": first_action["interaction_turn_id"],
                        "request_id": "action-not-pending",
                    },
                    "payload": {
                        "observations": [
                            {
                                "name": "runtime.health_state",
                                "value": "degraded",
                                "observed_at": "2026-07-13T10:01:00Z",
                                "confidence": 1.0,
                            }
                        ]
                    },
                }
            ]
        )

        self.assertFalse(
            any(reply["type"] == "action_request" for reply in replies)
        )
        self.assertEqual(len(gateway.state.interventions), intervention_count)
        self.assertEqual(gateway.state.observations[-1].name, "runtime.health_state")

    def test_observation_parent_event_id_reenters_unique_open_interaction(self) -> None:
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
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["runtime.health", "runtime.control"],
        )
        gateway.run_roundtrip(
            [
                terminal.build_connect_frame(),
                terminal.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
            ]
        )
        text_event = terminal.build_text_event("check runtime status")
        text_event["event_id"] = "terminal-runtime-status-1"
        first_action = next(
            reply
            for reply in gateway.run_roundtrip([text_event])
            if reply["type"] == "action_request"
        )

        replies = gateway.run_roundtrip(
            [
                {
                    "type": "event_push",
                    "device_id": "host-edge-1",
                    "capability": "runtime.health",
                    "event_id": "host-health-parent-event",
                    "parent_event_id": text_event["event_id"],
                    "payload": {
                        "observations": [
                            {
                                "name": "runtime.health_state",
                                "value": "degraded",
                                "observed_at": "2026-07-13T10:01:00Z",
                                "confidence": 1.0,
                            }
                        ]
                    },
                }
            ]
        )

        follow_up = next(
            reply for reply in replies if reply["type"] == "action_request"
        )
        self.assertEqual(follow_up["interaction_id"], first_action["interaction_id"])
        self.assertNotEqual(
            follow_up["interaction_turn_id"],
            first_action["interaction_turn_id"],
        )

    def test_gateway_records_cross_device_dispatch_diagnostics(self) -> None:
        diagnostics = InMemoryDiagnosticRecorder(
            timestamp_provider=lambda: "2026-06-30T12:00:00Z"
        )
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
            diagnostic_recorder=diagnostics,
        )

        class FakeWebsocket:
            def __init__(self) -> None:
                self.sent_frames: list[str] = []

            async def send(self, payload: str) -> None:
                self.sent_frames.append(payload)

        source_socket = FakeWebsocket()
        target_socket = FakeWebsocket()
        gateway.live_connections["host-edge-1"] = target_socket

        asyncio.run(
            gateway._dispatch_websocket_replies(
                "terminal-edge-1",
                source_socket,
                [
                    {
                        "type": "action_request",
                        "device_id": "host-edge-1",
                        "request_id": "action-1",
                        "interaction_id": "interaction-1",
                        "interaction_turn_id": "interaction-turn-1",
                        "trace_id": "trace-terminal-edge-1-1",
                        "action": {"capability": "runtime.status", "payload": {}},
                    }
                ],
            )
        )

        self.assertEqual(len(target_socket.sent_frames), 1)
        dispatch_events = [
            event
            for event in diagnostics.events
            if event.module == "Gateway" and event.operation == "dispatch_reply"
        ]
        self.assertEqual(len(dispatch_events), 1)
        self.assertTrue(dispatch_events[0].output["target_connection_found"])
        self.assertEqual(dispatch_events[0].output["send_status"], "sent")
        self.assertEqual(dispatch_events[0].output["dispatched_to"], "host-edge-1")

    def test_gateway_returns_failed_action_result_when_target_connection_missing(self) -> None:
        diagnostics = InMemoryDiagnosticRecorder(
            timestamp_provider=lambda: "2026-06-30T12:00:00Z"
        )
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
            diagnostic_recorder=diagnostics,
        )

        class FakeWebsocket:
            def __init__(self) -> None:
                self.sent_frames: list[str] = []

            async def send(self, payload: str) -> None:
                self.sent_frames.append(payload)

        source_socket = FakeWebsocket()

        asyncio.run(
            gateway._dispatch_websocket_replies(
                "terminal-edge-1",
                source_socket,
                [
                    {
                        "type": "action_request",
                        "device_id": "android-edge-1",
                        "request_id": "action-1",
                        "interaction_id": "interaction-1",
                        "interaction_turn_id": "interaction-turn-1",
                        "trace_id": "trace-terminal-edge-1-1",
                        "action": {
                            "capability": "notification.show",
                            "payload": {"message": "hello"},
                        },
                    }
                ],
            )
        )

        sent_frames = [json.loads(frame) for frame in source_socket.sent_frames]
        failed_result = next(
            frame for frame in sent_frames if frame["type"] == "action_result"
        )
        self.assertEqual(failed_result["device_id"], "android-edge-1")
        self.assertEqual(failed_result["request_id"], "action-1")
        self.assertEqual(failed_result["interaction_id"], "interaction-1")
        self.assertEqual(
            failed_result["interaction_turn_id"],
            "interaction-turn-1",
        )
        self.assertEqual(failed_result["result"]["status"], "failed")
        self.assertEqual(failed_result["result"]["reason"], "target_missing")
        self.assertEqual(
            failed_result["result"]["details"]["target_device_id"],
            "android-edge-1",
        )
        self.assertFalse(
            any(frame["type"] == "action_request" for frame in sent_frames)
        )

        dispatch_event = next(
            event
            for event in diagnostics.events
            if event.module == "Gateway" and event.operation == "dispatch_reply"
        )
        self.assertEqual(dispatch_event.output["send_status"], "target_missing")

    def test_gateway_records_synthetic_failed_action_result_for_missing_target(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        class FakeProposalFormation:
            def build_post_action_proposal(
                self,
                interaction: dict,
                prior_proposal: dict,
                result: dict,
                turn_index: int,
                snapshot: dict,
                grounding_bundle: dict | None = None,
                correlation: dict | None = None,
            ):
                from personal_runtime.agent_executor import InterventionProposal

                return InterventionProposal(
                    kind="notify",
                    proposal_type="action",
                    source="post_action",
                    action_capability="notification.show",
                    required_capability="notification.show",
                    action_payload={"message": "Phone is offline."},
                    message="Phone is offline.",
                    metadata={
                        "trigger": "action_result",
                        "result_status": result["status"],
                        "result_reason": result["reason"],
                        "previous_target_device_id": result["device_id"],
                    },
                    target_device_hint=interaction["source_device_id"],
                    interaction_type=interaction["interaction_type"],
                    visibility_intent="visible",
                    candidate_surface_hints=["source_device"],
                )

        class FakeWebsocket:
            def __init__(self) -> None:
                self.sent_frames: list[str] = []

            async def send(self, payload: str) -> None:
                self.sent_frames.append(payload)

        gateway.proposal_formation = FakeProposalFormation()
        gateway.state.register_device("terminal-edge-1", "desktop-cli")
        gateway.state.register_capability("terminal-edge-1", "notification.show")
        gateway.state.register_device("android-edge-1", "android-phone")
        gateway.state.register_capability("android-edge-1", "notification.show")
        gateway.online_device_ids.add("terminal-edge-1")
        gateway.interaction_pool.register(
            origin="user_event",
            causal_scope={"key": "terminal-event-1"},
            trigger={"event_id": "terminal-event-1"},
            participant_device_ids=["terminal-edge-1", "android-edge-1"],
            source_device_id="terminal-edge-1",
        )
        gateway.state.update_interaction(
            "interaction-1",
            status="planned",
            source_device_id="terminal-edge-1",
            participant_device_ids=["terminal-edge-1", "android-edge-1"],
            proposal_type="action",
            interaction_type="pull",
            visibility_intent="visible",
            primary_action={
                "capability": "notification.show",
                "target_device_id": "android-edge-1",
            },
        )
        gateway.interaction_pool.record_turn(
            "interaction-1",
            interaction_turn_id="interaction-turn-1",
            request_id="action-1",
        )
        gateway.state.record_intervention(
            {
                "interaction_id": "interaction-1",
                "interaction_turn_id": "interaction-turn-1",
                "request_id": "action-1",
                "source_device_id": "terminal-edge-1",
                "target_device_id": "android-edge-1",
                "action_capability": "notification.show",
                "decision": "allow",
                "reason": "context_clear",
                "proposal": {
                    "proposal_type": "action",
                    "source": "normal",
                    "action_capability": "notification.show",
                    "target_device_hint": "android-edge-1",
                },
            }
        )

        source_socket = FakeWebsocket()
        asyncio.run(
            gateway._dispatch_websocket_replies(
                "terminal-edge-1",
                source_socket,
                [
                    {
                        "type": "action_request",
                        "device_id": "android-edge-1",
                        "request_id": "action-1",
                        "interaction_id": "interaction-1",
                        "interaction_turn_id": "interaction-turn-1",
                        "trace_id": "trace-terminal-edge-1-1",
                        "action": {
                            "capability": "notification.show",
                            "payload": {"message": "hello"},
                        },
                    }
                ],
            )
        )

        self.assertEqual(gateway.state.action_results[-1]["status"], "failed")
        self.assertEqual(gateway.state.action_results[-1]["reason"], "target_missing")
        self.assertEqual(
            gateway.state.action_results[-1]["details"]["target_device_id"],
            "android-edge-1",
        )
        sent_frames = [json.loads(frame) for frame in source_socket.sent_frames]
        self.assertEqual(sent_frames[-1]["type"], "action_request")
        self.assertEqual(sent_frames[-1]["device_id"], "terminal-edge-1")
        self.assertEqual(
            sent_frames[-1]["action"]["payload"]["message"],
            "Phone is offline.",
        )

    def test_gateway_dispatch_diagnostics_include_error_details(self) -> None:
        diagnostics = InMemoryDiagnosticRecorder(
            timestamp_provider=lambda: "2026-06-30T12:00:00Z"
        )
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
            diagnostic_recorder=diagnostics,
        )

        class FakeWebsocket:
            def __init__(self) -> None:
                self.sent_frames: list[str] = []

            async def send(self, payload: str) -> None:
                self.sent_frames.append(payload)

        source_socket = FakeWebsocket()

        asyncio.run(
            gateway._dispatch_websocket_replies(
                "host-edge-1",
                source_socket,
                [
                    {
                        "type": "error",
                        "device_id": "host-edge-1",
                        "code": "schema_mismatch",
                        "message": "Observation value does not match registered schema.",
                        "capability": "runtime.health",
                        "observation": "runtime.process_started_at",
                    }
                ],
            )
        )

        dispatch_event = next(
            event
            for event in diagnostics.events
            if event.module == "Gateway" and event.operation == "dispatch_reply"
        )
        self.assertEqual(dispatch_event.output["error_code"], "schema_mismatch")
        self.assertEqual(dispatch_event.output["error_capability"], "runtime.health")
        self.assertEqual(
            dispatch_event.output["error_observation"],
            "runtime.process_started_at",
        )

    def test_orchestrator_does_not_delegate_to_gateway_private_event_impl(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        gateway._build_event_replies_impl = None
        client = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
        )
        gateway.run_roundtrip(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
            ]
        )

        replies = gateway.orchestrator.handle_event_frame(
            client.build_text_event("hello runtime")
        )

        self.assertTrue(any(reply["type"] == "action_request" for reply in replies))

    def test_orchestrator_does_not_delegate_to_gateway_private_action_result_impl(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
        )
        gateway.run_roundtrip(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
            ]
        )
        replies = gateway.run_roundtrip([client.build_text_event("hello runtime")])
        action_request = next(
            reply for reply in replies if reply["type"] == "action_request"
        )
        action_result = client.handle_action_request(action_request)
        gateway._build_action_result_replies_impl = None

        reentry_replies = gateway.orchestrator.handle_action_result_frame(action_result)

        self.assertTrue(reentry_replies)

    def test_orchestrator_does_not_record_gateway_boundary_diagnostic(self) -> None:
        diagnostics = InMemoryDiagnosticRecorder(
            timestamp_provider=lambda: "2026-06-30T12:00:00Z"
        )
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
            diagnostic_recorder=diagnostics,
        )
        client = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
        )
        gateway.run_roundtrip(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
            ]
        )

        gateway.orchestrator.handle_event_frame(client.build_text_event("hello runtime"))

        self.assertNotIn("Gateway", [event.module for event in diagnostics.events])

    def test_runtime_modules_record_their_own_boundaries(self) -> None:
        diagnostics = InMemoryDiagnosticRecorder(
            timestamp_provider=lambda: "2026-06-30T12:00:00Z"
        )
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
            diagnostic_recorder=diagnostics,
        )
        client = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
        )
        gateway.run_roundtrip(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
            ]
        )

        gateway.orchestrator.handle_event_frame(client.build_text_event("hello runtime"))

        proposal_event = next(
            event for event in diagnostics.events if event.module == "Proposal Formation"
        )
        presence_event = next(
            event for event in diagnostics.events if event.module == "Presence Router"
        )
        execution_event = next(
            event for event in diagnostics.events if event.module == "Execution Planning"
        )
        self.assertEqual(proposal_event.operation, "build_proposal")
        self.assertEqual(presence_event.operation, "choose_presence_decision")
        self.assertEqual(execution_event.operation, "plan_action")
        self.assertEqual(proposal_event.output["proposal_type"], "action")

    def test_proposal_formation_records_own_module_boundary(self) -> None:
        diagnostics = InMemoryDiagnosticRecorder(
            timestamp_provider=lambda: "2026-06-30T12:00:00Z"
        )
        proposal_formation = ProposalFormation(
            diagnostic_recorder=diagnostics,
            runtime_instance_id="runtime-main",
            config_path=TEST_LLM_CONFIG,
        )

        proposal = proposal_formation.build_normal_path_proposal(
            frame={
                "device_id": "terminal-edge-1",
                "payload": {"text": "hello runtime"},
            },
            snapshot={},
            grounding_bundle=None,
            correlation={"trace_id": "trace-terminal-edge-1-1"},
        )

        self.assertEqual(proposal.proposal_type, "action")
        self.assertEqual(len(diagnostics.events), 1)
        self.assertEqual(diagnostics.events[0].module, "Proposal Formation")
        self.assertEqual(diagnostics.events[0].operation, "build_proposal")

    def test_presence_router_records_own_module_boundary(self) -> None:
        diagnostics = InMemoryDiagnosticRecorder(
            timestamp_provider=lambda: "2026-06-30T12:00:00Z"
        )
        router = PresenceRouter(
            diagnostic_recorder=diagnostics,
            runtime_instance_id="runtime-main",
        )

        decision = router.choose(
            source_device_id="terminal-edge-1",
            snapshot={},
            devices={},
            online_device_ids=set(),
            required_capability="notification.show",
            proposal={"proposal_type": "action"},
            intervention_history=[],
            now_timestamp="2026-06-30T12:00:00Z",
            correlation={"trace_id": "trace-terminal-edge-1-1"},
        )

        self.assertEqual(decision.decision, "allow")
        self.assertEqual(len(diagnostics.events), 1)
        self.assertEqual(diagnostics.events[0].module, "Presence Router")
        self.assertEqual(diagnostics.events[0].operation, "choose_presence_decision")

    def test_presence_router_suppresses_unhinted_proactive_notification_to_idle_source_terminal(
        self,
    ) -> None:
        router = PresenceRouter()

        decision = router.choose(
            source_device_id="terminal-edge-1",
            snapshot={"terminal.current_activity_state": "idle"},
            devices={
                "terminal-edge-1": {
                    "device_type": "desktop-cli",
                    "capabilities": {"notification.show", "terminal.context"},
                }
            },
            online_device_ids={"terminal-edge-1"},
            required_capability="notification.show",
            proposal={
                "proposal_type": "action",
                "source": "observation_driven",
                "action_capability": "notification.show",
            },
            intervention_history=[],
            now_timestamp="2026-07-13T10:00:00Z",
        )

        self.assertEqual(decision.decision, "suppress")
        self.assertIsNone(decision.target_device_id)
        self.assertEqual(decision.reason, "terminal_inactive")

    def test_presence_router_preserves_explicit_offline_target_hint(self) -> None:
        router = PresenceRouter()

        decision = router.choose(
            source_device_id="terminal-edge-1",
            snapshot={},
            devices={
                "terminal-edge-1": {
                    "device_type": "desktop-cli",
                    "capabilities": {"notification.show"},
                },
                "android-edge-1": {
                    "device_type": "android-phone",
                    "capabilities": {"notification.show"},
                },
            },
            online_device_ids={"terminal-edge-1"},
            required_capability="notification.show",
            proposal={
                "proposal_type": "action",
                "action_capability": "notification.show",
                "target_device_hint": "android-edge-1",
            },
            intervention_history=[],
            now_timestamp="2026-06-30T12:00:00Z",
        )

        self.assertEqual(decision.decision, "allow")
        self.assertEqual(decision.target_device_id, "android-edge-1")
        self.assertNotEqual(decision.target_device_id, "terminal-edge-1")

    def test_normal_phone_request_targets_known_offline_phone_from_context(self) -> None:
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
        gateway.run_roundtrip(
            [
                terminal.build_connect_frame(),
                terminal.build_capability_announce_frame(),
                {
                    "type": "connect",
                    "device": {
                        "device_id": "android-edge-1",
                        "device_type": "android-phone",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "android-edge-1",
                    "capabilities": ["notification.show"],
                },
            ]
        )
        gateway.online_device_ids.discard("android-edge-1")
        gateway.live_connections.pop("android-edge-1", None)

        replies = gateway.run_roundtrip(
            [terminal.build_text_event("send hello to my phone")]
        )

        action_request = next(
            reply for reply in replies if reply["type"] == "action_request"
        )
        self.assertEqual(action_request["device_id"], "android-edge-1")
        intervention = gateway.state.interventions[-1]
        self.assertEqual(intervention["target_device_id"], "android-edge-1")
        self.assertEqual(
            intervention["proposal"]["target_device_hint"],
            "android-edge-1",
        )

    def test_orchestrator_records_post_action_diagnostics_with_same_trace(self) -> None:
        diagnostics = InMemoryDiagnosticRecorder(
            timestamp_provider=lambda: "2026-06-30T12:00:00Z"
        )
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
            diagnostic_recorder=diagnostics,
        )
        client = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
        )
        gateway.run_roundtrip(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
            ]
        )
        replies = gateway.run_roundtrip([client.build_text_event("hello runtime")])
        action_request = next(
            reply for reply in replies if reply["type"] == "action_request"
        )
        action_result = client.handle_action_request(action_request)

        gateway.orchestrator.handle_action_result_frame(action_result)

        matching_events = [
            event
            for event in diagnostics.events
            if event.correlation.trace_id == action_request["trace_id"]
        ]
        modules = [event.module for event in matching_events]
        self.assertIn("Action Layer", modules)
        self.assertIn("Proposal Formation", modules)
        self.assertIn("Execution Planning", modules)

    def test_post_action_follow_up_preserves_original_correlation(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        source = SessionClient(
            device_id="terminal-edge-1",
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
        gateway.run_roundtrip(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
            ]
        )
        text_frame = source.build_text_event("check runtime status")
        first_replies = gateway.run_roundtrip([text_frame])
        first_action = next(
            reply for reply in first_replies if reply["type"] == "action_request"
        )

        follow_up_replies = gateway.run_roundtrip(
            [
                {
                    "type": "action_result",
                    "device_id": "host-edge-1",
                    "request_id": first_action["request_id"],
                    "interaction_id": first_action["interaction_id"],
                    "interaction_turn_id": first_action["interaction_turn_id"],
                    "trace_id": first_action["trace_id"],
                    "session_id": first_action["session_id"],
                    "turn_id": first_action["turn_id"],
                    "event_id": first_action["event_id"],
                    "result": {
                        "status": "ok",
                        "capability": "runtime.status",
                        "details": {"state": "running", "pid": 42137},
                    },
                }
            ]
        )

        follow_up = next(
            reply for reply in follow_up_replies if reply["type"] == "action_request"
        )
        self.assertRegex(follow_up["request_id"], r"^action-\d+$")
        self.assertEqual(follow_up["interaction_id"], first_action["interaction_id"])
        self.assertEqual(follow_up["trace_id"], first_action["trace_id"])
        self.assertEqual(follow_up["session_id"], first_action["session_id"])
        self.assertEqual(follow_up["turn_id"], first_action["turn_id"])
        self.assertEqual(follow_up["event_id"], first_action["event_id"])

    def test_runtime_jsonl_diagnostics_are_written_for_normal_turn(self) -> None:
        with TemporaryDirectory() as directory:
            diagnostic_path = Path(directory) / "runtime.jsonl"
            gateway = RuntimeGateway(
                shared_token="dev-token",
                persist_state=False,
                llm_config_path=TEST_LLM_CONFIG,
                diagnostic_recorder=JsonlDiagnosticRecorder(diagnostic_path),
            )
            client = SessionClient(
                device_id="terminal-edge-1",
                device_type="desktop-cli",
                token="dev-token",
            )
            gateway.run_roundtrip(
                [
                    client.build_connect_frame(),
                    client.build_capability_announce_frame(),
                    client.build_text_event("hello runtime"),
                ]
            )

            payloads = [
                json.loads(line)
                for line in diagnostic_path.read_text(encoding="utf-8").splitlines()
            ]
            modules = [payload["module"] for payload in payloads]
            self.assertIn("Gateway", modules)
            self.assertIn("Execution Planning", modules)
            self.assertIn("Action Layer", modules)
            trace_ids = {
                payload["correlation"]["trace_id"]
                for payload in payloads
                if payload["correlation"]["trace_id"] is not None
            }
            self.assertEqual(len(trace_ids), 1)
            self.assertRegex(next(iter(trace_ids)), r"^trace-terminal-edge-1-\d+$")


if __name__ == "__main__":
    unittest.main()
