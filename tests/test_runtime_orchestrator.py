import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from device_edge.shared.session_client import SessionClient
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.runtime_orchestrator import RuntimeOrchestrator
from openhalo_common.diagnostics import InMemoryDiagnosticRecorder
from openhalo_common.diagnostics import JsonlDiagnosticRecorder


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
