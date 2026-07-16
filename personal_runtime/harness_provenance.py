"""Sanitized Hermes tool and durable-memory provenance contracts."""

from __future__ import annotations

import hashlib


TRACE_PROVENANCE_EVENT_LIMIT = 32
RUNTIME_PROVENANCE_HISTORY_LIMIT = 128
TRUSTED_INTENT_REF_VERSION = "m20.trusted-intent.v1"
_REMOTE_RESEARCH_TOOL_PREFIXES = (
    "openhalo_web_",
)
def build_trusted_user_intent_ref(harness_input: object) -> dict | None:
    """Build the body-free reference for an authenticated normal text turn."""

    operation = getattr(harness_input, "operation", None)
    operation_value = getattr(operation, "value", operation)
    frame = getattr(harness_input, "frame", None)
    if operation_value != "normal" or not isinstance(frame, dict):
        return None
    payload = frame.get("payload")
    if not isinstance(payload, dict):
        return None
    text = payload.get("text")
    source_device_id = frame.get("device_id")
    interaction_id = getattr(harness_input, "interaction_id", None)
    interaction_turn_id = getattr(harness_input, "interaction_turn_id", None)
    if (
        not isinstance(text, str)
        or not text.strip()
        or not isinstance(source_device_id, str)
        or not source_device_id
        or not isinstance(interaction_id, str)
        or not interaction_id
        or not isinstance(interaction_turn_id, str)
        or not interaction_turn_id
    ):
        return None
    return {
        "version": TRUSTED_INTENT_REF_VERSION,
        "kind": "normal_user_request",
        "operation": "normal",
        "interaction_id": interaction_id,
        "interaction_turn_id": interaction_turn_id,
        "source_device_id": source_device_id,
        "source_event_id": _optional_string(frame.get("event_id")),
        "source_capability": _optional_string(frame.get("capability")),
        "user_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "user_text_chars": len(text),
    }


def trusted_user_intent_ref_matches(
    reference: object,
    harness_input: object,
) -> bool:
    """Verify a model-visible reference still matches the current trusted turn."""

    expected = build_trusted_user_intent_ref(harness_input)
    return expected is not None and reference == expected


def sanitize_trusted_intent_ref(reference: object) -> dict:
    """Keep a stable hash-only intent reference for durable provenance."""

    if not isinstance(reference, dict):
        return {}
    sanitized = {}
    for field_name in (
        "version",
        "kind",
        "operation",
        "interaction_id",
        "interaction_turn_id",
        "source_device_id",
        "user_text_sha256",
        "memory_intent_scope",
    ):
        value = reference.get(field_name)
        if isinstance(value, str):
            sanitized[field_name] = value
    for field_name in ("source_event_id", "source_capability"):
        value = reference.get(field_name)
        if isinstance(value, str) or value is None:
            sanitized[field_name] = value
    user_text_chars = reference.get("user_text_chars")
    if _is_non_negative_int(user_text_chars):
        sanitized["user_text_chars"] = user_text_chars
    return sanitized


def sanitize_research_input_refs(
    refs: object,
    *,
    limit: int = TRACE_PROVENANCE_EVENT_LIMIT,
) -> list[dict]:
    """Retain only hash-based references to untrusted research inputs."""

    if not isinstance(refs, list):
        return []
    sanitized = []
    for reference in refs[-limit:]:
        if not isinstance(reference, dict):
            continue
        item = {}
        for field_name in (
            "tool_call_id",
            "tool_name",
            "content_sha256",
            "url_sha256",
        ):
            value = reference.get(field_name)
            if isinstance(value, str):
                item[field_name] = value
        if reference.get("untrusted") is True:
            item["untrusted"] = True
        if item:
            sanitized.append(item)
    return sanitized


def sanitize_internal_tool_events(
    events: object,
    *,
    limit: int = TRACE_PROVENANCE_EVENT_LIMIT,
) -> list[dict]:
    """Keep only bounded, body-free internal-tool audit fields."""

    if events is None:
        return []
    if not isinstance(events, list):
        return [{}]
    return [
        _sanitize_internal_tool_event(event)
        for event in events[-limit:]
    ]


