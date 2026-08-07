"""Source-neutral interaction lifecycle records backed by runtime state."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Callable

from personal_runtime.context_contracts import RuntimeObservation


_CONTINUATION_POLICIES = {"one_shot", "until_settled", "until_verified"}
_TERMINAL_PHASES = {"completed", "failed", "cancelled", "expired"}
_RELATED_PROCESS_LIMIT = 4
_RELATED_PROCESS_SUMMARY_BYTES = 4096
_SUMMARY_STRING_LIMIT = 256
_SUMMARY_LIST_LIMIT = 8
_SUMMARY_MAP_LIMIT = 12
_SUMMARY_DEPTH_LIMIT = 3


@dataclass(frozen=True, slots=True)
class EventHypothesis:
    """Runtime-owned assessment of one observation against an active watch."""

    status: str
    observation_name: str
    source_event_id: str
    confidence: float
    evidence_ref: str | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def validate_continuation_intent(intent: object) -> dict:
    """Normalize a bounded model-proposed continuation contract."""

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
        normalized_watches.append(
            {
                key: watch[key]
                for key in (
                    "watch_id", "observation_names", "source_capability",
                    "source_device_id", "process_id", "requires_evidence",
                    "resolve_when",
                )
                if key in watch
            }
        )
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
                for key in (
                    "obligation_id", "kind", "success_condition", "failure_condition"
                )
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


@dataclass(frozen=True, slots=True)
class InteractionRegistration:
    interaction: "InteractionRecord"
    created: bool
    related_process_summaries: list[dict] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class InteractionTurn:
    interaction_turn_id: str
    request_id: str | None = None
    action_status: str = "resolved"
    action_batch_id: str | None = None
    action_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "interaction_turn_id": self.interaction_turn_id,
            "request_id": self.request_id,
            "action_status": self.action_status,
            "action_batch_id": self.action_batch_id,
            "action_id": self.action_id,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "InteractionTurn":
        return cls(
            interaction_turn_id=payload["interaction_turn_id"],
            request_id=payload.get("request_id"),
            action_status=payload.get(
                "action_status",
                "pending" if payload.get("request_id") is not None else "resolved",
            ),
            action_batch_id=payload.get(
                "action_batch_id",
                payload.get("interaction_turn_id")
                if payload.get("request_id") is not None
                else None,
            ),
            action_id=payload.get(
                "action_id",
                payload.get("request_id")
                if payload.get("request_id") is not None
                else None,
            ),
        )


@dataclass(frozen=True, slots=True)
class InteractionRecord:
    interaction_id: str
    origin: str
    causal_scope: dict
    trigger: dict
    participant_device_ids: list[str]
    source_device_id: str | None
    status: str
    initiator_kind: str = "legacy"
    requesting_device_id: str | None = None
    outcome_delivery_required: bool = False
    agent_session_id: str | None = None
    turns: list[InteractionTurn] = field(default_factory=list)
    lifecycle_phase: str = "planned"
    continuation_policy: str = "one_shot"
    objective: dict = field(default_factory=dict)
    watches: list[dict] = field(default_factory=list)
    obligations: list[dict] = field(default_factory=list)
    process_state: dict = field(default_factory=dict)
    health: dict = field(default_factory=lambda: {"state": "healthy"})
    lineage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "interaction_id": self.interaction_id,
            "origin": self.origin,
            "causal_scope": dict(self.causal_scope),
            "trigger": dict(self.trigger),
            "participant_device_ids": list(self.participant_device_ids),
            "source_device_id": self.source_device_id,
            "initiator_kind": self.initiator_kind,
            "requesting_device_id": self.requesting_device_id,
            "outcome_delivery_required": self.outcome_delivery_required,
            "agent_session_id": self.agent_session_id,
            "status": self.status,
            "turns": [turn.to_dict() for turn in self.turns],
            "lifecycle_phase": self.lifecycle_phase,
            "continuation_policy": self.continuation_policy,
            "objective": dict(self.objective),
            "watches": [dict(watch) for watch in self.watches],
            "obligations": [dict(obligation) for obligation in self.obligations],
            "process_state": dict(self.process_state),
            "health": dict(self.health),
            "lineage": dict(self.lineage),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "InteractionRecord":
        interaction_id = payload["interaction_id"]
        status = payload.get("status", "planned")
        continuation_policy = payload.get("continuation_policy", "one_shot")
        if continuation_policy not in _CONTINUATION_POLICIES:
            continuation_policy = "one_shot"
        lifecycle_phase = payload.get("lifecycle_phase")
        if not isinstance(lifecycle_phase, str) or not lifecycle_phase:
            lifecycle_phase = _phase_for_status(status)
        obligations = [
            _normalize_obligation(obligation)
            for obligation in payload.get("obligations", [])
            if isinstance(obligation, dict)
        ]
        return cls(
            interaction_id=interaction_id,
            origin=payload.get("origin", "legacy"),
            causal_scope=dict(
                payload.get("causal_scope", {"key": f"legacy:{interaction_id}"})
            ),
            trigger=dict(payload.get("trigger", {})),
            participant_device_ids=list(payload.get("participant_device_ids", [])),
            source_device_id=payload.get("source_device_id"),
            initiator_kind=payload.get("initiator_kind", "legacy"),
            requesting_device_id=payload.get("requesting_device_id"),
            outcome_delivery_required=bool(
                payload.get("outcome_delivery_required", False)
            ),
            agent_session_id=payload.get(
                "agent_session_id",
                f"openhalo-child:{interaction_id}",
            ),
            status=status,
            turns=[
                InteractionTurn.from_dict(turn)
                for turn in payload.get("turns", [])
                if "interaction_turn_id" in turn
            ],
            lifecycle_phase=lifecycle_phase,
            continuation_policy=continuation_policy,
            objective=dict(payload.get("objective", {})),
            watches=[
                dict(watch)
                for watch in payload.get("watches", [])
                if isinstance(watch, dict)
            ],
            obligations=obligations,
            process_state=dict(payload.get("process_state", {})),
            health=dict(payload.get("health", {"state": "healthy"})),
            lineage=dict(payload.get("lineage", {})),
        )


class InteractionPool:
    def __init__(
        self,
        state,
        interaction_id_factory: Callable[[], str] | None = None,
        turn_limit: int = 20,
        max_pending_actions: int | None = None,
    ) -> None:
        if turn_limit < 1:
            raise ValueError("turn_limit must be positive")
        if max_pending_actions is None:
            max_pending_actions = turn_limit
        if max_pending_actions < 1 or max_pending_actions > turn_limit:
            raise ValueError("max_pending_actions must be between one and turn_limit")
        self.state = state
        self._interaction_id_factory = interaction_id_factory
        self.turn_limit = turn_limit
        self.max_pending_actions = max_pending_actions

    def __len__(self) -> int:
        return len(self.state.interactions)

    def register(
        self,
        *,
        origin: str,
        causal_scope: dict,
        trigger: dict,
        participant_device_ids: list[str],
        source_device_id: str | None = None,
        initiator_kind: str = "legacy",
        requesting_device_id: str | None = None,
        outcome_delivery_required: bool = False,
        continuation_policy: str = "one_shot",
        objective: dict | None = None,
        watches: list[dict] | None = None,
        obligations: list[dict] | None = None,
        process_state: dict | None = None,
        health: dict | None = None,
        lineage: dict | None = None,
        process_id: str | None = None,
        process_source_capability: str | None = None,
    ) -> InteractionRegistration:
        scope_key = causal_scope.get("key")
        if not isinstance(scope_key, str) or not scope_key:
            raise ValueError("causal_scope requires a non-empty key")
        if continuation_policy not in _CONTINUATION_POLICIES:
            raise ValueError("unsupported continuation policy")
        existing = self._active_record_for_scope(causal_scope)
        if existing is not None:
            return InteractionRegistration(interaction=existing, created=False)

        participants = list(dict.fromkeys(participant_device_ids))
        resolved_source_device_id = source_device_id or (
            participants[0] if participants else None
        )
        related_process_summaries = self.related_process_summaries(
            source_device_id=resolved_source_device_id,
            process_id=process_id,
            source_capability=process_source_capability,
        )
        record_lineage = dict(lineage or {})
        if related_process_summaries:
            record_lineage["context_process_refs"] = [
                {
                    "interaction_id": summary["interaction_id"],
                    "process_state_version": summary["process_state_version"],
                }
                for summary in related_process_summaries
            ]
        interaction_id = self._allocate_interaction_id()
        record = InteractionRecord(
            interaction_id=interaction_id,
            origin=origin,
            causal_scope=dict(causal_scope),
            trigger=dict(trigger),
            participant_device_ids=participants,
            source_device_id=resolved_source_device_id,
            initiator_kind=initiator_kind,
            requesting_device_id=requesting_device_id,
            outcome_delivery_required=outcome_delivery_required,
            agent_session_id=f"openhalo-child:{interaction_id}",
            status="planned",
            lifecycle_phase="planned",
            continuation_policy=continuation_policy,
            objective=dict(objective or {}),
            watches=[_normalize_watch(watch) for watch in watches or []],
            obligations=[_normalize_obligation(obligation) for obligation in obligations or []],
            process_state=dict(process_state or {}),
            health={"state": "healthy", **dict(health or {})},
            lineage=record_lineage,
        )
        if hasattr(self.state, "record_interaction"):
            self.state.record_interaction(record.to_dict())
        else:
            self.state.interactions.append(record.to_dict())
        return InteractionRegistration(
            interaction=record,
            created=True,
            related_process_summaries=related_process_summaries,
        )

    def get(self, interaction_id: str) -> InteractionRecord | None:
        payload = self._payload_for(interaction_id)
        return InteractionRecord.from_dict(payload) if payload is not None else None

    def active_records(self) -> list[InteractionRecord]:
        return [
            InteractionRecord.from_dict(payload)
            for payload in self.state.interactions
            if payload.get("status") not in _TERMINAL_PHASES
        ]

    def related_process_summaries(
        self,
        *,
        source_device_id: str | None,
        limit: int = _RELATED_PROCESS_LIMIT,
        process_id: str | None = None,
        source_capability: str | None = None,
    ) -> list[dict]:
        """Return bounded authoritative process facts relevant to one source.

        This deliberately exposes summaries rather than raw records. The Pool
        remains the lifecycle authority and callers may only persist its stable
        ID/version references in a new Interaction's lineage.
        """

        if not source_device_id or limit < 1:
            return []
        summaries = []
        for payload in reversed(self.state.interactions):
            record = InteractionRecord.from_dict(payload)
            if record.source_device_id != source_device_id:
                continue
            if record.continuation_policy == "one_shot":
                continue
            if process_id and not self._record_matches_process_id(record, process_id):
                continue
            if source_capability and not self._record_matches_capability(
                record, source_capability
            ):
                continue
            summaries.append(self._process_summary(record))
            if len(summaries) >= limit:
                break
        return summaries

    @staticmethod
    def _process_summary(record: InteractionRecord) -> dict:
        process_state = dict(record.process_state)
        process_ids = {
            watch.get("process_id")
            for watch in record.watches
            if isinstance(watch.get("process_id"), str) and watch.get("process_id")
        }
        if isinstance(process_state.get("process_id"), str) and process_state["process_id"]:
            process_ids.add(process_state["process_id"])
        process_ids = sorted(process_ids)
        source_capabilities = {
            watch.get("source_capability")
            for watch in record.watches
            if isinstance(watch.get("source_capability"), str)
            and watch.get("source_capability")
        }
        if isinstance(process_state.get("source_capability"), str) and process_state["source_capability"]:
            source_capabilities.add(process_state["source_capability"])
        source_capabilities = sorted(source_capabilities)
        summary = {
            "interaction_id": record.interaction_id,
            "causal_scope_key": _bound_summary_value(record.causal_scope.get("key")),
            "objective": _bound_summary_value(record.objective),
            "status": record.status,
            "lifecycle_phase": record.lifecycle_phase,
            "last_observation": _bound_summary_value(
                process_state.get("last_observation", {})
            ),
            "last_progress_at": record.health.get("last_progress_at"),
            "health_state": record.health.get("state", "unknown"),
            "process_state_version": int(process_state.get("version", 0)),
        }
        if process_ids:
            summary["process_id"] = _bound_summary_value(
                process_ids[0] if len(process_ids) == 1 else process_ids
            )
        if source_capabilities:
            summary["source_capability"] = _bound_summary_value(
                source_capabilities[0]
                if len(source_capabilities) == 1
                else source_capabilities
            )
        return _fit_summary_bytes(summary)

    @staticmethod
    def _record_matches_process_id(record: InteractionRecord, process_id: str) -> bool:
        return record.process_state.get("process_id") == process_id or any(
            watch.get("process_id") == process_id for watch in record.watches
        )

    @staticmethod
    def _record_matches_capability(record: InteractionRecord, capability: str) -> bool:
        return record.process_state.get("source_capability") == capability or any(
            watch.get("source_capability") == capability for watch in record.watches
        )

    def apply_observations(
        self,
        observations: list[RuntimeObservation],
    ) -> list[InteractionRecord]:
        """Match normalized facts to persistent watches and update their state.

        This is lifecycle correlation only. The caller decides whether a match
        should reawaken Hermes and perform another deliberation turn.
        """

        matches = []
        seen_event_ids: set[tuple[str, str]] = set()
        for observation in observations:
            event_key = (observation.source_device_id, observation.source_event_id)
            if event_key in seen_event_ids:
                continue
            seen_event_ids.add(event_key)
            for interaction in self.active_records():
                watch = self._matching_watch(interaction, observation)
                if watch is None:
                    continue
                hypothesis = self._hypothesis(watch, observation)
                phase = (
                    "awaiting_evidence"
                    if hypothesis.status == "uncertain"
                    else "monitoring"
                )
                updated = self.update_process_state(
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
                if updated.lifecycle_phase in _TERMINAL_PHASES:
                    continue
                if self._watch_is_resolved(watch, observation):
                    self.resolve_watch(interaction.interaction_id, watch["watch_id"])
                self.transition(
                    interaction.interaction_id,
                    phase=phase,
                    status=phase,
                )
                matches.append(self.get(interaction.interaction_id))
        return [interaction for interaction in matches if interaction is not None]

    def reconcile_health(
        self,
        *,
        current_time: str,
        online_device_ids: set[str],
    ) -> list[InteractionRecord]:
        """Update process health from connection and observation freshness facts."""

        now = _parse_timestamp(current_time)
        updated = []
        for interaction in self.active_records():
            if interaction.continuation_policy == "one_shot":
                continue
            target_device_id = interaction.health.get("target_device_id")
            if target_device_id is None:
                target_device_id = next(
                    (
                        watch.get("source_device_id")
                        for watch in interaction.watches
                        if watch.get("source_device_id")
                    ),
                    None,
                )
            if not target_device_id:
                continue
            if target_device_id not in online_device_ids:
                reason, state = "edge_offline", "unreachable"
            else:
                last_observation = interaction.health.get("last_observation_at")
                if not isinstance(last_observation, str):
                    continue
                age = (now - _parse_timestamp(last_observation)).total_seconds()
                stale_after = float(interaction.health.get("stale_after_seconds", 300))
                if age <= stale_after:
                    reason, state = "fresh_observation", "healthy"
                else:
                    reason, state = "observation_timeout", "stale"
            if (
                interaction.health.get("state") == state
                and interaction.health.get("reason") == reason
            ):
                continue
            updated.append(
                self.update_process_state(
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
    def _matching_watch(
        interaction: InteractionRecord,
        observation: RuntimeObservation,
    ) -> dict | None:
        for watch in interaction.watches:
            if watch.get("status", "active") != "active":
                continue
            if observation.name not in watch.get("observation_names", []):
                continue
            if (
                watch.get("source_capability")
                and watch["source_capability"] != observation.source_capability
            ):
                continue
            if (
                watch.get("source_device_id")
                and watch["source_device_id"] != observation.source_device_id
            ):
                continue
            if watch.get("process_id") and watch["process_id"] != observation.process_id:
                continue
            return watch
        return None

    @staticmethod
    def _watch_is_resolved(
        watch: dict,
        observation: RuntimeObservation,
    ) -> bool:
        resolve_when = watch.get("resolve_when")
        if not isinstance(resolve_when, dict) or not isinstance(observation.value, dict):
            return False
        return bool(resolve_when) and all(
            observation.value.get(key)
            in (expected if isinstance(expected, list) else [expected])
            for key, expected in resolve_when.items()
        )

    @staticmethod
    def _hypothesis(watch: dict, observation: RuntimeObservation) -> EventHypothesis:
        requires_evidence = bool(watch.get("requires_evidence"))
        coverage = observation.coverage or {}
        if (requires_evidence and not observation.evidence_ref) or (
            coverage.get("capture_healthy", True) is not True
        ):
            status = "uncertain"
            reason = "additional evidence or healthy coverage required"
        else:
            status = "confirmed"
            reason = "observation matched active watch"
        return EventHypothesis(
            status=status,
            observation_name=observation.name,
            source_event_id=observation.source_event_id,
            confidence=observation.confidence,
            evidence_ref=observation.evidence_ref,
            reason=reason,
        )

    def complete(self, interaction_id: str) -> InteractionRecord:
        payload = self._payload_for(interaction_id)
        if payload is None:
            raise KeyError(f"unknown interaction: {interaction_id}")
        payload["status"] = "completed"
        payload["lifecycle_phase"] = "completed"
        self._mark_changed(payload)
        return InteractionRecord.from_dict(payload)

    def transition(
        self,
        interaction_id: str,
        *,
        phase: str,
        status: str | None = None,
        reason: str | None = None,
    ) -> InteractionRecord:
        payload = self._payload_for(interaction_id)
        if payload is None:
            raise KeyError(f"unknown interaction: {interaction_id}")
        if phase == "completed" and not self.can_complete(interaction_id):
            raise ValueError("interaction has unresolved continuation state")
        payload["lifecycle_phase"] = phase
        payload["status"] = status or phase
        if reason:
            process_state = dict(payload.get("process_state", {}))
            process_state["last_transition_reason"] = reason
            payload["process_state"] = process_state
        self._mark_changed(payload)
        return InteractionRecord.from_dict(payload)

    def update_process_state(
        self,
        interaction_id: str,
        *,
        updates: dict,
        health: dict | None = None,
    ) -> InteractionRecord:
        payload = self._payload_for(interaction_id)
        if payload is None:
            raise KeyError(f"unknown interaction: {interaction_id}")
        state = dict(payload.get("process_state", {}))
        state.update(updates)
        payload["process_state"] = state
        if health is not None:
            current_health = dict(payload.get("health", {}))
            current_health.update(health)
            payload["health"] = current_health
        self._mark_changed(payload)
        return InteractionRecord.from_dict(payload)

    def configure_continuation(
        self,
        interaction_id: str,
        contract: dict,
        *,
        target_device_id: str | None = None,
    ) -> InteractionRecord:
        payload = self._payload_for(interaction_id)
        if payload is None:
            raise KeyError(f"unknown interaction: {interaction_id}")
        if not isinstance(contract, dict):
            raise ValueError("continuation contract must be an object")
        policy = contract.get("continuation_policy", "until_settled")
        if policy not in _CONTINUATION_POLICIES or policy == "one_shot":
            raise ValueError("continuation contract requires a persistent policy")
        watches = list(payload.get("watches", []))
        known_watch_ids = {watch.get("watch_id") for watch in watches}
        for watch in contract.get("watches", []):
            normalized = _normalize_watch(watch)
            if normalized["watch_id"] not in known_watch_ids:
                watches.append(normalized)
                known_watch_ids.add(normalized["watch_id"])
        obligations = list(payload.get("obligations", []))
        known_obligation_ids = {
            obligation.get("obligation_id") for obligation in obligations
        }
        for obligation in contract.get("obligations", []):
            normalized = _normalize_obligation(obligation)
            if normalized["obligation_id"] not in known_obligation_ids:
                obligations.append(normalized)
                known_obligation_ids.add(normalized["obligation_id"])
        payload["continuation_policy"] = policy
        payload["watches"] = watches
        payload["obligations"] = obligations
        if isinstance(contract.get("objective"), dict):
            payload["objective"] = {**payload.get("objective", {}), **contract["objective"]}
        health = dict(payload.get("health", {}))
        if target_device_id:
            health["target_device_id"] = target_device_id
        health.update(dict(contract.get("health", {})))
        payload["health"] = health
        self._mark_changed(payload)
        return InteractionRecord.from_dict(payload)

    def add_watch(self, interaction_id: str, watch: dict) -> InteractionRecord:
        payload = self._payload_for(interaction_id)
        if payload is None:
            raise KeyError(f"unknown interaction: {interaction_id}")
        if not isinstance(watch, dict) or not watch.get("watch_id"):
            raise ValueError("watch requires a watch_id")
        watches = list(payload.get("watches", []))
        if any(item.get("watch_id") == watch["watch_id"] for item in watches):
            raise ValueError("watch_id already exists")
        watches.append(_normalize_watch(watch))
        payload["watches"] = watches
        self._mark_changed(payload)
        return InteractionRecord.from_dict(payload)

    def resolve_watch(self, interaction_id: str, watch_id: str) -> InteractionRecord:
        payload = self._payload_for(interaction_id)
        if payload is None:
            raise KeyError(f"unknown interaction: {interaction_id}")
        watches = list(payload.get("watches", []))
        for index, watch in enumerate(watches):
            if watch.get("watch_id") == watch_id:
                watches[index] = {**watch, "status": "resolved"}
                payload["watches"] = watches
                self._mark_changed(payload)
                return InteractionRecord.from_dict(payload)
        raise KeyError(f"unknown watch: {watch_id}")

    def add_obligation(self, interaction_id: str, obligation: dict) -> InteractionRecord:
        payload = self._payload_for(interaction_id)
        if payload is None:
            raise KeyError(f"unknown interaction: {interaction_id}")
        normalized = _normalize_obligation(obligation)
        obligations = list(payload.get("obligations", []))
        if any(item.get("obligation_id") == normalized["obligation_id"] for item in obligations):
            raise ValueError("obligation_id already exists")
        obligations.append(normalized)
        payload["obligations"] = obligations
        self._mark_changed(payload)
        return InteractionRecord.from_dict(payload)

    def resolve_obligation(
        self,
        interaction_id: str,
        obligation_id: str,
        *,
        result: dict | None = None,
    ) -> InteractionRecord:
        payload = self._payload_for(interaction_id)
        if payload is None:
            raise KeyError(f"unknown interaction: {interaction_id}")
        obligations = list(payload.get("obligations", []))
        for index, obligation in enumerate(obligations):
            if obligation.get("obligation_id") == obligation_id:
                obligations[index] = {
                    **obligation,
                    "status": "resolved",
                    "result": dict(result or {}),
                }
                payload["obligations"] = obligations
                self._mark_changed(payload)
                return InteractionRecord.from_dict(payload)
        raise KeyError(f"unknown obligation: {obligation_id}")

    def can_complete(self, interaction_id: str) -> bool:
        payload = self._payload_for(interaction_id)
        if payload is None:
            return False
        if self._pending_action_count(payload):
            return False
        if any(
            obligation.get("status", "pending") == "pending"
            for obligation in payload.get("obligations", [])
        ):
            return False
        if payload.get("continuation_policy") != "one_shot" and any(
            watch.get("status", "active") == "active"
            for watch in payload.get("watches", [])
        ):
            return False
        return True

    def mark_failed(self, interaction_id: str, *, reason: str) -> InteractionRecord:
        return self.transition(interaction_id, phase="failed", status="failed", reason=reason)

    def mark_cancelled(self, interaction_id: str, *, reason: str) -> InteractionRecord:
        return self.transition(interaction_id, phase="cancelled", status="cancelled", reason=reason)

    def mark_expired(self, interaction_id: str, *, reason: str) -> InteractionRecord:
        return self.transition(interaction_id, phase="expired", status="expired", reason=reason)

    def record_turn(
        self,
        interaction_id: str,
        *,
        interaction_turn_id: str,
        request_id: str | None = None,
    ) -> InteractionTurn:
        if request_id is not None:
            return self.record_action_batch(
                interaction_id,
                interaction_turn_id=interaction_turn_id,
                action_batch_id=interaction_turn_id,
                action_requests=[
                    (request_id, f"{interaction_turn_id}:{request_id}")
                ],
            )[0]
        payload = self._payload_for(interaction_id)
        if payload is None:
            raise KeyError(f"unknown interaction: {interaction_id}")
        turn = InteractionTurn(
            interaction_turn_id=interaction_turn_id,
        )
        turns = list(payload.get("turns", []))
        turns.append(turn.to_dict())
        payload["turns"] = self._prune_turns(turns)
        self._mark_changed(payload)
        return turn

    def record_action_batch(
        self,
        interaction_id: str,
        *,
        interaction_turn_id: str,
        action_batch_id: str,
        action_requests: list[tuple[str, str]],
    ) -> list[InteractionTurn]:
        """Atomically register the requests dispatched from one action batch."""

        payload = self._payload_for(interaction_id)
        if payload is None:
            raise KeyError(f"unknown interaction: {interaction_id}")
        if payload.get("status") == "completed":
            raise ValueError("interaction is already completed")
        if not isinstance(action_batch_id, str) or not action_batch_id:
            raise ValueError("action_batch_id must be a non-empty string")
        if not action_requests:
            raise ValueError("action batch requires at least one request")
        if len(action_requests) > self.max_pending_actions:
            raise ValueError("action batch exceeds pending action limit")
        if self._pending_action_count(payload):
            raise ValueError("interaction already has a pending action batch")

        existing_request_keys = {
            (turn.interaction_turn_id, turn.request_id)
            for turn in (
                InteractionTurn.from_dict(raw_turn)
                for raw_turn in payload.get("turns", [])
            )
            if turn.request_id is not None
        }
        existing_action_ids = {
            turn.action_id
            for turn in (
                InteractionTurn.from_dict(raw_turn)
                for raw_turn in payload.get("turns", [])
            )
            if turn.action_id is not None
        }
        request_ids = [request_id for request_id, _ in action_requests]
        action_ids = [action_id for _, action_id in action_requests]
        if (
            any(not isinstance(request_id, str) or not request_id for request_id in request_ids)
            or any(not isinstance(action_id, str) or not action_id for action_id in action_ids)
            or len(request_ids) != len(set(request_ids))
            or len(action_ids) != len(set(action_ids))
            or any(
                (interaction_turn_id, request_id) in existing_request_keys
                for request_id in request_ids
            )
            or any(action_id in existing_action_ids for action_id in action_ids)
        ):
            raise ValueError("action batch request and action IDs must be unique")

        turns = list(payload.get("turns", []))
        recorded_turns = [
            InteractionTurn(
                interaction_turn_id=interaction_turn_id,
                request_id=request_id,
                action_status="pending",
                action_batch_id=action_batch_id,
                action_id=action_id,
            )
            for request_id, action_id in action_requests
        ]
        turns.extend(turn.to_dict() for turn in recorded_turns)
        payload["turns"] = self._prune_turns(turns)
        payload["status"] = "awaiting_action_results"
        payload["lifecycle_phase"] = "awaiting_action_results"
        self._mark_changed(payload)
        return recorded_turns

    def get_for_action_result(
        self,
        interaction_id: str,
        interaction_turn_id: str,
        request_id: str,
    ) -> InteractionRecord | None:
        record = self.get(interaction_id)
        if record is None or record.status == "completed":
            return None
        if any(
            turn.interaction_turn_id == interaction_turn_id
            and turn.request_id == request_id
            and turn.action_status == "pending"
            for turn in record.turns
        ):
            return record
        return None

    def resolve_action_result(
        self,
        interaction_id: str,
        interaction_turn_id: str,
        request_id: str,
    ) -> InteractionRecord | None:
        payload = self._payload_for(interaction_id)
        if payload is None or payload.get("status") == "completed":
            return None
        turns = list(payload.get("turns", []))
        for index, turn in enumerate(turns):
            recorded_turn = InteractionTurn.from_dict(turn)
            if (
                recorded_turn.interaction_turn_id == interaction_turn_id
                and recorded_turn.request_id == request_id
                and recorded_turn.action_status == "pending"
            ):
                turns[index] = {**turn, "action_status": "resolved"}
                payload["turns"] = self._prune_turns(turns)
                if self._pending_action_count(payload) == 0:
                    status, phase = self._status_after_action_batch(payload)
                    payload["status"] = status
                    payload["lifecycle_phase"] = phase
                self._mark_changed(payload)
                return InteractionRecord.from_dict(payload)
        return None

    def has_pending_action(self, interaction_id: str) -> bool:
        payload = self._payload_for(interaction_id)
        return payload is not None and self._pending_action_count(payload) > 0

    def is_action_batch_settled(
        self,
        interaction_id: str,
        action_batch_id: str,
    ) -> bool:
        payload = self._payload_for(interaction_id)
        if payload is None:
            return False
        batch_turns = [
            InteractionTurn.from_dict(turn)
            for turn in payload.get("turns", [])
            if InteractionTurn.from_dict(turn).action_batch_id == action_batch_id
        ]
        return bool(batch_turns) and all(
            turn.action_status == "resolved" for turn in batch_turns
        )

    def action_batch_id_for_request(
        self,
        interaction_id: str,
        interaction_turn_id: str,
        request_id: str,
    ) -> str | None:
        payload = self._payload_for(interaction_id)
        if payload is None:
            return None
        for turn in payload.get("turns", []):
            recorded_turn = InteractionTurn.from_dict(turn)
            if (
                recorded_turn.interaction_turn_id == interaction_turn_id
                and recorded_turn.request_id == request_id
            ):
                return recorded_turn.action_batch_id
        return None

    def action_requests_for_batch(
        self,
        interaction_id: str,
        action_batch_id: str,
    ) -> list[InteractionTurn]:
        payload = self._payload_for(interaction_id)
        if payload is None:
            return []
        return [
            InteractionTurn.from_dict(turn)
            for turn in payload.get("turns", [])
            if InteractionTurn.from_dict(turn).action_batch_id == action_batch_id
        ]

    def _active_record_for_scope(self, causal_scope: dict) -> InteractionRecord | None:
        for payload in reversed(self.state.interactions):
            if payload.get("status") == "completed":
                continue
            if payload.get("causal_scope") == causal_scope:
                return InteractionRecord.from_dict(payload)
        return None

    def _allocate_interaction_id(self) -> str:
        if self._interaction_id_factory is not None:
            interaction_id = self._interaction_id_factory()
            if self._payload_for(interaction_id) is not None:
                raise ValueError(f"interaction_id already exists: {interaction_id}")
            return interaction_id

        return self.state.allocate_interaction_id()

    def _prune_turns(self, turns: list[dict]) -> list[dict]:
        parsed_turns = [InteractionTurn.from_dict(turn) for turn in turns]
        pending_indexes = [
            index
            for index, turn in enumerate(parsed_turns)
            if turn.action_status == "pending"
        ]
        pending_batch_ids = {
            parsed_turns[index].action_batch_id
            for index in pending_indexes
            if parsed_turns[index].action_batch_id is not None
        }
        batch_indexes = [
            index
            for index, turn in enumerate(parsed_turns)
            if turn.action_batch_id in pending_batch_ids
        ]
        settled_indexes = [
            index for index in range(len(turns)) if index not in batch_indexes
        ]
        retained_indexes = set(batch_indexes)
        retained_indexes.update(
            settled_indexes[-max(self.turn_limit - len(pending_indexes), 0) :]
        )
        return [
            turn for index, turn in enumerate(turns) if index in retained_indexes
        ]

    @staticmethod
    def _pending_action_count(payload: dict) -> int:
        return sum(
            1
            for turn in payload.get("turns", [])
            if InteractionTurn.from_dict(turn).action_status == "pending"
        )

    def _payload_for(self, interaction_id: str) -> dict | None:
        for payload in self.state.interactions:
            if payload.get("interaction_id") == interaction_id:
                return payload
        return None

    def _mark_changed(self, payload: dict) -> None:
        process_state = dict(payload.get("process_state", {}))
        process_state["version"] = int(process_state.get("version", 0)) + 1
        payload["process_state"] = process_state
        marker = getattr(self.state, "mark_interaction_changed", None)
        if marker is not None:
            marker(payload)

    def _status_after_action_batch(self, payload: dict) -> tuple[str, str]:
        if payload.get("continuation_policy") == "one_shot":
            return "planned", "planned"
        if any(
            obligation.get("status", "pending") == "pending"
            for obligation in payload.get("obligations", [])
        ):
            return "awaiting_verification", "awaiting_verification"
        if any(
            watch.get("status", "active") == "active"
            for watch in payload.get("watches", [])
        ):
            return "monitoring", "monitoring"
        return "planned", "planned"


def _phase_for_status(status: str) -> str:
    if status in {
        "planned",
        "awaiting_action_results",
        "monitoring",
        "awaiting_verification",
        "completed",
        "failed",
        "cancelled",
        "expired",
        "paused",
    }:
        return status
    return "planned"


def _bound_summary_value(value: object, *, depth: int = 0) -> object:
    """Keep Pool-owned prompt projections small and JSON-safe."""

    if depth >= _SUMMARY_DEPTH_LIMIT:
        return "[truncated]"
    if isinstance(value, str):
        return value[:_SUMMARY_STRING_LIMIT]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict):
        return {
            str(key)[:_SUMMARY_STRING_LIMIT]: _bound_summary_value(
                item, depth=depth + 1
            )
            for key, item in list(value.items())[:_SUMMARY_MAP_LIMIT]
        }
    if isinstance(value, (list, tuple)):
        return [
            _bound_summary_value(item, depth=depth + 1)
            for item in list(value)[:_SUMMARY_LIST_LIMIT]
        ]
    return str(value)[:_SUMMARY_STRING_LIMIT]


def _fit_summary_bytes(summary: dict) -> dict:
    """Enforce a final byte budget after field-level projection."""

    if len(json.dumps(summary, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= _RELATED_PROCESS_SUMMARY_BYTES:
        return summary
    compact = dict(summary)
    compact["objective"] = _bound_summary_value(
        {"summary": compact.get("objective", {}).get("summary", "")}
        if isinstance(compact.get("objective"), dict)
        else {}
    )
    compact["last_observation"] = _bound_summary_value(
        {"name": compact.get("last_observation", {}).get("name", "")}
        if isinstance(compact.get("last_observation"), dict)
        else {}
    )
    if len(json.dumps(compact, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > _RELATED_PROCESS_SUMMARY_BYTES:
        compact["objective"] = {}
        compact["last_observation"] = {}
    if len(json.dumps(compact, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > _RELATED_PROCESS_SUMMARY_BYTES:
        for key in ("causal_scope_key", "process_id", "source_capability"):
            compact.pop(key, None)
    return compact


def _normalize_obligation(obligation: dict) -> dict:
    normalized = dict(obligation)
    if not normalized.get("obligation_id"):
        raise ValueError("obligation requires an obligation_id")
    normalized.setdefault("status", "pending")
    return normalized


def _normalize_watch(watch: dict) -> dict:
    normalized = dict(watch)
    if not normalized.get("watch_id"):
        raise ValueError("watch requires a watch_id")
    names = normalized.get("observation_names")
    if not isinstance(names, list) or not all(isinstance(name, str) and name for name in names):
        raise ValueError("watch requires observation_names")
    normalized.setdefault("status", "active")
    return normalized


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def build_action_result_outcome_contract(
    interaction: dict | InteractionRecord | None,
    action_result: dict | None,
) -> dict:
    """Describe whether a settled action still owes its requester an outcome."""
    lineage = (
        interaction.to_dict()
        if isinstance(interaction, InteractionRecord)
        else dict(interaction or {})
    )
    result = dict(action_result or {})
    requesting_device_id = lineage.get("requesting_device_id")
    target_device_id = (lineage.get("primary_action") or {}).get(
        "target_device_id"
    )
    result_device_id = result.get("device_id")
    outcome_delivery_required = bool(lineage.get("outcome_delivery_required"))
    source_outcome_required = bool(
        lineage.get("initiator_kind") == "explicit_user_intent"
        and outcome_delivery_required
        and requesting_device_id
        and (target_device_id or result_device_id)
        and (target_device_id or result_device_id) != requesting_device_id
    )
    return {
        "initiator_kind": lineage.get("initiator_kind", "legacy"),
        "requesting_device_id": requesting_device_id,
        "outcome_delivery_required": outcome_delivery_required,
        "target_device_id": target_device_id,
        "result_device_id": result_device_id,
        "result_status": result.get("status"),
        "source_outcome_required": source_outcome_required,
    }
