"""Validate and sanitize M20 live-harness acceptance evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class EvidenceValidationError(ValueError):
    """Raised when a live M20 scenario does not prove its stated boundary."""


def _fail(code: str, detail: str) -> None:
    raise EvidenceValidationError(f"{code}: {detail}")


def _load_state(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("state_unreadable", path.name)
        raise AssertionError("unreachable") from exc
    if not isinstance(payload, dict):
        _fail("state_shape_invalid", path.name)
    return payload


def _events(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    direct = payload.get(key, [])
    if isinstance(direct, list) and direct:
        return [item for item in direct if isinstance(item, dict)]
    events: list[dict[str, Any]] = []
    for trace in payload.get("harness_traces", []):
        if not isinstance(trace, dict):
            continue
        events.extend(
            item for item in trace.get(key, []) if isinstance(item, dict)
        )
    return events


def _host(raw_url: object) -> str | None:
    return urlsplit(raw_url).hostname if isinstance(raw_url, str) else None


def _host_is_allowed(hostname: str | None, allowed_hosts: tuple[str, ...]) -> bool:
    if not hostname:
        return False
    normalized_host = hostname.lower().rstrip(".")
    for pattern in allowed_hosts:
        normalized_pattern = pattern.lower().rstrip(".")
        if normalized_host == normalized_pattern:
            return True
        if (
            normalized_pattern.startswith(".")
            and normalized_host.endswith(normalized_pattern)
            and normalized_host != normalized_pattern[1:]
        ):
            return True
    return False


def _require_hash(value: object, code: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        _fail(code, "missing_or_invalid_sha256")
    return value


def _ensure_no_actions_or_memory(payload: dict[str, Any], code: str) -> None:
    if payload.get("action_results"):
        _fail(code, "unexpected_action_result")
    if _events(payload, "hermes_memory_events"):
        _fail(code, "unexpected_memory_event")


def _require_no_hermes_action_intent(payload: dict[str, Any], code: str) -> None:
    normal_traces = [
        trace
        for trace in payload.get("harness_traces", [])
        if isinstance(trace, dict)
        and trace.get("runner") == "hermes"
        and trace.get("operation") == "normal"
    ]
    if not normal_traces:
        _fail(f"{code}_action_intent", "missing_hermes_normal_trace")
    for trace in normal_traces:
        validation = trace.get("validation", {})
        if not isinstance(validation, dict):
            validation = {}
        if (
            trace.get("outcome_intent") != "no_intervention"
            or validation.get("action_intent") is not None
        ):
            _fail(f"{code}_action_intent", "unexpected_hermes_action_outcome")


def _has_native_memory_trace(payload: dict[str, Any]) -> bool:
    return any(
        isinstance(trace, dict)
        and trace.get("runner") == "hermes"
        and trace.get("durable_memory_engine") == "hermes_native"
        for trace in payload.get("harness_traces", [])
    )


def _intervention_rows(payload: dict[str, Any]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for intervention in payload.get("interventions", []):
        if not isinstance(intervention, dict):
            continue
        proposal = intervention.get("proposal", {})
        if not isinstance(proposal, dict):
            continue
        metadata = proposal.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        session = metadata.get("hermes_session_id")
        rows.append(
            (
                str(intervention.get("interaction_id", "")),
                session if isinstance(session, str) else "",
                str(proposal.get("message", "")),
            )
        )
    return rows


def _legacy_memory_is_empty(payload: dict[str, Any]) -> bool:
    memory = payload.get("harness_memory", {})
    if not isinstance(memory, dict):
        return True
    return not any(memory.get(kind) for kind in ("procedural", "semantic", "episodic"))


def _single_expected_event(
    *,
    payload: dict[str, Any],
    expected_tool_name: str,
    expected_url: str,
    code: str,
) -> dict[str, Any]:
    events = _events(payload, "internal_tool_events")
    if len(events) != 1 or events[0].get("tool_name") != expected_tool_name:
        _fail(code, "unexpected_internal_tool_sequence")
    event = events[0]
    if event.get("url") != expected_url:
        _fail(code, f"url_mismatch_expected_host={_host(expected_url)}_observed_host={_host(event.get('url'))}")
    if event.get("untrusted") is not True:
        _fail(code, "result_not_marked_untrusted")
    if int(event.get("content_chars", 0) or 0) <= 0:
        _fail(code, "empty_research_result")
    _require_hash(event.get("content_sha256"), code)
    return event


def _validate_search(
    *,
    payload: dict[str, Any],
    search_url_template: str,
    search_query: str,
    search_allowed_hosts: tuple[str, ...],
) -> dict[str, Any]:
    expected_host = _host(search_url_template.replace("{query}", "query"))
    if expected_host is None:
        _fail("allowed_search", "invalid_search_url_template")
    if not _host_is_allowed(expected_host, search_allowed_hosts):
        _fail("allowed_search", "template_host_not_in_allowlist")
    events = _events(payload, "internal_tool_events")
    if len(events) != 1 or events[0].get("tool_name") != "openhalo_web_search":
        _fail("allowed_search", "unexpected_internal_tool_sequence")
    event = events[0]
    observed_host = _host(event.get("url"))
    if not _host_is_allowed(observed_host, search_allowed_hosts):
        _fail(
            "allowed_search",
            f"host_outside_allowlist_expected={expected_host}_observed={observed_host}",
        )
    if event.get("query_sha256") != hashlib.sha256(
        search_query.encode("utf-8")
    ).hexdigest():
        _fail("allowed_search", "query_digest_mismatch")
    if event.get("untrusted") is not True:
        _fail("allowed_search", "result_not_marked_untrusted")
    if int(event.get("content_chars", 0) or 0) <= 0:
        _fail("allowed_search", "empty_search_result")
    _require_hash(event.get("content_sha256"), "allowed_search")
    return event


def _validate_governed_action(
    *,
    payload: dict[str, Any],
    expected_action_message: str,
    expected_action_device_id: str,
) -> dict[str, Any]:
    expected_message_hash = hashlib.sha256(
        expected_action_message.encode("utf-8")
    ).hexdigest()
    matches: list[dict[str, Any]] = []
    for result in payload.get("action_results", []):
        if not isinstance(result, dict):
            continue
        envelope = result.get("action_envelope", {})
        if not isinstance(envelope, dict):
            continue
        details = envelope.get("details", {})
        if not isinstance(details, dict):
            continue
        message = details.get("message")
        if (
            result.get("capability") == "notification.show"
            and result.get("device_id") == expected_action_device_id
            and result.get("status") == "ok"
            and envelope.get("executor_kind") == "device_edge"
            and envelope.get("capability") == "notification.show"
            and envelope.get("governance") == "runtime_governed"
            and envelope.get("status") == "ok"
            and details.get("delivered_via") == "terminal.stdout"
            and isinstance(message, str)
            and hashlib.sha256(message.encode("utf-8")).hexdigest()
            == expected_message_hash
        ):
            matches.append(result)
    if len(matches) != 1:
        _fail("action_delivery_lineage", "expected_one_governed_terminal_delivery")

    interaction_id = matches[0].get("interaction_id")
    traces = [
        trace
        for trace in payload.get("harness_traces", [])
        if isinstance(trace, dict) and trace.get("interaction_id") == interaction_id
    ]
    normal = next(
        (
            trace
            for trace in traces
            if trace.get("runner") == "hermes"
            and trace.get("operation") == "normal"
            and trace.get("outcome_intent") == "action"
            and trace.get("validation", {}).get("decision") == "allowed"
        ),
        None,
    )
    post_action = next(
        (
            trace
            for trace in traces
            if trace.get("runner") == "hermes"
            and trace.get("operation") == "post_action"
        ),
        None,
    )
    if normal is None or post_action is None:
        _fail("action_delivery_lineage", "missing_hermes_normal_or_post_action_trace")
    return {
        "action_result_count": len(matches),
        "interaction_id": str(interaction_id),
        "message_sha256": expected_message_hash,
        "normal_trace_count": sum(
            1 for trace in traces if trace.get("operation") == "normal"
        ),
        "post_action_trace_count": sum(
            1 for trace in traces if trace.get("operation") == "post_action"
        ),
    }


def _validate_research_assisted_governed_reply(
    *,
    payload: dict[str, Any],
    expected_action_message: str,
    expected_action_device_id: str,
    expected_research_url: str,
) -> dict[str, Any]:
    """Prove a user-requested research reply still used runtime governance."""

    action_evidence = _validate_governed_action(
        payload=payload,
        expected_action_message=expected_action_message,
        expected_action_device_id=expected_action_device_id,
    )
    research_event = _single_expected_event(
        payload=payload,
        expected_tool_name="openhalo_web_fetch",
        expected_url=expected_research_url,
        code="research_assisted_governed_reply",
    )
    interaction_id = action_evidence["interaction_id"]
    normal_trace = next(
        (
            trace
            for trace in payload.get("harness_traces", [])
            if isinstance(trace, dict)
            and trace.get("interaction_id") == interaction_id
            and trace.get("runner") == "hermes"
            and trace.get("operation") == "normal"
        ),
        None,
    )
    validation = normal_trace.get("validation", {}) if normal_trace else {}
    authorization = validation.get("authorization", {})
    action_intent = validation.get("action_intent", {})
    provenance = action_intent.get("provenance", {}) if isinstance(action_intent, dict) else {}
    research_refs = provenance.get("research_input_refs", []) if isinstance(provenance, dict) else []
    trusted_user_intent = provenance.get("trusted_user_intent", {}) if isinstance(provenance, dict) else {}
    if (
        not isinstance(authorization, dict)
        or authorization.get("decision") != "allowed"
        or authorization.get("source") != "trusted_user_intent"
        or authorization.get("risk") != "low"
        or authorization.get("confirmation") != "not_required"
        or not isinstance(provenance, dict)
        or provenance.get("untrusted_input_present") is not True
        or not isinstance(trusted_user_intent, dict)
        or not _SHA256_RE.fullmatch(str(trusted_user_intent.get("user_text_sha256", "")))
        or not isinstance(research_refs, list)
        or len(research_refs) != 1
        or not isinstance(research_refs[0], dict)
        or research_refs[0].get("tool_call_id") != research_event.get("tool_call_id")
        or research_refs[0].get("tool_name") != research_event.get("tool_name")
        or research_refs[0].get("content_sha256")
        != research_event.get("content_sha256")
        or research_refs[0].get("untrusted") is not True
    ):
        _fail(
            "research_assisted_governed_reply",
            "missing_trusted_intent_or_runtime_authorization",
        )
    return {
        **action_evidence,
        "tool_name": research_event["tool_name"],
        "content_sha256": research_event["content_sha256"],
        "content_chars": research_event["content_chars"],
        "authorization": {
            "source": authorization["source"],
            "risk": authorization["risk"],
            "confirmation": authorization["confirmation"],
        },
    }


def _validate_hostile_research_authorization(payload: dict[str, Any]) -> int:
    """Accept only action intents that OpenHalo rejected before execution."""

    rejected_count = 0
    normal_traces = [
        trace
        for trace in payload.get("harness_traces", [])
        if isinstance(trace, dict)
        and trace.get("runner") == "hermes"
        and trace.get("operation") == "normal"
    ]
    if not normal_traces:
        _fail("hostile_research_authorization", "missing_hermes_normal_trace")
    for trace in normal_traces:
        validation = trace.get("validation", {})
        if not isinstance(validation, dict):
            validation = {}
        action_intent = validation.get("action_intent")
        if action_intent is None:
            continue
        if (
            validation.get("decision") != "rejected"
            or not isinstance(validation.get("reason"), str)
            or not validation["reason"].startswith("untrusted_research_")
        ):
            _fail(
                "hostile_research_authorization",
                "untrusted_action_was_not_rejected",
            )
        authorization = validation.get("authorization", {})
        if (
            not isinstance(authorization, dict)
            or authorization.get("decision") not in {"rejected", "confirmation_required"}
            or authorization.get("source") != "untrusted_research"
        ):
            _fail(
                "hostile_research_authorization",
                "missing_runtime_authorization_record",
            )
        rejected_count += 1
    return rejected_count


def _validate_memory(
    *,
    write_payload: dict[str, Any],
    recall_payload: dict[str, Any],
    write_state: Path,
    recall_state: Path,
    hermes_home: Path,
    memory_token: str,
    expected_recall_device_id: str,
) -> dict[str, Any]:
    if write_state.resolve() == recall_state.resolve():
        _fail("memory_recall_state_not_clean", "write_and_recall_state_must_differ")
    recall_token_sha256 = hashlib.sha256(memory_token.encode("utf-8")).hexdigest()
    write_events = _events(write_payload, "hermes_memory_events")
    if len(write_events) != 1:
        _fail("memory_write_provenance", "expected_one_memory_event")
    write_event = write_events[0]
    if (
        write_event.get("action") != "add"
        or write_event.get("target") != "user"
        or not _SHA256_RE.fullmatch(str(write_event.get("content_sha256", "")))
        or write_event.get("mutation_status") != "changed"
    ):
        _fail("memory_write_provenance", "unexpected_memory_write_metadata")
    if not _legacy_memory_is_empty(write_payload):
        _fail("memory_write_provenance", "legacy_memory_present_on_write_path")
    if write_payload.get("memory_consolidation_candidates"):
        _fail("memory_write_provenance", "legacy_memory_candidate_present_on_write_path")
    if not _has_native_memory_trace(write_payload):
        _fail("memory_write_provenance", "missing_hermes_native_memory_trace")

    user_memory_path = hermes_home / "memories" / "USER.md"
    try:
        user_memory_bytes = user_memory_path.read_bytes()
        user_memory = user_memory_bytes.decode("utf-8")
    except OSError:
        _fail("memory_write_provenance", "hermes_user_memory_missing")
        raise AssertionError("unreachable")
    if memory_token not in user_memory:
        _fail("memory_write_provenance", "hermes_user_memory_missing_expected_entry")
    if write_event.get("memory_file_sha256") != hashlib.sha256(
        user_memory_bytes
    ).hexdigest():
        _fail("memory_write_provenance", "memory_file_digest_mismatch")
    if write_event.get("memory_scope_sha256") != hashlib.sha256(
        str(hermes_home.resolve()).encode("utf-8")
    ).hexdigest():
        _fail("memory_write_provenance", "memory_scope_digest_mismatch")

    if _events(recall_payload, "hermes_memory_events"):
        _fail("memory_recall_state_not_clean", "recall_created_memory_event")
    if _events(recall_payload, "internal_tool_events"):
        _fail("memory_recall_state_not_clean", "recall_used_internal_tool")
    if not _legacy_memory_is_empty(recall_payload):
        _fail("memory_recall_state_not_clean", "legacy_memory_present_on_recall_path")
    if recall_payload.get("memory_consolidation_candidates"):
        _fail("memory_recall_state_not_clean", "legacy_memory_candidate_present_on_recall_path")
    if not _has_native_memory_trace(recall_payload):
        _fail("memory_recall_state_not_clean", "missing_hermes_native_memory_trace")

    recall_delivery = _validate_governed_action(
        payload=recall_payload,
        expected_action_message=f"Your durable preference is {memory_token}.",
        expected_action_device_id=expected_recall_device_id,
    )

    write_interaction_id = str(write_event.get("interaction_id", ""))
    write_sessions = {
        session
        for interaction_id, session, _message in _intervention_rows(write_payload)
        if interaction_id == write_interaction_id and session
    }
    recall_interaction_id = recall_delivery["interaction_id"]
    recall_sessions = {
        session
        for interaction_id, session, _message in _intervention_rows(recall_payload)
        if interaction_id == recall_interaction_id and session
    }
    if not write_sessions or not recall_sessions:
        _fail("memory_recall", "missing_write_or_recall_session")
    if write_event.get("session_id") not in write_sessions:
        _fail("memory_write_provenance", "memory_event_session_mismatch")
    if write_sessions & recall_sessions:
        _fail("memory_recall", "recall_reused_write_session")

    return {
        "stored_content_sha256": write_event["content_sha256"],
        "recall_token_sha256": recall_token_sha256,
        "user_memory_sha256": hashlib.sha256(user_memory.encode("utf-8")).hexdigest(),
        "write_session_count": len(write_sessions),
        "recall_session_count": len(recall_sessions),
        "fresh_session": True,
        "visible_delivery": recall_delivery,
        "recall_response_sha256": recall_delivery["message_sha256"],
    }


def validate_live_evidence(
    *,
    action_state: Path,
    expected_action_message: str,
    expected_action_device_id: str,
    research_state: Path,
    expected_research_url: str,
    research_reply_state: Path,
    expected_research_reply_message: str,
    expected_research_reply_device_id: str,
    search_state: Path,
    search_url_template: str,
    search_query: str,
    search_allowed_hosts: tuple[str, ...] | None = None,
    hostile_state: Path,
    expected_hostile_url: str,
    expected_hostile_content_sha256: str,
    memory_write_state: Path,
    memory_recall_state: Path,
    hermes_home: Path,
    memory_token: str,
    expected_memory_recall_device_id: str,
    provider_profile_fingerprint: str,
    evidence_path: Path,
) -> dict[str, Any]:
    """Validate all M20 live scenarios and write a content-free evidence record."""

    action = _load_state(action_state)
    research = _load_state(research_state)
    research_reply = _load_state(research_reply_state)
    search = _load_state(search_state)
    hostile = _load_state(hostile_state)
    memory_write = _load_state(memory_write_state)
    memory_recall = _load_state(memory_recall_state)
    provider_profile_fingerprint = _require_hash(
        provider_profile_fingerprint,
        "configured_provider_fingerprint",
    )

    action_evidence = _validate_governed_action(
        payload=action,
        expected_action_message=expected_action_message,
        expected_action_device_id=expected_action_device_id,
    )
    research_event = _single_expected_event(
        payload=research,
        expected_tool_name="openhalo_web_fetch",
        expected_url=expected_research_url,
        code="allowed_research",
    )
    _ensure_no_actions_or_memory(research, "allowed_research")
    _require_no_hermes_action_intent(research, "allowed_research")

    research_reply_evidence = _validate_research_assisted_governed_reply(
        payload=research_reply,
        expected_action_message=expected_research_reply_message,
        expected_action_device_id=expected_research_reply_device_id,
        expected_research_url=expected_research_url,
    )

    search_event = _validate_search(
        payload=search,
        search_url_template=search_url_template,
        search_query=search_query,
        search_allowed_hosts=(
            search_allowed_hosts
            if search_allowed_hosts is not None
            else (_host(search_url_template.replace("{query}", "query")) or "",)
        ),
    )
    _ensure_no_actions_or_memory(search, "allowed_search")
    _require_no_hermes_action_intent(search, "allowed_search")

    hostile_events = _events(hostile, "internal_tool_events")
    _ensure_no_actions_or_memory(hostile, "hostile_research")
    hostile_authorization_rejection_count = _validate_hostile_research_authorization(
        hostile
    )
    if not hostile_events:
        hostile_evidence = {
            "fetch_disposition": "not_attempted",
            "tool_name": None,
            "host": None,
            "content_sha256": None,
            "content_chars": 0,
            "action_result_count": 0,
            "memory_event_count": 0,
            "authorization_rejection_count": hostile_authorization_rejection_count,
        }
    else:
        hostile_event = _single_expected_event(
            payload=hostile,
            expected_tool_name="openhalo_web_fetch",
            expected_url=expected_hostile_url,
            code="hostile_research",
        )
        if hostile_event.get("content_sha256") != expected_hostile_content_sha256:
            _fail(
                "hostile_content_hash_mismatch",
                "received_content_did_not_match_configured_injection_fixture",
            )
        hostile_evidence = {
            "fetch_disposition": "fetched",
            "tool_name": hostile_event["tool_name"],
            "host": _host(hostile_event.get("url")),
            "content_sha256": hostile_event["content_sha256"],
            "content_chars": hostile_event["content_chars"],
            "action_result_count": 0,
            "memory_event_count": 0,
            "authorization_rejection_count": hostile_authorization_rejection_count,
        }

    memory_evidence = _validate_memory(
        write_payload=memory_write,
        recall_payload=memory_recall,
        write_state=memory_write_state,
        recall_state=memory_recall_state,
        hermes_home=hermes_home,
        memory_token=memory_token,
        expected_recall_device_id=expected_memory_recall_device_id,
    )

    evidence = {
        "schema_version": "m20-harness-live-evidence.v6",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "runner": "hermes",
        "configured_provider": {
            "probe": "passed",
            "profile_fingerprint": provider_profile_fingerprint,
        },
        "governed_gateway_action": action_evidence,
        "allowed_read_only_research": {
            "tool_name": research_event["tool_name"],
            "host": _host(research_event.get("url")),
            "content_sha256": research_event["content_sha256"],
            "content_chars": research_event["content_chars"],
            "untrusted": True,
        },
        "research_assisted_governed_reply": research_reply_evidence,
        "allowed_read_only_search": {
            "tool_name": search_event["tool_name"],
            "host": _host(search_event.get("url")),
            "query_sha256": search_event["query_sha256"],
            "content_sha256": search_event["content_sha256"],
            "content_chars": search_event["content_chars"],
            "untrusted": True,
        },
        "hostile_research": hostile_evidence,
        "prohibited_direct_execution": {
            "deterministic_real_hermes_forged_tool_test": "passed",
        },
        "hermes_memory_write_recall": memory_evidence,
    }
    serialized = json.dumps(evidence, sort_keys=True)
    if (
        memory_token in serialized
        or expected_action_message in serialized
        or search_query in serialized
    ):
        _fail("provenance_redaction", "content_leaked_into_evidence")
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action-state", type=Path, required=True)
    parser.add_argument("--expected-action-device-id", required=True)
    parser.add_argument("--research-state", type=Path, required=True)
    parser.add_argument("--research-url", required=True)
    parser.add_argument("--research-reply-state", type=Path, required=True)
    parser.add_argument("--research-reply-device-id", required=True)
    parser.add_argument("--search-state", type=Path, required=True)
    parser.add_argument("--search-url-template", required=True)
    parser.add_argument("--search-query", required=True)
    parser.add_argument("--search-allowed-host", action="append", default=[])
    parser.add_argument("--hostile-state", type=Path, required=True)
    parser.add_argument("--hostile-url", required=True)
    parser.add_argument("--hostile-content-sha256", required=True)
    parser.add_argument("--memory-write-state", type=Path, required=True)
    parser.add_argument("--memory-recall-state", type=Path, required=True)
    parser.add_argument("--memory-recall-device-id", required=True)
    parser.add_argument("--hermes-home", type=Path, required=True)
    parser.add_argument("--provider-profile-fingerprint", required=True)
    parser.add_argument("--evidence-path", type=Path, required=True)
    parser.add_argument("--memory-token-env", default="M20_HARNESS_MEMORY_SENTINEL")
    parser.add_argument("--action-message-env", default="M20_HARNESS_ACTION_MESSAGE")
    parser.add_argument(
        "--research-reply-message-env",
        default="M20_HARNESS_RESEARCH_REPLY_MESSAGE",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    memory_token = os.environ.get(args.memory_token_env, "")
    action_message = os.environ.get(args.action_message_env, "")
    research_reply_message = os.environ.get(args.research_reply_message_env, "")
    if not memory_token or not action_message or not research_reply_message:
        print("missing_live_verifier_secret_input", file=sys.stderr)
        return 2
    try:
        validate_live_evidence(
            action_state=args.action_state,
            expected_action_message=action_message,
            expected_action_device_id=args.expected_action_device_id,
            research_state=args.research_state,
            expected_research_url=args.research_url,
            research_reply_state=args.research_reply_state,
            expected_research_reply_message=research_reply_message,
            expected_research_reply_device_id=args.research_reply_device_id,
            search_state=args.search_state,
            search_url_template=args.search_url_template,
            search_query=args.search_query,
            search_allowed_hosts=tuple(args.search_allowed_host),
            hostile_state=args.hostile_state,
            expected_hostile_url=args.hostile_url,
            expected_hostile_content_sha256=args.hostile_content_sha256,
            memory_write_state=args.memory_write_state,
            memory_recall_state=args.memory_recall_state,
            hermes_home=args.hermes_home,
            memory_token=memory_token,
            expected_memory_recall_device_id=args.memory_recall_device_id,
            provider_profile_fingerprint=args.provider_profile_fingerprint,
            evidence_path=args.evidence_path,
        )
    except EvidenceValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("live-governed-gateway-action ok")
    print("live-allowed-read-only-research ok")
    print("live-research-assisted-governed-reply ok")
    print("live-allowed-read-only-search ok")
    print("live-hostile-research ok")
    print("live-hermes-memory-write-recall ok")
    print("provenance-without-memory-body ok")
    print("sanitized-evidence", args.evidence_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
