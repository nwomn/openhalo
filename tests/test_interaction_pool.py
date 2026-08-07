"""Regression coverage for the source-neutral interaction pool."""

from __future__ import annotations

import unittest
import json

from personal_runtime.interaction_pool import InteractionPool
from personal_runtime.runtime_state import RuntimeState
from tests.v2_test_support import create_test_gateway


class InteractionPoolTests(unittest.TestCase):
    def test_register_preserves_explicit_user_requester_outcome_contract(self) -> None:
        interaction = InteractionPool(RuntimeState()).register(
            origin="user_event",
            causal_scope={"key": "terminal-message:outcome-contract"},
            trigger={"event_id": "event-outcome-contract"},
            participant_device_ids=["terminal-1"],
            source_device_id="terminal-1",
            initiator_kind="explicit_user_intent",
            requesting_device_id="terminal-1",
            outcome_delivery_required=True,
        ).interaction

        self.assertEqual(interaction.initiator_kind, "explicit_user_intent")
        self.assertEqual(interaction.requesting_device_id, "terminal-1")
        self.assertTrue(interaction.outcome_delivery_required)

    def test_register_keeps_passive_observation_without_requester_outcome_contract(self) -> None:
        interaction = InteractionPool(RuntimeState()).register(
            origin="observation_driven",
            causal_scope={"key": "phone-observation:no-outcome-contract"},
            trigger={"observation_id": "observation-no-outcome-contract"},
            participant_device_ids=["android-1"],
            source_device_id="android-1",
            initiator_kind="passive_observation",
            requesting_device_id=None,
            outcome_delivery_required=False,
        ).interaction

        self.assertEqual(interaction.initiator_kind, "passive_observation")
        self.assertIsNone(interaction.requesting_device_id)
        self.assertFalse(interaction.outcome_delivery_required)

    def test_register_reports_exact_scope_deduplication(self) -> None:
        pool = InteractionPool(RuntimeState())

        created = pool.register(
            origin="user_event",
            causal_scope={"key": "terminal-message:42"},
            trigger={"event_id": "event-42"},
            participant_device_ids=["terminal-1"],
        )
        duplicate = pool.register(
            origin="observation_driven",
            causal_scope={"key": "terminal-message:42"},
            trigger={"observation_id": "observation-42"},
            participant_device_ids=["terminal-1", "phone-1"],
        )

        self.assertTrue(created.created)
        self.assertFalse(duplicate.created)
        self.assertEqual(created.interaction.interaction_id, duplicate.interaction.interaction_id)
        self.assertEqual("user_event", created.interaction.origin)
        self.assertEqual({"key": "terminal-message:42"}, created.interaction.causal_scope)
        self.assertEqual(["terminal-1"], created.interaction.participant_device_ids)
        self.assertEqual(1, len(pool))

    def test_register_keeps_different_scopes_concurrent_and_reopens_completed_scope(self) -> None:
        pool = InteractionPool(RuntimeState())
        first = pool.register(
            origin="user_event",
            causal_scope={"key": "terminal-message:42"},
            trigger={"event_id": "event-42"},
            participant_device_ids=["terminal-1"],
        )
        second = pool.register(
            origin="agent_initiative",
            causal_scope={"key": "daily-briefing:2026-07-13"},
            trigger={"scheduler": "daily-briefing"},
            participant_device_ids=["phone-1"],
        )
        pool.complete(first.interaction.interaction_id)
        reopened = pool.register(
            origin="observation_driven",
            causal_scope={"key": "terminal-message:42"},
            trigger={"observation_id": "observation-43"},
            participant_device_ids=["terminal-1"],
        )

        self.assertNotEqual(first.interaction.interaction_id, second.interaction.interaction_id)
        self.assertTrue(second.created)
        self.assertTrue(reopened.created)
        self.assertNotEqual(first.interaction.interaction_id, reopened.interaction.interaction_id)
        self.assertEqual(3, len(pool))

    def test_register_projects_same_source_recent_persistent_process_and_binds_reference(self) -> None:
        pool = InteractionPool(RuntimeState())
        completed_process = pool.register(
            origin="user_event",
            causal_scope={"key": "coding:completed"},
            trigger={"event_id": "coding-start"},
            participant_device_ids=["terminal-1"],
            source_device_id="terminal-1",
            continuation_policy="until_settled",
            objective={"summary": "Complete the coding task."},
            watches=[
                {
                    "watch_id": "completion",
                    "observation_names": ["coding.activity.v1"],
                }
            ],
        ).interaction
        pool.update_process_state(
            completed_process.interaction_id,
            updates={
                "last_observation": {
                    "name": "coding.activity.v1",
                    "event_kind": "turn_completed",
                    "observed_at": "2026-08-08T00:00:00Z",
                }
            },
            health={"state": "healthy", "last_progress_at": "2026-08-08T00:00:00Z"},
        )
        pool.resolve_watch(completed_process.interaction_id, "completion")
        pool.complete(completed_process.interaction_id)
        pool.register(
            origin="user_event",
            causal_scope={"key": "other-device:completed"},
            trigger={"event_id": "other-start"},
            participant_device_ids=["terminal-2"],
            source_device_id="terminal-2",
            continuation_policy="until_settled",
            watches=[
                {
                    "watch_id": "completion",
                    "observation_names": ["coding.activity.v1"],
                }
            ],
        )
        pool.register(
            origin="user_event",
            causal_scope={"key": "one-shot:completed"},
            trigger={"event_id": "one-shot"},
            participant_device_ids=["terminal-1"],
            source_device_id="terminal-1",
        )

        query = pool.register(
            origin="user_event",
            causal_scope={"key": "terminal-query:completion"},
            trigger={"event_id": "query"},
            participant_device_ids=["terminal-1"],
            source_device_id="terminal-1",
        )

        self.assertEqual(
            [
                {
                    "interaction_id": completed_process.interaction_id,
                    "causal_scope_key": "coding:completed",
                    "objective": {"summary": "Complete the coding task."},
                    "status": "completed",
                    "lifecycle_phase": "completed",
                    "last_observation": {
                        "name": "coding.activity.v1",
                        "event_kind": "turn_completed",
                        "observed_at": "2026-08-08T00:00:00Z",
                    },
                    "last_progress_at": "2026-08-08T00:00:00Z",
                    "health_state": "healthy",
                    "process_state_version": 3,
                }
            ],
            query.related_process_summaries,
        )
        self.assertEqual(
            [{"interaction_id": completed_process.interaction_id, "process_state_version": 3}],
            query.interaction.lineage["context_process_refs"],
        )
        self.assertNotIn("process_state", query.interaction.lineage)

    def test_related_process_projection_can_select_one_process_on_a_shared_edge(self) -> None:
        pool = InteractionPool(RuntimeState())
        coding = pool.register(
            origin="user_event",
            causal_scope={"key": "coding:shared-edge"},
            trigger={"event_id": "coding-start"},
            participant_device_ids=["terminal-1"],
            source_device_id="terminal-1",
            continuation_policy="until_settled",
            watches=[{
                "watch_id": "coding-completion",
                "observation_names": ["coding.activity.v1"],
                "process_id": "codex-task-1",
                "source_capability": "coding",
            }],
        ).interaction
        download = pool.register(
            origin="user_event",
            causal_scope={"key": "download:shared-edge"},
            trigger={"event_id": "download-start"},
            participant_device_ids=["terminal-1"],
            source_device_id="terminal-1",
            continuation_policy="until_settled",
            watches=[{
                "watch_id": "download-completion",
                "observation_names": ["download.activity.v1"],
                "process_id": "download-1",
                "source_capability": "download",
            }],
        ).interaction

        selected = pool.related_process_summaries(
            source_device_id="terminal-1",
            process_id="codex-task-1",
        )

        self.assertEqual([coding.interaction_id], [item["interaction_id"] for item in selected])
        self.assertEqual("codex-task-1", selected[0]["process_id"])
        self.assertEqual("coding", selected[0]["source_capability"])
        self.assertNotEqual(coding.interaction_id, download.interaction_id)

    def test_related_process_projection_bounds_nested_summary_payload(self) -> None:
        pool = InteractionPool(RuntimeState())
        process = pool.register(
            origin="user_event",
            causal_scope={"key": "large-process"},
            trigger={"event_id": "large-process"},
            participant_device_ids=["terminal-1"],
            source_device_id="terminal-1",
            continuation_policy="until_settled",
            objective={"summary": "x" * 10000, "nested": {"items": ["y" * 10000] * 100}},
            watches=[{"watch_id": "watch", "observation_names": ["process.activity.v1"], "process_id": "large-1"}],
        ).interaction
        pool.update_process_state(
            process.interaction_id,
            updates={"last_observation": {"payload": "z" * 10000}},
        )

        summary = pool.related_process_summaries(source_device_id="terminal-1")[0]
        self.assertLessEqual(len(json.dumps(summary, ensure_ascii=False)), 4096)

    def test_process_state_version_advances_for_lifecycle_and_watch_changes(self) -> None:
        pool = InteractionPool(RuntimeState())
        process = pool.register(
            origin="user_event",
            causal_scope={"key": "versioned-process"},
            trigger={"event_id": "versioned-process"},
            participant_device_ids=["terminal-1"],
            source_device_id="terminal-1",
            continuation_policy="until_settled",
            watches=[{"watch_id": "completion", "observation_names": ["process.activity.v1"]}],
        ).interaction
        initial = pool.get(process.interaction_id).process_state.get("version", 0)
        pool.transition(process.interaction_id, phase="monitoring", status="monitoring")
        after_transition = pool.get(process.interaction_id).process_state["version"]
        pool.resolve_watch(process.interaction_id, "completion")
        after_watch = pool.get(process.interaction_id).process_state["version"]
        pool.complete(process.interaction_id)

        self.assertGreater(after_transition, initial)
        self.assertGreater(after_watch, after_transition)
        self.assertGreater(
            pool.get(process.interaction_id).process_state["version"], after_watch
        )

    def test_action_result_lookup_requires_exact_interaction_turn_and_request(self) -> None:
        pool = InteractionPool(RuntimeState())
        interaction = pool.register(
            origin="observation_driven",
            causal_scope={"key": "runtime-health:degraded"},
            trigger={"observation_id": "health-1"},
            participant_device_ids=["host-1", "terminal-1"],
        ).interaction
        turn = pool.record_turn(
            interaction.interaction_id,
            interaction_turn_id="interaction-1:turn-1",
            request_id="request-1",
        )

        self.assertEqual("interaction-1:turn-1", turn.interaction_turn_id)
        self.assertEqual("request-1", turn.request_id)
        resolved = pool.get_for_action_result(
            interaction.interaction_id,
            "interaction-1:turn-1",
            "request-1",
        )
        self.assertEqual(interaction.interaction_id, resolved.interaction_id)
        self.assertIsNone(
            pool.get_for_action_result(
                interaction.interaction_id,
                "interaction-1:turn-2",
                "request-1",
            )
        )

    def test_action_result_lookup_rejects_completed_interaction(self) -> None:
        pool = InteractionPool(RuntimeState())
        interaction = pool.register(
            origin="user_event",
            causal_scope={"key": "terminal-message:completed"},
            trigger={"event_id": "event-completed"},
            participant_device_ids=["terminal-1"],
        ).interaction
        pool.record_turn(
            interaction.interaction_id,
            interaction_turn_id="interaction-1:turn-1",
            request_id="request-1",
        )
        pool.complete(interaction.interaction_id)

        self.assertIsNone(
            pool.get_for_action_result(
                interaction.interaction_id,
                "interaction-1:turn-1",
                "request-1",
            )
        )
        self.assertIsNone(
            pool.get_for_action_result(
                interaction.interaction_id,
                "interaction-1:turn-1",
                "other-request",
            )
        )

    def test_retains_a_bounded_number_of_turns(self) -> None:
        pool = InteractionPool(RuntimeState(), turn_limit=2)
        interaction = pool.register(
            origin="user_event",
            causal_scope={"key": "terminal-message:44"},
            trigger={"event_id": "event-44"},
            participant_device_ids=["terminal-1"],
        ).interaction

        for index in range(3):
            pool.record_turn(
                interaction.interaction_id,
                interaction_turn_id=f"interaction-1:turn-{index}",
            )

        restored = pool.get(interaction.interaction_id)
        self.assertEqual(
            ["interaction-1:turn-1", "interaction-1:turn-2"],
            [turn.interaction_turn_id for turn in restored.turns],
        )

    def test_retains_pending_action_correlation_until_its_result_is_resolved(self) -> None:
        pool = InteractionPool(RuntimeState(), turn_limit=2)
        interaction = pool.register(
            origin="user_event",
            causal_scope={"key": "terminal-message:45"},
            trigger={"event_id": "event-45"},
            participant_device_ids=["terminal-1"],
        ).interaction

        pool.record_turn(
            interaction.interaction_id,
            interaction_turn_id="interaction-1:turn-1",
            request_id="request-1",
        )
        pool.record_turn(
            interaction.interaction_id,
            interaction_turn_id="interaction-1:turn-2",
        )
        pool.record_turn(
            interaction.interaction_id,
            interaction_turn_id="interaction-1:turn-3",
        )

        self.assertIsNotNone(
            pool.get_for_action_result(
                interaction.interaction_id,
                "interaction-1:turn-1",
                "request-1",
            )
        )

        pool.resolve_action_result(
            interaction.interaction_id,
            "interaction-1:turn-1",
            "request-1",
        )
        pool.record_turn(
            interaction.interaction_id,
            interaction_turn_id="interaction-1:turn-4",
        )

        self.assertIsNone(
            pool.get_for_action_result(
                interaction.interaction_id,
                "interaction-1:turn-1",
                "request-1",
            )
        )
        self.assertLessEqual(
            len(pool.get(interaction.interaction_id).turns),
            2,
        )

    def test_rejects_a_second_pending_action_for_the_same_interaction(self) -> None:
        pool = InteractionPool(RuntimeState(), turn_limit=2)
        interaction = pool.register(
            origin="user_event",
            causal_scope={"key": "terminal-message:pending"},
            trigger={"event_id": "event-pending"},
            participant_device_ids=["terminal-1"],
        ).interaction
        pool.record_turn(
            interaction.interaction_id,
            interaction_turn_id="interaction-1:turn-1",
            request_id="request-1",
        )

        with self.assertRaisesRegex(ValueError, "pending action"):
            pool.record_turn(
                interaction.interaction_id,
                interaction_turn_id="interaction-1:turn-2",
                request_id="request-2",
            )

        self.assertEqual(1, len(pool.get(interaction.interaction_id).turns))

    def test_batch_stays_awaiting_until_all_results_resolve(self) -> None:
        pool = InteractionPool(RuntimeState(), max_pending_actions=2)
        interaction = pool.register(
            origin="user_event",
            causal_scope={"key": "terminal-message:batch-await"},
            trigger={"event_id": "event-batch-await"},
            participant_device_ids=["terminal-1", "android-1"],
        ).interaction

        pool.record_action_batch(
            interaction.interaction_id,
            interaction_turn_id="interaction-1:turn-1",
            action_batch_id="batch-1",
            action_requests=[
                ("action-1", "intent-1"),
                ("action-2", "intent-2"),
            ],
        )

        self.assertEqual("awaiting_action_results", pool.get(interaction.interaction_id).status)
        with self.assertRaisesRegex(ValueError, "pending action batch"):
            pool.record_action_batch(
                interaction.interaction_id,
                interaction_turn_id="interaction-1:turn-2",
                action_batch_id="batch-2",
                action_requests=[("action-3", "intent-3")],
            )

        pool.resolve_action_result(
            interaction.interaction_id,
            "interaction-1:turn-1",
            "action-1",
        )
        self.assertTrue(pool.has_pending_action(interaction.interaction_id))
        self.assertEqual("awaiting_action_results", pool.get(interaction.interaction_id).status)
        self.assertFalse(
            pool.is_action_batch_settled(interaction.interaction_id, "batch-1")
        )

        pool.resolve_action_result(
            interaction.interaction_id,
            "interaction-1:turn-1",
            "action-2",
        )
        self.assertFalse(pool.has_pending_action(interaction.interaction_id))
        self.assertEqual("planned", pool.get(interaction.interaction_id).status)
        self.assertTrue(
            pool.is_action_batch_settled(interaction.interaction_id, "batch-1")
        )

    def test_default_batch_limit_tracks_turn_limit(self) -> None:
        pool = InteractionPool(RuntimeState(), turn_limit=3)
        interaction = pool.register(
            origin="user_event",
            causal_scope={"key": "terminal-message:three-action-batch"},
            trigger={"event_id": "event-three-action-batch"},
            participant_device_ids=["terminal-1"],
        ).interaction

        turns = pool.record_action_batch(
            interaction.interaction_id,
            interaction_turn_id="interaction-1:turn-1",
            action_batch_id="batch-3",
            action_requests=[
                ("request-1", "intent-1"),
                ("request-2", "intent-2"),
                ("request-3", "intent-3"),
            ],
        )

        self.assertEqual(3, len(turns))
        self.assertEqual(3, pool.max_pending_actions)

    def test_same_scope_key_with_different_evidence_remains_distinct(self) -> None:
        pool = InteractionPool(RuntimeState())

        first = pool.register(
            origin="observation_driven",
            causal_scope={
                "key": "runtime-health:degraded",
                "provenance": {
                    "source_device_id": "host-1",
                    "source_event_id": "event-1",
                },
                "evidence_refs": ["observation-1"],
            },
            trigger={"observation_id": "observation-1"},
            participant_device_ids=["host-1"],
        )
        second = pool.register(
            origin="observation_driven",
            causal_scope={
                "key": "runtime-health:degraded",
                "provenance": {
                    "source_device_id": "host-1",
                    "source_event_id": "event-2",
                },
                "evidence_refs": ["observation-2"],
            },
            trigger={"observation_id": "observation-2"},
            participant_device_ids=["host-1"],
        )

        self.assertTrue(first.created)
        self.assertTrue(second.created)
        self.assertNotEqual(
            first.interaction.interaction_id,
            second.interaction.interaction_id,
        )

    def test_gateway_and_pool_share_the_persisted_interaction_id_allocator(self) -> None:
        state = RuntimeState()
        first = InteractionPool(state).register(
            origin="user_event",
            causal_scope={"key": "terminal-message:46"},
            trigger={"event_id": "event-46"},
            participant_device_ids=["terminal-1"],
        ).interaction
        restored_state = RuntimeState.from_dict(state.to_dict())
        gateway = create_test_gateway(
            state=restored_state,
            persist_state=False,
        )

        gateway_interaction_id = gateway._next_interaction_id()
        restored_state.record_interaction(
            {"interaction_id": gateway_interaction_id, "status": "planned"}
        )
        third = InteractionPool(restored_state).register(
            origin="agent_initiative",
            causal_scope={"key": "daily-briefing:2026-07-13"},
            trigger={"scheduler": "daily-briefing"},
            participant_device_ids=["phone-1"],
        ).interaction

        self.assertEqual("interaction-1", first.interaction_id)
        self.assertEqual("interaction-2", gateway_interaction_id)
        self.assertEqual("interaction-3", third.interaction_id)

    def test_runtime_state_round_trips_pool_records_and_id_sequence(self) -> None:
        state = RuntimeState()
        pool = InteractionPool(state)
        first = pool.register(
            origin="user_event",
            causal_scope={"key": "terminal-message:43"},
            trigger={"event_id": "event-43"},
            participant_device_ids=["terminal-1", "phone-1"],
        ).interaction
        pool.record_turn(
            first.interaction_id,
            interaction_turn_id="interaction-1:turn-1",
            request_id="request-43",
        )

        restored_state = RuntimeState.from_dict(state.to_dict())
        restored_pool = InteractionPool(restored_state)
        restored = restored_pool.get(first.interaction_id)
        second = restored_pool.register(
            origin="agent_initiative",
            causal_scope={"key": "daily-briefing:2026-07-13"},
            trigger={"scheduler": "daily-briefing"},
            participant_device_ids=["phone-1"],
        ).interaction

        self.assertEqual("user_event", restored.origin)
        self.assertEqual({"key": "terminal-message:43"}, restored.causal_scope)
        self.assertEqual("request-43", restored.turns[0].request_id)
        self.assertEqual("interaction-2", second.interaction_id)

    def test_legacy_registration_defaults_to_one_shot_lifecycle(self) -> None:
        interaction = InteractionPool(RuntimeState()).register(
            origin="user_event",
            causal_scope={"key": "legacy-one-shot"},
            trigger={"event_id": "legacy-one-shot"},
            participant_device_ids=["terminal-1"],
        ).interaction

        self.assertEqual("one_shot", interaction.continuation_policy)
        self.assertEqual("planned", interaction.lifecycle_phase)
        self.assertEqual({}, interaction.objective)
        self.assertEqual([], interaction.watches)
        self.assertEqual([], interaction.obligations)
        self.assertEqual("healthy", interaction.health["state"])

    def test_persistent_interaction_keeps_watch_and_obligation_state(self) -> None:
        pool = InteractionPool(RuntimeState())
        interaction = pool.register(
            origin="user_event",
            causal_scope={"key": "persistent-process-1"},
            trigger={"event_id": "persistent-process-1"},
            participant_device_ids=["terminal-1"],
            continuation_policy="until_verified",
            objective={"summary": "Verify the requested process."},
            watches=[{"watch_id": "watch-1", "observation_names": ["process.activity.v1"]}],
            obligations=[{"obligation_id": "obligation-1", "kind": "outcome_verification"}],
        ).interaction

        restored = pool.get(interaction.interaction_id)
        self.assertEqual("until_verified", restored.continuation_policy)
        self.assertEqual("Verify the requested process.", restored.objective["summary"])
        self.assertEqual("watch-1", restored.watches[0]["watch_id"])
        self.assertEqual("pending", restored.obligations[0]["status"])

    def test_action_batch_resolution_moves_persistent_interaction_to_monitoring(self) -> None:
        pool = InteractionPool(RuntimeState())
        interaction = pool.register(
            origin="user_event",
            causal_scope={"key": "persistent-action-1"},
            trigger={"event_id": "persistent-action-1"},
            participant_device_ids=["terminal-1"],
            continuation_policy="until_settled",
            watches=[{"watch_id": "watch-1", "observation_names": ["process.activity.v1"]}],
        ).interaction

        pool.record_action_batch(
            interaction.interaction_id,
            interaction_turn_id="turn-1",
            action_batch_id="batch-1",
            action_requests=[("request-1", "intent-1")],
        )
        pool.resolve_action_result(interaction.interaction_id, "turn-1", "request-1")

        restored = pool.get(interaction.interaction_id)
        self.assertEqual("monitoring", restored.status)
        self.assertEqual("monitoring", restored.lifecycle_phase)
        self.assertFalse(pool.can_complete(interaction.interaction_id))

    def test_resolving_the_required_obligation_allows_persistent_completion(self) -> None:
        pool = InteractionPool(RuntimeState())
        interaction = pool.register(
            origin="user_event",
            causal_scope={"key": "persistent-verified-1"},
            trigger={"event_id": "persistent-verified-1"},
            participant_device_ids=["terminal-1"],
            continuation_policy="until_verified",
            obligations=[{"obligation_id": "obligation-1", "kind": "outcome_verification"}],
        ).interaction

        self.assertFalse(pool.can_complete(interaction.interaction_id))
        pool.resolve_obligation(interaction.interaction_id, "obligation-1", result={"status": "ok"})
        self.assertTrue(pool.can_complete(interaction.interaction_id))
        completed = pool.complete(interaction.interaction_id)

        self.assertEqual("completed", completed.status)
        self.assertEqual("completed", completed.lifecycle_phase)

    def test_configures_a_one_shot_interaction_from_a_generic_process_contract(self) -> None:
        pool = InteractionPool(RuntimeState())
        interaction = pool.register(
            origin="user_event",
            causal_scope={"key": "process-contract-1"},
            trigger={"event_id": "process-contract-1"},
            participant_device_ids=["terminal-1"],
        ).interaction

        configured = pool.configure_continuation(
            interaction.interaction_id,
            {
                "continuation_policy": "until_settled",
                "watches": [
                    {
                        "watch_id": "completion",
                        "observation_names": ["process.activity.v1"],
                    }
                ],
            },
            target_device_id="terminal-1",
        )

        self.assertEqual("until_settled", configured.continuation_policy)
        self.assertEqual("terminal-1", configured.health["target_device_id"])
        self.assertEqual("completion", configured.watches[0]["watch_id"])


if __name__ == "__main__":
    unittest.main()
