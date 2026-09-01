"""Device-neutral materialized context facts for Runtime observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from typing import Iterable

from personal_runtime.context_contracts import RuntimeObservation


_DISPOSITIONS = {"full", "structural", "unavailable", "withheld"}
_SENSITIVE_STATES = {"blocked", "sensitive", "redacted"}
_HEALTH_ONLY_MODES = {"health_only", "blocked", "redacted"}


@dataclass(frozen=True, slots=True)
class ContextFact:
    fact_id: str
    source_device_id: str
    observation_name: str
    value: object
    confidence: float
    observed_at: str
    expires_at: str
    disposition: str
    provenance: dict
    version: int
    withheld_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "fact_id": self.fact_id,
            "source_device_id": self.source_device_id,
            "observation_name": self.observation_name,
            "value": self.value,
            "confidence": self.confidence,
            "observed_at": self.observed_at,
            "expires_at": self.expires_at,
            "disposition": self.disposition,
            "provenance": dict(self.provenance),
            "version": self.version,
            "withheld_reason": self.withheld_reason,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "ContextFact":
        return cls(
            fact_id=payload["fact_id"],
            source_device_id=payload["source_device_id"],
            observation_name=payload["observation_name"],
            value=payload["value"],
            confidence=float(payload["confidence"]),
            observed_at=payload["observed_at"],
            expires_at=payload["expires_at"],
            disposition=payload["disposition"],
            provenance=dict(payload["provenance"]),
            version=int(payload["version"]),
            withheld_reason=payload.get("withheld_reason"),
        )


class ContextFactStore:
    """In-memory latest-state index with no transport or model dependencies."""

    def __init__(self, facts: Iterable[ContextFact] = ()) -> None:
        self._facts = {fact.fact_id: fact for fact in facts}
        self._version = max((fact.version for fact in self._facts.values()), default=0)

    def all_facts(self) -> list[ContextFact]:
        return sorted(self._facts.values(), key=lambda fact: fact.fact_id)

    def materialize(
        self,
        observation: RuntimeObservation,
        *,
        freshness_seconds: int,
        schema_version: str | None = None,
        semantic_contract: dict | None = None,
    ) -> bool:
        if freshness_seconds < 1:
            raise ValueError("freshness_seconds must be positive")
        fact_id = f"{observation.source_device_id}/{observation.name}"
        existing = self._facts.get(fact_id)
        if existing is not None and _timestamp(observation.observed_at) <= _timestamp(existing.observed_at):
            return False
        disposition, value, withheld_reason = _safe_value(observation)
        self._version += 1
        self._facts[fact_id] = ContextFact(
            fact_id=fact_id,
            source_device_id=observation.source_device_id,
            observation_name=observation.name,
            value=value,
            confidence=observation.confidence,
            observed_at=observation.observed_at,
            expires_at=_format_timestamp(
                _timestamp(observation.observed_at) + timedelta(seconds=freshness_seconds)
            ),
            disposition=disposition,
            provenance={
                "source_capability": observation.source_capability,
                "source_event_id": observation.source_event_id,
                "schema_version": schema_version,
                "semantic_contract": dict(semantic_contract or {}),
            },
            version=self._version,
            withheld_reason=withheld_reason,
        )
        return True

    def query(self, *, now: str, fact_ids: list[str] | None = None) -> list[ContextFact]:
        selected = self.all_facts()
        if fact_ids is not None:
            wanted = set(fact_ids)
            selected = [fact for fact in selected if fact.fact_id in wanted]
        return [_view_at(fact, now) for fact in selected]


def _safe_value(observation: RuntimeObservation) -> tuple[str, object, str | None]:
    disposition = observation.context_disposition
    if disposition not in _DISPOSITIONS:
        raise ValueError("unsupported context_disposition")
    value = observation.value
    if disposition in {"unavailable", "withheld"}:
        return "structural", {"state": disposition}, disposition
    if isinstance(value, dict):
        sensitivity = str(value.get("sensitivity", "")).lower()
        capture_mode = str(value.get("capture_mode", "")).lower()
        if sensitivity in _SENSITIVE_STATES or capture_mode in _HEALTH_ONLY_MODES:
            return "structural", {"state": "withheld"}, "sensitive_or_health_only"
    return disposition, value, None


def _view_at(fact: ContextFact, now: str) -> ContextFact:
    if _timestamp(now) <= _timestamp(fact.expires_at):
        return fact
    return ContextFact(
        **{
            **fact.to_dict(),
            "value": {"state": "unknown"},
            "disposition": "unknown",
            "withheld_reason": "stale",
        }
    )


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


__all__ = ["ContextFact", "ContextFactStore"]
