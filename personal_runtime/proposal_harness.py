"""Replay harness helpers for Agent Runtime proposal formation."""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

from personal_runtime.model_provider import generate_text_proposal_plan
from personal_runtime.model_provider import ProposalPlan


SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "provider_api_key",
    "token",
}


def build_proposal_harness_case(
    case_id: str,
    scenario: str,
    phase: str,
    prompt_context_package: dict,
    interaction: dict | None = None,
    prior_proposal: dict | None = None,
    action_result: dict | None = None,
    observations: list[dict] | None = None,
    expected: dict | None = None,
    provider_config: dict | None = None,
) -> dict:
    """Build a secret-scrubbed replay case from a live proposal package."""

    return _redact_secrets(
        {
            "case_id": case_id,
            "scenario": scenario,
            "phase": phase,
            "prompt_context_package": deepcopy(prompt_context_package),
            "interaction": deepcopy(interaction or {}),
            "prior_proposal": deepcopy(prior_proposal or {}),
            "action_result": deepcopy(action_result or {}),
            "observations": deepcopy(observations or []),
            "expected": deepcopy(expected or {}),
            "provider_config": deepcopy(provider_config or {}),
        }
    )


def classify_proposal_outcome(case: dict, proposal: ProposalPlan | dict) -> dict:
    expected = case.get("expected", {})
    plan = _proposal_to_dict(proposal)
    metadata = plan.get("metadata", {})

    failure_class = metadata.get("provider_failure_class")
    if metadata.get("provider_failure_contained"):
        if _contains_provider_error_text(plan):
            return _outcome(
                "validation_failure",
                "provider_error_routed_as_normal_action",
            )
        return {
            "classification": "correct",
            "reason": "provider_failure_contained",
            "correct": True,
        }
    if failure_class:
        return _outcome(
            classification="provider_protocol_failure"
            if failure_class in {"protocol_shape", "connection", "timeout"}
            else "provider_failure",
            reason=str(failure_class),
        )

    if metadata.get("validation_error"):
        return _outcome("validation_failure", str(metadata["validation_error"]))

    if _contains_provider_error_text(case.get("action_result")) or _contains_provider_error_text(plan):
        return _outcome(
            "validation_failure",
            "provider_error_routed_as_normal_action",
        )

    if expected.get("requires_source_ack") and plan.get("proposal_type") == "no_intervention":
        return _outcome("semantically_incomplete", "source_ack_missing")

    correct_capability = expected.get("correct_action_capability")
    if correct_capability and plan.get("action_capability") != correct_capability:
        return _outcome("incorrect_target_or_source_surface", "action_capability_mismatch")

    return {
        "classification": "correct",
        "reason": "matched_expected_obligations",
        "correct": True,
    }


