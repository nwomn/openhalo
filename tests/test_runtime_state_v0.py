import os
import unittest
from stat import S_IMODE
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from threading import Lock
from unittest.mock import patch

from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.presence_router import choose_response_device
from personal_runtime.runtime_state import RuntimeState
from personal_runtime.state_store import JsonStateStore

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_TEST_DIR = REPO_ROOT / ".worktrees" / "v0-single-edge-loop" / ".runtime-test"


class RuntimeStateTests(unittest.TestCase):
    def test_registers_device_and_capability(self) -> None:
        state = RuntimeState()
        state.register_device("desktop-dev-1", "desktop-cli")
        state.register_capability("desktop-dev-1", "text.input")

        self.assertIn("desktop-dev-1", state.devices)
        self.assertIn("text.input", state.devices["desktop-dev-1"]["capabilities"])

    def test_roundtrips_device_capability_and_observation_registries(self) -> None:
        state = RuntimeState()
        state.register_device(
            "phone-edge-1",
            "mobile",
            role="interactive_surface",
            profile={"trust_tier": "personal", "placement": "pocket"},
        )
        state.register_capability(
            "phone-edge-1",
            {
                "name": "notification.show",
                "direction": "runtime_to_edge",
                "kind": "action",
                "affordances": ["notify_user", "deliver_private_text"],
                "modality": "visual_text",
                "content_capacity": "short_text",
                "privacy": "personal",
                "interruptiveness": "medium",
                "side_effect": "user_visible",
                "input_schema": {
                    "type": "object",
                    "required": ["body"],
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                    },
                },
            },
        )
        state.register_capability(
            "phone-edge-1",
            {
                "name": "mobile.context",
                "direction": "edge_to_runtime",
                "kind": "observation_provider",
                "observations": [
                    {
                        "name": "mobile.screen_state",
                        "schema": {
                            "type": "string",
                            "enum": ["locked", "unlocked", "unknown"],
                        },
                        "semantics": ["device_activity"],
                        "privacy": "personal_device_state",
                        "freshness_seconds": 120,
                    }
                ],
            },
        )

        restored = RuntimeState.from_dict(state.to_dict())

        self.assertEqual(
            restored.device_registry["phone-edge-1"]["role"],
            "interactive_surface",
        )
        self.assertEqual(
            restored.device_registry["phone-edge-1"]["profile"]["trust_tier"],
            "personal",
        )
        self.assertIn(
            "notification.show",
            restored.devices["phone-edge-1"]["capabilities"],
        )
        self.assertEqual(
            restored.capability_registry["phone-edge-1"]["notification.show"][
                "content_capacity"
            ],
            "short_text",
        )
        self.assertEqual(
            restored.observation_registry["phone-edge-1"]["mobile.context"][
                "mobile.screen_state"
            ]["schema"]["enum"],
            ["locked", "unlocked", "unknown"],
        )

    def test_restores_legacy_state_without_registries(self) -> None:
        restored = RuntimeState.from_dict(
            {
                "devices": {
                    "terminal-edge-1": {
                        "device_type": "desktop-cli",
                        "capabilities": ["text.input"],
                    }
                }
            }
        )

        self.assertEqual(
            restored.devices["terminal-edge-1"]["capabilities"],
            {"text.input"},
        )
        self.assertEqual(restored.device_registry, {})
        self.assertEqual(restored.capability_registry, {})
        self.assertEqual(restored.observation_registry, {})

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

    def test_roundtrips_interaction_history(self) -> None:
        state = RuntimeState()
        state.record_interaction(
            {
                "interaction_id": "interaction-1",
                "status": "completed",
                "source_device_id": "terminal-edge-1",
                "participant_device_ids": ["terminal-edge-1", "host-edge-1"],
                "primary_action": {
                    "capability": "runtime.status",
                    "target_device_id": "host-edge-1",
                },
                "completion": {
                    "visibility": "visible",
                    "summary": "Runtime status is healthy.",
                },
            }
        )

        restored = RuntimeState.from_dict(state.to_dict())

        self.assertEqual(len(restored.interactions), 1)
        self.assertEqual(
            restored.interactions[0]["interaction_id"],
            "interaction-1",
        )
        self.assertEqual(
            restored.interactions[0]["participant_device_ids"],
            ["terminal-edge-1", "host-edge-1"],
        )

    def test_records_and_roundtrips_runtime_model_health(self) -> None:
        state = RuntimeState()
        state.record_model_health(
            {
                "llm_profile": "proposal_formation",
                "llm_provider": "crs_main",
                "llm_model": "gpt-5.4",
                "model_unavailable": True,
                "provider_failure_class": "protocol_shape",
                "provider_failure_reason": "bad response shape",
                "provider_wire_api": "responses",
                "provider_request_format": "json_schema",
                "provider_latency_ms": 42,
            },
            observed_at="2026-06-26T10:00:00Z",
        )

        restored = RuntimeState.from_dict(state.to_dict())
        health = restored.model_health["proposal_formation"]

        self.assertEqual(health["status"], "unavailable")
        self.assertEqual(health["provider"], "crs_main")
        self.assertEqual(health["model"], "gpt-5.4")
        self.assertEqual(health["last_failure_class"], "protocol_shape")
        self.assertEqual(health["last_failure_reason"], "bad response shape")
        self.assertEqual(health["provider_wire_api"], "responses")
        self.assertEqual(health["provider_request_format"], "json_schema")
        self.assertEqual(health["last_latency_ms"], 42)

    def test_managed_host_edge_status_round_trips_without_secrets(self) -> None:
        state = RuntimeState()
        self.assertTrue(hasattr(state, "record_managed_host_edge_status"))

        state.record_managed_host_edge_status(
            state="retrying",
            retry_attempt=2,
            latest_failure_class="ConnectionRefusedError",
            next_retry_delay_s=1.25,
            updated_at="2026-07-18T10:00:00Z",
        )

        payload = state.to_dict()
        restored = RuntimeState.from_dict(payload)

        self.assertEqual(
            payload["managed_host_edge"],
            {
                "state": "retrying",
                "retry_attempt": 2,
                "latest_failure_class": "ConnectionRefusedError",
                "next_retry_delay_s": 1.25,
                "updated_at": "2026-07-18T10:00:00Z",
            },
        )
        self.assertNotIn("token", str(payload["managed_host_edge"]))
        self.assertNotIn("url", str(payload["managed_host_edge"]))
        self.assertEqual(restored.managed_host_edge, payload["managed_host_edge"])

    def test_records_bounded_hermes_provenance_without_tool_or_memory_bodies(self) -> None:
        state = RuntimeState()
        self.assertTrue(hasattr(state, "record_internal_tool_events"))
        secret_body = "never persist this remote or memory body"
        state.record_internal_tool_events(
            [
                {
                    "tool_name": "openhalo_web_search",
                    "url": "https://search.example.test?q=openhalo",
                    "query_sha256": "a" * 64,
                    "content_sha256": "b" * 64,
                    "content_chars": 42,
                    "untrusted": True,
                    "content": secret_body,
                    "raw_body": secret_body,
                }
            ],
            interaction_id="interaction-1",
            interaction_turn_id="interaction-turn-1",
        )
        state.record_hermes_memory_events(
            [
                {
                    "tool_call_id": "memory-call-1",
                    "task_id": "interaction-turn-1",
                    "action": "add",
                    "target": "user",
                    "content_sha256": "c" * 64,
                    "content": secret_body,
                }
            ],
            interaction_id="interaction-1",
            interaction_turn_id="interaction-turn-1",
        )
        state.record_internal_tool_events(
            [
                {
                    "tool_name": f"tool-{index}",
                    "content_sha256": f"{index:064x}",
                    "content_chars": index,
                    "untrusted": False,
                }
                for index in range(129)
            ],
            interaction_id="interaction-2",
            interaction_turn_id="interaction-turn-2",
        )

        payload = state.to_dict()
        restored = RuntimeState.from_dict(payload)

        self.assertEqual(
            len(state.internal_tool_events),
            128,
        )
        self.assertEqual(state.internal_tool_events[-1]["tool_name"], "tool-128")
        stored_memory_event = state.hermes_memory_events[0]
        self.assertEqual(stored_memory_event["interaction_id"], "interaction-1")
        self.assertEqual(stored_memory_event["content_sha256"], "c" * 64)
        self.assertNotIn("content", stored_memory_event)
        self.assertNotIn("raw_body", payload["internal_tool_events"][0])
        self.assertNotIn(secret_body, str(payload))
        self.assertEqual(restored.hermes_memory_events, state.hermes_memory_events)


