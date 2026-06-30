"""Human-inspectable reports for the M5 runtime chain."""

from __future__ import annotations

import json

from personal_runtime.prompt_context import build_behavior_contract
from personal_runtime.prompt_context import build_prompt_context_package
from personal_runtime.prompt_replay import build_replay_eval


def build_chain_report(session, action_result: dict) -> dict:
    related_interventions = _related_interventions(
        session.gateway.state.interventions,
        action_result,
    )
    intervention = _primary_intervention(related_interventions)
    interaction = next(
        (
            item
            for item in reversed(session.gateway.state.interactions)
            if item.get("interaction_id") == intervention.get("interaction_id")
        ),
        None,
    )
    snapshot_contract = intervention["snapshot_contract"]
    prompt_context = build_prompt_context_package(
        user_text=intervention["proposal"].get("message", ""),
        snapshot={
            field_name: field_contract["value"]
            for field_name, field_contract in snapshot_contract["fields"].items()
        },
        grounding_bundle=intervention.get("grounding_bundle", {}),
    )
    behavior_contract = build_behavior_contract(
        prompt_context_package=prompt_context,
        grounding_bundle=intervention.get("grounding_bundle", {}),
    )
    replay_eval = build_replay_eval(
        prompt_context_package=prompt_context,
        grounding_bundle=intervention.get("grounding_bundle", {}),
    )
    return {
        "trace_lines": session.drain_trace_lines(),
        "diagnostic_events": [
            event.to_dict()
            for event in getattr(session, "diagnostic_recorder", None).events
        ]
        if getattr(session, "diagnostic_recorder", None) is not None
        else [],
        "observations": [
            observation.to_dict() for observation in session.gateway.state.observations
        ],
        "snapshot": {
            field_name: field_contract["value"]
            for field_name, field_contract in snapshot_contract["fields"].items()
        },
        "snapshot_contract": snapshot_contract,
        "grounding": intervention.get("grounding_bundle", {}),
        "prompt_context": prompt_context,
        "behavior_contract": behavior_contract,
        "proposal": intervention["proposal"],
        "interaction": interaction,
        "presence_decision": {
            "decision": intervention["decision"],
            "reason": intervention["reason"],
            "target_device_id": intervention["target_device_id"],
        },
        "planning_record": intervention.get("planning_record", {}),
        "intervention": intervention,
        "post_action_interventions": [
            item
            for item in related_interventions
            if item.get("proposal", {}).get("source") == "post_action"
        ],
        "replay_eval": replay_eval,
        "action_result": action_result,
    }


def format_chain_report(report: dict) -> str:
    sections = [
        ("Trace", report["trace_lines"]),
        ("Diagnostic Events", report.get("diagnostic_events", [])),
        ("Observations", report["observations"]),
        ("Compact Snapshot", report["snapshot"]),
        ("Grounding Bundle", report.get("grounding", {})),
        ("Prompt Context", report.get("prompt_context", {})),
        ("Behavior Contract", report.get("behavior_contract", {})),
        ("Snapshot Contract", report["snapshot_contract"]),
        ("Proposal", report["proposal"]),
        ("Interaction", report.get("interaction", {})),
        ("Presence Decision", report["presence_decision"]),
        ("Execution Plan", report.get("planning_record", {})),
        ("Recorded Intervention", report["intervention"]),
        ("Post-Action Interventions", report.get("post_action_interventions", [])),
        ("Replay Eval", report.get("replay_eval", {})),
        ("Action Result", report["action_result"]),
    ]
    rendered_sections = []
    for title, payload in sections:
        rendered_sections.append(f"{title}:")
        if isinstance(payload, list):
            if payload and all(isinstance(item, str) for item in payload):
                rendered_sections.extend(f"- {item}" for item in payload)
            else:
                rendered_sections.append(json.dumps(payload, indent=2, ensure_ascii=True))
        else:
            rendered_sections.append(json.dumps(payload, indent=2, ensure_ascii=True))
    return "\n".join(rendered_sections)


def _related_interventions(interventions: list[dict], action_result: dict) -> list[dict]:
    interaction_id = action_result.get("interaction_id")
    if interaction_id:
        related = [
            intervention
            for intervention in interventions
            if intervention.get("interaction_id") == interaction_id
        ]
        if related:
            return related
    return interventions[-1:]


def _primary_intervention(interventions: list[dict]) -> dict:
    return next(
        (
            intervention
            for intervention in interventions
            if intervention.get("proposal", {}).get("source") != "post_action"
        ),
        interventions[-1],
    )
