"""Generic continuation matching for long-lived interactions."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import asdict
from datetime import datetime
from datetime import timezone

from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.interaction_pool import InteractionPool


@dataclass(frozen=True, slots=True)
class EventHypothesis:
    status: str
    observation_name: str
    source_event_id: str
    confidence: float
    evidence_ref: str | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def validate_continuation_intent(intent: object) -> dict:
    if intent is None:
        return {}
    if not isinstance(intent, dict):
        raise ValueError("continuation intent must be an object")
    mode = intent.get("mode")
    if mode not in {"until_settled", "until_verified"}:
        raise ValueError("continuation intent requires a persistent mode")
    watches = intent.get("watches", [])
    if not isinstance(watches, list) or len(watches) > 8:
        raise ValueError("continuation intent watches are bounded")
    normalized_watches = []
    for watch in watches:
        if not isinstance(watch, dict):
            raise ValueError("continuation watch must be an object")
        names = watch.get("observation_names")
        if (
            not isinstance(watch.get("watch_id"), str)
            or not watch["watch_id"]
            or not isinstance(names, list)
            or not names
            or len(names) > 16
            or not all(isinstance(name, str) and name for name in names)
        ):
            raise ValueError("continuation watch requires bounded observation_names")
        normalized = {
            key: watch[key]
            for key in (
                "watch_id",
                "observation_names",
                "source_capability",
                "source_device_id",
                "process_id",
                "requires_evidence",
                "resolve_when",
            )
            if key in watch
        }
        normalized_watches.append(normalized)
    obligations = intent.get("obligations", [])
    if not isinstance(obligations, list) or len(obligations) > 8:
        raise ValueError("continuation intent obligations are bounded")
    normalized_obligations = []
    for obligation in obligations:
        if not isinstance(obligation, dict) or not isinstance(
            obligation.get("obligation_id"), str
        ) or not isinstance(obligation.get("kind"), str):
            raise ValueError("continuation obligation requires id and kind")
        normalized_obligations.append(
            {
                key: obligation[key]
                for key in ("obligation_id", "kind", "success_condition", "failure_condition")
                if key in obligation
            }
        )
    return {
        "continuation_policy": mode,
        "objective": dict(intent.get("objective", {}))
        if isinstance(intent.get("objective"), dict)
        else {},
        "watches": normalized_watches,
        "obligations": normalized_obligations,
        "health": dict(intent.get("health", {}))
        if isinstance(intent.get("health"), dict)
        else {},
    }


class ContinuationRouter:
    """Match facts to active watches and persist bounded process state."""

    def __init__(self, interaction_pool: InteractionPool) -> None:
        self.interaction_pool = interaction_pool

    def apply_observations(
        self,
        observations: list[RuntimeObservation],
    ) -> list:
        matches = []
        seen_event_ids: set[tuple[str, str]] = set()
        for observation in observations:
            event_key = (observation.source_device_id, observation.source_event_id)
            if event_key in seen_event_ids:
                continue
            seen_event_ids.add(event_key)
            for interaction in self.interaction_pool.active_records():
                watch = self._matching_watch(interaction, observation)
                if watch is None:
                    continue
                hypothesis = self._hypothesis(watch, observation)
                phase = (
                    "awaiting_evidence"
                    if hypothesis.status == "uncertain"
                    else "monitoring"
                )
                updated = self.interaction_pool.update_process_state(
                    interaction.interaction_id,
                    updates={
                        "last_observation": {
                            "name": observation.name,
                            "source_event_id": observation.source_event_id,
                            "observed_at": observation.observed_at,
                        },
                        "last_hypothesis": hypothesis.to_dict(),
                    },
                    health={
                        "state": "healthy",
                        "last_observation_at": observation.observed_at,
                        "last_progress_at": observation.observed_at,
                    },
                )
                if updated.lifecycle_phase not in {"completed", "failed", "cancelled", "expired"}:
                    if self._watch_is_resolved(watch, observation):
                        updated = self.interaction_pool.resolve_watch(
                            interaction.interaction_id,
                            watch["watch_id"],
                        )
                    self.interaction_pool.transition(
                        interaction.interaction_id,
                        phase=phase,
                        status=phase,
                    )
                    matches.append(self.interaction_pool.get(interaction.interaction_id))
        return matches

    @staticmethod
    def _watch_is_resolved(watch: dict, observation: RuntimeObservation) -> bool:
        resolve_when = watch.get("resolve_when")
        if not isinstance(resolve_when, dict) or not isinstance(observation.value, dict):
            return False
        for key, expected in resolve_when.items():
            values = expected if isinstance(expected, list) else [expected]
            if observation.value.get(key) not in values:
                return False
        return bool(resolve_when)

    def reconcile_health(
        self,
        *,
        current_time: str,
        online_device_ids: set[str],
    ) -> list:
        now = _parse_timestamp(current_time)
        updated = []
        for interaction in self.interaction_pool.active_records():
            if interaction.continuation_policy == "one_shot":
                continue
            target_device_id = interaction.health.get("target_device_id")
            if target_device_id is None:
                for watch in interaction.watches:
                    target_device_id = watch.get("source_device_id")
                    if target_device_id:
                        break
            if not target_device_id:
                continue
            if target_device_id not in online_device_ids:
                reason = "edge_offline"
                state = "unreachable"
            else:
                last_observation = interaction.health.get("last_observation_at")
                if not isinstance(last_observation, str):
                    continue
                age = (now - _parse_timestamp(last_observation)).total_seconds()
                stale_after = float(interaction.health.get("stale_after_seconds", 300))
                if age <= stale_after:
                    state = "healthy"
                    reason = "fresh_observation"
                else:
                    state = "stale"
                    reason = "observation_timeout"
            if interaction.health.get("state") == state and interaction.health.get("reason") == reason:
                continue
            updated.append(
                self.interaction_pool.update_process_state(
                    interaction.interaction_id,
                    updates={
                        "last_health_change": {
                            "state": state,
                            "reason": reason,
                            "observed_at": current_time,
                        }
                    },
                    health={
                        "state": state,
                        "reason": reason,
                        "target_device_id": target_device_id,
                        "last_health_check_at": current_time,
                    },
                )
            )
        return updated

    @staticmethod
    def _matching_watch(interaction, observation: RuntimeObservation) -> dict | None:
        for watch in interaction.watches:
            if watch.get("status", "active") != "active":
                continue
            names = watch.get("observation_names", [])
            if observation.name not in names:
                continue
            source_capability = watch.get("source_capability")
            if source_capability and source_capability != observation.source_capability:
                continue
            source_device_id = watch.get("source_device_id")
            if source_device_id and source_device_id != observation.source_device_id:
                continue
            process_id = watch.get("process_id")
            if process_id and process_id != observation.process_id:
                continue
            return watch
        return None

    @staticmethod
    def _hypothesis(watch: dict, observation: RuntimeObservation) -> EventHypothesis:
        requires_evidence = bool(watch.get("requires_evidence"))
        has_evidence = bool(observation.evidence_ref)
        coverage = observation.coverage or {}
        coverage_healthy = coverage.get("capture_healthy", True) is True
        status = "confirmed"
        reason = "observation matched active watch"
        if (requires_evidence and not has_evidence) or not coverage_healthy:
            status = "uncertain"
            reason = "additional evidence or healthy coverage required"
        return EventHypothesis(
            status=status,
            observation_name=observation.name,
            source_event_id=observation.source_event_id,
            confidence=observation.confidence,
            evidence_ref=observation.evidence_ref,
            reason=reason,
        )


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


__all__ = ["ContinuationRouter", "EventHypothesis", "validate_continuation_intent"]