class JsonStateStoreTests(unittest.TestCase):
    def test_serializes_concurrent_saves_for_one_store(self) -> None:
        with TemporaryDirectory() as directory:
            store = JsonStateStore(Path(directory) / "state.json")
            state = RuntimeState()
            first_replace_entered = Event()
            second_replace_entered = Event()
            release_first_replace = Event()
            replace_count = 0
            count_lock = Lock()
            original_replace = Path.replace

            def hold_first_replace(path, target, *args, **kwargs):
                nonlocal replace_count
                with count_lock:
                    replace_count += 1
                    position = replace_count
                if position == 1:
                    first_replace_entered.set()
                    release_first_replace.wait(timeout=1)
                else:
                    second_replace_entered.set()
                return original_replace(path, target, *args, **kwargs)

            with patch.object(Path, "replace", new=hold_first_replace):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    first_save = executor.submit(store.save, state)
                    self.assertTrue(first_replace_entered.wait(timeout=1))
                    second_save = executor.submit(store.save, state)
                    try:
                        self.assertFalse(second_replace_entered.wait(timeout=0.05))
                    finally:
                        release_first_replace.set()
                    first_save.result(timeout=1)
                    second_save.result(timeout=1)

    def test_persists_runtime_state_owner_only(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"

            original_umask = os.umask(0o022)
            try:
                JsonStateStore(path).save(RuntimeState())
            finally:
                os.umask(original_umask)

            self.assertEqual(S_IMODE(path.stat().st_mode), 0o600)

    def test_saves_and_loads_runtime_state(self) -> None:
        path = RUNTIME_TEST_DIR / "state.json"
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
