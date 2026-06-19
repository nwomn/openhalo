"""Presence decision rules for the early runtime path."""

from dataclasses import asdict
from dataclasses import dataclass


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
    required_capability: str | None = None,
    trace_recorder=None,
) -> str:
    return choose_presence_decision(
        source_device_id=source_device_id,
        devices=devices,
        required_capability=required_capability,
        trace_recorder=trace_recorder,
    ).target_device_id or source_device_id


def choose_presence_decision(
    source_device_id: str,
    snapshot: dict | None = None,
    proposal: dict | None = None,
    devices: dict | None = None,
    required_capability: str | None = None,
    intervention_history: list[dict] | None = None,
    now_timestamp: str | None = None,
    trace_recorder=None,
) -> PresenceDecision:
    snapshot = snapshot or {}
    _proposal = proposal or {}
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
    if devices and target_capability:
        for device_id, payload in devices.items():
            if device_id == source_device_id:
                continue
            if target_capability in payload["capabilities"]:
                target_device_id = device_id
                break

    decision = PresenceDecision(
        decision="allow",
        target_device_id=target_device_id,
        reason="context_clear",
    )
    _record_decision(decision, trace_recorder)
    return decision


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
) -> bool:
    if (
        not intervention_history
        or now_timestamp is None
        or now_timestamp == ""
    ):
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


def _to_epoch_minutes(timestamp: str) -> int:
    date_part, time_part = timestamp.rstrip("Z").split("T", maxsplit=1)
    year, month, day = (int(part) for part in date_part.split("-"))
    hour, minute, _second = (int(part) for part in time_part.split(":"))
    return (((year * 12 + month) * 31 + day) * 24 + hour) * 60 + minute
