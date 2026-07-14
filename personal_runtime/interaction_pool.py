"""Source-neutral interaction lifecycle records backed by runtime state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True, slots=True)
class InteractionRegistration:
    interaction: "InteractionRecord"
    created: bool


@dataclass(frozen=True, slots=True)
class InteractionTurn:
    interaction_turn_id: str
    request_id: str | None = None
    action_status: str = "resolved"

    def to_dict(self) -> dict:
        return {
            "interaction_turn_id": self.interaction_turn_id,
            "request_id": self.request_id,
            "action_status": self.action_status,
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
    turns: list[InteractionTurn] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "interaction_id": self.interaction_id,
            "origin": self.origin,
            "causal_scope": dict(self.causal_scope),
            "trigger": dict(self.trigger),
            "participant_device_ids": list(self.participant_device_ids),
            "source_device_id": self.source_device_id,
            "status": self.status,
            "turns": [turn.to_dict() for turn in self.turns],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "InteractionRecord":
        interaction_id = payload["interaction_id"]
        return cls(
            interaction_id=interaction_id,
            origin=payload.get("origin", "legacy"),
            causal_scope=dict(
                payload.get("causal_scope", {"key": f"legacy:{interaction_id}"})
            ),
            trigger=dict(payload.get("trigger", {})),
            participant_device_ids=list(payload.get("participant_device_ids", [])),
            source_device_id=payload.get("source_device_id"),
            status=payload.get("status", "planned"),
            turns=[
                InteractionTurn.from_dict(turn)
                for turn in payload.get("turns", [])
                if "interaction_turn_id" in turn
            ],
        )


class InteractionPool:
    def __init__(
        self,
        state,
        interaction_id_factory: Callable[[], str] | None = None,
        turn_limit: int = 20,
        max_pending_actions: int = 1,
    ) -> None:
        if turn_limit < 1:
            raise ValueError("turn_limit must be positive")
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
    ) -> InteractionRegistration:
        scope_key = causal_scope.get("key")
        if not isinstance(scope_key, str) or not scope_key:
            raise ValueError("causal_scope requires a non-empty key")
        existing = self._active_record_for_scope(causal_scope)
        if existing is not None:
            return InteractionRegistration(interaction=existing, created=False)

        participants = list(dict.fromkeys(participant_device_ids))
        record = InteractionRecord(
            interaction_id=self._allocate_interaction_id(),
            origin=origin,
            causal_scope=dict(causal_scope),
            trigger=dict(trigger),
            participant_device_ids=participants,
            source_device_id=source_device_id or (participants[0] if participants else None),
            status="planned",
        )
        self.state.interactions.append(record.to_dict())
        return InteractionRegistration(interaction=record, created=True)

    def get(self, interaction_id: str) -> InteractionRecord | None:
        payload = self._payload_for(interaction_id)
        return InteractionRecord.from_dict(payload) if payload is not None else None

    def complete(self, interaction_id: str) -> InteractionRecord:
        payload = self._payload_for(interaction_id)
        if payload is None:
            raise KeyError(f"unknown interaction: {interaction_id}")
        payload["status"] = "completed"
        return InteractionRecord.from_dict(payload)

    def record_turn(
        self,
        interaction_id: str,
        *,
        interaction_turn_id: str,
        request_id: str | None = None,
    ) -> InteractionTurn:
        payload = self._payload_for(interaction_id)
        if payload is None:
            raise KeyError(f"unknown interaction: {interaction_id}")
        if request_id is not None and self._pending_action_count(payload) >= self.max_pending_actions:
            raise ValueError("interaction already has a pending action")
        turn = InteractionTurn(
            interaction_turn_id=interaction_turn_id,
            request_id=request_id,
            action_status="pending" if request_id is not None else "resolved",
        )
        turns = list(payload.get("turns", []))
        turns.append(turn.to_dict())
        payload["turns"] = self._prune_turns(turns)
        return turn

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
                return InteractionRecord.from_dict(payload)
        return None

    def has_pending_action(self, interaction_id: str) -> bool:
        payload = self._payload_for(interaction_id)
        return payload is not None and self._pending_action_count(payload) > 0

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
        pending_indexes = [
            index
            for index, turn in enumerate(turns)
            if InteractionTurn.from_dict(turn).action_status == "pending"
        ]
        settled_indexes = [
            index for index in range(len(turns)) if index not in pending_indexes
        ]
        retained_indexes = set(pending_indexes)
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
