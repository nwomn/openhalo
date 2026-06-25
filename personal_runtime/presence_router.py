"""Presence decision rules for the early runtime path."""

from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime


COOLDOWN_MINUTES = 5


@dataclass(slots=True)
class PresenceDecision:
    decision: str
    target_device_id: str | None
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def choose_response_device(
    source_device_id: str,
    devices: dict | None = None,
    online_device_ids: set[str] | None = None,
    required_capability: str | None = None,
    trace_recorder=None,
) -> str:
    return choose_presence_decision(
        source_device_id=source_device_id,
        devices=devices,
        online_device_ids=online_device_ids,
        required_capability=required_capability,
        trace_recorder=trace_recorder,
    ).target_device_id or source_device_id


def choose_presence_decision(
    source_device_id: str,
    snapshot: dict | None = None,
    proposal: dict | None = None,
    devices: dict | None = None,
    online_device_ids: set[str] | None = None,
    required_capability: str | None = None,
    intervention_history: list[dict] | None = None,
    now_timestamp: str | None = None,
    trace_recorder=None,
) -> PresenceDecision:
    snapshot = snapshot or {}
    _proposal = proposal or {}
    if _terminal_push_suppressed(
        snapshot=snapshot,
        proposal=_proposal,
        devices=devices,
    ):
        decision = PresenceDecision(
            decision="suppress",
            target_device_id=None,
            reason="terminal_inactive",
        )
        _record_decision(decision, trace_recorder)
        return decision

    if snapshot.get("user.current_location") == "ambiguous":
        decision = PresenceDecision(
            decision="suppress",
            target_device_id=None,
            reason="context_ambiguous",
        )
        _record_decision(decision, trace_recorder)
        return decision

    if _cooldown_active(
        intervention_history=intervention_history or [],
        now_timestamp=now_timestamp,
        proposal=_proposal,
    ):
        decision = PresenceDecision(
            decision="suppress",
            target_device_id=None,
            reason="cooldown_active",
        )
        _record_decision(decision, trace_recorder)
        return decision

    target_device_id = source_device_id
    target_capability = required_capability or _proposal.get("action_capability")
    target_device_hint = _proposal.get("target_device_hint")
    terminal_target_locked = _terminal_target_locked(
        proposal=_proposal,
        devices=devices,
    )
    if devices and target_capability:
        if (
            target_device_hint in devices
            and target_capability in devices[target_device_hint]["capabilities"]
            and (
                online_device_ids is None
                or target_device_hint in online_device_ids
            )
        ):
            target_device_id = target_device_hint
        elif not terminal_target_locked:
            for device_id, payload in devices.items():
                if device_id == source_device_id:
                    continue
                if (
                    online_device_ids is not None
                    and device_id not in online_device_ids
                ):
                    continue
                if target_capability in payload["capabilities"]:
                    target_device_id = device_id
                    break

    if terminal_target_locked and target_device_id != target_device_hint:
        decision = PresenceDecision(
            decision="suppress",
            target_device_id=None,
            reason="terminal_unavailable",
        )
        _record_decision(decision, trace_recorder)
        return decision

    decision = PresenceDecision(
        decision="allow",
        target_device_id=target_device_id,
        reason="context_clear",
    )
    _record_decision(decision, trace_recorder)
    return decision


def _terminal_push_suppressed(
    snapshot: dict,
    proposal: dict,
    devices: dict | None,
) -> bool:
    if proposal.get("source") != "agent_initiative":
        return False
    if proposal.get("action_capability") != "notification.show":
        return False
    target_device_hint = proposal.get("target_device_hint")
    if not target_device_hint or not devices or target_device_hint not in devices:
        return False
    target_device = devices[target_device_hint]
    if "terminal.context" not in target_device.get("capabilities", set()):
        return False
    return snapshot.get("terminal.current_activity_state") != "active"


def _terminal_target_locked(
    proposal: dict,
    devices: dict | None,
) -> bool:
    if proposal.get("source") != "agent_initiative":
        return False
    if proposal.get("action_capability") != "notification.show":
        return False
    target_device_hint = proposal.get("target_device_hint")
    if not target_device_hint or not devices or target_device_hint not in devices:
        return False
    target_device = devices[target_device_hint]
    return "terminal.context" in target_device.get("capabilities", set())


def _record_decision(decision: PresenceDecision, trace_recorder) -> None:
    if trace_recorder is None:
        return
    trace_recorder.record(
        "PRESENCE",
        "evaluated intervention",
        decision=decision.decision,
        target_device_id=decision.target_device_id or "none",
        reason=decision.reason,
    )
    if decision.target_device_id is not None:
        trace_recorder.record(
            "PRESENCE",
            "selected target device",
            target_device_id=decision.target_device_id,
        )


def _cooldown_active(
    intervention_history: list[dict],
    now_timestamp: str | None,
    proposal: dict | None = None,
) -> bool:
    if (
        not intervention_history
        or now_timestamp is None
        or now_timestamp == ""
    ):
        return False
    if _is_explicit_user_text_proposal(proposal or {}):
        return False
    last_allowed = next(
        (
            intervention
            for intervention in reversed(intervention_history)
            if intervention.get("decision") == "allow"
            and intervention.get("recorded_at")
        ),
        None,
    )
    if last_allowed is None:
        return False
    return (
        abs(
            _to_epoch_minutes(now_timestamp)
            - _to_epoch_minutes(last_allowed["recorded_at"])
        )
        < COOLDOWN_MINUTES
    )


def _is_explicit_user_text_proposal(proposal: dict) -> bool:
    metadata = proposal.get("metadata", {})
    return (
        proposal.get("source") == "sense_first"
        and metadata.get("trigger") == "text.input"
    )


def _to_epoch_minutes(timestamp: str) -> int:
    normalized = timestamp.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return (((parsed.year * 12 + parsed.month) * 31 + parsed.day) * 24 + parsed.hour) * 60 + parsed.minute
