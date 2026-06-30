"""Execution planning boundary for proposal-to-action outcomes."""

from __future__ import annotations


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


__all__ = ["build_execution_outcome"]
