"""Minimal agent proposal and reply generation for the early runtime path."""

from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path

from personal_runtime.model_provider import generate_text_reply_plan
from personal_runtime.action_layer import required_device_capability_for_action


@dataclass(slots=True)
class InterventionProposal:
    kind: str
    source: str
    action_capability: str
    required_capability: str
    action_payload: dict
    message: str
    metadata: dict
    target_device_hint: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def build_intervention_proposal(
    user_text: str,
    snapshot: dict | None = None,
    trace_recorder=None,
    config_path: Path | None = None,
) -> InterventionProposal:
    _snapshot = snapshot or {}
    reply_plan = generate_text_reply_plan(
        user_text=user_text,
        snapshot=_snapshot,
        profile_name="interactive_reply",
        config_path=config_path,
    )
    proposal = InterventionProposal(
        kind="notify",
        source="sense_first",
        action_capability="notification.show",
        required_capability=required_device_capability_for_action(
            "notification.show"
        ),
        action_payload={"message": reply_plan.message},
        message=user_text,
        metadata={
            "trigger": "text.input",
            "snapshot_fields": sorted(_snapshot.keys()),
            **reply_plan.metadata,
        },
    )
    if trace_recorder is not None:
        trace_recorder.record(
            "AGENT",
            "built intervention proposal",
            source=proposal.source,
            kind=proposal.kind,
            action_capability=proposal.action_capability,
        )
    return proposal


def build_agent_initiative_proposal(
    initiative_request: dict,
    snapshot: dict | None = None,
    trace_recorder=None,
) -> InterventionProposal:
    _snapshot = snapshot or {}
    action_capability = initiative_request["action_capability"]
    action_payload = dict(initiative_request.get("action_payload", {}))
    metadata = {
        key: value
        for key, value in initiative_request.items()
        if key
        not in {"action_capability", "action_payload", "target_device_hint"}
    }
    proposal = InterventionProposal(
        kind="runtime_control"
        if action_capability.startswith("runtime.")
        else "notify",
        source="agent_initiative",
        action_capability=action_capability,
        required_capability=required_device_capability_for_action(
            action_capability
        ),
        action_payload=action_payload,
        message=initiative_request.get("message", ""),
        metadata={
            **metadata,
            "snapshot_fields": sorted(_snapshot.keys()),
        },
        target_device_hint=initiative_request.get("target_device_hint"),
    )
    if trace_recorder is not None:
        trace_recorder.record(
            "AGENT",
            "built intervention proposal",
            source=proposal.source,
            kind=proposal.kind,
            action_capability=proposal.action_capability,
        )
    return proposal


def generate_reply(user_text: str, trace_recorder=None) -> str:
    reply = f"Runtime heard: {user_text}"
    if trace_recorder is not None:
        trace_recorder.record("AGENT", "generated reply", reply=reply)
    return reply
