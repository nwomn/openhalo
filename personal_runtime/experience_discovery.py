"""Validated, side-effect-free attention decisions for observation context."""

from __future__ import annotations

from dataclasses import dataclass


_STATUSES = {"skip", "defer", "observe_more", "trigger"}
_MAX_REFS = 16


@dataclass(frozen=True, slots=True)
class ExperienceDecision:
    status: str
    reason: str
    fact_ids: list[str]
    evidence_refs: list[str]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "fact_ids": list(self.fact_ids),
            "evidence_refs": list(self.evidence_refs),
        }


def validate_experience_decision(payload: object) -> ExperienceDecision:
    if not isinstance(payload, dict):
        raise ValueError("experience decision must be an object")
    status = payload.get("status")
    if status not in _STATUSES:
        raise ValueError("experience decision status is invalid")
    reason = payload.get("reason", "")
    if not isinstance(reason, str) or not reason:
        raise ValueError("experience decision requires a reason")
    fact_ids = _bounded_strings(payload.get("fact_ids", []))
    evidence_refs = _bounded_strings(payload.get("evidence_refs", []))
    if status == "observe_more" and not (fact_ids or evidence_refs):
        raise ValueError("observe_more requires bounded fact or evidence references")
    if status != "observe_more" and evidence_refs:
        raise ValueError("only observe_more may request evidence")
    return ExperienceDecision(
        status=status,
        reason=reason,
        fact_ids=fact_ids,
        evidence_refs=evidence_refs,
    )


def _bounded_strings(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > _MAX_REFS:
        raise ValueError("experience decision references must be bounded")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError("experience decision references must be non-empty strings")
    return list(value)


__all__ = ["ExperienceDecision", "validate_experience_decision"]