def sanitize_hermes_memory_events(
    events: object,
    *,
    limit: int = TRACE_PROVENANCE_EVENT_LIMIT,
) -> list[dict]:
    """Keep Hermes memory references without retaining a memory body."""

    if not isinstance(events, list):
        return []
    return [
        _sanitize_hermes_memory_event(event)
        for event in events[-limit:]
        if isinstance(event, dict)
    ]


def internal_tool_audit_issue(event: object) -> str | None:
    """Return the promotion-blocking classification for an unsafe audit."""

    if not isinstance(event, dict):
        return "malformed_internal_tool_audit"
    tool_name = event.get("tool_name")
    untrusted = event.get("untrusted")
    requires_untrusted_audit = (
        isinstance(tool_name, str)
        and tool_name.startswith(_REMOTE_RESEARCH_TOOL_PREFIXES)
    )
    missing_required_audit = (
        not isinstance(tool_name, str)
        or not tool_name
        or not _is_sha256(event.get("content_sha256"))
        or not _is_non_negative_int(event.get("content_chars"))
        or not isinstance(untrusted, bool)
    )
    missing_research_audit = requires_untrusted_audit and (
        not isinstance(event.get("tool_call_id"), str)
        or not event["tool_call_id"]
        or not isinstance(event.get("url"), str)
        or not event["url"]
        or not _is_sha256(event.get("url_sha256"))
        or not isinstance(event.get("policy_version"), str)
        or not event["policy_version"]
        or event.get("egress_decision") != "allowed"
        or not _is_non_negative_int(event.get("duration_ms"))
    )
    if (
        missing_required_audit
        or missing_research_audit
        or (requires_untrusted_audit and untrusted is not True)
    ):
        if untrusted is True or requires_untrusted_audit:
            return "untrusted_internal_tool_missing_audit"
        return "malformed_internal_tool_audit"
    return None


def _sanitize_internal_tool_event(event: object) -> dict:
    if not isinstance(event, dict):
        return {}
    sanitized = {}
    for field_name in (
        "tool_name",
        "tool_call_id",
        "task_id",
        "url",
        "url_sha256",
        "query_sha256",
        "content_sha256",
        "policy_version",
        "egress_decision",
    ):
        value = event.get(field_name)
        if isinstance(value, str):
            sanitized[field_name] = value
    content_chars = event.get("content_chars")
    if _is_non_negative_int(content_chars):
        sanitized["content_chars"] = content_chars
    duration_ms = event.get("duration_ms")
    if _is_non_negative_int(duration_ms):
        sanitized["duration_ms"] = duration_ms
    untrusted = event.get("untrusted")
    if isinstance(untrusted, bool):
        sanitized["untrusted"] = untrusted
    return sanitized


def _sanitize_hermes_memory_event(event: dict) -> dict:
    sanitized = {}
    for field_name in (
        "tool_call_id",
        "task_id",
        "session_id",
        "action",
        "target",
        "content_sha256",
        "old_text_sha256",
        "operations_sha256",
        "mutation_status",
        "memory_file_sha256",
        "memory_scope_sha256",
        "authorization_decision",
    ):
        value = event.get(field_name)
        if isinstance(value, str):
            sanitized[field_name] = value
    trusted_user_intent = sanitize_trusted_intent_ref(
        event.get("trusted_user_intent")
    )
    if trusted_user_intent:
        sanitized["trusted_user_intent"] = trusted_user_intent
    research_input_refs = sanitize_research_input_refs(
        event.get("research_input_refs")
    )
    if research_input_refs:
        sanitized["research_input_refs"] = research_input_refs
    if isinstance(event.get("untrusted_input_present"), bool):
        sanitized["untrusted_input_present"] = event["untrusted_input_present"]
    return sanitized


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _is_non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdefABCDEF" for character in value)


__all__ = [
    "RUNTIME_PROVENANCE_HISTORY_LIMIT",
    "TRACE_PROVENANCE_EVENT_LIMIT",
    "TRUSTED_INTENT_REF_VERSION",
    "build_trusted_user_intent_ref",
    "internal_tool_audit_issue",
    "sanitize_research_input_refs",
    "sanitize_trusted_intent_ref",
    "sanitize_hermes_memory_events",
    "sanitize_internal_tool_events",
    "trusted_user_intent_ref_matches",
]
