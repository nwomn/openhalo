import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.interaction_pool import InteractionPool
from personal_runtime.runtime_state import RuntimeState
from personal_runtime.sqlite_state_store import SQLiteRuntimeStateStore
from personal_runtime.state_migration import export_sqlite_to_json
from personal_runtime.state_migration import migrate_json_to_sqlite
from personal_runtime.state_migration import sha256_file
from personal_runtime.state_migration import write_bounded_legacy_snapshot
from personal_runtime.sqlite_state_store import SCHEMA_VERSION


class StateMigrationTests(unittest.TestCase):
    def test_migrates_legacy_json_without_loading_the_full_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "state.json"
            target = root / "state.sqlite3"
            state = RuntimeState()
            state.register_device("terminal-1", "desktop-cli")
            state.events.append(
                {
                    "event_id": "event-1",
                    "type": "event_push",
                    "timestamp": "2026-08-01T10:00:00Z",
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
            interaction = InteractionPool(state).register(
                origin="explicit_user",
                causal_scope={"key": "request:1"},
                trigger={"text": "keep pending action"},
                participant_device_ids=["terminal-1"],
                source_device_id="terminal-1",
            )
            InteractionPool(state).record_action_batch(
                interaction.interaction.interaction_id,
                interaction_turn_id="turn-1",
                action_batch_id="batch-1",
                action_requests=[("request-1", "action-1")],
            )
            source.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")

            with patch("json.load", side_effect=AssertionError("whole-document load")):
                result = migrate_json_to_sqlite(source, target)

            restored = SQLiteRuntimeStateStore(target).load()
            self.assertEqual(result["schema_version"], SCHEMA_VERSION)
            self.assertEqual(restored.events[0]["event_id"], "event-1")
            self.assertEqual(restored.observations[0].name, "terminal.activity")
            self.assertEqual(restored.interactions[0]["status"], "awaiting_action_results")
            self.assertEqual(restored.interactions[0]["turns"][0]["request_id"], "request-1")

    def test_failed_migration_removes_incomplete_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "state.json"
            target = root / "state.sqlite3"
            source.write_text('{"events": [}', encoding="utf-8")

            with self.assertRaises(ValueError):
                migrate_json_to_sqlite(source, target)

            self.assertFalse(target.exists())
            self.assertFalse(Path(f"{target}.migrating").exists())

    def test_failed_migration_removes_temporary_sqlite_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "state.json"
            target = root / "state.sqlite3"
            source.write_text('{"events": [}', encoding="utf-8")
            Path(f"{target}.migrating-wal").write_bytes(b"stale")
            Path(f"{target}.migrating-shm").write_bytes(b"stale")

            with self.assertRaises(ValueError):
                migrate_json_to_sqlite(source, target)

            self.assertFalse(Path(f"{target}.migrating-wal").exists())
            self.assertFalse(Path(f"{target}.migrating-shm").exists())

    def test_migration_replaces_stale_temporary_sqlite_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "state.json"
            target = root / "state.sqlite3"
            source.write_text(
                json.dumps({"events": [{"event_id": "fresh"}]}),
                encoding="utf-8",
            )
            Path(f"{target}.migrating").touch()

            migrate_json_to_sqlite(source, target)

            self.assertTrue(target.exists())
            self.assertEqual(
                SQLiteRuntimeStateStore(target).load().events[0]["event_id"],
                "fresh",
            )

    def test_migration_rejects_trailing_json_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "state.json"
            target = root / "state.sqlite3"
            source.write_text('{} trailing', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "trailing"):
                migrate_json_to_sqlite(source, target)

            self.assertFalse(target.exists())
            self.assertFalse(Path(f"{target}.migrating").exists())

    def test_migration_preserves_records_with_duplicate_legacy_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "state.json"
            target = root / "state.sqlite3"
            source.write_text(
                json.dumps(
                    {
                        "events": [
                            {"event_id": "duplicate", "payload": {"value": 1}},
                            {"event_id": "duplicate", "payload": {"value": 2}},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            migrate_json_to_sqlite(source, target)

            restored = SQLiteRuntimeStateStore(target).load()
            self.assertEqual(len(restored.events), 2)
            self.assertEqual(
                [event["payload"]["value"] for event in restored.events],
                [1, 2],
            )

    def test_migration_cleans_temporary_target_when_store_close_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "state.json"
            target = root / "state.sqlite3"
            source.write_text('{}', encoding="utf-8")

            with patch(
                "personal_runtime.state_migration.SQLiteRuntimeStateStore.close",
                side_effect=RuntimeError("close failed"),
            ):
                with self.assertRaisesRegex(ValueError, "close failed"):
                    migrate_json_to_sqlite(source, target)

            self.assertFalse(target.exists())
            self.assertFalse(Path(f"{target}.migrating").exists())

    def test_exports_sqlite_to_legacy_json_for_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sqlite_path = root / "state.sqlite3"
            json_path = root / "state.json"
            state = RuntimeState()
            state.events.append({"event_id": "event-1", "timestamp": "2026-08-01T10:00:00Z"})
            SQLiteRuntimeStateStore(sqlite_path).save(state)

            result = export_sqlite_to_json(sqlite_path, json_path)

            self.assertEqual(result["schema_version"], "json-v1")
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["events"][0]["event_id"], "event-1")
            self.assertNotIn("storage_schema", payload)
            second_sqlite = root / "second.sqlite3"
            migrate_json_to_sqlite(json_path, second_sqlite)
            self.assertEqual(
                SQLiteRuntimeStateStore(second_sqlite).load().events[0]["event_id"],
                "event-1",
            )

    def test_bounded_legacy_snapshot_replaces_full_json_after_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "state.json"
            target = root / "state.sqlite3"
            state = RuntimeState()
            for index in range(2_100):
                state.events.append({"event_id": f"event-{index}"})
            source.write_text(json.dumps(state.to_dict()), encoding="utf-8")
            migrate_json_to_sqlite(source, target)

            write_bounded_legacy_snapshot(target, source)

            payload = json.loads(source.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["events"]), 2_000)
            self.assertEqual(
                SQLiteRuntimeStateStore(target).metadata()["legacy_source_sha256"],
                sha256_file(source),
            )


if __name__ == "__main__":
    unittest.main()
