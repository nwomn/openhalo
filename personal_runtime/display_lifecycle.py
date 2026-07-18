"""Safe, Runtime-owned interaction progress projection."""

from __future__ import annotations


SAFE_PROGRESS_PHASES = frozenset(
    {
        "deliberating",
        "researching",
        "planning",
        "executing",
        "awaiting_action_result",
        "completing",
        "completed",
        "failed",
        "cancelled",
    }
)

SAFE_PROGRESS_STATES = frozenset({"active", "settled"})
SAFE_PRESENTATION_HINTS = frozenset(
    {"working", "waiting", "completed", "failed", "cancelled"}
)


class DisplayLifecycle:
    """Reduce Runtime lifecycle transitions into a safe public projection."""

    def __init__(self) -> None:
        self._sequence_by_interaction: dict[str, int] = {}

    def advance(
        self,
        *,
        interaction_id: str,
        interaction_turn_id: str | None,
        phase: str,
        state: str,
        occurred_at: str,
        presentation_hint: str,
    ) -> dict:
        if phase not in SAFE_PROGRESS_PHASES:
            raise ValueError(f"unsupported progress phase: {phase!r}")
        if state not in SAFE_PROGRESS_STATES:
            raise ValueError(f"unsupported progress state: {state!r}")
        if not interaction_id:
            raise ValueError("interaction_id is required")
        if not occurred_at:
            raise ValueError("occurred_at is required")
        if not presentation_hint:
            raise ValueError("presentation_hint is required")
        if presentation_hint not in SAFE_PRESENTATION_HINTS:
            raise ValueError(
                f"unsupported presentation hint: {presentation_hint!r}"
            )

        sequence = self._sequence_by_interaction.get(interaction_id, 0) + 1
        self._sequence_by_interaction[interaction_id] = sequence
        return {
            "version": 1,
            "interaction_id": interaction_id,
            "interaction_turn_id": interaction_turn_id,
            "sequence": sequence,
            "phase": phase,
            "state": state,
            "occurred_at": occurred_at,
            "presentation_hint": presentation_hint,
        }

    def restore_sequence(self, interaction_id: str, sequence: object) -> None:
        """Restore a persisted safe sequence without accepting invalid state."""

        if isinstance(sequence, int) and sequence > 0:
            self._sequence_by_interaction[interaction_id] = max(
                self._sequence_by_interaction.get(interaction_id, 0),
                sequence,
            )
