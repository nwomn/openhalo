"""Regression coverage for the source-neutral interaction pool."""

from __future__ import annotations

import unittest

from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.interaction_pool import InteractionPool
from personal_runtime.runtime_state import RuntimeState


class InteractionPoolTests(unittest.TestCase):
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
        gateway = RuntimeGateway(
            shared_token="dev-token",
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


if __name__ == "__main__":
    unittest.main()
