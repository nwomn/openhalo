import unittest
from pathlib import Path

from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.presence_router import choose_response_device
from personal_runtime.runtime_state import RuntimeState
from personal_runtime.state_store import JsonStateStore


class RuntimeStateTests(unittest.TestCase):
    def test_registers_device_and_capability(self) -> None:
        state = RuntimeState()
        state.register_device("desktop-dev-1", "desktop-cli")
        state.register_capability("desktop-dev-1", "text.input")

        self.assertIn("desktop-dev-1", state.devices)
        self.assertIn("text.input", state.devices["desktop-dev-1"]["capabilities"])

    def test_presence_defaults_to_source_device(self) -> None:
        target = choose_response_device(source_device_id="desktop-dev-1")

        self.assertEqual(target, "desktop-dev-1")

    def test_presence_prefers_other_device_with_requested_capability(self) -> None:
        devices = {
            "desktop-dev-1": {
                "device_type": "desktop-cli",
                "capabilities": {"text.input", "notification.show"},
            },
            "desktop-dev-2": {
                "device_type": "desktop-cli",
                "capabilities": {"text.input", "notification.show"},
            },
        }

        target = choose_response_device(
            source_device_id="desktop-dev-1",
            devices=devices,
            required_capability="notification.show",
        )

        self.assertEqual(target, "desktop-dev-2")

    def test_roundtrips_to_dict_and_back(self) -> None:
        state = RuntimeState()
        state.register_device("desktop-dev-1", "desktop-cli")
        state.register_capability("desktop-dev-1", "text.input")
        state.events.append({"type": "event_push", "payload": {"text": "hello"}})
        state.record_action_result({"status": "ok"})

        restored = RuntimeState.from_dict(state.to_dict())

        self.assertEqual(
            restored.devices["desktop-dev-1"]["capabilities"],
            {"text.input"},
        )
        self.assertEqual(restored.events[-1]["payload"]["text"], "hello")
        self.assertEqual(restored.action_results[-1]["status"], "ok")

    def test_records_runtime_observation_with_provenance(self) -> None:
        state = RuntimeState()
        observation = RuntimeObservation(
            name="user.location",
            value="home.office",
            source_device_id="desktop-dev-1",
            source_capability="desktop_context",
            source_event_id="evt-123",
            observed_at="2026-06-18T10:30:00Z",
            confidence=0.91,
        )

        state.record_observation(observation)
        restored = RuntimeState.from_dict(state.to_dict())

        self.assertEqual(len(state.observations), 1)
        self.assertEqual(state.observations[0].name, "user.location")
        self.assertEqual(state.observations[0].value, "home.office")
        self.assertEqual(
            state.observations[0].source_capability,
            "desktop_context",
        )
        self.assertEqual(len(restored.observations), 1)
        self.assertEqual(restored.observations[0].source_event_id, "evt-123")

    def test_roundtrips_intervention_history(self) -> None:
        state = RuntimeState()
        state.record_intervention(
            {
                "target_device_id": "desktop-dev-1",
                "action_capability": "notification.show",
                "decision": "allow",
                "reason": "context_clear",
                "recorded_at": "2026-06-19T10:30:00Z",
            }
        )

        restored = RuntimeState.from_dict(state.to_dict())

        self.assertEqual(len(restored.interventions), 1)
        self.assertEqual(
            restored.interventions[0]["action_capability"],
            "notification.show",
        )
        self.assertEqual(restored.interventions[0]["decision"], "allow")

    def test_roundtrips_runtime_goals(self) -> None:
        state = RuntimeState()
        state.upsert_goal(
            goal_id="goal-1",
            title="Keep runtime healthy",
            status="active",
            summary="Watch runtime health signals.",
            updated_at="2026-06-22T10:00:00Z",
        )
        state.upsert_goal(
            goal_id="goal-2",
            title="Review idle terminal pushes",
            status="done",
            summary="Completed verification.",
            updated_at="2026-06-22T10:05:00Z",
        )

        restored = RuntimeState.from_dict(state.to_dict())

        self.assertEqual(len(restored.tasks), 2)
        self.assertEqual(restored.tasks[0]["goal_id"], "goal-1")
        self.assertEqual(restored.tasks[0]["status"], "active")
        self.assertEqual(restored.tasks[1]["goal_id"], "goal-2")
        self.assertEqual(restored.tasks[1]["status"], "done")


class JsonStateStoreTests(unittest.TestCase):
    def test_saves_and_loads_runtime_state(self) -> None:
        path = Path("/root/personal-runtime-agent/.worktrees/v0-single-edge-loop/.runtime-test/state.json")
        store = JsonStateStore(path)
        state = RuntimeState()
        state.register_device("desktop-dev-1", "desktop-cli")
        state.register_capability("desktop-dev-1", "text.input")
        state.events.append({"type": "event_push", "payload": {"text": "hello"}})

        store.save(state)
        loaded = store.load()

        self.assertEqual(loaded.devices["desktop-dev-1"]["device_type"], "desktop-cli")
        self.assertEqual(
            loaded.devices["desktop-dev-1"]["capabilities"],
            {"text.input"},
        )
        self.assertEqual(loaded.events[-1]["payload"]["text"], "hello")


if __name__ == "__main__":
    unittest.main()
