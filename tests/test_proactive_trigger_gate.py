import unittest

from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.proactive_trigger_gate import ProactiveTriggerGate
from personal_runtime.runtime_state import RuntimeState


def observation(
    *,
    name: str,
    value,
    source_event_id: str,
    observed_at: str = "2026-07-13T09:59:30Z",
    source_device_id: str = "host-edge-1",
    source_capability: str = "runtime.health",
    parent_event_id: str | None = None,
    reentry_parent: dict | None = None,
) -> RuntimeObservation:
    return RuntimeObservation(
        name=name,
        value=value,
        source_device_id=source_device_id,
        source_capability=source_capability,
        source_event_id=source_event_id,
        observed_at=observed_at,
        confidence=1.0,
        parent_event_id=parent_event_id,
        reentry_parent=reentry_parent,
    )


class ProactiveTriggerGateTests(unittest.TestCase):
    current_time = "2026-07-13T10:00:00Z"

    def test_triggers_fresh_runtime_health_failure_with_safe_scope(self) -> None:
        decision = ProactiveTriggerGate().evaluate(
            observations=[
                observation(
                    name="runtime.health_state",
                    value="degraded",
                    source_event_id="health-event-1",
                )
            ],
            snapshot_contract={
                "fields": {
                    "runtime.current_health_state": {
                        "status": "fresh",
                        "value": "degraded",
                    }
                }
            },
            state=RuntimeState(),
            current_time=self.current_time,
        )

        self.assertEqual(decision.status, "trigger")
        self.assertEqual(decision.reason_code, "runtime_health_failure")
        self.assertEqual(decision.primary_evidence_device_id, "host-edge-1")
        self.assertEqual(
            decision.causal_scope["key"],
            "proactive:runtime_health_failure:host-edge-1:health-event-1",
        )
        self.assertEqual(
            decision.evidence_refs,
            [
                {
                    "source_device_id": "host-edge-1",
                    "source_event_id": "health-event-1",
                    "observation_name": "runtime.health_state",
                    "observed_at": "2026-07-13T09:59:30Z",
                }
            ],
        )

    def test_skips_causally_linked_observations(self) -> None:
        gate = ProactiveTriggerGate()
        contract = {
            "fields": {
                "runtime.current_health_state": {"status": "fresh"},
            }
        }

        for linked_observation in (
            observation(
                name="runtime.health_state",
                value="degraded",
                source_event_id="linked-parent-event",
                parent_event_id="parent-event-1",
            ),
            observation(
                name="runtime.health_state",
                value="degraded",
                source_event_id="linked-reentry-parent",
                reentry_parent={
                    "interaction_id": "interaction-1",
                    "interaction_turn_id": "interaction-turn-1",
                    "request_id": "action-1",
                },
            ),
        ):
            with self.subTest(source_event_id=linked_observation.source_event_id):
                decision = gate.evaluate(
                    observations=[linked_observation],
                    snapshot_contract=contract,
                    state=RuntimeState(),
                    current_time=self.current_time,
                )

                self.assertEqual(decision.status, "skip")
                self.assertEqual(
                    decision.reason_code,
                    "causally_linked_observation",
                )

    def test_skips_runtime_health_when_live_snapshot_contract_is_stale(self) -> None:
        decision = ProactiveTriggerGate().evaluate(
            observations=[
                observation(
                    name="runtime.health_state",
                    value="degraded",
                    source_event_id="health-event-stale-contract",
                )
            ],
            snapshot_contract={
                "fields": {
                    "runtime.current_health_state": {"status": "stale"},
                }
            },
            state=RuntimeState(),
            current_time=self.current_time,
        )

        self.assertEqual(decision.status, "skip")
        self.assertEqual(decision.reason_code, "stale_evidence")

    def test_failure_episode_coalesces_heartbeats_and_resets_after_recovery(
        self,
    ) -> None:
        gate = ProactiveTriggerGate(failure_cooldown_seconds=300)
        state = RuntimeState()

        def evaluate_and_record(item: RuntimeObservation, current_time: str):
            contract_field = (
                "runtime.current_health_state"
                if item.name == "runtime.health_state"
                else "runtime.current_process_present"
            )
            decision = gate.evaluate(
                observations=[item],
                snapshot_contract={
                    "fields": {contract_field: {"status": "fresh"}}
                },
                state=state,
                current_time=current_time,
            )
            gate.record_decision(
                state,
                decision,
                recorded_at=current_time,
                observations=[item],
            )
            return decision

        first_failure = evaluate_and_record(
            observation(
                name="runtime.health_state",
                value="degraded",
                source_event_id="health-episode-1",
                observed_at="2026-07-13T10:00:00Z",
            ),
            "2026-07-13T10:00:00Z",
        )
        repeated_failure = evaluate_and_record(
            observation(
                name="runtime.health_state",
                value="degraded",
                source_event_id="health-episode-2",
                observed_at="2026-07-13T10:01:00Z",
            ),
            "2026-07-13T10:01:00Z",
        )
        recovery = evaluate_and_record(
            observation(
                name="runtime.health_state",
                value="healthy",
                source_event_id="health-episode-3",
                observed_at="2026-07-13T10:02:00Z",
            ),
            "2026-07-13T10:02:00Z",
        )
        failure_after_recovery = evaluate_and_record(
            observation(
                name="runtime.health_state",
                value="degraded",
                source_event_id="health-episode-4",
                observed_at="2026-07-13T10:03:00Z",
            ),
            "2026-07-13T10:03:00Z",
        )

        restored_state = RuntimeState.from_dict(state.to_dict())
        persisted_gate = ProactiveTriggerGate(failure_cooldown_seconds=300)
        persisted_failure = persisted_gate.evaluate(
            observations=[
                observation(
                    name="runtime.health_state",
                    value="degraded",
                    source_event_id="health-episode-5",
                    observed_at="2026-07-13T10:04:00Z",
                )
            ],
            snapshot_contract={
                "fields": {
                    "runtime.current_health_state": {"status": "fresh"},
                }
            },
            state=restored_state,
            current_time="2026-07-13T10:04:00Z",
        )

        self.assertEqual(first_failure.status, "trigger")
        self.assertEqual(repeated_failure.status, "skip")
        self.assertEqual(
            repeated_failure.reason_code,
            "failure_cooldown_active",
        )
        self.assertEqual(recovery.status, "skip")
        self.assertEqual(failure_after_recovery.status, "trigger")
        self.assertEqual(persisted_failure.status, "skip")
        self.assertEqual(
            persisted_failure.reason_code,
            "failure_cooldown_active",
        )

    def test_skips_stale_unknown_sensitive_and_derived_evidence(self) -> None:
        gate = ProactiveTriggerGate()
        state = RuntimeState()
        stale = gate.evaluate(
            observations=[
                observation(
                    name="runtime.health_state",
                    value="degraded",
                    source_event_id="stale-health",
                    observed_at="2026-07-13T09:50:00Z",
                )
            ],
            snapshot_contract={},
            state=state,
            current_time=self.current_time,
        )
        sensitive = gate.evaluate(
            observations=[
                observation(
                    name="mobile.screen_context",
                    value={
                        "sensitivity": "blocked",
                        "visible_text_summary": "secret message",
                        "package_name": "com.example.private",
                    },
                    source_event_id="screen-event-1",
                    source_device_id="android-edge-1",
                    source_capability="mobile.screen_context",
                )
            ],
            snapshot_contract={},
            state=state,
            current_time=self.current_time,
        )
        unknown = gate.evaluate(
            observations=[
                observation(
                    name="runtime.health_state",
                    value="unknown",
                    source_event_id="unknown-health",
                )
            ],
            snapshot_contract={},
            state=state,
            current_time=self.current_time,
        )
        liveness = gate.evaluate(
            observations=[
                observation(
                    name="mobile.observation_liveness",
                    value="degraded",
                    source_event_id="liveness-event-1",
                    source_device_id="android-edge-1",
                    source_capability="runtime.mobile_liveness",
                )
            ],
            snapshot_contract={},
            state=state,
            current_time=self.current_time,
        )

        self.assertEqual(stale.reason_code, "stale_evidence")
        self.assertEqual(sensitive.reason_code, "sensitive_evidence")
        self.assertEqual(unknown.reason_code, "unknown_evidence")
        self.assertEqual(liveness.reason_code, "derived_liveness_evidence")
        self.assertNotIn("secret message", str(sensitive))
        self.assertNotIn("com.example.private", str(sensitive))

    def test_defers_fresh_non_sensitive_screen_context_without_raw_fingerprint(self) -> None:
        decision = ProactiveTriggerGate().evaluate(
            observations=[
                observation(
                    name="mobile.screen_context",
                    value={
                        "sensitivity": "normal",
                        "visible_text_summary": "meeting agenda",
                        "package_name": "com.example.calendar",
                    },
                    source_event_id="screen-event-2",
                    source_device_id="android-edge-1",
                    source_capability="mobile.screen_context",
                )
            ],
            snapshot_contract={},
            state=RuntimeState(),
            current_time=self.current_time,
        )

        self.assertEqual(decision.status, "defer")
        self.assertEqual(decision.reason_code, "screen_context_only")
        self.assertEqual(
            decision.causal_scope["key"],
            "proactive:screen_context_only:android-edge-1:screen-event-2",
        )
        self.assertNotIn("meeting agenda", str(decision))
        self.assertNotIn("com.example.calendar", str(decision))

    def test_exact_scope_coalesces_without_suppressing_a_different_reason(self) -> None:
        gate = ProactiveTriggerGate()
        state = RuntimeState()
        health = observation(
            name="runtime.health_state",
            value="degraded",
            source_event_id="combined-event-1",
        )
        first = gate.evaluate(
            observations=[health],
            snapshot_contract={},
            state=state,
            current_time=self.current_time,
        )
        gate.record_decision(state, first, recorded_at=self.current_time)
        duplicate = gate.evaluate(
            observations=[health],
            snapshot_contract={},
            state=state,
            current_time=self.current_time,
        )
        process_missing = gate.evaluate(
            observations=[
                observation(
                    name="runtime.process_present",
                    value=False,
                    source_event_id="combined-event-1",
                )
            ],
            snapshot_contract={},
            state=state,
            current_time=self.current_time,
        )

        self.assertEqual(first.status, "trigger")
        self.assertEqual(duplicate.status, "skip")
        self.assertEqual(duplicate.reason_code, "duplicate_evidence")
        self.assertEqual(process_missing.status, "trigger")
        self.assertEqual(process_missing.reason_code, "runtime_process_missing")
        self.assertNotEqual(first.causal_scope["key"], process_missing.causal_scope["key"])


if __name__ == "__main__":
    unittest.main()
