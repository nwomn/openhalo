"""Execution planning boundary for proposal-to-action outcomes."""

from __future__ import annotations

from openhalo_common.diagnostics import DiagnosticBoundaryRecorder


class ExecutionPlanner:
    def __init__(
        self,
        diagnostic_recorder=None,
        runtime_instance_id: str = "runtime-main",
    ) -> None:
        self.diagnostics = DiagnosticBoundaryRecorder(
            recorder=diagnostic_recorder,
            side="runtime",
            runtime_instance_id=runtime_instance_id,
        )

    def plan_action(
        self,
        source_device_id: str,
        proposal: dict,
        decision: dict,
        interaction_id: str,
        correlation: dict | None = None,
    ) -> dict:
        operation = (
            "plan_action"
            if decision.get("decision") == "allow"
            and proposal.get("action_capability") is not None
            else "complete_interaction"
        )
        input_payload = {
            "proposal": proposal,
            "decision": decision,
            "interaction_id": interaction_id,
        }
        with self.diagnostics.boundary(
            module="Execution Planning",
            operation=operation,
            correlation=correlation or {},
            input_payload=input_payload,
            summary="Planned runtime execution outcome.",
        ) as boundary:
            outcome = build_execution_outcome(
                source_device_id=source_device_id,
                proposal=proposal,
                decision=decision,
                interaction_id=interaction_id,
                correlation=correlation,
            )
            boundary.output(outcome)
            return outcome

    def plan_direct_action(
        self,
        source_device_id: str,
        direct_action: dict,
        correlation: dict | None = None,
    ) -> dict:
        outcome = {
            "kind": "action",
            "target_device_id": direct_action.get("target_device_id", source_device_id),
            "action": {
                "capability": direct_action["capability"],
                "payload": direct_action["payload"],
            },
            "correlation": correlation or {},
        }
        with self.diagnostics.boundary(
            module="Execution Planning",
            operation="plan_direct_action",
            correlation=correlation or {},
            input_payload={"direct_action": direct_action},
            summary="Planned direct action fast path.",
        ) as boundary:
            boundary.output(outcome)
            return outcome


def build_execution_outcome(
    source_device_id: str,
    proposal: dict,
    decision: dict,
    interaction_id: str,
    correlation: dict | None = None,
) -> dict:
    if decision.get("decision") != "allow" or proposal.get("action_capability") is None:
        return {
            "kind": "completion",
            "interaction_id": interaction_id,
            "reason": decision.get("reason", ""),
            "summary": _proposal_summary(proposal),
            "visibility": proposal.get("visibility_intent", "visible"),
            "correlation": correlation or {},
        }

    target_device_id = decision.get("target_device_id") or source_device_id
    return {
        "kind": "action",
        "interaction_id": interaction_id,
        "target_device_id": target_device_id,
        "action": {
            "capability": proposal["action_capability"],
            "payload": proposal.get("action_payload", {}),
        },
        "correlation": correlation or {},
    }


def _proposal_summary(proposal: dict) -> str:
    proposal_type = proposal.get("proposal_type")
    if proposal_type in {"reply", "clarification"}:
        return proposal.get("action_payload", {}).get("message", "")
    if proposal_type == "no_intervention":
        rationale = proposal.get("metadata", {}).get("proposal_rationale", {})
        return rationale.get("summary", "")
    return ""


__all__ = ["ExecutionPlanner", "build_execution_outcome"]
