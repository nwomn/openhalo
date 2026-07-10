"""Read-only runtime context viewer for live observation inspection."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any

from personal_runtime.context_snapshot import build_context_snapshot_contract
from personal_runtime.mobile_liveness import build_mobile_liveness_view
from personal_runtime.prompt_context import build_behavior_contract
from personal_runtime.prompt_context import build_prompt_context_package
from personal_runtime.runtime_state import RuntimeState


DEFAULT_STATE_PATH = Path(".runtime/state.json")


def load_state_payload(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_runtime_state(path: Path) -> RuntimeState:
    payload = load_state_payload(path)
    if not payload:
        return RuntimeState()
    return RuntimeState.from_dict(payload)


def load_diagnostic_events(path: Path | None, limit: int) -> list[dict]:
    if path is None or not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    events: list[dict] = []
    for line in lines[-limit:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"malformed_jsonl": line})
    return events


def build_context_view(
    state_payload: dict,
    diagnostic_events: list[dict] | None = None,
    limit: int = 8,
    current_time: str | None = None,
    online_device_ids: set[str] | None = None,
) -> dict:
    state = RuntimeState.from_dict(state_payload) if state_payload else RuntimeState()
    observations = [observation.to_dict() for observation in state.observations]
    generated_at = current_time or _utc_now()
    current_snapshot_contract = build_context_snapshot_contract(
        state.observations,
        snapshot_time=generated_at,
    )
    current_snapshot = {
        field_name: field["value"]
        for field_name, field in current_snapshot_contract["fields"].items()
    }
    latest_intervention = state.interventions[-1] if state.interventions else {}
    latest_prompt_context = _build_latest_prompt_context(latest_intervention)
    snapshot_evidence_keys = _snapshot_evidence_keys(current_snapshot_contract)
    latest_observations = observations[-limit:]
    mobile_liveness = build_mobile_liveness_view(
        state,
        online_device_ids=online_device_ids or set(),
        current_time=generated_at,
    )
    return {
        "counts": {
            "events": len(state.events),
            "observations": len(state.observations),
            "interventions": len(state.interventions),
            "interactions": len(state.interactions),
            "diagnostic_events": len(diagnostic_events or []),
        },
        "latest_ingress_events": state.events[-limit:],
        "latest_observations": [
            {
                **observation,
                "in_current_snapshot_evidence": _observation_key(observation)
                in snapshot_evidence_keys,
                "snapshot_fields": _snapshot_fields_for_observation(
                    observation,
                    current_snapshot_contract,
                ),
            }
            for observation in latest_observations
        ],
        "current_snapshot_evidence": _snapshot_evidence(current_snapshot_contract),
        "current_snapshot": current_snapshot,
        "current_snapshot_contract": current_snapshot_contract,
        "latest_intervention_summary": _intervention_summary(latest_intervention),
        "latest_intervention_snapshot_contract": latest_intervention.get(
            "snapshot_contract",
            {},
        ),
        "mobile_liveness": mobile_liveness,
        "latest_prompt_context": latest_prompt_context,
        "latest_diagnostic_events": diagnostic_events or [],
        "generated_at": generated_at,
    }


def format_context_view(
    view: dict,
    state_path: Path,
    diagnostic_path: Path | None = None,
    debug_history: bool = False,
) -> str:
    lines = [
        "OpenHalo Runtime Context Viewer",
        f"state_path: {state_path}",
        f"diagnostic_log_path: {diagnostic_path if diagnostic_path else 'not configured'}",
        f"generated_at: {view.get('generated_at')}",
        "",
        "Counts:",
        _format_json(view["counts"]),
        "",
        "Latest Accepted Ingress Events:",
        _format_json(_summarize_events(view["latest_ingress_events"])),
        "",
        "Latest Normalized Observations:",
        _format_json(_summarize_observations(view["latest_observations"])),
        "",
        "Current Agent-Visible Compact Snapshot:",
        _format_json(view["current_snapshot"]),
        "",
        "Current Snapshot Evidence Contract:",
        _format_json(_summarize_snapshot_contract(view["current_snapshot_contract"])),
        "",
        "Current Snapshot Evidence Only:",
        _format_json(_summarize_observations(view["current_snapshot_evidence"])),
        "",
        "Latest Agent Turn:",
        _format_json(view["latest_intervention_summary"]),
        "",
        "Latest Agent Turn Snapshot Contract:",
        _format_json(_summarize_snapshot_contract(view["latest_intervention_snapshot_contract"])),
        "",
        "Mobile Observation Liveness:",
        _format_json(_summarize_mobile_liveness(view.get("mobile_liveness", {}))),
        "",
        "Latest Prompt Context:",
        _format_json(view["latest_prompt_context"]),
    ]
    if debug_history:
        lines.extend(
            [
                "",
                "Debug History:",
                "No additional persisted history sections are enabled yet.",
            ]
        )
    if debug_history and view.get("latest_diagnostic_events"):
        lines.extend(
            [
                "",
                "Debug History - Latest Diagnostic Events:",
                _format_json(_summarize_diagnostics(view["latest_diagnostic_events"])),
            ]
        )
    return "\n".join(lines)


def render_context_view(
    state_path: Path,
    diagnostic_log_path: Path | None = None,
    limit: int = 8,
    debug_history: bool = False,
) -> str:
    state_payload = load_state_payload(state_path)
    diagnostic_events = load_diagnostic_events(diagnostic_log_path, limit)
    view = build_context_view(
        state_payload,
        diagnostic_events=diagnostic_events,
        limit=limit,
    )
    return format_context_view(
        view,
        state_path=state_path,
        diagnostic_path=diagnostic_log_path,
        debug_history=debug_history,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect runtime observations, compact snapshot, and latest agent context.",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=DEFAULT_STATE_PATH,
        help="Runtime state JSON path to inspect.",
    )
    parser.add_argument(
        "--diagnostic-log-path",
        type=Path,
        help="Optional runtime diagnostic.v1 JSONL path to include.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Number of latest events, observations, and diagnostics to show.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Refresh the view continuously.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=1.0,
        help="Refresh interval when --watch is used.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the raw viewer model as JSON instead of the readable report.",
    )
    parser.add_argument(
        "--debug-history",
        action="store_true",
        help="Also show persisted ingress events, latest raw observations, and diagnostic tail.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    while True:
        if args.json:
            payload = load_state_payload(args.state_path)
            diagnostics = load_diagnostic_events(args.diagnostic_log_path, args.limit)
            view = build_context_view(
                payload,
                diagnostic_events=diagnostics,
                limit=args.limit,
            )
            if not args.debug_history:
                view = _agent_context_view(view)
            text = _format_json(view)
        else:
            text = render_context_view(
                state_path=args.state_path,
                diagnostic_log_path=args.diagnostic_log_path,
                limit=args.limit,
                debug_history=args.debug_history,
            )
        print(text)
        if not args.watch:
            return
        print("\n--- refresh ---\n", flush=True)
        time.sleep(args.interval_seconds)


def _build_latest_prompt_context(intervention: dict) -> dict:
    if not intervention:
        return {}
    snapshot_contract = intervention.get("snapshot_contract", {})
    snapshot = {
        field_name: field.get("value")
        for field_name, field in snapshot_contract.get("fields", {}).items()
    }
    prompt_context = build_prompt_context_package(
        user_text=intervention.get("proposal", {}).get("message", ""),
        snapshot=snapshot,
        grounding_bundle=intervention.get("grounding_bundle", {}),
    )
    behavior_contract = build_behavior_contract(
        prompt_context_package=prompt_context,
        grounding_bundle=intervention.get("grounding_bundle", {}),
    )
    return {
        "prompt_context": prompt_context,
        "behavior_contract": behavior_contract,
    }


def _snapshot_evidence_keys(snapshot_contract: dict) -> set[tuple[str, str, str, str]]:
    keys: set[tuple[str, str, str, str]] = set()
    for field in snapshot_contract.get("fields", {}).values():
        for evidence in field.get("evidence", []):
            keys.add(_observation_key(evidence))
    return keys


def _snapshot_fields_for_observation(observation: dict, snapshot_contract: dict) -> list[str]:
    key = _observation_key(observation)
    fields = []
    for field_name, field in snapshot_contract.get("fields", {}).items():
        if any(_observation_key(evidence) == key for evidence in field.get("evidence", [])):
            fields.append(field_name)
    return fields


def _snapshot_evidence(snapshot_contract: dict) -> list[dict]:
    evidence = []
    for field_name, field in snapshot_contract.get("fields", {}).items():
        for observation in field.get("evidence", []):
            evidence.append(
                {
                    **observation,
                    "in_current_snapshot_evidence": True,
                    "snapshot_fields": [field_name],
                    "snapshot_field_status": field.get("status"),
                }
            )
    return evidence


def _observation_key(observation: dict) -> tuple[str, str, str, str]:
    return (
        str(observation.get("name", "")),
        str(observation.get("source_device_id", "")),
        str(observation.get("source_capability", "")),
        str(observation.get("observed_at", "")),
    )


def _intervention_summary(intervention: dict) -> dict:
    if not intervention:
        return {}
    proposal = intervention.get("proposal", {})
    return {
        "interaction_id": intervention.get("interaction_id"),
        "proposal_type": proposal.get("proposal_type"),
        "proposal_source": proposal.get("source"),
        "action_capability": proposal.get("action_capability"),
        "target_device_id": intervention.get("target_device_id"),
        "presence_decision": intervention.get("decision"),
        "presence_reason": intervention.get("reason"),
    }


def _summarize_events(events: list[dict]) -> list[dict]:
    summarized = []
    for event in events:
        observations = event.get("payload", {}).get("observations", [])
        summarized.append(
            {
                "type": event.get("type"),
                "device_id": event.get("device_id"),
                "capability": event.get("capability"),
                "event_id": event.get("event_id"),
                "observation_names": [
                    observation.get("name") for observation in observations
                ],
                "payload": event.get("payload", {}),
            }
        )
    return summarized


def _summarize_observations(observations: list[dict]) -> list[dict]:
    return [
        {
            "name": observation.get("name"),
            "source": (
                f"{observation.get('source_device_id', '')}/"
                f"{observation.get('source_capability', '')}"
            ),
            "observed_at": observation.get("observed_at"),
            "confidence": observation.get("confidence"),
            "in_current_snapshot_evidence": observation.get(
                "in_current_snapshot_evidence",
                False,
            ),
            "snapshot_fields": observation.get("snapshot_fields", []),
            "snapshot_field_status": observation.get("snapshot_field_status"),
            "value": _compact_value(observation.get("value")),
        }
        for observation in observations
    ]


def _summarize_snapshot_contract(contract: dict) -> dict:
    return {
        "snapshot_time": contract.get("snapshot_time"),
        "fields": {
            field_name: {
                "observation_name": field.get("observation_name"),
                "value": field.get("value"),
                "status": field.get("status"),
                "evidence_count": len(field.get("evidence", [])),
                "evidence": [
                    {
                        "name": evidence.get("name"),
                        "source": (
                            f"{evidence.get('source_device_id', '')}/"
                            f"{evidence.get('source_capability', '')}"
                        ),
                        "observed_at": evidence.get("observed_at"),
                        "value": _compact_value(evidence.get("value")),
                    }
                    for evidence in field.get("evidence", [])
                ],
            }
            for field_name, field in contract.get("fields", {}).items()
        },
    }


def _summarize_mobile_liveness(mobile_liveness: dict) -> list[dict]:
    return [
        {
            "device_id": payload.get("device_id", device_id),
            "state": payload.get("state"),
            "online": payload.get("online"),
            "expected_active_observation": payload.get(
                "expected_active_observation"
            ),
            "last_screen_context_at": payload.get("last_screen_context_at"),
            "silence_seconds": payload.get("silence_seconds"),
            "wake_recovery_eligible": payload.get("wake_recovery_eligible"),
            "last_recovery_attempt": payload.get("last_recovery_attempt"),
        }
        for device_id, payload in sorted(mobile_liveness.items())
    ]


def _summarize_diagnostics(events: list[dict]) -> list[dict]:
    summarized = []
    for event in events:
        summarized.append(
            {
                "module": event.get("module"),
                "operation": event.get("operation"),
                "phase": event.get("phase"),
                "summary": event.get("summary"),
                "input": event.get("input"),
                "output": event.get("output"),
                "correlation": event.get("correlation"),
            }
        )
    return summarized


def _compact_value(value: Any) -> Any:
    if isinstance(value, dict):
        preferred_keys = [
            "trigger",
            "event_kind",
            "source",
            "screen_state",
            "capture_mode",
            "capture_pause_reason",
            "screen_kind",
            "visible_text_summary",
            "sensitivity",
            "raw_screenshot_uploaded",
        ]
        compact = {key: value[key] for key in preferred_keys if key in value}
        if compact:
            return compact
    return value


def _format_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _agent_context_view(view: dict) -> dict:
    return {
        "generated_at": view.get("generated_at"),
        "counts": view.get("counts", {}),
        "latest_ingress_events": view.get("latest_ingress_events", []),
        "latest_observations": view.get("latest_observations", []),
        "current_snapshot": view.get("current_snapshot", {}),
        "current_snapshot_contract": view.get("current_snapshot_contract", {}),
        "current_snapshot_evidence": view.get("current_snapshot_evidence", []),
        "latest_intervention_summary": view.get("latest_intervention_summary", {}),
        "latest_intervention_snapshot_contract": view.get(
            "latest_intervention_snapshot_contract",
            {},
        ),
        "mobile_liveness": view.get("mobile_liveness", {}),
        "latest_prompt_context": view.get("latest_prompt_context", {}),
    }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


if __name__ == "__main__":
    main()
