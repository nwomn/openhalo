import json
import os
import stat
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.interaction_pool import InteractionPool
from personal_runtime.runtime_state import RuntimeState
from personal_runtime.sqlite_state_store import RetentionPolicy
from personal_runtime.sqlite_state_store import SCHEMA_VERSION
from personal_runtime.sqlite_state_store import StorageQuotaExceeded
from personal_runtime.sqlite_state_store import SQLiteRuntimeStateStore
from personal_runtime.state_store import build_state_store


class SQLiteRuntimeStateStoreTests(unittest.TestCase):
    def test_context_facts_are_upserted_and_survive_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            store = SQLiteRuntimeStateStore(path)
            store.upsert_context_fact(
                {
                    "fact_id": "camera-1/camera.person_presence.v1",
                    "source_device_id": "camera-1",
                    "observation_name": "camera.person_presence.v1",
                    "value": {"state": "present"},
                    "confidence": 0.9,
                    "observed_at": "2026-08-23T10:00:00Z",
                    "expires_at": "2026-08-23T10:01:00Z",
                    "disposition": "full",
                    "provenance": {"source_event_id": "event-1"},
                    "version": 1,
                    "withheld_reason": None,
                }
            )
            store.upsert_context_fact(
                {
                    "fact_id": "camera-1/camera.person_presence.v1",
                    "source_device_id": "camera-1",
                    "observation_name": "camera.person_presence.v1",
                    "value": {"state": "absent"},
                    "confidence": 1.0,
                    "observed_at": "2026-08-23T10:00:30Z",
                    "expires_at": "2026-08-23T10:01:30Z",
                    "disposition": "full",
                    "provenance": {"source_event_id": "event-2"},
                    "version": 2,
                    "withheld_reason": None,
                }
            )
            store.close()

            restored = SQLiteRuntimeStateStore(path)
            facts = restored.load_context_facts()
            restored.close()

        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["value"], {"state": "absent"})
        self.assertEqual(facts[0]["version"], 2)

    def test_state_store_factory_selects_sqlite_for_database_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = build_state_store(Path(directory) / "state.sqlite3")

            self.assertIsInstance(store, SQLiteRuntimeStateStore)

    def test_state_store_refuses_empty_sqlite_when_legacy_json_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "state.sqlite3"
            (root / "state.json").write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "migration"):
                build_state_store(database)

    def test_state_store_refuses_unmigrated_existing_sqlite_when_legacy_json_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "state.sqlite3"
            SQLiteRuntimeStateStore(database).close()
            (root / "state.json").write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "migration"):
                build_state_store(database)

    def test_sqlite_sidecars_are_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            original_umask = os.umask(0o022)
            try:
                store = SQLiteRuntimeStateStore(path)
                state = RuntimeState()
                state.events.append({"event_id": "private-event", "payload": {"secret": "value"}})
                store.save(state)
            finally:
                os.umask(original_umask)

            for sidecar in (Path(f"{path}-wal"), Path(f"{path}-shm")):
                if sidecar.exists():
                    self.assertEqual(stat.S_IMODE(sidecar.stat().st_mode), 0o600)

    def test_round_trips_state_and_keeps_history_in_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRuntimeStateStore(Path(directory) / "state.sqlite3")
            state = RuntimeState()
            state.register_device("terminal-1", "desktop-cli")
            state.events.append(
                {
                    "type": "event_push",
                    "device_id": "terminal-1",
                    "timestamp": "2026-08-01T10:00:00Z",
                    "payload": {"text": "hello"},
                }
            )
            state.record_observation(
                RuntimeObservation(
                    name="terminal.activity",
                    value="active",
                    source_device_id="terminal-1",
                    source_capability="terminal.context",
                    source_event_id="event-1",
                    observed_at="2026-08-01T10:00:00Z",
                    confidence=1.0,
                )
            )

            store.save(state)
            restored = store.load()

            self.assertEqual(restored.devices["terminal-1"]["device_type"], "desktop-cli")
            self.assertEqual(restored.events[-1]["payload"]["text"], "hello")
            self.assertEqual(restored.observations[-1].name, "terminal.activity")
            self.assertTrue((Path(directory) / "state.sqlite3").exists())

    def test_sqlite_event_projection_does_not_duplicate_observation_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRuntimeStateStore(Path(directory) / "state.sqlite3")
            state = RuntimeState()
            state.record_event(
                {
                    "event_id": "event-1",
                    "type": "event_push",
                    "capability": "mobile.context",
                    "payload": {
                        "observations": [
                            {"name": "mobile.context", "value": "private"}
                        ]
                    },
                }
            )
            store.save(state)

            persisted_event = store.load().events[0]

            self.assertNotIn("observations", persisted_event["payload"])
            self.assertEqual(persisted_event["payload"]["observation_count"], 1)

    def test_incremental_save_uses_record_journal_without_serializing_full_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRuntimeStateStore(Path(directory) / "state.sqlite3")
            state = RuntimeState()
            state.events.append({"event_id": "event-1", "timestamp": "2026-08-01T10:00:00Z"})
            store.save(state)
            state.record_event(
                {"event_id": "event-2", "timestamp": "2026-08-01T10:00:01Z"}
            )
            state.to_dict = lambda: (_ for _ in ()).throw(AssertionError("full snapshot"))

            store.save(state)

            restored = store.load()
            self.assertEqual([item["event_id"] for item in restored.events], ["event-1", "event-2"])

    def test_save_can_run_from_gateway_worker_thread(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRuntimeStateStore(Path(directory) / "state.sqlite3")
            store.save(RuntimeState())
            state = RuntimeState()
            state.record_event({"event_id": "worker-event"})

            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(store.save, state).result()

            self.assertEqual(store.load().events[-1]["event_id"], "worker-event")

    def test_deferred_save_batches_high_frequency_records_until_flush(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRuntimeStateStore(Path(directory) / "state.sqlite3")
            state = RuntimeState()
            state.events.append({"event_id": "event-1", "timestamp": "2026-08-01T10:00:00Z"})
            store.save(state)
            state.record_event(
                {"event_id": "event-2", "timestamp": "2026-08-01T10:00:01Z"}
            )

            store.save(state, deferred=True)

            self.assertEqual(store.storage_status()["counts"]["events"], 1)
            store.flush()
            self.assertEqual(store.storage_status()["counts"]["events"], 2)

    def test_deferred_save_coalesces_duplicate_observations_in_one_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRuntimeStateStore(Path(directory) / "state.sqlite3")
            state = RuntimeState()
            store.save(state)
            for index in range(3):
                state.record_observation(
                    RuntimeObservation(
                        name="mobile.screen_capture_health",
                        value="healthy",
                        source_device_id="phone-1",
                        source_capability="mobile.context",
                        source_event_id=f"event-{index}",
                        observed_at=f"2026-08-01T10:00:0{index}Z",
                        confidence=1.0,
                    )
                )

            store.save(state, deferred=True)
            store.flush()

            self.assertEqual(store.storage_status()["counts"]["observations"], 1)

    def test_flush_failure_restores_uncoalesced_pending_operations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRuntimeStateStore(
                Path(directory) / "state.sqlite3",
                batch_size=8,
                flush_interval_s=60,
            )
            state = RuntimeState()
            store.save(state)
            state.register_device("terminal-1", "desktop-cli")
            state.register_device("terminal-1", "desktop-cli")
            store.save(state, deferred=True)
            pending = list(store._pending_operations)

            with patch.object(
                store,
                "_apply_operation",
                side_effect=RuntimeError("flush failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "flush failed"):
                    store.flush()

            self.assertEqual(store._pending_operations, pending)
            store.flush()
            self.assertIn("terminal-1", store.load().devices)

    def test_close_releases_connection_when_flush_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRuntimeStateStore(
                Path(directory) / "state.sqlite3",
                batch_size=8,
                flush_interval_s=60,
            )
            state = RuntimeState()
            store.save(state)
            state.record_event({"event_id": "event-1"})
            store.save(state, deferred=True)

            with patch.object(
                store,
                "_apply_operation",
                side_effect=RuntimeError("flush failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "flush failed"):
                    store.close()

            self.assertIsNone(store._connection)
            self.assertTrue(store._pending_operations)

    def test_legacy_import_restores_sqlite_synchronous_mode_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRuntimeStateStore(Path(directory) / "state.sqlite3")

            with self.assertRaisesRegex(ValueError, "unknown legacy import entry"):
                store.import_legacy(
                    iter([("unsupported", "events", {}, 0)])
                )

            synchronous = store._connection.execute(
                "PRAGMA synchronous"
            ).fetchone()[0]
            self.assertEqual(synchronous, 1)
            store.close()

    def test_write_quota_rejects_large_mutation_and_preserves_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            store = SQLiteRuntimeStateStore(path)
            store.save(RuntimeState())
            store.database_limit_bytes = store.storage_status()["bytes"]["live_pages"] + 1024
            state = RuntimeState()
            state.record_event({"event_id": "large", "payload": {"text": "x" * 100_000}})

            with self.assertRaises(StorageQuotaExceeded):
                store.save(state)

            self.assertNotIn("large", {event.get("event_id") for event in store.load().events})
            store.database_limit_bytes += 300_000
            store.flush()
            self.assertEqual(store.load().events[-1]["event_id"], "large")

    def test_initial_snapshot_honors_database_quota(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRuntimeStateStore(
                Path(directory) / "state.sqlite3",
                database_limit_bytes=1,
            )

            with self.assertRaises(StorageQuotaExceeded):
                store.save(RuntimeState())

            store.close()

    def test_quota_compaction_reclaims_eligible_history_before_rejecting_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            store = SQLiteRuntimeStateStore(path)
            state = RuntimeState()
            state.events.extend(
                {
                    "event_id": f"old-{index}",
                    "timestamp": "2020-01-01T00:00:00Z",
                    "payload": {"text": "x" * 10_000},
                }
                for index in range(20)
            )
            store.save(state)
            store.database_limit_bytes = 128 * 1024

            result = store.enforce_retention(
                now="2026-08-01T00:00:00Z",
                policy=RetentionPolicy(
                    raw_event_limit=1,
                    raw_observation_limit=1,
                    database_limit_bytes=128 * 1024,
                ),
            )

            self.assertEqual(store.storage_status()["counts"]["events"], 0)
            self.assertLessEqual(result["quota_bytes"], 128 * 1024)

    def test_load_bounds_hot_history_but_preserves_active_interaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRuntimeStateStore(
                Path(directory) / "state.sqlite3",
                hot_observation_limit=3,
                hot_event_limit=2,
            )
            state = RuntimeState()
            for index in range(6):
                state.events.append(
                    {
                        "type": "event_push",
                        "event_id": f"event-{index}",
                        "timestamp": f"2026-08-01T10:00:0{index}Z",
                    }
                )
                state.record_observation(
                    RuntimeObservation(
                        name="terminal.activity",
                        value=index,
                        source_device_id="terminal-1",
                        source_capability="terminal.context",
                        source_event_id=f"event-{index}",
                        observed_at=f"2026-08-01T10:00:0{index}Z",
                        confidence=1.0,
                    )
                )
            registration = InteractionPool(state).register(
                origin="explicit_user",
                causal_scope={"key": "request:1"},
                trigger={"text": "keep this active"},
                participant_device_ids=["terminal-1"],
                source_device_id="terminal-1",
            )
            state.update_interaction(registration.interaction.interaction_id, status="awaiting_action_results")

            store.save(state)
            restored = store.load()

            self.assertEqual(len(restored.events), 2)
            self.assertEqual(restored.events[-1]["event_id"], "event-5")
            self.assertEqual(len(restored.observations), 3)
            self.assertEqual(restored.observations[-1].value, 5)
            self.assertEqual(len(restored.interactions), 1)
            self.assertEqual(restored.interactions[0]["status"], "awaiting_action_results")

    def test_load_keeps_active_interactions_even_when_completed_history_is_large(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRuntimeStateStore(
                Path(directory) / "state.sqlite3",
                hot_interaction_limit=2,
            )
            state = RuntimeState()
            active = InteractionPool(state).register(
                origin="explicit_user",
                causal_scope={"key": "active:old"},
                trigger={"text": "active"},
                participant_device_ids=["terminal-1"],
            )
            for index in range(5):
                completed = InteractionPool(state).register(
                    origin="explicit_user",
                    causal_scope={"key": f"completed:{index}"},
                    trigger={"text": "done"},
                    participant_device_ids=["terminal-1"],
                )
                InteractionPool(state).complete(completed.interaction.interaction_id)
            store.save(state)

            restored = store.load()

            self.assertIn(
                active.interaction.interaction_id,
                {item["interaction_id"] for item in restored.interactions},
            )

    def test_compact_removes_old_history_without_deleting_active_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRuntimeStateStore(Path(directory) / "state.sqlite3")
            state = RuntimeState()
            state.events.extend(
                [
                    {"event_id": "old", "timestamp": "2020-01-01T00:00:00Z"},
                    {"event_id": "new", "timestamp": "2026-08-01T10:00:00Z"},
                ]
            )
            registration = InteractionPool(state).register(
                origin="observation_driven",
                causal_scope={"key": "health:1"},
                trigger={"reason_code": "health_degraded"},
                participant_device_ids=["host-1"],
                source_device_id="host-1",
            )
            state.update_interaction(registration.interaction.interaction_id, status="planned")
            store.save(state)

            result = store.compact(
                before="2026-01-01T00:00:00Z",
                preserve_active=True,
            )
            restored = store.load()

            self.assertGreaterEqual(result["deleted"], 1)
            self.assertEqual([item["event_id"] for item in restored.events], ["new"])
            self.assertEqual(len(restored.interactions), 1)

    def test_compact_preserves_records_linked_to_active_interaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRuntimeStateStore(Path(directory) / "state.sqlite3")
            state = RuntimeState()
            registration = InteractionPool(state).register(
                origin="explicit_user",
                causal_scope={"key": "request:pending"},
                trigger={"text": "keep action result correlation"},
                participant_device_ids=["terminal-1"],
                source_device_id="terminal-1",
            )
            interaction_id = registration.interaction.interaction_id
            state.record_action_result(
                {
                    "interaction_id": interaction_id,
                    "interaction_turn_id": "turn-1",
                    "request_id": "request-1",
                    "status": "ok",
                    "recorded_at": "2020-01-01T00:00:00Z",
                }
            )
            store.save(state)

            store.compact(before="2026-01-01T00:00:00Z")

            restored = store.load()
            self.assertEqual(len(restored.action_results), 1)
            self.assertEqual(restored.action_results[0]["request_id"], "request-1")

    def test_compact_preserves_links_when_active_interaction_has_no_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRuntimeStateStore(Path(directory) / "state.sqlite3")
            state = RuntimeState()
            state.interactions.append({"interaction_id": "legacy-active"})
            state.record_action_result(
                {
                    "interaction_id": "legacy-active",
                    "request_id": "request-legacy",
                    "recorded_at": "2020-01-01T00:00:00Z",
                }
            )
            store.save(state)

            store.compact(before="2026-01-01T00:00:00Z")

            restored = store.load()
            self.assertEqual(restored.interactions[0]["interaction_id"], "legacy-active")
            self.assertEqual(restored.action_results[0]["request_id"], "request-legacy")

    def test_storage_status_exposes_counts_and_size_without_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            store = SQLiteRuntimeStateStore(path)
            state = RuntimeState()
            state.events.append(
                {
                    "event_id": "event-1",
                    "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                }
            )
            store.save(state)

            status = store.storage_status()
            encoded = json.dumps(status, ensure_ascii=True)

            self.assertEqual(status["schema_version"], SCHEMA_VERSION)
            self.assertEqual(status["counts"]["events"], 1)
            self.assertGreater(status["bytes"]["database"], 0)
            self.assertEqual(status["recent_write_volume"]["total"], 1)
            self.assertIn("eligible_records", status["old_data_eligibility"])
            self.assertNotIn("event-1", encoded)

    def test_balanced_retention_enforces_collection_count_limits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRuntimeStateStore(Path(directory) / "state.sqlite3")
            state = RuntimeState()
            for index in range(4):
                state.events.append(
                    {"event_id": f"event-{index}", "timestamp": "2026-08-01T10:00:00Z"}
                )
            store.save(state)

            result = store.enforce_retention(
                now="2026-08-01T12:00:00Z",
                policy=RetentionPolicy(raw_event_limit=2, raw_observation_limit=2),
            )

            self.assertEqual(result["profile"], "balanced")
            self.assertEqual(store.storage_status()["counts"]["events"], 2)

    def test_export_writes_replayable_history_without_changing_hot_limits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = SQLiteRuntimeStateStore(
                root / "state.sqlite3",
                hot_event_limit=1,
            )
            state = RuntimeState()
            state.events.extend(
                [
                    {"event_id": "event-1", "timestamp": "2026-08-01T10:00:00Z"},
                    {"event_id": "event-2", "timestamp": "2026-08-01T10:00:01Z"},
                ]
            )
            store.save(state)
            output = root / "replay.json"

            result = store.export_json(output)

            self.assertEqual(result["records"], 2)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual([item["event_id"] for item in payload["events"]], ["event-1", "event-2"])

    def test_export_removes_temporary_file_when_replace_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = SQLiteRuntimeStateStore(root / "state.sqlite3")
            state = RuntimeState()
            state.events.append({"event_id": "event-1"})
            store.save(state)
            output = root / "replay.json"

            with patch(
                "personal_runtime.sqlite_state_store.os.replace",
                side_effect=OSError("replace failed"),
            ):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    store.export_json(output)

            self.assertFalse((root / ".replay.json.tmp").exists())
            store.close()


if __name__ == "__main__":
    unittest.main()
