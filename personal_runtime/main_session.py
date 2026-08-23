"""Persistent identity and recovery policy for the singleton Main Hermes session."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from typing import Callable


@dataclass(frozen=True, slots=True)
class MainSession:
    session_id: str
    generation: int
    recovered: bool


class MainSessionManager:
    """Own session identity; callers own actual model invocation."""

    def __init__(
        self,
        *,
        state: dict,
        restore: Callable[[str], bool],
        create: Callable[[int], str],
    ) -> None:
        self._state = state
        self._restore = restore
        self._create = create

    def ensure_session(self) -> MainSession:
        session_id = self._state.get("session_id")
        generation = int(self._state.get("generation", 0))
        if isinstance(session_id, str) and session_id and self._restore(session_id):
            return MainSession(session_id=session_id, generation=generation, recovered=False)
        next_generation = generation + 1
        next_session_id = self._create(next_generation)
        if not isinstance(next_session_id, str) or not next_session_id:
            raise RuntimeError("Main session creation did not return an identity")
        audit = list(self._state.get("recovery_audit", []))
        audit.append(
            {
                "occurred_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "reason": "native_session_unavailable" if session_id else "initial_session",
                "prior_session_id": session_id,
                "session_id": next_session_id,
                "generation": next_generation,
            }
        )
        self._state.update(
            {
                "session_id": next_session_id,
                "generation": next_generation,
                "recovery_audit": audit[-32:],
            }
        )
        return MainSession(
            session_id=next_session_id,
            generation=next_generation,
            recovered=session_id is not None,
        )


__all__ = ["MainSession", "MainSessionManager"]
