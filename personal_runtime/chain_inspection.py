"""Human-inspectable reports for the M5 runtime chain."""

from __future__ import annotations

import json

from personal_runtime.prompt_context import build_behavior_contract
from personal_runtime.prompt_context import build_prompt_context_package
from personal_runtime.prompt_replay import build_replay_eval


def build_chain_report(session, action_result: dict) -> dict:
    intervention = session.gateway.state.interventions[-1]
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
        "intervention": intervention,
        "replay_eval": replay_eval,
        "action_result": action_result,
    }


def format_chain_report(report: dict) -> str:
    sections = [
        ("Trace", report["trace_lines"]),
        ("Observations", report["observations"]),
        ("Compact Snapshot", report["snapshot"]),
        ("Grounding Bundle", report.get("grounding", {})),
        ("Prompt Context", report.get("prompt_context", {})),
        ("Behavior Contract", report.get("behavior_contract", {})),
        ("Snapshot Contract", report["snapshot_contract"]),
        ("Proposal", report["proposal"]),
        ("Interaction", report.get("interaction", {})),
        ("Presence Decision", report["presence_decision"]),
        ("Recorded Intervention", report["intervention"]),
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