def build_post_action_prompt_variant(case: dict, variant: str) -> str:
    interaction = case.get("interaction", {})
    prior_proposal = case.get("prior_proposal", {})
    action_result = case.get("action_result", {})
    interaction_id = interaction.get("interaction_id") or case.get("interaction_id")

    raw_payload = {
        "instruction": (
            "Post-action deliberation: inspect the action_result and prior "
            "interaction context, then choose one proposal_type. Prefer a natural "
            "user-facing action when the result is useful or the next step needs "
            "user input, and no_intervention when the action already completed visibly."
        ),
        "trigger": "action_result",
        "interaction_id": interaction_id,
        "interaction": interaction,
        "prior_proposal": prior_proposal,
        "action_result": action_result,
    }

    if variant == "raw_json":
        return json.dumps(raw_payload, sort_keys=True)
    if variant != "decision_brief":
        raise ValueError(f"unsupported prompt variant: {variant}")

    source_device_id = interaction.get("source_device_id")
    target_device_id = (interaction.get("primary_action") or {}).get(
        "target_device_id"
    )
    result_status = action_result.get("status")
    provider_failure_observed = _contains_provider_error_text(
        {
            "interaction": interaction,
            "prior_proposal": prior_proposal,
            "action_result": action_result,
        }
    )
    source_ack_required = bool(
        source_device_id
        and target_device_id
        and source_device_id != target_device_id
        and result_status == "ok"
    )
    return "\n".join(
        [
            "Decision task:",
            "A target device action has completed. Decide whether this interaction needs another proposal.",
            "",
            "Obligations:",
            f"- source_device_id: {source_device_id or 'unknown'}",
            f"- target_device_id: {target_device_id or 'unknown'}",
            f"- target_action_status: {result_status or 'unknown'}",
            f"- source_ack_required: {str(source_ack_required).lower()}",
            f"- provider_failure_observed: {str(provider_failure_observed).lower()}",
            "- source_surface_satisfied: false"
            if source_ack_required
            else "- source_surface_satisfied: unknown",
            "- target_surface_satisfied: true"
            if result_status == "ok"
            else "- target_surface_satisfied: false",
            "",
            "Rule:",
            "If source_ack_required is true and source_surface_satisfied is false, do not choose no_intervention.",
            "If provider_failure_observed is true, do not copy raw provider failure text into response_text or action payload.",
            "Forbidden raw provider failure text includes: Real model reply unavailable, provider returned an incompatible response shape, codex_agent_envelope_empty_output.",
            "When a provider failure needs user visibility, use a short friendly failure explanation to the source surface instead of routing provider internals as normal notification content.",
            "",
            "Evidence appendix:",
            json.dumps(raw_payload, sort_keys=True),
        ]
    )


def replay_proposal_harness_cases(
    cases: list[dict],
    runner: Callable[[dict], ProposalPlan | dict],
) -> dict:
    outcomes = []
    classifications: dict[str, int] = {}

    for case in cases:
        try:
            proposal = runner(case)
            outcome = classify_proposal_outcome(case, proposal)
        except ValueError as exc:
            outcome = _outcome("parser_shape_failure", str(exc))
        outcomes.append({"case_id": case.get("case_id"), **outcome})
        classifications[outcome["classification"]] = (
            classifications.get(outcome["classification"], 0) + 1
        )

    total_cases = len(cases)
    correct_cases = classifications.get("correct", 0)
    return {
        "total_cases": total_cases,
        "correct_cases": correct_cases,
        "success_rate": correct_cases / total_cases if total_cases else 0.0,
        "classifications": classifications,
        "outcomes": outcomes,
    }


def compare_prompt_variants(
    cases: list[dict],
    runners: dict[str, Callable[[dict], ProposalPlan | dict]],
) -> dict:
    variants = {
        name: replay_proposal_harness_cases(cases, runner)
        for name, runner in runners.items()
    }
    best_variant = None
    if variants:
        best_variant = max(
            variants,
            key=lambda name: variants[name]["success_rate"],
        )
    return {
        "variant_count": len(variants),
        "best_variant": best_variant,
        "variants": variants,
    }


def replay_prompt_variants_with_provider(
    cases: list[dict],
    config_path: str | Path,
    transport=None,
    variants: tuple[str, ...] = ("raw_json", "decision_brief"),
) -> dict:
    config = Path(config_path)
    runners = {}
    for variant in variants:
        runners[variant] = _build_provider_variant_runner(
            variant=variant,
            config_path=config,
            transport=transport,
        )
    return compare_prompt_variants(cases, runners)


