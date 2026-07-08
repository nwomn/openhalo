import asyncio
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
                    proposal_type="reply",
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
        gateway.state.record_interaction(
            {
                "interaction_id": "interaction-1",
                "status": "planned",
                "source_device_id": "terminal-edge-1",
                "participant_device_ids": ["terminal-edge-1", "android-edge-1"],
                "proposal_type": "action",
                "interaction_type": "pull",
                "visibility_intent": "visible",
                "primary_action": {
                    "capability": "notification.show",
                    "target_device_id": "android-edge-1",
                },
            }
        )
        gateway.state.record_intervention(
            {
                "interaction_id": "interaction-1",
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
        self.assertEqual(proposal_event.output["proposal_type"], "reply")

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

        self.assertEqual(proposal.proposal_type, "reply")
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
            proposal={"proposal_type": "reply"},
            intervention_history=[],
            now_timestamp="2026-06-30T12:00:00Z",
            correlation={"trace_id": "trace-terminal-edge-1-1"},
        )

        self.assertEqual(decision.decision, "allow")
        self.assertEqual(len(diagnostics.events), 1)
        self.assertEqual(diagnostics.events[0].module, "Presence Router")
        self.assertEqual(diagnostics.events[0].operation, "choose_presence_decision")

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
