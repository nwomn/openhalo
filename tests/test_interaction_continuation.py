from __future__ import annotations

import unittest

from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.interaction_pool import InteractionPool
from personal_runtime.runtime_state import RuntimeState


class InteractionPoolContinuationTests(unittest.TestCase):
    def observation(self, *, name: str, value, evidence_ref: str | None = None):
        return RuntimeObservation(
            name=name,
            value=value,
            source_device_id="edge-1",
            source_capability="process.activity",
            source_event_id="event-1",
            observed_at="2026-08-06T10:00:00Z",
            confidence=0.9,
            evidence_ref=evidence_ref,
        )

    def test_matches_base_fact_without_requiring_a_candidate_event(self) -> None:
        pool = InteractionPool(RuntimeState())
        interaction = pool.register(
            origin="user_event",
            causal_scope={"key": "watch-base-fact"},
            trigger={"event_id": "request-1"},
            participant_device_ids=["edge-1"],
            continuation_policy="until_verified",
            watches=[
                {
                    "watch_id": "watch-1",
                    "observation_names": ["ambient.scene_features"],
                }
            ],
        ).interaction

        result = pool.apply_observations(
            [self.observation(name="ambient.scene_features", value={"steam": 0.8})]
        )

        self.assertEqual([interaction.interaction_id], [item.interaction_id for item in result])
        updated = pool.get(interaction.interaction_id)
        self.assertEqual(2, updated.process_state["version"])
        self.assertEqual("confirmed", updated.process_state["last_hypothesis"]["status"])

    def test_inconclusive_watch_enters_awaiting_evidence_without_negative_conclusion(self) -> None:
        pool = InteractionPool(RuntimeState())
        interaction = pool.register(
            origin="user_event",
            causal_scope={"key": "watch-evidence"},
            trigger={"event_id": "request-2"},
            participant_device_ids=["edge-1"],
            continuation_policy="until_verified",
            watches=[
                {
                    "watch_id": "watch-1",
                    "observation_names": ["ambient.scene_features"],
                    "requires_evidence": True,
                }
            ],
        ).interaction

        pool.apply_observations(
            [self.observation(name="ambient.scene_features", value={"steam": 0.2})]
        )

        updated = pool.get(interaction.interaction_id)
        self.assertEqual("uncertain", updated.process_state["last_hypothesis"]["status"])
        self.assertEqual("awaiting_evidence", updated.lifecycle_phase)
        self.assertNotEqual("rejected", updated.process_state["last_hypothesis"]["status"])

    def test_ignores_inactive_watches_and_deduplicates_event_ids(self) -> None:
        pool = InteractionPool(RuntimeState())
        interaction = pool.register(
            origin="user_event",
            causal_scope={"key": "watch-dedupe"},
            trigger={"event_id": "request-3"},
            participant_device_ids=["edge-1"],
            continuation_policy="until_settled",
            watches=[
                {
                    "watch_id": "watch-1",
                    "observation_names": ["process.activity.v1"],
                    "status": "resolved",
                }
            ],
        ).interaction
        observation = self.observation(name="process.activity.v1", value={"state": "done"})

        self.assertEqual([], pool.apply_observations([observation]))
        self.assertEqual([], pool.apply_observations([observation]))
        self.assertEqual({}, pool.get(interaction.interaction_id).process_state)

    def test_marks_a_persistent_process_unreachable_when_target_edge_is_offline(self) -> None:
        pool = InteractionPool(RuntimeState())
        interaction = pool.register(
            origin="user_event",
            causal_scope={"key": "health-watch"},
            trigger={"event_id": "request-health"},
            participant_device_ids=["edge-1"],
            continuation_policy="until_settled",
            watches=[
                {
                    "watch_id": "watch-health",
                    "observation_names": ["process.activity.v1"],
                    "source_device_id": "edge-1",
                }
            ],
            health={
                "last_observation_at": "2026-08-06T09:50:00Z",
                "stale_after_seconds": 60,
                "probe_after_seconds": 120,
            },
        ).interaction

        updated = pool.reconcile_health(
            current_time="2026-08-06T10:00:00Z",
            online_device_ids=set(),
        )

        self.assertEqual([interaction.interaction_id], [item.interaction_id for item in updated])
        health = pool.get(interaction.interaction_id).health
        self.assertEqual("unreachable", health["state"])
        self.assertEqual("edge_offline", health["reason"])

    def test_resolves_a_watch_when_its_declared_terminal_fact_arrives(self) -> None:
        pool = InteractionPool(RuntimeState())
        interaction = pool.register(
            origin="user_event",
            causal_scope={"key": "watch-terminal"},
            trigger={"event_id": "request-terminal"},
            participant_device_ids=["edge-1"],
            continuation_policy="until_settled",
            watches=[
                {
                    "watch_id": "watch-1",
                    "observation_names": ["coding.activity.v1"],
                    "resolve_when": {"event_kind": ["turn_completed", "turn_failed"]},
                }
            ],
        ).interaction

        pool.apply_observations(
            [
                self.observation(
                    name="coding.activity.v1",
                    value={"event_kind": "turn_completed"},
                )
            ]
        )

        updated = pool.get(interaction.interaction_id)
        self.assertEqual("resolved", updated.watches[0]["status"])
        self.assertTrue(pool.can_complete(interaction.interaction_id))


if __name__ == "__main__":
    unittest.main()
