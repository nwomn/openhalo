"""Replay/evaluation gates for runtime-owned Agent Harness traces."""

from __future__ import annotations

from personal_runtime.harness_provenance import internal_tool_audit_issue
from personal_runtime.harness_provenance import sanitize_hermes_memory_events
from personal_runtime.harness_provenance import sanitize_internal_tool_events


_SAFE_TERMINAL_REASONS = {
    "complete",
    "no_intervention",
    "suppressed",
}


def build_harness_trace(
    *,
    harness_input,
    outcome,
    validation: dict,
    terminal_reason: str,
) -> dict:
    """Capture bounded, replay-oriented evidence for one harness decision."""

    validation_decision = (
        "rejected"
        if validation.get("reason") is not None
        else "allowed"
        if validation.get("action_intent") is not None
        else "not_applicable"
    )
    return {
        "interaction_id": harness_input.interaction_id,
        "interaction_turn_id": harness_input.interaction_turn_id,
        "operation": harness_input.operation.value,
        "runner": outcome.metadata.get("runner"),
        "durable_memory_engine": outcome.metadata.get("durable_memory_engine"),
        "outcome_intent": outcome.intent,
        "terminal_reason": terminal_reason,
        "validation": {
            "decision": validation_decision,
            "reason": validation.get("reason"),
            "action_intent": validation.get("action_intent"),
            "authorization": validation.get("authorization"),
        },
        "memory_lineage": {
            "working_memory_keys": sorted((harness_input.working_memory or {}).keys()),
            "procedural_count": len(harness_input.procedural_memory or []),
            "semantic_count": len(harness_input.semantic_memory or []),
            "episodic_count": len(harness_input.episodic_memory or []),
        },
        "internal_tool_events": sanitize_internal_tool_events(
            outcome.metadata.get("internal_tool_events")
        ),
        "hermes_memory_events": sanitize_hermes_memory_events(
            outcome.metadata.get("hermes_memory_events")
        ),
    }


def evaluate_harness_traces(traces: list[dict]) -> dict:
    """Classify trace evidence without mutating runtime behavior."""

    terminal_traces = {}
    for trace in traces:
        interaction_id = trace.get("interaction_id")
        key = interaction_id or f"trace-{len(terminal_traces)}"
        terminal_traces[key] = trace
    classifications: dict[str, int] = {}
    outcomes = []
    for trace in terminal_traces.values():
        classification = _classify_trace(trace)
        classifications[classification] = classifications.get(classification, 0) + 1
        outcomes.append(
            {
                "interaction_id": trace.get("interaction_id"),
                "interaction_turn_id": trace.get("interaction_turn_id"),
                "classification": classification,
            }
        )
    return {
        "total_traces": len(terminal_traces),
        "classifications": classifications,
        "outcomes": outcomes,
    }


def gate_harness_promotion(evaluation: dict) -> dict:
    """Require positive evidence and human review before any promotion."""

    classifications = evaluation.get("classifications", {})
    blocked = {
        classification: classifications.get(classification, 0)
        for classification in (
            "provider_failure",
            "governance_rejected",
            "incomplete_terminal",
            "malformed_internal_tool_audit",
            "untrusted_internal_tool_missing_audit",
        )
        if classifications.get(classification, 0)
    }
    if not evaluation.get("total_traces"):
        return {
            "eligible": False,
            "decision": "blocked",
            "reason": "no_trace_evidence",
        }
    if blocked:
        return {
            "eligible": False,
            "decision": "blocked",
            "reason": "unsafe_or_incomplete_trace_evidence",
            "blocked_classifications": blocked,
        }
    return {
        "eligible": True,
        "decision": "review_required",
        "reason": "all_recorded_traces_safe",
    }


def _classify_trace(trace: dict) -> str:
    if trace.get("outcome_intent") == "provider_failure":
        return "provider_failure"
    validation = trace.get("validation", {})
    if validation.get("decision") == "rejected":
        return "governance_rejected"
    for event in trace.get("internal_tool_events", []):
        issue = internal_tool_audit_issue(event)
        if issue is not None:
            return issue
    if trace.get("terminal_reason") not in _SAFE_TERMINAL_REASONS:
        return "incomplete_terminal"
    return "accepted"


__all__ = [
    "build_harness_trace",
    "evaluate_harness_traces",
    "gate_harness_promotion",
]
