"""Human-inspectable reports for the M5 runtime chain."""

from __future__ import annotations

import json


def build_chain_report(session, action_result: dict) -> dict:
    intervention = session.gateway.state.interventions[-1]
    snapshot_contract = intervention["snapshot_contract"]
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
        "proposal": intervention["proposal"],
        "presence_decision": {
            "decision": intervention["decision"],
            "reason": intervention["reason"],
            "target_device_id": intervention["target_device_id"],
        },
        "intervention": intervention,
        "action_result": action_result,
    }


def format_chain_report(report: dict) -> str:
    sections = [
        ("Trace", report["trace_lines"]),
        ("Observations", report["observations"]),
        ("Compact Snapshot", report["snapshot"]),
        ("Snapshot Contract", report["snapshot_contract"]),
        ("Proposal", report["proposal"]),
        ("Presence Decision", report["presence_decision"]),
        ("Recorded Intervention", report["intervention"]),
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
