"""Bounded model-facing projections of materialized Runtime context facts."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
import json

from personal_runtime.context_facts import ContextFact


@dataclass(frozen=True, slots=True)
class ContextEnvelope:
    context_version: int
    facts: list[dict]
    changed_facts: list[dict]
    fact_sources: list[str]
    uncertainty: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


class ContextEnvelopeCompiler:
    """Compile facts into a bounded, transport-neutral model projection."""

    def __init__(self, *, fact_limit: int = 32, byte_limit: int = 24 * 1024) -> None:
        if fact_limit < 1 or byte_limit < 1:
            raise ValueError("context envelope limits must be positive")
        self.fact_limit = fact_limit
        self.byte_limit = byte_limit

    def compile(
        self,
        *,
        facts: list[ContextFact],
        processed_version: int,
        now: str,
        interaction_projection: list[dict] | None = None,
    ) -> ContextEnvelope:
        del now
        ordered = sorted(
            facts,
            key=lambda fact: (fact.version > processed_version, fact.version),
            reverse=True,
        )
        selected: list[dict] = []
        used_bytes = 0
        for fact in ordered:
            payload = fact.to_dict()
            payload_bytes = len(json.dumps(payload, sort_keys=True).encode("utf-8"))
            if len(selected) >= self.fact_limit or used_bytes + payload_bytes > self.byte_limit:
                continue
            selected.append(payload)
            used_bytes += payload_bytes
        changed = [
            fact.to_dict()
            for fact in ordered
            if fact.version > processed_version
        ]
        uncertainty = [
            {
                "fact_id": fact.fact_id,
                "reason": fact.withheld_reason or fact.disposition,
                "disposition": fact.disposition,
            }
            for fact in ordered
            if fact.disposition != "full"
        ]
        if interaction_projection:
            uncertainty.extend(
                {
                    "interaction_id": item.get("interaction_id"),
                    "reason": "interaction_projection",
                }
                for item in interaction_projection
                if isinstance(item, dict)
            )
        return ContextEnvelope(
            context_version=max((fact.version for fact in facts), default=processed_version),
            facts=selected,
            changed_facts=changed,
            fact_sources=[fact.fact_id for fact in sorted(facts, key=lambda item: item.fact_id)],
            uncertainty=uncertainty,
        )


__all__ = ["ContextEnvelope", "ContextEnvelopeCompiler"]
