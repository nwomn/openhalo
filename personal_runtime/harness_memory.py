"""Runtime-owned memory contracts around the Hermes harness boundary."""

from __future__ import annotations

from enum import Enum


MEMORY_RETRIEVAL_LIMIT = 5


class MemoryKind(str, Enum):
    """Durable memory categories owned by the OpenHalo runtime."""

    PROCEDURAL = "procedural"
    SEMANTIC = "semantic"
    EPISODIC = "episodic"


def build_harness_memory_context(
    *,
    state,
    interaction_id: str,
    interaction_turn_id: str,
    working_memory: dict | None = None,
) -> dict:
    """Build bounded harness memory without persisting turn-local state."""

    memory = state.harness_memory
    return {
        "working": dict(working_memory or {}),
        "procedural": list(memory[MemoryKind.PROCEDURAL.value])[
            -MEMORY_RETRIEVAL_LIMIT:
        ],
        "semantic": list(memory[MemoryKind.SEMANTIC.value])[
            -MEMORY_RETRIEVAL_LIMIT:
        ],
        "episodic": list(memory[MemoryKind.EPISODIC.value])[
            -MEMORY_RETRIEVAL_LIMIT:
        ],
        "lineage": {
            "interaction_id": interaction_id,
            "interaction_turn_id": interaction_turn_id,
        },
    }


def build_memory_consolidation_candidate(
    *,
    harness_input,
    outcome,
    terminal_reason: str,
) -> dict:
    """Describe a possible durable-memory update without applying it."""

    return {
        "interaction_id": harness_input.interaction_id,
        "interaction_turn_id": harness_input.interaction_turn_id,
        "operation": harness_input.operation.value,
        "terminal_reason": terminal_reason,
        "outcome_intent": outcome.intent,
        "runner": outcome.metadata.get("runner"),
        "source_action_result": dict(harness_input.action_result or {}),
        "working_memory_summary": dict(harness_input.working_memory or {}),
        "review_status": "review_required",
        "memory_write_disposition": "candidate_only",
    }


__all__ = [
    "MemoryKind",
    "build_harness_memory_context",
    "build_memory_consolidation_candidate",
]
