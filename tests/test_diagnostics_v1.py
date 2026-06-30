import json
import tempfile
import unittest
from pathlib import Path

from openhalo_common.diagnostics import DiagnosticCorrelation
from openhalo_common.diagnostics import DiagnosticBoundaryRecorder
from openhalo_common.diagnostics import DiagnosticEvent
from openhalo_common.diagnostics import InMemoryDiagnosticRecorder
from openhalo_common.diagnostics import JsonlDiagnosticRecorder
from openhalo_common.diagnostics import build_trace_id


class DiagnosticsV1Tests(unittest.TestCase):
    def test_diagnostic_event_serializes_required_boundary_fields(self) -> None:
        event = DiagnosticEvent(
            timestamp="2026-06-30T12:00:00Z",
            side="edge",
            module="Local Capability Runtime",
            operation="normalize_user_input",
            phase="output",
            correlation=DiagnosticCorrelation(
                trace_id="trace-terminal-edge-1-1",
                session_id="session-terminal-edge-1",
                turn_id="turn-terminal-edge-1-1",
                event_id="terminal-edge-1-evt-1",
            ),
            device={
                "device_id": "terminal-edge-1",
                "device_name": "Terminal Edge",
                "device_type": "desktop-cli",
            },
            input={"text": "check runtime status"},
            output={"type": "event_push", "capability": "text.input"},
            summary="Normalized terminal input into text.input event.",
        )

        payload = event.to_dict()

        self.assertEqual(payload["schema_version"], "diagnostic.v1")
        self.assertEqual(payload["side"], "edge")
        self.assertEqual(payload["module"], "Local Capability Runtime")
        self.assertEqual(payload["phase"], "output")
        self.assertEqual(payload["severity"], "info")
        self.assertEqual(payload["device"]["device_id"], "terminal-edge-1")
        self.assertEqual(
            payload["correlation"]["trace_id"],
            "trace-terminal-edge-1-1",
        )
        self.assertEqual(payload["input"]["text"], "check runtime status")
        self.assertEqual(payload["output"]["capability"], "text.input")

    def test_jsonl_writer_appends_one_event_per_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "edge-terminal-edge-1.jsonl"
            writer = JsonlDiagnosticRecorder(
                path,
                timestamp_provider=lambda: "2026-06-30T12:00:00Z",
            )
            writer.record_boundary(
                side="runtime",
                runtime_instance_id="runtime-main",
                module="Gateway",
                operation="receive_frame",
                phase="input",
                correlation={
                    "trace_id": "trace-terminal-edge-1-1",
                    "event_id": "terminal-edge-1-evt-1",
                },
                input_payload={"type": "event_push"},
                output_payload={},
                summary="Received event_push frame.",
            )

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["schema_version"], "diagnostic.v1")
            self.assertEqual(payload["runtime_instance_id"], "runtime-main")
            self.assertEqual(payload["module"], "Gateway")

    def test_trace_ids_are_stable_strings_for_frame_correlation(self) -> None:
        self.assertTrue(build_trace_id("terminal-edge-1", 3).startswith("trace-"))
        self.assertIn("terminal-edge-1", build_trace_id("terminal-edge-1", 3))

    def test_in_memory_recorder_keeps_structured_events(self) -> None:
        recorder = InMemoryDiagnosticRecorder()
        recorder.record_boundary(
            side="runtime",
            module="Gateway",
            operation="receive_frame",
            phase="input",
            correlation={"trace_id": "trace-terminal-edge-1-1"},
            input_payload={"type": "event_push"},
            output_payload={},
            summary="Received event_push frame.",
            runtime_instance_id="runtime-main",
            timestamp="2026-06-30T12:00:00Z",
        )

        self.assertEqual(len(recorder.events), 1)
        payload = recorder.events[0].to_dict()
        self.assertEqual(payload["module"], "Gateway")
        self.assertEqual(payload["correlation"]["trace_id"], "trace-terminal-edge-1-1")

    def test_boundary_recorder_records_output_from_module_scope(self) -> None:
        recorder = InMemoryDiagnosticRecorder(
            timestamp_provider=lambda: "2026-06-30T12:00:00Z"
        )
        boundary_recorder = DiagnosticBoundaryRecorder(
            recorder=recorder,
            side="runtime",
            runtime_instance_id="runtime-main",
        )

        with boundary_recorder.boundary(
            module="Execution Planning",
            operation="plan_action",
            correlation={"trace_id": "trace-terminal-edge-1-1"},
            input_payload={"proposal_type": "reply"},
            summary="Planned runtime execution outcome.",
        ) as boundary:
            boundary.output({"kind": "action"})

        self.assertEqual(len(recorder.events), 1)
        event = recorder.events[0]
        self.assertEqual(event.module, "Execution Planning")
        self.assertEqual(event.phase, "output")
        self.assertEqual(event.output["kind"], "action")

    def test_boundary_recorder_records_error_from_module_scope(self) -> None:
        recorder = InMemoryDiagnosticRecorder(
            timestamp_provider=lambda: "2026-06-30T12:00:00Z"
        )
        boundary_recorder = DiagnosticBoundaryRecorder(
            recorder=recorder,
            side="runtime",
            runtime_instance_id="runtime-main",
        )

        with self.assertRaisesRegex(ValueError, "bad plan"):
            with boundary_recorder.boundary(
                module="Execution Planning",
                operation="plan_action",
                correlation={"trace_id": "trace-terminal-edge-1-1"},
                input_payload={"proposal_type": "reply"},
                summary="Execution planning failed.",
            ):
                raise ValueError("bad plan")

        self.assertEqual(len(recorder.events), 1)
        event = recorder.events[0]
        self.assertEqual(event.phase, "error")
        self.assertEqual(event.severity, "error")
        self.assertEqual(event.output["error_type"], "ValueError")
        self.assertEqual(event.output["message"], "bad plan")


if __name__ == "__main__":
    unittest.main()
