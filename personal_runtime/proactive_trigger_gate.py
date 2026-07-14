"""Deterministic admission for observation-driven proactive evaluation."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ProactiveTriggerDecision:
    status: str
    reason_code: str
    causal_scope: dict
    evidence_refs: list[dict]
    primary_evidence_device_id: str | None

    def to_dict(self) -> dict:
        return asdict(self)


class ProactiveTriggerGate:
    def __init__(
        self,
        freshness_seconds: int = 300,
        history_limit: int = 100,
        failure_cooldown_seconds: int = 300,
    ) -> None:
        self.freshness_seconds = freshness_seconds
        self.history_limit = history_limit
        self.failure_cooldown_seconds = failure_cooldown_seconds

    def evaluate(
        self,
        *,
        observations: list,
        snapshot_contract: dict,
        state,
        current_time: str,
    ) -> ProactiveTriggerDecision:
        deferred_decision = None
        skipped_decision = None
        for observation in self._ordered_observations(observations):
            decision = self._classify_observation(
                observation=observation,
                snapshot_contract=snapshot_contract,
                current_time=current_time,
            )
            if decision.status in {"trigger", "defer"} and self._was_recorded(
                state,
                decision.causal_scope["key"],
            ):
                decision = self._decision_for(
                    observation=observation,
                    status="skip",
                    reason_code="duplicate_evidence",
                )
            elif (
                decision.status == "trigger"
                and self._failure_cooldown_active(
                    state,
                    observation,
                    current_time,
                )
            ):
                decision = self._decision_for(
                    observation=observation,
                    status="skip",
                    reason_code="failure_cooldown_active",
                )
            if decision.status == "trigger":
                return decision
            if decision.status == "defer" and deferred_decision is None:
                deferred_decision = decision
            if decision.status == "skip" and skipped_decision is None:
                skipped_decision = decision
        if deferred_decision is not None:
            return deferred_decision
        if skipped_decision is not None:
            return skipped_decision
        return ProactiveTriggerDecision(
            status="skip",
            reason_code="no_evidence",
            causal_scope={"key": "proactive:no_evidence"},
            evidence_refs=[],
            primary_evidence_device_id=None,
        )

    def record_decision(
        self,
        state,
        decision: ProactiveTriggerDecision,
        *,
        recorded_at: str,
        observations: list | None = None,
    ) -> None:
        trigger_state = dict(getattr(state, "proactive_trigger_state", {}))
        recent = list(trigger_state.get("recent", []))
        recent.append(
            {
                "scope_key": decision.causal_scope["key"],
                "status": decision.status,
                "reason_code": decision.reason_code,
                "recorded_at": recorded_at,
            }
        )
        trigger_state["recent"] = recent[-self.history_limit :]
        failure_episodes = dict(trigger_state.get("failure_episodes", {}))
        for observation in observations or []:
            episode_key = self._failure_episode_key(observation)
            if episode_key is None:
                continue
            if self._is_failure_recovery(observation):
                failure_episodes.pop(episode_key, None)
                continue
            if not self._is_failure_observation(observation):
                continue
            if (
                decision.status == "trigger"
                and self._decision_matches_observation(decision, observation)
            ):
                failure_episodes[episode_key] = {
                    "value": self._normalized_value(observation.value),
                    "last_triggered_at": recorded_at,
                    "last_observed_at": recorded_at,
                }
                continue
            existing = failure_episodes.get(episode_key)
            if isinstance(existing, dict):
                failure_episodes[episode_key] = {
                    **existing,
                    "last_observed_at": recorded_at,
                }
        trigger_state["failure_episodes"] = self._bounded_failure_episodes(
            failure_episodes,
        )
        state.proactive_trigger_state = trigger_state

    def _classify_observation(
        self,
        *,
        observation,
        snapshot_contract: dict,
        current_time: str,
    ) -> ProactiveTriggerDecision:
        if (
            observation.parent_event_id is not None
            or observation.reentry_parent is not None
        ):
            return self._decision_for(
                observation=observation,
                status="skip",
                reason_code="causally_linked_observation",
            )
        if not self._is_fresh(observation.observed_at, current_time):
            return self._decision_for(
                observation=observation,
                status="skip",
                reason_code="stale_evidence",
            )
        contract_status = self._snapshot_status(
            snapshot_contract,
            observation.name,
        )
        if contract_status == "stale":
            return self._decision_for(
                observation=observation,
                status="skip",
                reason_code="stale_evidence",
            )
        if contract_status in {"missing", "ambiguous"}:
            return self._decision_for(
                observation=observation,
                status="skip",
                reason_code="unknown_evidence",
            )
        if observation.name == "mobile.observation_liveness":
            return self._decision_for(
                observation=observation,
                status="skip",
                reason_code="derived_liveness_evidence",
            )
        if observation.name == "mobile.screen_context":
            return self._screen_context_decision(observation)
        if self._is_unknown(observation.value):
            return self._decision_for(
                observation=observation,
                status="skip",
                reason_code="unknown_evidence",
            )
        if observation.name == "runtime.health_state":
            if self._normalized_value(observation.value) in {
                "degraded",
                "unhealthy",
                "down",
                "failed",
            }:
                return self._decision_for(
                    observation=observation,
                    status="trigger",
                    reason_code="runtime_health_failure",
                )
        if observation.name == "runtime.process_present":
            if self._normalized_value(observation.value) == "false":
                return self._decision_for(
                    observation=observation,
                    status="trigger",
                    reason_code="runtime_process_missing",
                )
        return self._decision_for(
            observation=observation,
            status="skip",
            reason_code="not_high_salience",
        )

    def _screen_context_decision(self, observation) -> ProactiveTriggerDecision:
        value = observation.value if isinstance(observation.value, dict) else {}
        sensitivity = self._normalized_value(value.get("sensitivity", "unknown"))
        capture_mode = self._normalized_value(value.get("capture_mode", ""))
        if sensitivity in {"unknown", "blocked", "sensitive", "redacted"}:
            return self._decision_for(
                observation=observation,
                status="skip",
                reason_code=(
                    "unknown_evidence" if sensitivity == "unknown" else "sensitive_evidence"
                ),
            )
        if capture_mode in {"health_only", "blocked", "redacted"}:
            return self._decision_for(
                observation=observation,
                status="skip",
                reason_code="sensitive_evidence",
            )
        return self._decision_for(
            observation=observation,
            status="defer",
            reason_code="screen_context_only",
        )

    def _decision_for(
        self,
        *,
        observation,
        status: str,
        reason_code: str,
    ) -> ProactiveTriggerDecision:
        evidence_ref = {
            "source_device_id": observation.source_device_id,
            "source_event_id": observation.source_event_id,
            "observation_name": observation.name,
            "observed_at": observation.observed_at,
        }
        scope_key = (
            f"proactive:{reason_code}:{observation.source_device_id}:"
            f"{observation.source_event_id}"
        )
        return ProactiveTriggerDecision(
            status=status,
            reason_code=reason_code,
            causal_scope={
                "key": scope_key,
                "provenance": {
                    "source_device_id": observation.source_device_id,
                    "source_capability": observation.source_capability,
                    "source_event_id": observation.source_event_id,
                },
                "evidence_refs": [evidence_ref],
            },
            evidence_refs=[evidence_ref],
            primary_evidence_device_id=observation.source_device_id,
        )

    def _was_recorded(self, state, scope_key: str) -> bool:
        recent = getattr(state, "proactive_trigger_state", {}).get("recent", [])
        return any(item.get("scope_key") == scope_key for item in recent)

    def _failure_cooldown_active(
        self,
        state,
        observation,
        current_time: str,
    ) -> bool:
        episode_key = self._failure_episode_key(observation)
        if episode_key is None:
            return False
        episodes = getattr(state, "proactive_trigger_state", {}).get(
            "failure_episodes",
            {},
        )
        episode = episodes.get(episode_key) if isinstance(episodes, dict) else None
        if not isinstance(episode, dict):
            return False
        if episode.get("value") != self._normalized_value(observation.value):
            return False
        last_triggered_at = episode.get("last_triggered_at")
        try:
            age_seconds = (
                self._to_epoch_seconds(current_time)
                - self._to_epoch_seconds(last_triggered_at)
            )
        except (TypeError, ValueError):
            return False
        return 0 <= age_seconds < self.failure_cooldown_seconds

    @staticmethod
    def _failure_episode_key(observation) -> str | None:
        if observation.name not in {
            "runtime.health_state",
            "runtime.process_present",
        }:
            return None
        return f"{observation.name}:{observation.source_device_id}"

    def _is_failure_observation(self, observation) -> bool:
        value = self._normalized_value(observation.value)
        return (
            observation.name == "runtime.health_state"
            and value in {"degraded", "unhealthy", "down", "failed"}
        ) or (
            observation.name == "runtime.process_present" and value == "false"
        )

    def _is_failure_recovery(self, observation) -> bool:
        value = self._normalized_value(observation.value)
        return (
            observation.name == "runtime.health_state" and value == "healthy"
        ) or (
            observation.name == "runtime.process_present" and value == "true"
        )

    @staticmethod
    def _decision_matches_observation(
        decision: ProactiveTriggerDecision,
        observation,
    ) -> bool:
        return any(
            evidence_ref.get("source_device_id") == observation.source_device_id
            and evidence_ref.get("source_event_id") == observation.source_event_id
            and evidence_ref.get("observation_name") == observation.name
            and evidence_ref.get("observed_at") == observation.observed_at
            for evidence_ref in decision.evidence_refs
        )

    def _bounded_failure_episodes(self, episodes: dict) -> dict:
        ordered = sorted(
            (
                (episode_key, episode)
                for episode_key, episode in episodes.items()
                if isinstance(episode, dict)
            ),
            key=lambda item: item[1].get("last_observed_at", ""),
        )
        return dict(ordered[-self.history_limit :])

    def _snapshot_status(self, snapshot_contract: dict, observation_name: str) -> str | None:
        field_name = {
            "runtime.health_state": "runtime.current_health_state",
            "runtime.process_present": "runtime.current_process_present",
        }.get(observation_name)
        if field_name is None:
            return None
        return snapshot_contract.get("fields", {}).get(field_name, {}).get("status")

    def _is_fresh(self, observed_at: str, current_time: str) -> bool:
        try:
            observed_epoch = self._to_epoch_seconds(observed_at)
            current_epoch = self._to_epoch_seconds(current_time)
        except (TypeError, ValueError):
            return False
        age_seconds = current_epoch - observed_epoch
        return 0 <= age_seconds <= self.freshness_seconds

    @staticmethod
    def _ordered_observations(observations: list) -> list:
        priority = {
            "runtime.health_state": 0,
            "runtime.process_present": 1,
            "mobile.screen_context": 2,
        }
        return sorted(
            observations,
            key=lambda observation: (
                priority.get(observation.name, 3),
                observation.source_device_id,
                observation.source_event_id,
                observation.name,
            ),
        )

    @staticmethod
    def _is_unknown(value) -> bool:
        return value is None or ProactiveTriggerGate._normalized_value(value) == "unknown"

    @staticmethod
    def _normalized_value(value) -> str:
        return str(value).strip().lower()

    @staticmethod
    def _to_epoch_seconds(timestamp: str) -> float:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
