"""SQLite-backed runtime state persistence with a bounded hot projection."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from threading import RLock
from typing import Any

from personal_runtime.runtime_state import RuntimeState
from personal_runtime.runtime_state import sanitize_event_for_storage


SCHEMA_VERSION = "sqlite-v2"


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    profile: str = "balanced"
    raw_days: int = 7
    raw_event_limit: int = 50_000
    raw_observation_limit: int = 250_000
    completed_interaction_days: int = 30
    completed_interaction_limit: int = 5_000
    database_limit_bytes: int = 512 * 1024 * 1024


class StorageQuotaExceeded(RuntimeError):
    """Raised when a mutation cannot fit within the configured DB budget."""

    def __init__(self, *, limit_bytes: int, observed_bytes: int) -> None:
        self.limit_bytes = limit_bytes
        self.observed_bytes = observed_bytes
        super().__init__(
            "SQLite state storage quota exceeded: "
            f"{observed_bytes} bytes used, {limit_bytes} byte limit"
        )
_HISTORY_COLLECTIONS = (
    "events",
    "action_results",
    "interactions",
    "observations",
    "interventions",
    "memory_consolidation_candidates",
    "harness_traces",
    "internal_tool_events",
    "hermes_memory_events",
)
_STATE_VALUE_KEYS = (
    "devices",
    "device_registry",
    "capability_registry",
    "observation_registry",
    "tasks",
    "interaction_sequence",
    "interaction_turn_sequence",
    "proactive_trigger_state",
    "model_health",
    "mobile_liveness",
    "managed_host_edge",
    "action_registry",
    "harness_memory",
    "main_session",
    "interaction_work",
)
_INTERACTION_LINKED_COLLECTIONS = {
    "action_results",
    "interventions",
    "memory_consolidation_candidates",
    "harness_traces",
    "internal_tool_events",
    "hermes_memory_events",
}


class SQLiteRuntimeStateStore:
    """Persist RuntimeState records without serializing the full history."""

    def __init__(
        self,
        path: Path,
        *,
        hot_event_limit: int = 2_000,
        hot_observation_limit: int = 10_000,
        hot_interaction_limit: int = 500,
        batch_size: int = 128,
        flush_interval_s: float = 0.25,
        database_limit_bytes: int = RetentionPolicy().database_limit_bytes,
    ) -> None:
        if min(hot_event_limit, hot_observation_limit, hot_interaction_limit) < 1:
            raise ValueError("hot history limits must be positive")
        self.path = Path(path)
        self.hot_event_limit = hot_event_limit
        self.hot_observation_limit = hot_observation_limit
        self.hot_interaction_limit = hot_interaction_limit
        if batch_size < 1 or flush_interval_s <= 0:
            raise ValueError("SQLite batch settings must be positive")
        if database_limit_bytes < 1:
            raise ValueError("SQLite database limit must be positive")
        self.batch_size = batch_size
        self.flush_interval_s = flush_interval_s
        self.database_limit_bytes = database_limit_bytes
        self._lock = RLock()
        self._connection: sqlite3.Connection | None = None
        self._pending_operations: list[dict[str, Any]] = []
        self._last_flush_at = time.monotonic()
        self._initialize()

    def load(self) -> RuntimeState:
        with self._lock:
            connection = self._connect()
            state = RuntimeState()
            values = {
                row["key"]: json.loads(row["payload"])
                for row in connection.execute(
                    "SELECT key, payload FROM state_values"
                )
            }
            payload: dict[str, Any] = dict(values)
            payload["devices"] = values.get("devices", {})
            payload["device_registry"] = values.get("device_registry", {})
            payload["capability_registry"] = values.get("capability_registry", {})
            payload["observation_registry"] = values.get("observation_registry", {})
            payload["tasks"] = values.get("tasks", [])
            payload["interaction_sequence"] = values.get("interaction_sequence", 0)
            payload["interaction_turn_sequence"] = values.get(
                "interaction_turn_sequence",
                0,
            )
            payload["proactive_trigger_state"] = values.get(
                "proactive_trigger_state",
                {},
            )
            payload["model_health"] = values.get("model_health", {})
            payload["mobile_liveness"] = values.get("mobile_liveness", {})
            payload["managed_host_edge"] = values.get("managed_host_edge", {})
            payload["action_registry"] = values.get("action_registry", {})
            payload["harness_memory"] = values.get("harness_memory", {})
            payload["main_session"] = values.get("main_session", {})
            payload["interaction_work"] = values.get("interaction_work", [])
            state.replace_context_facts(self.load_context_facts())
            for collection in _HISTORY_COLLECTIONS:
                limit = self._hot_limit(collection)
                if collection == "interactions":
                    rows = connection.execute(
                        """
                        SELECT payload
                        FROM records
                        WHERE collection = ?
                          AND (
                            id IN (
                                SELECT id FROM records
                                WHERE collection = ?
                                ORDER BY id DESC LIMIT ?
                            )
                            OR COALESCE(json_extract(payload, '$.status'), 'planned')
                               != 'completed'
                          )
                        ORDER BY id ASC
                        """,
                        (collection, collection, limit),
                    ).fetchall()
                elif collection in _INTERACTION_LINKED_COLLECTIONS:
                    rows = connection.execute(
                        """
                        SELECT payload
                        FROM records
                        WHERE collection = ?
                          AND (
                            id IN (
                                SELECT id FROM records
                                WHERE collection = ?
                                ORDER BY id DESC LIMIT ?
                            )
                            OR json_extract(payload, '$.interaction_id') IN (
                                SELECT json_extract(payload, '$.interaction_id')
                                FROM records
                                WHERE collection = 'interactions'
                                  AND COALESCE(json_extract(payload, '$.status'), 'planned')
                                      != 'completed'
                            )
                          )
                        ORDER BY id ASC
                        """,
                        (collection, collection, limit),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """
                        SELECT payload
                        FROM records
                        WHERE collection = ?
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (collection, limit),
                    ).fetchall()
                payload[collection] = [
                    json.loads(row["payload"]) for row in reversed(rows)
                ]
            restored = RuntimeState.from_dict(payload)
            restored.replace_context_facts(self.load_context_facts())
            return restored

    def save(self, state: RuntimeState, *, deferred: bool = False) -> None:
        with self._lock:
            connection = self._connect()
            if self._is_empty(connection):
                self._ensure_write_capacity([])
                connection.execute("BEGIN IMMEDIATE")
                try:
                    self._replace_from_state(connection, state)
                    self._ensure_connection_capacity(connection)
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
                try:
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
                state.drain_storage_operations()
                self._set_private_mode()
                return

            operations = state.drain_storage_operations()
            if not operations:
                return
            self._pending_operations.extend(operations)
            if deferred and (
                len(self._pending_operations) < self.batch_size
                and time.monotonic() - self._last_flush_at < self.flush_interval_s
            ):
                return
            self.flush()

    def flush(self) -> None:
        with self._lock:
            if not self._pending_operations:
                return
            connection = self._connect()
            pending_operations = list(self._pending_operations)
            operations = self._coalesce_operations(pending_operations)
            self._pending_operations = []
            try:
                self._ensure_write_capacity(operations)
                connection.execute("BEGIN IMMEDIATE")
                try:
                    for operation in operations:
                        self._apply_operation(connection, operation)
                    self._ensure_connection_capacity(connection)
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
                try:
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
            except Exception:
                self._pending_operations = pending_operations + self._pending_operations
                raise
            self._last_flush_at = time.monotonic()
            self._set_private_mode()

    @staticmethod
    def _coalesce_operations(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        positions: dict[tuple, int] = {}
        for operation in operations:
            if operation["kind"] == "state_value":
                key = ("state_value", operation["key"])
            elif operation["collection"] == "observations":
                payload = operation["payload"]
                key = (
                    "observation",
                    payload.get("source_device_id"),
                    payload.get("source_capability"),
                    payload.get("name"),
                    _json(payload.get("value")),
                )
            elif operation.get("record_key") is not None:
                key = ("record", operation["collection"], operation["record_key"])
            else:
                result.append(operation)
                continue
            if key in positions:
                result[positions[key]] = operation
            else:
                positions[key] = len(result)
                result.append(operation)
        return result

    def import_legacy(self, entries) -> None:
        """Import streamed JSON members into a new empty database."""

        with self._lock:
            connection = self._connect()
            if not self._is_empty(connection):
                raise ValueError("SQLite import target is not empty")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute("DROP INDEX IF EXISTS records_collection_id")
            connection.execute("DROP INDEX IF EXISTS records_collection_time")
            try:
                record_batch = []
                used_record_keys: set[tuple[str, str]] = set()
                connection.execute("BEGIN IMMEDIATE")
                try:
                    for kind, key, payload, ordinal in entries:
                        if kind == "state_value":
                            connection.execute(
                                "INSERT INTO state_values(key, payload) VALUES(?, ?)",
                                (key, _json(payload)),
                            )
                        elif kind == "record":
                            encoded = _encode_payload(payload, collection=key)
                            record_key, recorded_at = _record_metadata_from_payload(
                                key,
                                payload,
                                ordinal,
                            )
                            record_key = _unique_record_key(
                                key,
                                record_key,
                                used_record_keys,
                            )
                            used_record_keys.add((key, record_key))
                            record_batch.append((key, record_key, recorded_at, encoded))
                            if len(record_batch) >= 10_000:
                                connection.executemany(
                                    """
                                    INSERT INTO records(
                                        collection, record_key, recorded_at, payload
                                    ) VALUES(?, ?, ?, ?)
                                    """,
                                    record_batch,
                                )
                                record_batch.clear()
                        elif kind == "context_fact":
                            connection.execute(
                                """
                                INSERT INTO context_facts(
                                    fact_id, source_device_id, observation_name,
                                    value_payload, confidence, observed_at, expires_at,
                                    disposition, provenance_payload, fact_version,
                                    withheld_reason
                                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    payload["fact_id"], payload["source_device_id"],
                                    payload["observation_name"], _json(payload["value"]),
                                    payload["confidence"], payload["observed_at"],
                                    payload["expires_at"], payload["disposition"],
                                    _json(payload["provenance"]), payload["version"],
                                    payload.get("withheld_reason"),
                                ),
                            )
                        else:
                            raise ValueError(f"unknown legacy import entry: {kind}")
                    if record_batch:
                        connection.executemany(
                            """
                            INSERT INTO records(
                                collection, record_key, recorded_at, payload
                            ) VALUES(?, ?, ?, ?)
                            """,
                            record_batch,
                        )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
                try:
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
            finally:
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS records_collection_id "
                    "ON records(collection, id)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS records_collection_time "
                    "ON records(collection, recorded_at)"
                )
                connection.execute("PRAGMA synchronous=NORMAL")
            self._set_private_mode()

    def compact(
        self,
        *,
        before: str,
        preserve_active: bool = True,
        collections: tuple[str, ...] | None = None,
    ) -> dict[str, int]:
        """Delete eligible historical rows and reclaim SQLite pages."""

        with self._lock:
            connection = self._connect()
            deleted = 0
            connection.execute("BEGIN IMMEDIATE")
            try:
                for collection in collections or _HISTORY_COLLECTIONS:
                    if collection == "interactions" and preserve_active:
                        cursor = connection.execute(
                            """
                            DELETE FROM records
                            WHERE collection = ?
                              AND recorded_at < ?
                              AND json_extract(payload, '$.status') = 'completed'
                            """,
                            (collection, before),
                        )
                    elif preserve_active and collection in _INTERACTION_LINKED_COLLECTIONS:
                        cursor = connection.execute(
                            """
                            DELETE FROM records
                            WHERE collection = ?
                              AND recorded_at < ?
                              AND (
                                json_extract(payload, '$.interaction_id') IS NULL
                                OR NOT EXISTS (
                                    SELECT 1
                                    FROM records active
                                    WHERE active.collection = 'interactions'
                                      AND json_extract(active.payload, '$.interaction_id')
                                          = json_extract(records.payload, '$.interaction_id')
                                      AND COALESCE(
                                            json_extract(active.payload, '$.status'),
                                            'planned'
                                          ) != 'completed'
                                )
                              )
                            """,
                            (collection, before),
                        )
                    else:
                        cursor = connection.execute(
                            """
                            DELETE FROM records
                            WHERE collection = ? AND recorded_at < ?
                            """,
                            (collection, before),
                        )
                    deleted += cursor.rowcount
            except Exception:
                connection.execute("ROLLBACK")
                raise
            try:
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
            self._reclaim_sqlite_pages(connection)
            self._set_private_mode()
            return {"deleted": deleted}

    def enforce_retention(
        self,
        *,
        now: str,
        policy: RetentionPolicy | None = None,
    ) -> dict[str, int | str]:
        selected = policy or RetentionPolicy()
        self.flush()
        cutoff = _subtract_days(now, selected.raw_days)
        result = self.compact(
            before=cutoff,
            preserve_active=True,
            collections=("events", "observations"),
        )
        completed_cutoff = _subtract_days(now, selected.completed_interaction_days)
        completed_result = self.compact(
            before=completed_cutoff,
            preserve_active=True,
            collections=(
                "interactions",
                "action_results",
                "interventions",
                "memory_consolidation_candidates",
                "harness_traces",
                "internal_tool_events",
                "hermes_memory_events",
            ),
        )
        result["deleted"] += completed_result["deleted"]
        with self._lock:
            connection = self._connect()
            trimmed = 0
            connection.execute("BEGIN IMMEDIATE")
            try:
                trimmed += self._trim_collection(
                    connection,
                    "events",
                    selected.raw_event_limit,
                )
                trimmed += self._trim_collection(
                    connection,
                    "observations",
                    selected.raw_observation_limit,
                )
                cursor = connection.execute(
                    """
                    DELETE FROM records
                    WHERE collection = 'interactions'
                      AND json_extract(payload, '$.status') = 'completed'
                      AND id NOT IN (
                        SELECT id FROM records
                        WHERE collection = 'interactions'
                          AND json_extract(payload, '$.status') = 'completed'
                        ORDER BY id DESC LIMIT ?
                      )
                    """,
                    (selected.completed_interaction_limit,),
                )
                trimmed += cursor.rowcount
            except Exception:
                connection.execute("ROLLBACK")
                raise
            try:
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
            self._reclaim_sqlite_pages(connection)
            result["trimmed"] = trimmed
            result["profile"] = selected.profile
            limit = min(self.database_limit_bytes, selected.database_limit_bytes)
            result["database_limit_bytes"] = limit
            result["quota_bytes"] = self._enforce_database_limit(limit)
            return result

    def storage_status(self) -> dict[str, Any]:
        with self._lock:
            connection = self._connect()
            now = datetime.now(UTC)
            now_text = now.isoformat().replace("+00:00", "Z")
            recent_cutoff = (now - timedelta(hours=24)).isoformat().replace(
                "+00:00",
                "Z",
            )
            retention = RetentionPolicy()
            raw_cutoff = _subtract_days(now_text, retention.raw_days)
            completed_cutoff = _subtract_days(
                now_text,
                retention.completed_interaction_days,
            )
            counts = {
                collection: connection.execute(
                    "SELECT COUNT(*) FROM records WHERE collection = ?",
                    (collection,),
                ).fetchone()[0]
                for collection in _HISTORY_COLLECTIONS
            }
            recent_by_collection = {
                collection: connection.execute(
                    """
                    SELECT COUNT(*) FROM records
                    WHERE collection = ? AND recorded_at >= ?
                    """,
                    (collection, recent_cutoff),
                ).fetchone()[0]
                for collection in _HISTORY_COLLECTIONS
            }
            eligible = 0
            oldest_recorded_at = None
            for collection in _HISTORY_COLLECTIONS:
                cutoff = (
                    raw_cutoff
                    if collection in {"events", "observations"}
                    else completed_cutoff
                )
                if collection == "interactions":
                    predicate = (
                        "collection = ? AND recorded_at < ? AND "
                        "COALESCE(json_extract(payload, '$.status'), 'planned') = 'completed'"
                    )
                elif collection in _INTERACTION_LINKED_COLLECTIONS:
                    predicate = (
                        "collection = ? AND recorded_at < ? AND "
                        "(json_extract(payload, '$.interaction_id') IS NULL OR NOT EXISTS ("
                        "SELECT 1 FROM records active WHERE active.collection = 'interactions' "
                        "AND json_extract(active.payload, '$.interaction_id') = "
                        "json_extract(records.payload, '$.interaction_id') AND "
                        "COALESCE(json_extract(active.payload, '$.status'), 'planned') != 'completed'))"
                    )
                else:
                    predicate = "collection = ? AND recorded_at < ?"
                eligible += connection.execute(
                    f"SELECT COUNT(*) FROM records WHERE {predicate}",
                    (collection, cutoff),
                ).fetchone()[0]
                oldest = connection.execute(
                    "SELECT MIN(recorded_at) FROM records WHERE collection = ?",
                    (collection,),
                ).fetchone()[0]
                if oldest and (oldest_recorded_at is None or oldest < oldest_recorded_at):
                    oldest_recorded_at = oldest
            page_count = connection.execute("PRAGMA page_count").fetchone()[0]
            page_size = connection.execute("PRAGMA page_size").fetchone()[0]
            freelist_count = connection.execute("PRAGMA freelist_count").fetchone()[0]
            database_bytes = self.path.stat().st_size if self.path.exists() else 0
            wal_path = Path(f"{self.path}-wal")
            shm_path = Path(f"{self.path}-shm")
            wal_bytes = wal_path.stat().st_size if wal_path.exists() else 0
            shm_bytes = shm_path.stat().st_size if shm_path.exists() else 0
            result = {
                "schema_version": SCHEMA_VERSION,
                "counts": counts,
                "bytes": {
                    "database": database_bytes,
                    "wal": wal_bytes,
                    "shm": shm_bytes,
                    "footprint": database_bytes + wal_bytes + shm_bytes,
                    "live_pages": (page_count - freelist_count) * page_size,
                },
                "page_count": page_count,
                "freelist_count": freelist_count,
                "database_limit_bytes": self.database_limit_bytes,
                "recent_write_volume": {
                    "window": "24h",
                    "total": sum(recent_by_collection.values()),
                    "by_collection": recent_by_collection,
                },
                "old_data_eligibility": {
                    "eligible_records": eligible,
                    "oldest_recorded_at": oldest_recorded_at,
                    "raw_cutoff": raw_cutoff,
                    "completed_interaction_cutoff": completed_cutoff,
                },
            }
            self._set_private_mode()
            return result

    def set_metadata(self, key: str, value: str) -> None:
        with self._lock:
            connection = self._connect()
            with connection:
                connection.execute(
                    """
                    INSERT INTO metadata(key, value) VALUES(?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, value),
                )
            self._set_private_mode()

    def metadata(self) -> dict[str, str]:
        with self._lock:
            connection = self._connect()
            return {
                row["key"]: row["value"]
                for row in connection.execute("SELECT key, value FROM metadata")
            }

    def export_json(
        self,
        path: Path,
        *,
        since: str | None = None,
        include_metadata: bool = True,
    ) -> dict[str, Any]:
        """Export a replay/eval artifact from SQLite history."""

        with self._lock:
            self.flush()
            connection = self._connect()
            payload = {
                row["key"]: json.loads(row["payload"])
                for row in connection.execute(
                    "SELECT key, payload FROM state_values"
                )
            }
            record_count = 0
            for collection in _HISTORY_COLLECTIONS:
                if since is None:
                    rows = connection.execute(
                        """
                        SELECT payload FROM records
                        WHERE collection = ? ORDER BY id ASC
                        """,
                        (collection,),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """
                        SELECT payload FROM records
                        WHERE collection = ? AND recorded_at >= ?
                        ORDER BY id ASC
                        """,
                        (collection, since),
                    ).fetchall()
                payload[collection] = [json.loads(row["payload"]) for row in rows]
                record_count += len(rows)
            if include_metadata:
                payload["storage_schema"] = SCHEMA_VERSION
            if include_metadata and since is not None:
                payload["export_since"] = since
            destination = Path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{destination.name}.tmp")
            try:
                temporary.write_text(
                    json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
                    encoding="utf-8",
                )
                os.replace(temporary, destination)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            os.chmod(destination, 0o600)
            return {
                "path": str(destination),
                "records": record_count,
                "schema_version": SCHEMA_VERSION,
            }

    def close(self) -> None:
        with self._lock:
            flush_error = None
            try:
                self.flush()
            except Exception as exc:
                flush_error = exc
            connection = self._connection
            self._connection = None
            try:
                if connection is not None:
                    connection.close()
            except Exception:
                if flush_error is None:
                    raise
            if flush_error is not None:
                raise flush_error

    def _ensure_write_capacity(self, operations: list[dict[str, Any]]) -> None:
        estimated_bytes = sum(self._operation_size(operation) for operation in operations)
        if self._storage_footprint_bytes() + estimated_bytes <= self.database_limit_bytes:
            return
        self._enforce_database_limit(self.database_limit_bytes)
        observed_bytes = self._storage_footprint_bytes()
        if observed_bytes + estimated_bytes > self.database_limit_bytes:
            raise StorageQuotaExceeded(
                limit_bytes=self.database_limit_bytes,
                observed_bytes=observed_bytes + estimated_bytes,
            )

    def _ensure_connection_capacity(self, connection: sqlite3.Connection) -> None:
        observed_bytes = self._storage_footprint_bytes(connection)
        if observed_bytes > self.database_limit_bytes:
            raise StorageQuotaExceeded(
                limit_bytes=self.database_limit_bytes,
                observed_bytes=observed_bytes,
            )

    @staticmethod
    def _operation_size(operation: dict[str, Any]) -> int:
        if operation["kind"] == "state_value":
            return len(_json(operation["payload"]).encode("utf-8"))
        return len(
            _encode_payload(
                operation["payload"],
                collection=operation.get("collection"),
            ).encode("utf-8")
        )

    def _storage_footprint_bytes(
        self,
        connection: sqlite3.Connection | None = None,
    ) -> int:
        database_bytes = self.path.stat().st_size if self.path.exists() else 0
        if connection is not None:
            page_count = connection.execute("PRAGMA page_count").fetchone()[0]
            page_size = connection.execute("PRAGMA page_size").fetchone()[0]
            database_bytes = max(database_bytes, page_count * page_size)
        sidecar_bytes = 0
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{self.path}{suffix}")
            if sidecar.exists():
                sidecar_bytes += sidecar.stat().st_size
        return database_bytes + sidecar_bytes

    def _enforce_database_limit(self, limit_bytes: int) -> int:
        with self._lock:
            connection = self._connect()
            self._reclaim_sqlite_pages(connection)
            observed_bytes = self._storage_footprint_bytes(connection)
            if observed_bytes <= limit_bytes:
                return observed_bytes
            connection.execute("VACUUM")
            self._reclaim_sqlite_pages(connection)
            observed_bytes = self._storage_footprint_bytes(connection)
            while observed_bytes > limit_bytes:
                candidates = connection.execute(
                    """
                    SELECT id
                    FROM records
                    WHERE NOT (
                        collection = 'interactions'
                        AND COALESCE(json_extract(payload, '$.status'), 'planned')
                            != 'completed'
                    )
                      AND (
                        collection NOT IN (
                            'action_results',
                            'interventions',
                            'memory_consolidation_candidates',
                            'harness_traces',
                            'internal_tool_events',
                            'hermes_memory_events'
                        )
                        OR json_extract(payload, '$.interaction_id') IS NULL
                        OR NOT EXISTS (
                            SELECT 1
                            FROM records active
                            WHERE active.collection = 'interactions'
                              AND json_extract(active.payload, '$.interaction_id')
                                  = json_extract(records.payload, '$.interaction_id')
                              AND COALESCE(json_extract(active.payload, '$.status'), 'planned')
                                  != 'completed'
                        )
                      )
                    ORDER BY COALESCE(recorded_at, '') ASC, id ASC
                    LIMIT 256
                    """
                ).fetchall()
                if not candidates:
                    raise StorageQuotaExceeded(
                        limit_bytes=limit_bytes,
                        observed_bytes=observed_bytes,
                    )
                with connection:
                    connection.executemany(
                        "DELETE FROM records WHERE id = ?",
                        [(row["id"],) for row in candidates],
                    )
                self._reclaim_sqlite_pages(connection)
                connection.execute("VACUUM")
                self._reclaim_sqlite_pages(connection)
                observed_bytes = self._storage_footprint_bytes(connection)
            return observed_bytes

    @staticmethod
    def _reclaim_sqlite_pages(connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.execute("PRAGMA incremental_vacuum")

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        with connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS state_values (
                    key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection TEXT NOT NULL,
                    record_key TEXT,
                    recorded_at TEXT,
                    payload TEXT NOT NULL,
                    UNIQUE(collection, record_key)
                );
                CREATE INDEX IF NOT EXISTS records_collection_id
                    ON records(collection, id);
                CREATE INDEX IF NOT EXISTS records_collection_time
                    ON records(collection, recorded_at);
                CREATE TABLE IF NOT EXISTS context_facts (
                    fact_id TEXT PRIMARY KEY,
                    source_device_id TEXT NOT NULL,
                    observation_name TEXT NOT NULL,
                    value_payload TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    observed_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    disposition TEXT NOT NULL,
                    provenance_payload TEXT NOT NULL,
                    fact_version INTEGER NOT NULL,
                    withheld_reason TEXT
                );
                CREATE INDEX IF NOT EXISTS context_facts_source_name
                    ON context_facts(source_device_id, observation_name);
                """
            )
            existing = connection.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
                    (SCHEMA_VERSION,),
                )
            elif existing[0] == "sqlite-v1":
                connection.execute(
                    "UPDATE metadata SET value = ? WHERE key = 'schema_version'",
                    (SCHEMA_VERSION,),
                )
            elif existing[0] != SCHEMA_VERSION:
                raise ValueError(f"unsupported SQLite state schema: {existing[0]}")
        self._set_private_mode()

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(
                self.path,
                timeout=5.0,
                isolation_level=None,
                check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=NORMAL")
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.execute("PRAGMA journal_size_limit=67108864")
            self._connection.execute("PRAGMA auto_vacuum=INCREMENTAL")
        return self._connection

    def upsert_context_fact(self, fact: dict) -> None:
        """Persist one materialized fact without coupling storage to Gateway."""

        required = {
            "fact_id", "source_device_id", "observation_name", "value",
            "confidence", "observed_at", "expires_at", "disposition",
            "provenance", "version",
        }
        missing = required.difference(fact)
        if missing:
            raise ValueError(f"context fact is missing fields: {sorted(missing)}")
        with self._lock:
            connection = self._connect()
            with connection:
                connection.execute(
                    """
                    INSERT INTO context_facts(
                        fact_id, source_device_id, observation_name, value_payload,
                        confidence, observed_at, expires_at, disposition,
                        provenance_payload, fact_version, withheld_reason
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(fact_id) DO UPDATE SET
                        source_device_id = excluded.source_device_id,
                        observation_name = excluded.observation_name,
                        value_payload = excluded.value_payload,
                        confidence = excluded.confidence,
                        observed_at = excluded.observed_at,
                        expires_at = excluded.expires_at,
                        disposition = excluded.disposition,
                        provenance_payload = excluded.provenance_payload,
                        fact_version = excluded.fact_version,
                        withheld_reason = excluded.withheld_reason
                    """,
                    (
                        fact["fact_id"], fact["source_device_id"],
                        fact["observation_name"], _json(fact["value"]),
                        fact["confidence"], fact["observed_at"], fact["expires_at"],
                        fact["disposition"], _json(fact["provenance"]),
                        fact["version"], fact.get("withheld_reason"),
                    ),
                )

    def load_context_facts(self) -> list[dict]:
        with self._lock:
            connection = self._connect()
            rows = connection.execute(
                """
                SELECT fact_id, source_device_id, observation_name, value_payload,
                       confidence, observed_at, expires_at, disposition,
                       provenance_payload, fact_version, withheld_reason
                FROM context_facts ORDER BY fact_id
                """
            ).fetchall()
        return [
            {
                "fact_id": row["fact_id"],
                "source_device_id": row["source_device_id"],
                "observation_name": row["observation_name"],
                "value": json.loads(row["value_payload"]),
                "confidence": row["confidence"],
                "observed_at": row["observed_at"],
                "expires_at": row["expires_at"],
                "disposition": row["disposition"],
                "provenance": json.loads(row["provenance_payload"]),
                "version": row["fact_version"],
                "withheld_reason": row["withheld_reason"],
            }
            for row in rows
        ]

    def _replace_from_state(
        self,
        connection: sqlite3.Connection,
        state: RuntimeState,
    ) -> None:
        connection.execute("DELETE FROM state_values")
        connection.execute("DELETE FROM records")
        for key, payload in self._state_values(state).items():
            connection.execute(
                "INSERT INTO state_values(key, payload) VALUES(?, ?)",
                (key, _json(payload)),
            )
        used_record_keys: set[tuple[str, str]] = set()
        for collection in _HISTORY_COLLECTIONS:
            values = getattr(state, collection)
            for index, payload in enumerate(values):
                encoded = _encode_payload(payload, collection=collection)
                record_key, recorded_at = _record_metadata(collection, encoded, index)
                record_key = _unique_record_key(
                    collection,
                    record_key,
                    used_record_keys,
                )
                used_record_keys.add((collection, record_key))
                connection.execute(
                    """
                    INSERT OR IGNORE INTO records(
                        collection, record_key, recorded_at, payload
                    ) VALUES(?, ?, ?, ?)
                    """,
                    (collection, record_key, recorded_at, encoded),
                )

    def _apply_operation(
        self,
        connection: sqlite3.Connection,
        operation: dict[str, Any],
    ) -> None:
        kind = operation["kind"]
        if kind == "state_value":
            connection.execute(
                """
                INSERT INTO state_values(key, payload) VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET payload = excluded.payload
                """,
                (operation["key"], _json(operation["payload"])),
            )
            return
        if kind != "record":
            raise ValueError(f"unknown SQLite state operation: {kind}")
        collection = operation["collection"]
        encoded = _encode_payload(
            operation["payload"],
            collection=collection,
        )
        key = operation.get("record_key") or _record_key(
            collection,
            encoded,
            operation.get("ordinal", 0),
        )
        connection.execute(
            """
            INSERT INTO records(collection, record_key, recorded_at, payload)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(collection, record_key)
            DO UPDATE SET recorded_at = excluded.recorded_at, payload = excluded.payload
            """,
            (collection, key, _record_metadata(collection, encoded, operation.get("ordinal", 0))[1], encoded),
        )

    def _state_values(self, state: RuntimeState) -> dict[str, Any]:
        return {
            "devices": {
                device_id: {
                    "device_type": payload["device_type"],
                    "capabilities": sorted(payload["capabilities"]),
                }
                for device_id, payload in state.devices.items()
            },
            "device_registry": state.device_registry,
            "capability_registry": state.capability_registry,
            "observation_registry": state.observation_registry,
            "tasks": state.tasks,
            "interaction_sequence": state.interaction_sequence,
            "interaction_turn_sequence": state.interaction_turn_sequence,
            "proactive_trigger_state": state.proactive_trigger_state,
            "model_health": state.model_health,
            "mobile_liveness": state.mobile_liveness,
            "managed_host_edge": state.managed_host_edge,
            "action_registry": state.action_registry,
            "harness_memory": state.harness_memory,
            "main_session": state.main_session,
            "interaction_work": state.interaction_work,
        }

    def _is_empty(self, connection: sqlite3.Connection) -> bool:
        return connection.execute("SELECT COUNT(*) FROM state_values").fetchone()[0] == 0

    def _hot_limit(self, collection: str) -> int:
        if collection == "events":
            return self.hot_event_limit
        if collection == "observations":
            return self.hot_observation_limit
        if collection == "interactions":
            return self.hot_interaction_limit
        return max(self.hot_interaction_limit, 2_000)

    @staticmethod
    def _trim_collection(
        connection: sqlite3.Connection,
        collection: str,
        limit: int,
    ) -> int:
        cursor = connection.execute(
            """
            DELETE FROM records
            WHERE collection = ?
              AND id NOT IN (
                SELECT id FROM records
                WHERE collection = ?
                ORDER BY id DESC LIMIT ?
              )
            """,
            (collection, collection, limit),
        )
        return cursor.rowcount

    def _set_private_mode(self) -> None:
        for path in (
            self.path,
            Path(f"{self.path}-wal"),
            Path(f"{self.path}-shm"),
        ):
            try:
                os.chmod(path, 0o600)
            except FileNotFoundError:
                continue


def _encode_payload(payload: Any, *, collection: str | None = None) -> str:
    if hasattr(payload, "to_dict"):
        payload = payload.to_dict()
    if collection == "events" and isinstance(payload, dict):
        payload = sanitize_event_for_storage(payload)
    return _json(payload)


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _record_key(collection: str, encoded: str, ordinal: int) -> str:
    return _record_metadata(collection, encoded, ordinal)[0]


def _unique_record_key(
    collection: str,
    record_key: str,
    used_record_keys: set[tuple[str, str]],
) -> str:
    candidate = record_key
    suffix = 1
    while (collection, candidate) in used_record_keys:
        candidate = f"{record_key}~{suffix}"
        suffix += 1
    return candidate


def _record_metadata(collection: str, encoded: str, ordinal: int) -> tuple[str, str]:
    return _record_metadata_from_payload(collection, json.loads(encoded), ordinal)


def _record_metadata_from_payload(
    collection: str,
    payload: Any,
    ordinal: int,
) -> tuple[str, str]:
    if not isinstance(payload, dict):
        payload = {}
    encoded = _json(payload)
    if collection == "interactions" and payload.get("interaction_id"):
        record_key = str(payload["interaction_id"])
    elif collection == "action_results" and payload.get("request_id"):
        record_key = ":".join(
            str(payload.get(field, ""))
            for field in ("interaction_id", "interaction_turn_id", "request_id")
        )
    elif collection == "observations":
        record_key = ":".join(
            str(payload.get(field, ""))
            for field in ("source_event_id", "name", "observed_at")
        )
    elif payload.get("event_id"):
        record_key = str(payload["event_id"])
    else:
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]
        record_key = f"{ordinal}:{digest}"
    candidates = (
        "observed_at",
        "recorded_at",
        "timestamp",
        "updated_at",
        "created_at",
    )
    for field in candidates:
        value = payload.get(field)
        if isinstance(value, str) and value:
            return record_key, value
    if collection == "events":
        nested = payload.get("payload")
        if isinstance(nested, dict) and isinstance(nested.get("observed_at"), str):
            return record_key, nested["observed_at"]
    return record_key, datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _recorded_at(collection: str, encoded: str) -> str:
    return _record_metadata(collection, encoded, 0)[1]


def _subtract_days(timestamp: str, days: int) -> str:
    value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return (value - timedelta(days=days)).isoformat().replace(
        "+00:00",
        "Z",
    )


__all__ = [
    "RetentionPolicy",
    "SCHEMA_VERSION",
    "SQLiteRuntimeStateStore",
    "StorageQuotaExceeded",
]
