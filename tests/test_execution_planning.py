import unittest

from openhalo_common.diagnostics import InMemoryDiagnosticRecorder
from personal_runtime.execution_planning import ExecutionPlanner
from personal_runtime.execution_planning import build_execution_outcome


class ExecutionPlanningTests(unittest.TestCase):
    def test_reply_proposal_with_allow_decision_yields_planned_action(self) -> None:
        outcome = build_execution_outcome(
            source_device_id="terminal-edge-1",
            proposal={
                "proposal_type": "reply",
                "action_capability": "notification.show",
                "action_payload": {"message": "hello"},
                "visibility_intent": "visible",
            },
            decision={
                "decision": "allow",
                "target_device_id": "terminal-edge-1",
                "reason": "context_clear",
            },
            interaction_id="interaction-1",
            correlation={"trace_id": "trace-terminal-edge-1-1"},
        )

        self.assertEqual(outcome["kind"], "action")
        self.assertEqual(outcome["target_device_id"], "terminal-edge-1")
        self.assertEqual(outcome["action"]["capability"], "notification.show")
        self.assertEqual(outcome["interaction_id"], "interaction-1")
        self.assertEqual(outcome["correlation"]["trace_id"], "trace-terminal-edge-1-1")

    def test_no_intervention_yields_completion(self) -> None:
        outcome = build_execution_outcome(
            source_device_id="terminal-edge-1",
            proposal={
                "proposal_type": "no_intervention",
                "action_capability": None,
                "action_payload": {},
                "visibility_intent": "silent",
                "metadata": {
                    "proposal_rationale": {"summary": "No user-facing action."}
                },
            },
            decision={
                "decision": "allow",
                "target_device_id": "terminal-edge-1",
                "reason": "context_clear",
            },
            interaction_id="interaction-1",
            correlation={"trace_id": "trace-terminal-edge-1-1"},
        )

        self.assertEqual(outcome["kind"], "completion")
        self.assertEqual(outcome["visibility"], "silent")
        self.assertEqual(outcome["summary"], "No user-facing action.")

    def test_suppressed_decision_yields_completion_without_action(self) -> None:
        outcome = build_execution_outcome(
            source_device_id="terminal-edge-1",
            proposal={
                "proposal_type": "reply",
                "action_capability": "notification.show",
                "action_payload": {"message": "hello"},
                "visibility_intent": "visible",
            },
            decision={
                "decision": "suppress",
                "target_device_id": None,
                "reason": "terminal_inactive",
            },
            interaction_id="interaction-1",
            correlation={"trace_id": "trace-terminal-edge-1-1"},
        )

        self.assertEqual(outcome["kind"], "completion")
        self.assertEqual(outcome["visibility"], "visible")
        self.assertEqual(outcome["reason"], "terminal_inactive")

    def test_execution_planner_records_own_module_boundary(self) -> None:
        diagnostics = InMemoryDiagnosticRecorder(
            timestamp_provider=lambda: "2026-06-30T12:00:00Z"
        )
        planner = ExecutionPlanner(
            diagnostic_recorder=diagnostics,
            runtime_instance_id="runtime-main",
        )

        outcome = planner.plan_action(
            source_device_id="terminal-edge-1",
            proposal={
                "proposal_type": "reply",
                "action_capability": "notification.show",
                "action_payload": {"message": "hello"},
                "visibility_intent": "visible",
            },
            decision={
                "decision": "allow",
                "target_device_id": "terminal-edge-1",
                "reason": "context_clear",
            },
            interaction_id="interaction-1",
            correlation={"trace_id": "trace-terminal-edge-1-1"},
        )

        self.assertEqual(outcome["kind"], "action")
        self.assertEqual(len(diagnostics.events), 1)
        event = diagnostics.events[0]
        self.assertEqual(event.module, "Execution Planning")
        self.assertEqual(event.operation, "plan_action")
        self.assertEqual(event.output["kind"], "action")
        self.assertEqual(event.correlation.trace_id, "trace-terminal-edge-1-1")


if __name__ == "__main__":
    unittest.main()
