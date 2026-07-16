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
        runtime_state=None,
        online_device_ids: set[str] | None = None,
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
                runtime_state=runtime_state,
                online_device_ids=online_device_ids,
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
    runtime_state=None,
    online_device_ids: set[str] | None = None,
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

    if not _harness_action_is_authorized(proposal):
        return {
            "kind": "completion",
            "interaction_id": interaction_id,
            "reason": "harness_action_not_authorized",
            "summary": _proposal_summary(proposal),
            "visibility": proposal.get("visibility_intent", "visible"),
            "correlation": correlation or {},
        }

    action_intent = (
        proposal.get("metadata", {})
        .get("harness_validation", {})
        .get("action_intent")
    )
    if action_intent is not None and action_intent.get("executor_kind") in {
        "runtime_local",
        "mcp",
        "skill_procedure",
    }:
        executor_kind = action_intent["executor_kind"]
        return {
            "kind": "completion",
            "interaction_id": interaction_id,
            "reason": f"{executor_kind}_executor_placeholder",
            "summary": _proposal_summary(proposal),
            "visibility": proposal.get("visibility_intent", "visible"),
            "correlation": correlation or {},
            "planning_record": {
                "executor_route": {
                    "kind": executor_kind,
                    "capability": action_intent.get("capability"),
                    "status": "placeholder",
                    "disposition": "not_dispatched",
                }
            },
        }

    planning_record = None
    if runtime_state is not None:
        planning_record = resolve_capability_provider(
            source_device_id=source_device_id,
            proposal=proposal,
            decision=decision,
            runtime_state=runtime_state,
            online_device_ids=online_device_ids or set(),
        )
        chosen = planning_record.get("chosen_candidate")
        if chosen is None:
            return {
                "kind": "completion",
                "interaction_id": interaction_id,
                "reason": "no_registered_capability",
                "summary": _proposal_summary(proposal),
                "visibility": proposal.get("visibility_intent", "visible"),
                "correlation": correlation or {},
                "planning_record": planning_record,
            }
        target_device_id = chosen["device_id"]
        action_capability = proposal["action_capability"]
    else:
        target_device_id = decision.get("target_device_id") or source_device_id
        action_capability = proposal["action_capability"]

    outcome = {
        "kind": "action",
        "interaction_id": interaction_id,
        "target_device_id": target_device_id,
        "action": {
            "capability": action_capability,
            "payload": proposal.get("action_payload", {}),
        },
        "correlation": correlation or {},
    }
    if planning_record is not None:
        outcome["planning_record"] = planning_record
    return outcome


def _harness_action_is_authorized(proposal: dict) -> bool:
    """Require a complete runtime envelope for action proposals from a harness."""

    metadata = proposal.get("metadata", {})
    if not isinstance(metadata, dict) or not isinstance(metadata.get("harness"), dict):
        return proposal.get("source") != "hermes"
    validation = metadata.get("harness_validation")
    if not isinstance(validation, dict) or validation.get("decision") != "allowed":
        return False
    action_intent = validation.get("action_intent")
    if not isinstance(action_intent, dict):
        return False
    executor_kind = action_intent.get("executor_kind")
    if executor_kind not in {
        "device_edge",
        "runtime_local",
        "mcp",
        "skill_procedure",
    }:
        return False
    if (
        action_intent.get("capability") != proposal.get("action_capability")
        or action_intent.get("payload") != proposal.get("action_payload", {})
    ):
        return False
    if executor_kind != "device_edge":
        return True
    return (
        action_intent.get("governance") == "runtime_governed"
        and action_intent.get("side_effect_class") == "external"
        and action_intent.get("visibility") == "user_visible"
    )


def resolve_capability_provider(
    source_device_id: str,
    proposal: dict,
    decision: dict,
    runtime_state,
    online_device_ids: set[str],
) -> dict:
    candidates = _registered_action_candidates(runtime_state)
    filtered_candidates = []
    survivors = []
    for candidate in candidates:
        reasons = _filter_reasons(
            candidate,
            proposal=proposal,
            decision=decision,
            online_device_ids=online_device_ids,
        )
        if reasons:
            filtered_candidates.append({**candidate, "reasons": reasons})
            continue
        scored = {
            **candidate,
            **_score_candidate(
                candidate,
                source_device_id=source_device_id,
                proposal=proposal,
                decision=decision,
            ),
        }
        if (
            candidate["device_id"] == decision.get("target_device_id")
            and candidate["device_id"] not in online_device_ids
        ):
            scored["score_reasons"] = [
                *scored["score_reasons"],
                "target_offline",
            ]
        survivors.append(scored)

    survivors.sort(key=lambda item: (-item["score"], item["device_id"], item["capability_name"]))
    chosen = survivors[0] if survivors else None
    fallback_candidates = survivors[1:]
    return {
        "proposal_action_hint": proposal.get("action_capability"),
        "requirements": _planning_requirements(proposal, decision),
        "candidates": candidates,
        "filtered_candidates": filtered_candidates,
        "chosen_candidate": chosen,
        "fallback_candidates": fallback_candidates,
    }


