"""Presence decision rules for the early runtime path."""

from dataclasses import asdict
from dataclasses import dataclass

from openhalo_common.diagnostics import DiagnosticBoundaryRecorder

@dataclass(slots=True)
class PresenceDecision:
    decision: str
    target_device_id: str | None
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


class PresenceRouter:
    def __init__(
        self,
        diagnostic_recorder=None,
        runtime_instance_id: str = "runtime-main",
        trace_recorder=None,
    ) -> None:
        self.diagnostics = DiagnosticBoundaryRecorder(
            recorder=diagnostic_recorder,
            side="runtime",
            runtime_instance_id=runtime_instance_id,
        )
        self.trace_recorder = trace_recorder

    def choose(
        self,
        source_device_id: str,
        snapshot: dict | None = None,
        proposal: dict | None = None,
        devices: dict | None = None,
        online_device_ids: set[str] | None = None,
        required_capability: str | None = None,
        intervention_history: list[dict] | None = None,
        now_timestamp: str | None = None,
        correlation: dict | None = None,
    ) -> PresenceDecision:
        input_payload = {
            "source_device_id": source_device_id,
            "required_capability": required_capability,
            "proposal_type": (proposal or {}).get("proposal_type"),
            "online_device_ids": sorted(online_device_ids or []),
        }
        with self.diagnostics.boundary(
            module="Presence Router",
            operation="choose_presence_decision",
            correlation=correlation or {},
            input_payload=input_payload,
            summary="Evaluated presence decision.",
        ) as boundary:
            decision = choose_presence_decision(
                source_device_id=source_device_id,
                snapshot=snapshot,
                proposal=proposal,
                devices=devices,
                online_device_ids=online_device_ids,
                required_capability=required_capability,
                intervention_history=intervention_history,
                now_timestamp=now_timestamp,
                trace_recorder=self.trace_recorder,
            )
            boundary.output(decision.to_dict())
            return decision


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

    target_device_id = None
    target_capability = required_capability or _proposal.get("action_capability")
    target_device_hint = _proposal.get("target_device_hint")
    terminal_target_locked = _terminal_target_locked(
        proposal=_proposal,
        devices=devices,
    )
    inactive_terminal_candidate = False
    if devices and target_capability:
        if (
            target_device_hint in devices
            and target_capability in devices[target_device_hint]["capabilities"]
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
                if _terminal_notification_candidate_is_inactive(
                    snapshot=snapshot,
                    proposal=_proposal,
                    device_id=device_id,
                    devices=devices,
                ):
                    inactive_terminal_candidate = True
                    continue
                if target_capability in payload["capabilities"]:
                    target_device_id = device_id
                    break

    if target_device_id is None:
        if inactive_terminal_candidate:
            decision = PresenceDecision(
                decision="suppress",
                target_device_id=None,
                reason="terminal_inactive",
            )
            _record_decision(decision, trace_recorder)
            return decision
        target_device_id = source_device_id

    if _terminal_notification_candidate_is_inactive(
        snapshot=snapshot,
        proposal=_proposal,
        device_id=target_device_id,
        devices=devices,
    ):
        decision = PresenceDecision(
            decision="suppress",
            target_device_id=None,
            reason="terminal_inactive",
        )
        _record_decision(decision, trace_recorder)
        return decision

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
    target_device_hint = proposal.get("target_device_hint")
    if not target_device_hint:
        return False
    return _terminal_notification_candidate_is_inactive(
        snapshot=snapshot,
        proposal=proposal,
        device_id=target_device_hint,
        devices=devices,
    )


def _terminal_notification_candidate_is_inactive(
    snapshot: dict,
    proposal: dict,
    device_id: str,
    devices: dict | None,
) -> bool:
    if not _is_proactive_proposal(proposal):
        return False
    if proposal.get("action_capability") != "notification.show":
        return False
    if not devices or device_id not in devices:
        return False
    target_device = devices[device_id]
    if "terminal.context" not in target_device.get("capabilities", set()):
        return False
    return snapshot.get("terminal.current_activity_state") != "active"


def _terminal_target_locked(
    proposal: dict,
    devices: dict | None,
) -> bool:
    if not _is_proactive_proposal(proposal):
        return False
    if proposal.get("action_capability") != "notification.show":
        return False
    target_device_hint = proposal.get("target_device_hint")
    if not target_device_hint or not devices or target_device_hint not in devices:
        return False
    target_device = devices[target_device_hint]
    return "terminal.context" in target_device.get("capabilities", set())


def _is_proactive_proposal(proposal: dict) -> bool:
    return proposal.get("source") in {"agent_initiative", "observation_driven"}


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
