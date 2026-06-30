import unittest

from openhalo_common.diagnostics import InMemoryDiagnosticRecorder
from personal_runtime.execution_planning import ExecutionPlanner
from personal_runtime.execution_planning import build_execution_outcome
from personal_runtime.runtime_state import RuntimeState


def _register_surface(
    state: RuntimeState,
    device_id: str,
    capability: dict,
    online_type: str = "external",
) -> None:
    state.register_device(device_id, online_type)
    state.register_capability(device_id, capability)


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

    def test_resolves_private_text_to_registered_personal_surface(self) -> None:
        state = RuntimeState()
        _register_surface(
            state,
            "phone-edge-1",
            {
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
                    "required": ["message"],
                    "properties": {"message": {"type": "string"}},
                },
            },
        )
        _register_surface(
            state,
            "speaker-edge-1",
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
            },
        )
        _register_surface(
            state,
            "desk-light-edge-1",
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
            },
        )
        planner = ExecutionPlanner()

        outcome = planner.plan_action(
            source_device_id="terminal-edge-1",
            proposal={
                "proposal_type": "reply",
                "action_capability": "notification.show",
                "action_payload": {"message": "private reminder"},
                "visibility_intent": "visible",
                "metadata": {"requirements": {"privacy": "personal"}},
            },
            decision={
                "decision": "allow",
                "target_device_id": None,
                "reason": "context_clear",
                "allowed_modalities": ["visual_text"],
                "blocked_modalities": ["public_audio"],
            },
            interaction_id="interaction-1",
            runtime_state=state,
            online_device_ids={"phone-edge-1", "speaker-edge-1", "desk-light-edge-1"},
        )

        self.assertEqual(outcome["kind"], "action")
        self.assertEqual(outcome["target_device_id"], "phone-edge-1")
        self.assertEqual(outcome["action"]["capability"], "notification.show")
        self.assertEqual(
            outcome["planning_record"]["chosen_candidate"]["device_id"],
            "phone-edge-1",
        )
        filtered = {
            item["device_id"]: item["reasons"]
            for item in outcome["planning_record"]["filtered_candidates"]
        }
        self.assertIn("blocked_modality:public_audio", filtered["speaker-edge-1"])
        self.assertIn("content_capacity:none", filtered["desk-light-edge-1"])

    def test_unregistered_legacy_hint_does_not_dispatch(self) -> None:
        state = RuntimeState()
        planner = ExecutionPlanner()

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
            runtime_state=state,
            online_device_ids={"terminal-edge-1"},
        )

        self.assertEqual(outcome["kind"], "completion")
        self.assertEqual(outcome["reason"], "no_registered_capability")


if __name__ == "__main__":
    unittest.main()