def _build_provider_variant_runner(
    variant: str,
    config_path: Path,
    transport=None,
):
    def runner(case: dict) -> ProposalPlan:
        if _contains_provider_error_text(case.get("action_result")):
            return ProposalPlan(
                proposal_type="provider_failure",
                response_text=(
                    "I hit a model-provider issue while handling that step. "
                    "Please retry shortly."
                ),
                action_capability=None,
                action_payload={},
                metadata={
                    "prompt_variant": variant,
                    "runtime_message_channel": "provider_failure",
                    "provider_failure_observed": True,
                    "provider_failure_contained": True,
                    "provider_failure_class": "protocol_shape",
                },
            )
        prompt = build_post_action_prompt_variant(case, variant=variant)
        sections = case.get("prompt_context_package", {}).get("sections", {})
        grounding = {
            "bundle_version": case.get("prompt_context_package", {}).get(
                "grounding_bundle_version",
                "m10.v1",
            ),
            "active_goals": sections.get("active_goals", []),
            "recent_memory": sections.get("recent_memory", {}),
            "edge_history": sections.get("edge_evidence", {}),
        }
        plan = generate_text_proposal_plan(
            user_text=prompt,
            snapshot=sections.get("compact_snapshot", {}),
            grounding=grounding,
            profile_name="proposal_formation",
            config_path=config_path,
            transport=transport,
        )
        plan.metadata["prompt_variant"] = variant
        plan.metadata["prompt_length"] = len(prompt)
        return plan

    return runner


def build_m17_6_terminal_phone_fixture_cases() -> list[dict]:
    return [
        build_proposal_harness_case(
            case_id="m17-6-terminal-phone-source-ack",
            scenario="terminal_to_phone_post_action_ack",
            phase="post_action",
            prompt_context_package={
                "version": "m12.v1",
                "user_text": "send hello to my phone",
                "sections": {"compact_snapshot": {}},
            },
            interaction={
                "interaction_id": "interaction-1",
                "source_device_id": "terminal-edge-1",
                "participant_device_ids": ["terminal-edge-1", "android-edge-1"],
                "primary_action": {"target_device_id": "android-edge-1"},
            },
            prior_proposal={
                "proposal_type": "action",
                "action_capability": "notification.show",
            },
            action_result={
                "status": "ok",
                "capability": "notification.show",
                "details": {"title": "OpenHalo", "body": "hello"},
            },
            expected={
                "requires_source_ack": True,
                "source_device_id": "terminal-edge-1",
                "correct_action_capability": "notification.show",
            },
        )
    ]


def load_harness_cases_from_runtime_state(state: dict) -> list[dict]:
    cases: list[dict] = []
    for index, intervention in enumerate(state.get("interventions", [])):
        proposal = intervention.get("proposal", {})
        if proposal.get("source") != "post_action":
            continue
        metadata = proposal.get("metadata", {})
        interaction_id = intervention.get("interaction_id") or metadata.get(
            "interaction_id"
        )
        source_device_id = metadata.get("source_device_id")
        previous_target_device_id = metadata.get("previous_target_device_id")
        result_status = metadata.get("result_status")
        interaction = {
            "interaction_id": interaction_id,
            "source_device_id": source_device_id,
            "participant_device_ids": list(
                metadata.get("participant_device_ids", [])
            ),
            "primary_action": {
                "target_device_id": previous_target_device_id,
            },
        }
        prior_proposal = {
            "proposal_type": metadata.get("parent_proposal_type"),
            "action_capability": metadata.get("parent_action_capability"),
        }
        action_result = {
            "status": result_status,
            "capability": metadata.get("parent_action_capability"),
            "details": {
                "summary": intervention.get("summary")
                or proposal.get("message")
                or (metadata.get("proposal_rationale") or {}).get("summary", ""),
            },
        }
        prompt_context_package = {
            "version": metadata.get("prompt_context_version", "m12.v1"),
            "user_text": build_post_action_prompt_variant(
                {
                    "interaction": interaction,
                    "prior_proposal": prior_proposal,
                    "action_result": action_result,
                },
                variant="raw_json",
            ),
            "sections": {
                "compact_snapshot": (
                    intervention.get("grounding_bundle", {}).get("snapshot", {})
                ),
                "active_goals": (
                    intervention.get("grounding_bundle", {}).get("active_goals", [])
                ),
                "recent_memory": (
                    intervention.get("grounding_bundle", {}).get("recent_memory", {})
                ),
                "edge_evidence": (
                    intervention.get("grounding_bundle", {}).get("edge_history", {})
                ),
            },
        }
        requires_source_ack = bool(
            source_device_id
            and previous_target_device_id
            and source_device_id != previous_target_device_id
            and result_status == "ok"
        )
        case = build_proposal_harness_case(
            case_id=f"runtime-state:{interaction_id}:{index}",
            scenario="runtime_state_post_action",
            phase="post_action",
            prompt_context_package=prompt_context_package,
            interaction=interaction,
            prior_proposal=prior_proposal,
            action_result=action_result,
            expected={
                "requires_source_ack": requires_source_ack,
                "source_device_id": source_device_id,
                "correct_action_capability": "notification.show"
                if requires_source_ack
                else None,
            },
        )
        case["observed_proposal"] = deepcopy(proposal)
        cases.append(_redact_secrets(case))
    return cases


