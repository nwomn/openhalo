"""Safe chronological replay for M18 observation admission."""

from __future__ import annotations

from datetime import datetime

from personal_runtime.context_snapshot import build_context_snapshot_contract
from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.interaction_pool import InteractionPool
from personal_runtime.proactive_trigger_gate import ProactiveTriggerGate
from personal_runtime.runtime_state import RuntimeState


def replay_m18_state_history(payload: dict) -> dict:
    state = RuntimeState()
    interaction_pool = InteractionPool(state)
    trigger_gate = ProactiveTriggerGate()
    decisions = []

    for batch_index, observations in enumerate(_chronological_batches(payload)):
        decision_time = _batch_decision_time(observations)
        state.record_observations(observations)
        snapshot_contract = build_context_snapshot_contract(
            state.observations,
            snapshot_time=decision_time,
        )
        decision = trigger_gate.evaluate(
            observations=observations,
            snapshot_contract=snapshot_contract,
            state=state,
            current_time=decision_time,
        )
        trigger_gate.record_decision(
            state,
            decision,
            recorded_at=decision_time,
            observations=observations,
        )
        registration = None
        if decision.status == "trigger":
            registration = interaction_pool.register(
                origin="observation_driven",
                causal_scope=decision.causal_scope,
                trigger={
                    "reason_code": decision.reason_code,
                    "evidence_refs": decision.evidence_refs,
                    "observed_at": decision_time,
                },
                participant_device_ids=_participant_device_ids(
                    decision.primary_evidence_device_id,
                    decision.evidence_refs,
                ),
                source_device_id=decision.primary_evidence_device_id,
            )
        decisions.append(
            {
                "batch_index": batch_index,
                "source_event_id": observations[0].source_event_id,
                "observed_at": decision_time,
                "observation_count": len(observations),
                **decision.to_dict(),
                "interaction_id": (
                    registration.interaction.interaction_id
                    if registration is not None
                    else None
                ),
                "interaction_created": (
                    registration.created if registration is not None else False
                ),
            }
        )

    return {
        "action_dispatch_count": 0,
        "processed_observation_count": len(state.observations),
        "decision_counts": {
            status: sum(1 for decision in decisions if decision["status"] == status)
            for status in ("skip", "defer", "trigger")
        },
        "decisions": decisions,
        "interactions": list(state.interactions),
    }


def _chronological_batches(payload: dict) -> list[list[RuntimeObservation]]:
    indexed_observations = [
        (index, RuntimeObservation.from_dict(observation))
        for index, observation in enumerate(payload.get("observations", []))
        if isinstance(observation, dict)
    ]
    batches: dict[tuple[str, str], dict] = {}
    for index, observation in indexed_observations:
        source_event_id = observation.source_event_id or f"replay-index-{index}"
        batch_key = (observation.source_device_id, source_event_id)
        if batch_key not in batches:
            batches[batch_key] = {
                "first_index": index,
                "observations": [],
            }
        batches[batch_key]["observations"].append(observation)
    ordered_batches = sorted(
        batches.values(),
        key=lambda batch: (
            _timestamp_sort_key(_batch_decision_time(batch["observations"])),
            batch["first_index"],
        ),
    )
    return [batch["observations"] for batch in ordered_batches]


def _participant_device_ids(
    primary_device_id: str | None,
    evidence_refs: list[dict],
) -> list[str]:
    participant_device_ids = []
    for device_id in [
        primary_device_id,
        *(evidence_ref.get("source_device_id") for evidence_ref in evidence_refs),
    ]:
        if device_id is not None and device_id not in participant_device_ids:
            participant_device_ids.append(device_id)
    return participant_device_ids


def _batch_decision_time(observations: list[RuntimeObservation]) -> str:
    return max(
        (observation.observed_at for observation in observations),
        key=_timestamp_sort_key,
    )


def _timestamp_sort_key(timestamp: str) -> tuple[int, float]:
    try:
        return (0, datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp())
    except (AttributeError, TypeError, ValueError):
        return (1, 0.0)


__all__ = ["replay_m18_state_history"]