def _registered_action_candidates(runtime_state) -> list[dict]:
    candidates = []
    for device_id, capabilities in runtime_state.capability_registry.items():
        for capability_name, metadata in capabilities.items():
            if metadata.get("direction") not in {"runtime_to_edge", "bidirectional"}:
                continue
            if metadata.get("kind") not in {None, "action"}:
                continue
            candidates.append(
                {
                    "device_id": device_id,
                    "capability_name": capability_name,
                    "metadata": metadata,
                    "registry_ref": f"{device_id}:{capability_name}",
                }
            )
    return candidates


def _planning_requirements(proposal: dict, decision: dict) -> dict:
    metadata_requirements = proposal.get("metadata", {}).get("requirements", {})
    message = proposal.get("action_payload", {}).get("message")
    return {
        "action_hint": proposal.get("action_capability"),
        "privacy": metadata_requirements.get("privacy", "personal" if message else None),
        "content_required": message is not None,
        "allowed_modalities": decision.get("allowed_modalities"),
        "blocked_modalities": decision.get("blocked_modalities", []),
        "target_device_id": decision.get("target_device_id"),
    }


def _filter_reasons(
    candidate: dict,
    proposal: dict,
    decision: dict,
    online_device_ids: set[str],
) -> list[str]:
    metadata = candidate["metadata"]
    requirements = _planning_requirements(proposal, decision)
    reasons = []
    target_device_id = requirements.get("target_device_id")
    explicit_target_candidate = (
        target_device_id is not None and candidate["device_id"] == target_device_id
    )
    if candidate["device_id"] not in online_device_ids and not explicit_target_candidate:
        reasons.append("device_offline")
    if target_device_id and candidate["device_id"] != target_device_id:
        reasons.append(f"target_mismatch:{target_device_id}")
    action_hint = requirements["action_hint"]
    if action_hint and candidate["capability_name"] != action_hint:
        if action_hint.startswith("runtime.") and candidate["capability_name"] == "runtime.control":
            return reasons
        affordances = set(metadata.get("affordances", []))
        if "deliver_private_text" not in affordances and "notify_user" not in affordances:
            reasons.append(f"capability_mismatch:{action_hint}")
    blocked_modalities = set(requirements.get("blocked_modalities") or [])
    modality = metadata.get("modality")
    if modality in blocked_modalities:
        reasons.append(f"blocked_modality:{modality}")
    allowed_modalities = requirements.get("allowed_modalities")
    if allowed_modalities and modality not in set(allowed_modalities):
        reasons.append(f"modality_not_allowed:{modality}")
    if requirements.get("privacy") == "personal" and metadata.get("privacy") == "public":
        reasons.append("privacy:public")
    if requirements.get("content_required") and metadata.get("content_capacity") == "none":
        reasons.append("content_capacity:none")
    schema = metadata.get("input_schema")
    payload = proposal.get("action_payload", {})
    if schema and not _payload_matches_required_schema(payload, schema):
        reasons.append("schema_mismatch")
    return reasons


def _payload_matches_required_schema(payload: dict, schema: dict) -> bool:
    if schema.get("type") == "object" and not isinstance(payload, dict):
        return False
    for key in schema.get("required", []):
        if key not in payload:
            return False
    return True


def _score_candidate(
    candidate: dict,
    source_device_id: str,
    proposal: dict,
    decision: dict,
) -> dict:
    score = 0
    reasons = []
    metadata = candidate["metadata"]
    if candidate["capability_name"] == proposal.get("action_capability"):
        score += 20
        reasons.append("matches_action_hint:+20")
    affordances = set(metadata.get("affordances", []))
    if proposal.get("action_payload", {}).get("message") and "deliver_private_text" in affordances:
        score += 15
        reasons.append("private_text_affordance:+15")
    if metadata.get("modality") == "visual_text":
        score += 5
        reasons.append("visual_text:+5")
    if candidate["device_id"] == decision.get("target_device_id"):
        score += 10
        reasons.append("presence_target:+10")
    if candidate["device_id"] == source_device_id:
        score += 1
        reasons.append("source_fallback:+1")
    return {"score": score, "score_reasons": reasons}


def _proposal_summary(proposal: dict) -> str:
    proposal_type = proposal.get("proposal_type")
    if proposal_type == "action":
        return proposal.get("action_payload", {}).get("message", "")
    if proposal_type == "provider_failure":
        return proposal.get("message") or proposal.get("response_text", "")
    if proposal_type == "no_intervention":
        rationale = proposal.get("metadata", {}).get("proposal_rationale", {})
        return rationale.get("summary", "")
    return ""


__all__ = [
    "ExecutionPlanner",
    "build_execution_outcome",
    "resolve_capability_provider",
]