def run_fixture_prompt_variant_comparison() -> dict:
    cases = build_m17_6_terminal_phone_fixture_cases()

    def raw_json_runner(case):
        prompt = build_post_action_prompt_variant(case, variant="raw_json")
        return ProposalPlan(
            proposal_type="no_intervention",
            response_text="",
            action_capability=None,
            action_payload={},
            metadata={"prompt_variant": "raw_json", "prompt_length": len(prompt)},
        )

    def decision_brief_runner(case):
        prompt = build_post_action_prompt_variant(case, variant="decision_brief")
        return ProposalPlan(
            proposal_type="action",
            response_text="Delivered hello to your phone.",
            action_capability="notification.show",
            action_payload={
                "title": "OpenHalo",
                "body": "Delivered hello to your phone.",
            },
            metadata={
                "prompt_variant": "decision_brief",
                "prompt_length": len(prompt),
            },
        )

    return compare_prompt_variants(
        cases,
        {
            "raw_json": raw_json_runner,
            "decision_brief": decision_brief_runner,
        },
    )


def classify_observed_runtime_state_cases(state: dict) -> dict:
    cases = load_harness_cases_from_runtime_state(state)
    return replay_proposal_harness_cases(
        cases,
        lambda case: case.get("observed_proposal", {}),
    )


def classify_observed_runtime_state_file(path: Path) -> dict:
    state = json.loads(path.read_text(encoding="utf-8"))
    return classify_observed_runtime_state_cases(state)


def _redact_secrets(value):
    if isinstance(value, dict):
        return {
            key: "redacted" if key.lower() in SECRET_KEYS else _redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def _proposal_to_dict(proposal: ProposalPlan | dict) -> dict:
    if isinstance(proposal, ProposalPlan):
        return {
            "proposal_type": proposal.proposal_type,
            "response_text": proposal.response_text,
            "action_capability": proposal.action_capability,
            "action_payload": dict(proposal.action_payload),
            "metadata": dict(proposal.metadata),
        }
    return dict(proposal)


def _contains_provider_error_text(value) -> bool:
    rendered = json.dumps(value or {}, sort_keys=True).lower()
    return (
        "real model reply unavailable" in rendered
        or "provider returned an incompatible response shape" in rendered
        or "codex_agent_envelope_empty_output" in rendered
    )


def _outcome(classification: str, reason: str) -> dict:
    return {
        "classification": classification,
        "reason": reason,
        "correct": False,
    }


__all__ = [
    "build_m17_6_terminal_phone_fixture_cases",
    "build_post_action_prompt_variant",
    "build_proposal_harness_case",
    "classify_proposal_outcome",
    "classify_observed_runtime_state_cases",
    "classify_observed_runtime_state_file",
    "compare_prompt_variants",
    "load_harness_cases_from_runtime_state",
    "replay_prompt_variants_with_provider",
    "run_fixture_prompt_variant_comparison",
    "replay_proposal_harness_cases",
]
