"""Explicit prompt/context assembly and inspection contracts for M12."""

from __future__ import annotations


PROMPT_CONTEXT_VERSION = "m12.v1"


def build_prompt_context_package(
    user_text: str,
    snapshot: dict | None = None,
    grounding_bundle: dict | None = None,
    harness_memory: dict | None = None,
) -> dict:
    grounding = grounding_bundle or {}
    sections = {
        "compact_snapshot": dict(snapshot or {}),
        "active_goals": list(grounding.get("active_goals", [])),
        "recent_memory": dict(grounding.get("recent_memory", {})),
        "edge_evidence": dict(grounding.get("edge_history", {})),
    }
    if harness_memory is not None:
        sections["harness_memory"] = {
            "working": dict(harness_memory.get("working", {})),
            "procedural": list(harness_memory.get("procedural", [])),
            "semantic": list(harness_memory.get("semantic", [])),
            "episodic": list(harness_memory.get("episodic", [])),
            "lineage": dict(harness_memory.get("lineage", {})),
        }
    return {
        "version": PROMPT_CONTEXT_VERSION,
        "user_text": user_text,
        "grounding_bundle_version": grounding.get("bundle_version"),
        "sections": sections,
    }


def build_behavior_contract(
    prompt_context_package: dict,
    grounding_bundle: dict | None = None,
) -> dict:
    grounding = grounding_bundle or {}
    sections = prompt_context_package.get("sections", {})
    checks = {
        "compact_snapshot_present": {
            "ok": bool(sections.get("compact_snapshot")),
            "detail": "compact snapshot section is populated",
        },
        "active_goals_present": {
            "ok": bool(sections.get("active_goals")),
            "detail": "active goals section is populated",
        },
        "recent_memory_present": {
            "ok": any(
                bool(value)
                for value in sections.get("recent_memory", {}).values()
            ),
            "detail": "recent memory section contains bounded runtime memory",
        },
        "edge_evidence_present": {
            "ok": sections.get("edge_evidence", {}).get("returned_entries", 0) > 0,
            "detail": "edge evidence section contains bounded edge history",
        },
        "grounding_bundle_version_matches": {
            "ok": prompt_context_package.get("grounding_bundle_version")
            == grounding.get("bundle_version"),
            "detail": "prompt context and grounding bundle versions match",
        },
    }
    return {
        "prompt_context_version": prompt_context_package.get("version"),
        "grounding_bundle_version": grounding.get("bundle_version"),
        "allowed_proposal_types": [
            "action",
            "no_intervention",
            "provider_failure",
        ],
        "required_runtime_inputs": [
            "compact_snapshot",
            "grounding_bundle",
        ],
        "action_governance": {
            "governed_action_route": "presence_then_execution_planning",
            "provider_native_tool_calls": "normalize_to_runtime_action_intent",
            "notification_show_payload": {
                "required": ["body"],
                "optional": ["title"],
                "title_owner": "openhalo_or_target_edge",
            },
            "agent_private_tool_requirements": [
                "non_user_visible",
                "non_side_effectful",
                "explicitly_allowlisted",
            ],
        },
        "checks": checks,
    }


def prompt_context_metadata_from_package(
    prompt_context_package: dict,
    behavior_contract: dict,
) -> dict:
    sections = prompt_context_package.get("sections", {})
    return {
        "prompt_context_version": prompt_context_package.get("version"),
        "prompt_context_sections": sorted(sections.keys()),
        "prompt_context_active_goal_count": len(
            sections.get("active_goals", [])
        ),
        "prompt_context_recent_memory_counts": {
            key: len(value)
            for key, value in sections.get("recent_memory", {}).items()
            if isinstance(value, list)
        },
        "prompt_context_edge_evidence_entries": sections.get(
            "edge_evidence", {}
        ).get("returned_entries", 0),
        "behavior_contract_checks": {
            key: value.get("ok", False)
            for key, value in behavior_contract.get("checks", {}).items()
        },
    }


__all__ = [
    "PROMPT_CONTEXT_VERSION",
    "build_behavior_contract",
    "build_prompt_context_package",
    "prompt_context_metadata_from_package",
]
