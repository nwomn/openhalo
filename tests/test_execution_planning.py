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
    def test_notification_show_rejects_legacy_message_payload(self) -> None:
        state = RuntimeState()
        state.register_device("terminal-edge-1", "desktop-cli")
        state.register_capability("terminal-edge-1", "notification.show")
        planner = ExecutionPlanner()
        decision = {
            "decision": "allow",
            "target_device_id": "terminal-edge-1",
            "reason": "context_clear",
        }

        canonical_outcome = planner.plan_action(
            source_device_id="terminal-edge-1",
            proposal={
                "proposal_type": "action",
                "action_capability": "notification.show",
                "action_payload": {"title": "OpenHalo", "body": "hello"},
                "visibility_intent": "visible",
            },
            decision=decision,
            interaction_id="interaction-canonical-notification-1",
            runtime_state=state,
            online_device_ids={"terminal-edge-1"},
        )
        legacy_outcome = planner.plan_action(
            source_device_id="terminal-edge-1",
            proposal={
                "proposal_type": "action",
                "action_capability": "notification.show",
                "action_payload": {"message": "hello"},
                "visibility_intent": "visible",
            },
            decision=decision,
            interaction_id="interaction-legacy-notification-1",
            runtime_state=state,
            online_device_ids={"terminal-edge-1"},
        )

        self.assertEqual(canonical_outcome["kind"], "action")
        self.assertEqual(
            canonical_outcome["action"]["payload"],
            {"title": "OpenHalo", "body": "hello"},
        )
        self.assertEqual(legacy_outcome["kind"], "completion")
        self.assertEqual(legacy_outcome["reason"], "no_registered_capability")
        self.assertIn(
            "schema_mismatch",
            legacy_outcome["planning_record"]["filtered_candidates"][0]["reasons"],
        )

    def test_unknown_runtime_action_does_not_fall_back_to_notification(self) -> None:
        state = RuntimeState()
        state.register_device("terminal-edge-1", "desktop-cli")
        state.register_capability("terminal-edge-1", "notification.show")
        planner = ExecutionPlanner()

        outcome = planner.plan_action(
            source_device_id="terminal-edge-1",
            proposal={
                "proposal_type": "action",
                "action_capability": "runtime.evil",
                "action_payload": {
                    "title": "OpenHalo",
                    "body": "forged runtime action",
                },
                "visibility_intent": "visible",
            },
            decision={
                "decision": "allow",
                "target_device_id": "terminal-edge-1",
                "reason": "context_clear",
            },
            interaction_id="interaction-unknown-runtime-action-1",
            runtime_state=state,
            online_device_ids={"terminal-edge-1"},
        )

        self.assertEqual(outcome["kind"], "completion")
        self.assertEqual(outcome["reason"], "invalid_action_capability")

    def test_runtime_control_mapping_still_respects_blocked_modality(self) -> None:
        state = RuntimeState()
        state.register_device("host-edge-1", "server")
        state.register_capability("host-edge-1", "runtime.control")
        planner = ExecutionPlanner()

        outcome = planner.plan_action(
            source_device_id="terminal-edge-1",
            proposal={
                "proposal_type": "action",
                "action_capability": "runtime.restart",
                "action_payload": {},
                "visibility_intent": "visible",
            },
            decision={
                "decision": "allow",
                "target_device_id": "host-edge-1",
                "reason": "context_clear",
                "blocked_modalities": ["machine_action"],
            },
            interaction_id="interaction-runtime-control-modality-1",
            runtime_state=state,
            online_device_ids={"host-edge-1"},
        )

        self.assertEqual(outcome["kind"], "completion")
        self.assertEqual(outcome["reason"], "no_registered_capability")
        self.assertIn(
            "blocked_modality:machine_action",
            outcome["planning_record"]["filtered_candidates"][0]["reasons"],
        )

    def test_visible_action_proposal_with_allow_decision_yields_planned_action(self) -> None:
        outcome = build_execution_outcome(
            source_device_id="terminal-edge-1",
            proposal={
                "proposal_type": "action",
                "action_capability": "notification.show",
                "action_payload": {"title": "OpenHalo", "body": "hello"},
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

    def test_harness_action_without_allowed_validation_does_not_plan_an_edge_action(
        self,
    ) -> None:
        outcome = build_execution_outcome(
            source_device_id="terminal-edge-1",
            proposal={
                "proposal_type": "action",
                "action_capability": "notification.show",
                "action_payload": {
                    "title": "OpenHalo",
                    "body": "unvalidated harness action",
                },
                "visibility_intent": "visible",
                "metadata": {"harness": {"runner": "hermes"}},
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
        self.assertEqual(outcome["reason"], "harness_action_not_authorized")

    def test_hermes_sourced_action_without_harness_metadata_does_not_plan_an_edge_action(
        self,
    ) -> None:
        outcome = build_execution_outcome(
            source_device_id="terminal-edge-1",
            proposal={
                "proposal_type": "action",
                "source": "hermes",
                "action_capability": "notification.show",
                "action_payload": {
                    "title": "OpenHalo",
                    "body": "unbound Hermes action",
                },
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

        self.assertEqual(outcome["kind"], "completion")
        self.assertEqual(outcome["reason"], "harness_action_not_authorized")

    def test_harness_action_with_mismatched_allowed_intent_does_not_plan_an_edge_action(
        self,
    ) -> None:
        outcome = build_execution_outcome(
            source_device_id="terminal-edge-1",
            proposal={
                "proposal_type": "action",
                "action_capability": "notification.show",
                "action_payload": {
                    "title": "OpenHalo",
                    "body": "forged proposal payload",
                },
                "visibility_intent": "visible",
                "metadata": {
                    "harness": {"runner": "hermes"},
                    "harness_validation": {
                        "decision": "allowed",
                        "action_intent": {
                            "executor_kind": "device_edge",
                            "governance": "runtime_governed",
                            "side_effect_class": "external",
                            "visibility": "user_visible",
                            "capability": "notification.show",
                            "payload": {
                                "title": "OpenHalo",
                                "body": "different payload",
                            },
                        },
                    },
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
        self.assertEqual(outcome["reason"], "harness_action_not_authorized")

    def test_runtime_outcome_fallback_requires_a_complete_runtime_contract(self) -> None:
        state = RuntimeState()
        _register_surface(
            state,
            "terminal-edge-1",
            {
                "name": "notification.show",
                "direction": "runtime_to_edge",
                "kind": "action",
                "affordances": ["notify_user", "deliver_private_text"],
                "modality": "visual_text",
                "content_capacity": "short_text",
                "privacy": "personal",
                "input_schema": {
                    "type": "object",
                    "required": ["body"],
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string", "minLength": 1},
                    },
                },
            },
        )
        decision = {
            "decision": "allow",
            "target_device_id": "terminal-edge-1",
            "reason": "context_clear",
        }
        proposal = {
            "proposal_type": "action",
            "source": "runtime_outcome_fallback",
            "action_capability": "notification.show",
            "action_payload": {"title": "OpenHalo", "body": "已发送到目标设备。"},
            "visibility_intent": "visible",
            "target_device_hint": "terminal-edge-1",
            "metadata": {"harness": {"operation": "post_action"}},
        }

        rejected = build_execution_outcome(
            source_device_id="terminal-edge-1",
            proposal=proposal,
            decision=decision,
            interaction_id="interaction-outcome-fallback-rejected",
            runtime_state=state,
            online_device_ids={"terminal-edge-1"},
        )
        accepted = build_execution_outcome(
            source_device_id="terminal-edge-1",
            proposal={
                **proposal,
                "metadata": {
                    **proposal["metadata"],
                    "outcome_delivery": {
                        "required": True,
                        "source_outcome_required": True,
                        "initiator_kind": "explicit_user_intent",
                        "requesting_device_id": "terminal-edge-1",
                    },
                    "runtime_generated_action": "outcome_delivery_fallback",
                },
            },
            decision=decision,
            interaction_id="interaction-outcome-fallback-accepted",
            runtime_state=state,
            online_device_ids={"terminal-edge-1"},
        )

        self.assertEqual(rejected["kind"], "completion")
        self.assertEqual(rejected["reason"], "harness_action_not_authorized")
        self.assertEqual(accepted["kind"], "action")
        self.assertEqual(accepted["target_device_id"], "terminal-edge-1")

    def test_runtime_local_intent_yields_inspectable_placeholder_completion(self) -> None:
        outcome = build_execution_outcome(
            source_device_id="terminal-edge-1",
            proposal={
                "proposal_type": "action",
                "action_capability": "notification.show",
                "action_payload": {
                    "title": "OpenHalo",
                    "body": "do not route to an edge",
                },
                "visibility_intent": "visible",
                "metadata": {
                    "harness_validation": {
                        "action_intent": {
                            "executor_kind": "runtime_local",
                            "capability": "notification.show",
                        }
                    }
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
        self.assertEqual(outcome["reason"], "runtime_local_executor_placeholder")
        self.assertEqual(
            outcome["planning_record"],
            {
                "executor_route": {
                    "kind": "runtime_local",
                    "capability": "notification.show",
                    "status": "placeholder",
                    "disposition": "not_dispatched",
                }
            },
        )

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
                "proposal_type": "action",
                "action_capability": "notification.show",
                "action_payload": {"title": "OpenHalo", "body": "hello"},
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
                "proposal_type": "action",
                "action_capability": "notification.show",
                "action_payload": {"title": "OpenHalo", "body": "hello"},
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
                    "required": ["body"],
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string", "minLength": 1},
                    },
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
                "proposal_type": "action",
                "action_capability": "notification.show",
                "action_payload": {
                    "title": "OpenHalo",
                    "body": "private reminder",
                },
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
                "proposal_type": "action",
                "action_capability": "notification.show",
                "action_payload": {"title": "OpenHalo", "body": "hello"},
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

    def test_explicit_target_offline_still_plans_action_for_gateway_failure(self) -> None:
        state = RuntimeState()
        _register_surface(
            state,
            "terminal-edge-1",
            {
                "name": "notification.show",
                "direction": "runtime_to_edge",
                "kind": "action",
                "affordances": ["notify_user", "deliver_private_text"],
                "modality": "visual_text",
                "content_capacity": "short_text",
                "privacy": "personal",
                "input_schema": {
                    "type": "object",
                    "required": ["body"],
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string", "minLength": 1},
                    },
                },
            },
        )
        _register_surface(
            state,
            "android-edge-1",
            {
                "name": "notification.show",
                "direction": "runtime_to_edge",
                "kind": "action",
                "affordances": ["notify_user", "deliver_private_text"],
                "modality": "visual_text",
                "content_capacity": "short_text",
                "privacy": "personal",
                "input_schema": {
                    "type": "object",
                    "required": ["body"],
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string", "minLength": 1},
                    },
                },
            },
        )

        outcome = ExecutionPlanner().plan_action(
            source_device_id="terminal-edge-1",
            proposal={
                "proposal_type": "action",
                "action_capability": "notification.show",
                "action_payload": {"title": "OpenHalo", "body": "hello"},
                "visibility_intent": "visible",
                "target_device_hint": "android-edge-1",
            },
            decision={
                "decision": "allow",
                "target_device_id": "android-edge-1",
                "reason": "context_clear",
            },
            interaction_id="interaction-1",
            runtime_state=state,
            online_device_ids={"terminal-edge-1"},
        )

        self.assertEqual(outcome["kind"], "action")
        self.assertEqual(outcome["target_device_id"], "android-edge-1")
        self.assertEqual(
            outcome["planning_record"]["chosen_candidate"]["device_id"],
            "android-edge-1",
        )
        self.assertIn(
            "target_offline",
            outcome["planning_record"]["chosen_candidate"]["score_reasons"],
        )


if __name__ == "__main__":
    unittest.main()
