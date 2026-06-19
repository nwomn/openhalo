"""Minimal agent proposal and reply generation for the early runtime path."""

from dataclasses import asdict
from dataclasses import dataclass


@dataclass(slots=True)
class InterventionProposal:
    kind: str
    action_capability: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def build_intervention_proposal(
    user_text: str,
    snapshot: dict | None = None,
    trace_recorder=None,
) -> InterventionProposal:
    _snapshot = snapshot or {}
    proposal = InterventionProposal(
        kind="notify",
        action_capability="notification.show",
        message=f"Runtime heard: {user_text}",
    )
    if trace_recorder is not None:
        trace_recorder.record(
            "AGENT",
            "built intervention proposal",
            kind=proposal.kind,
            action_capability=proposal.action_capability,
        )
    return proposal


def generate_reply(user_text: str, trace_recorder=None) -> str:
    reply = f"Runtime heard: {user_text}"
    if trace_recorder is not None:
        trace_recorder.record("AGENT", "generated reply", reply=reply)
    return reply
