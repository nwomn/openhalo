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
        self.assertIn("Gateway", modules)
        self.assertIn("State / Context", modules)
        self.assertIn("Grounding / Runtime Memory", modules)
        self.assertIn("Proposal Formation", modules)
        self.assertIn("Presence Router", modules)
        self.assertIn("Execution Planning", modules)
        self.assertIn("Action Layer", modules)

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
