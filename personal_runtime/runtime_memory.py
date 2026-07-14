"""Runtime-native grounding bundle helpers for the first M10 slice."""

from __future__ import annotations

from personal_runtime.context_snapshot import sanitize_observation_driven_snapshot


GROUNDING_BUNDLE_VERSION = "m10.v1"
ACTIVE_GOAL_LIMIT = 3
RECENT_MEMORY_LIMIT = 3


def build_model_grounding_bundle(
    state,
    snapshot: dict | None,
    edge_history: dict | None = None,
) -> dict:
    compact_snapshot = dict(snapshot or {})
    recent_memory = {
        "user_inputs": _collect_recent_user_inputs(state),
        "interventions": _collect_recent_interventions(state),
        "action_results": _collect_recent_action_results(state),
    }
    return {
        "bundle_version": GROUNDING_BUNDLE_VERSION,
        "snapshot": compact_snapshot,
        "active_goals": _collect_active_goals(state),
        "recent_memory": recent_memory,
        "durable_state_summary": {
            "known_device_ids": sorted(state.devices.keys()),
            "stored_observation_count": len(state.observations),
            "stored_intervention_count": len(state.interventions),
            "stored_action_result_count": len(state.action_results),
        },
        "edge_history": _normalize_edge_history(edge_history),
    }


def grounding_metadata_from_bundle(grounding_bundle: dict | None) -> dict:
    if not grounding_bundle:
        return {}
    recent_memory = grounding_bundle.get("recent_memory", {})
    edge_history = grounding_bundle.get("edge_history", {})
    returned_entries = edge_history.get("returned_entries", 0)
    return {
        "grounding_bundle_version": grounding_bundle.get("bundle_version"),
        "grounding_active_goal_count": len(
            grounding_bundle.get("active_goals", [])
        ),
        "grounding_recent_user_inputs": len(
            recent_memory.get("user_inputs", [])
        ),
        "grounding_recent_interventions": len(
            recent_memory.get("interventions", [])
        ),
        "grounding_recent_action_results": len(
            recent_memory.get("action_results", [])
        ),
        "grounding_has_edge_history": returned_entries > 0,
        "grounding_edge_history_entries": returned_entries,
    }


def sanitize_observation_driven_grounding_bundle(
    grounding_bundle: dict | None,
    snapshot: dict | None = None,
) -> dict:
    raw_grounding = grounding_bundle if isinstance(grounding_bundle, dict) else {}
    source_snapshot = snapshot
    if source_snapshot is None:
        source_snapshot = raw_grounding.get("snapshot")
    sanitized = dict(raw_grounding)
    sanitized["snapshot"] = sanitize_observation_driven_snapshot(source_snapshot)
    sanitized["edge_history"] = {
        "history_kind": "excluded_for_observation_driven_proposal",
        "entries": [],
        "available_entries": 0,
        "returned_entries": 0,
    }
    return sanitized


def _collect_active_goals(state) -> list[dict]:
    active_goals = [
        {
            "goal_id": goal.get("goal_id"),
            "title": goal.get("title", ""),
            "status": goal.get("status", ""),
            "summary": goal.get("summary", ""),
            "updated_at": goal.get("updated_at", ""),
        }
        for goal in state.tasks
        if goal.get("status") == "active"
    ]
    return active_goals[-ACTIVE_GOAL_LIMIT:]


def _collect_recent_user_inputs(state) -> list[dict]:
    user_inputs = []
    for event in state.events:
        if event.get("type") != "event_push":
            continue
        if event.get("capability") != "text.input":
            continue
        payload = event.get("payload", {})
        user_inputs.append(
            {
                "device_id": event.get("device_id"),
                "text": payload.get("text", ""),
                "observed_at": payload.get("observed_at", ""),
            }
        )
    return user_inputs[-RECENT_MEMORY_LIMIT:]


def _collect_recent_interventions(state) -> list[dict]:
    interventions = []
    for intervention in state.interventions[-RECENT_MEMORY_LIMIT:]:
        proposal = intervention.get("proposal", {})
        interventions.append(
            {
                "recorded_at": intervention.get("recorded_at", ""),
                "decision": intervention.get("decision", ""),
                "reason": intervention.get("reason", ""),
                "source": proposal.get("source", ""),
                "action_capability": proposal.get(
                    "action_capability",
                    intervention.get("action_capability", ""),
                ),
                "message": proposal.get("message", ""),
            }
        )
    return interventions


def _collect_recent_action_results(state) -> list[dict]:
    results = []
    for action_result in state.action_results[-RECENT_MEMORY_LIMIT:]:
        details = action_result.get("details", {})
        results.append(
            {
                "status": action_result.get("status", ""),
                "capability": action_result.get("capability", ""),
                "message": details.get("message") if isinstance(details, dict) else None,
            }
        )
    return results


def _normalize_edge_history(edge_history: dict | None) -> dict:
    if edge_history is None:
        return {
            "history_kind": "unavailable",
            "entries": [],
            "available_entries": 0,
            "returned_entries": 0,
        }
    normalized = dict(edge_history)
    normalized.setdefault("history_kind", "observation_window")
    normalized.setdefault("entries", [])
    normalized.setdefault("available_entries", len(normalized["entries"]))
    normalized.setdefault("returned_entries", len(normalized["entries"]))
    return normalized


__all__ = [
    "GROUNDING_BUNDLE_VERSION",
    "build_model_grounding_bundle",
    "grounding_metadata_from_bundle",
    "sanitize_observation_driven_grounding_bundle",
]
