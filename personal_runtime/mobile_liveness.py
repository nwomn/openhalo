"""Runtime-side mobile observation liveness classification."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC
from datetime import datetime

from personal_runtime.runtime_state import RuntimeState

FRESH_FALLBACK_SECONDS = 60
STALE_AFTER_SECONDS = 300
UNAVAILABLE_AFTER_SECONDS = 900
WAKE_TTL_SECONDS = 120
WAKE_RATE_LIMIT_SECONDS = 300
SERVER_HEALTH_SUPPRESSION_SECONDS = 120

WakeTransport = Callable[[dict], dict | None]


def build_mobile_liveness_view(
    state: RuntimeState,
    online_device_ids: set[str] | None = None,
    current_time: str | None = None,
) -> dict:
    now = _parse_time(current_time) if current_time else datetime.now(UTC)
    online = online_device_ids or set()
    view = {}
    for device_id in _mobile_device_ids(state):
        latest_screen = _latest_observation(state, device_id, "mobile.screen_context")
        latest_health = _latest_observation(
            state,
            device_id,
            "mobile.screen_capture_health",
        )
        last_at = latest_screen.observed_at if latest_screen is not None else ""
        silence_seconds = _age_seconds(last_at, now) if last_at else None
        expected_active = _expected_active_observation(latest_health, latest_screen)
        stale_buffered_replay = _stale_buffered_replay(
            state,
            device_id,
            latest_screen.observed_at if latest_screen else "",
        )
        state_name = _classify_state(
            state=state,
            device_id=device_id,
            online=device_id in online,
            silence_seconds=silence_seconds,
            expected_active=expected_active,
            stale_buffered_replay=stale_buffered_replay,
            now=now,
        )
        last_attempt = _last_recovery_attempt(state, device_id)
        wake_suppression_reason = _wake_suppression_reason(state, now)
        view[device_id] = {
            "device_id": device_id,
            "state": state_name,
            "online": device_id in online,
            "expected_active_observation": expected_active,
            "last_screen_context_at": last_at,
            "last_health_at": latest_health.observed_at if latest_health else "",
            "silence_seconds": silence_seconds,
            "freshness_seconds": _freshness_seconds(state, device_id),
            "wake_recovery_eligible": _wake_recovery_eligible(
                state_name,
                online=device_id in online,
                expected_active=expected_active,
                wake_suppression_reason=wake_suppression_reason,
            ),
            "wake_suppression_reason": wake_suppression_reason,
            "stale_buffered_replay": stale_buffered_replay,
            "last_recovery_attempt": last_attempt,
        }
    return view


def update_mobile_liveness_after_observations(
    state: RuntimeState,
    device_id: str,
    online_device_ids: set[str] | None,
    current_time: str,
) -> dict:
    view = build_mobile_liveness_view(
        state,
        online_device_ids=online_device_ids,
        current_time=current_time,
    ).get(device_id)
    if view is None:
        return {}
    record = state.mobile_liveness.setdefault(device_id, {})
    record["last_view"] = view
    last_attempt = dict(record.get("last_recovery_attempt", {}))
    if last_attempt and view["state"] == "fresh":
        recovered_at = _fresh_recovery_observed_at(state, device_id, last_attempt)
        if recovered_at:
            last_attempt["recovery"] = {
                "status": "recovered",
                "recovered_at": recovered_at,
                "provenance": "fresh_mobile_observation_after_wake_request",
            }
            record["last_recovery_attempt"] = last_attempt
    elif last_attempt and view.get("stale_buffered_replay"):
        last_attempt["recovery"] = {
            "status": "stale_replay_ignored",
            "checked_at": current_time,
            "provenance": "screen_context_observed_before_wake_request",
        }
        record["last_recovery_attempt"] = last_attempt
    return view


def record_mobile_session_state(
    state: RuntimeState,
    device_id: str,
    status: str,
    observed_at: str,
) -> None:
    if device_id not in _mobile_device_ids(state):
        return
    state.mobile_liveness.setdefault(device_id, {})["last_session"] = {
        "status": status,
        "observed_at": observed_at,
    }


def request_mobile_wake_recovery(
    state: RuntimeState,
    device_id: str,
    current_time: str,
    online_device_ids: set[str] | None = None,
    configured: bool = False,
    wake_transport: WakeTransport | None = None,
) -> dict:
    view = build_mobile_liveness_view(
        state,
        online_device_ids=online_device_ids,
        current_time=current_time,
    ).get(device_id)
    if view is None:
        return {"device_id": device_id, "state": "unknown_device"}
    last_attempt = _last_recovery_attempt(state, device_id)
    now = _parse_time(current_time)
    if (
        last_attempt
        and _age_seconds(last_attempt.get("requested_at", ""), now)
        < WAKE_RATE_LIMIT_SECONDS
    ):
        return {
            "device_id": device_id,
            "state": "rate_limited",
            "last_recovery_attempt": last_attempt,
        }
    if not configured:
        return {"device_id": device_id, "state": "not_configured"}
    if view.get("wake_suppression_reason"):
        return {
            "device_id": device_id,
            "state": "suppressed",
            "reason": view["wake_suppression_reason"],
        }
    if not view["wake_recovery_eligible"]:
        return {"device_id": device_id, "state": "not_eligible"}

    attempt = {
        "attempt_id": f"wake-{device_id}-{_attempt_timestamp(now)}",
        "device_id": device_id,
        "state": "wake_requested",
        "requested_at": current_time,
        "ttl_seconds": WAKE_TTL_SECONDS,
        "transport": "mobile_push",
        "payload": {"reason": "mobile_observation_recovery"},
    }
    if wake_transport is None:
        attempt["dispatch_status"] = "audit_only"
    else:
        transport_result = wake_transport(attempt["payload"]) or {}
        attempt["dispatch_status"] = transport_result.get("status", "sent")
        attempt["transport_result"] = {
            key: value
            for key, value in transport_result.items()
            if key not in {"raw_screen_context", "visible_text_summary"}
        }
    state.mobile_liveness.setdefault(device_id, {})[
        "last_recovery_attempt"
    ] = attempt
    return attempt


def evaluate_mobile_liveness_recovery(
    state: RuntimeState,
    current_time: str,
    online_device_ids: set[str] | None = None,
    configured_device_ids: set[str] | None = None,
    wake_transports: dict[str, WakeTransport] | None = None,
) -> dict:
    configured = configured_device_ids or set()
    transports = wake_transports or {}
    view = build_mobile_liveness_view(
        state,
        online_device_ids=online_device_ids,
        current_time=current_time,
    )
    attempts = {}
    for device_id, payload in view.items():
        if not payload.get("wake_recovery_eligible"):
            continue
        attempts[device_id] = request_mobile_wake_recovery(
            state,
            device_id=device_id,
            current_time=current_time,
            online_device_ids=online_device_ids,
            configured=device_id in configured,
            wake_transport=transports.get(device_id),
        )
    return {
        "evaluated_at": current_time,
        "mobile_liveness": build_mobile_liveness_view(
            state,
            online_device_ids=online_device_ids,
            current_time=current_time,
        ),
        "recovery_attempts": attempts,
    }


def _mobile_device_ids(state: RuntimeState) -> list[str]:
    device_ids = set()
    for device_id, payload in state.devices.items():
        device_type = str(payload.get("device_type", "")).lower()
        capabilities = payload.get("capabilities", set())
        if (
            "android" in device_type
            or "phone" in device_type
            or "mobile" in device_type
            or "mobile.screen_context" in capabilities
            or "mobile.context" in capabilities
        ):
            device_ids.add(device_id)
    for device_id, payload in state.device_registry.items():
        device_type = str(payload.get("device_type", "")).lower()
        if (
            "android" in device_type
            or "phone" in device_type
            or "mobile" in device_type
        ):
            device_ids.add(device_id)
    return sorted(device_ids)


def _latest_observation(state: RuntimeState, device_id: str, name: str):
    matches = [
        observation
        for observation in state.observations
        if observation.source_device_id == device_id and observation.name == name
    ]
    if not matches:
        return None
    return max(matches, key=lambda observation: _parse_time(observation.observed_at))


def _expected_active_observation(health, screen) -> bool:
    if screen is not None:
        return True
    if health is None or not isinstance(health.value, dict):
        return False
    service_state = str(
        health.value.get("accessibility_service_state", "")
    ).lower()
    pause_reason = str(health.value.get("capture_pause_reason", "")).lower()
    return service_state in {"enabled", "running", "active"} and pause_reason in {
        "",
        "none",
        "not_paused",
        "active",
    }


def _classify_state(
    state: RuntimeState,
    device_id: str,
    online: bool,
    silence_seconds: int | None,
    expected_active: bool,
    stale_buffered_replay: bool,
    now: datetime,
) -> str:
    last_attempt = _last_recovery_attempt(state, device_id)
    if silence_seconds is None:
        return "unavailable"
    fresh_seconds = _freshness_seconds(state, device_id)
    if silence_seconds <= fresh_seconds:
        return "fresh"
    if last_attempt:
        age = _age_seconds(last_attempt.get("requested_at", ""), now)
        if age < int(last_attempt.get("ttl_seconds", WAKE_TTL_SECONDS)):
            if online and stale_buffered_replay:
                return "stale"
            return "wake_requested"
    if stale_buffered_replay:
        return "stale"
    if not expected_active:
        return "stale"
    if online and silence_seconds <= STALE_AFTER_SECONDS:
        return "degraded"
    if silence_seconds <= UNAVAILABLE_AFTER_SECONDS:
        return "stale"
    return "unavailable"


def _wake_recovery_eligible(
    state_name: str,
    online: bool,
    expected_active: bool,
    wake_suppression_reason: str,
) -> bool:
    return (
        expected_active
        and not online
        and not wake_suppression_reason
        and state_name in {"stale", "unavailable"}
    )


def _last_recovery_attempt(state: RuntimeState, device_id: str) -> dict:
    return dict(
        state.mobile_liveness.get(device_id, {}).get(
            "last_recovery_attempt",
            {},
        )
    )


def _freshness_seconds(state: RuntimeState, device_id: str) -> int:
    registrations = state.observation_registry.get(device_id, {}).get(
        "mobile.screen_context",
        {},
    )
    screen = registrations.get("mobile.screen_context", {})
    return int(screen.get("freshness_seconds", FRESH_FALLBACK_SECONDS))


def _wake_suppression_reason(state: RuntimeState, now: datetime) -> str:
    latest = _latest_observation(state, "host-edge-1", "runtime.health_state")
    for observation in state.observations:
        if observation.name != "runtime.health_state":
            continue
        if latest is None or _parse_time(observation.observed_at) > _parse_time(
            latest.observed_at
        ):
            latest = observation
    if latest is None:
        return ""
    if _age_seconds(latest.observed_at, now) > SERVER_HEALTH_SUPPRESSION_SECONDS:
        return ""
    if str(latest.value).lower() in {"degraded", "unhealthy", "down", "failed"}:
        return "server_or_network_unhealthy"
    return ""


def _stale_buffered_replay(
    state: RuntimeState,
    device_id: str,
    latest_screen_at: str,
) -> bool:
    last_attempt = _last_recovery_attempt(state, device_id)
    requested_at = last_attempt.get("requested_at", "")
    if not requested_at or not latest_screen_at:
        return False
    return _parse_time(latest_screen_at) < _parse_time(requested_at)


def _fresh_recovery_observed_at(
    state: RuntimeState,
    device_id: str,
    last_attempt: dict,
) -> str:
    requested_at = last_attempt.get("requested_at", "")
    if not requested_at:
        return ""
    observed_at_values = [
        observation.observed_at
        for observation in state.observations
        if observation.source_device_id == device_id
        and observation.name
        in {"mobile.screen_context", "mobile.screen_capture_health", "mobile.context"}
        and _parse_time(observation.observed_at) >= _parse_time(requested_at)
    ]
    if not observed_at_values:
        return ""
    return max(observed_at_values, key=_parse_time)


def _age_seconds(timestamp: str, now: datetime) -> int:
    if not timestamp:
        return 10**9
    return max(0, int((now - _parse_time(timestamp)).total_seconds()))


def _parse_time(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def _attempt_timestamp(timestamp: datetime) -> str:
    return timestamp.strftime("%Y%m%dT%H%M%SZ")
