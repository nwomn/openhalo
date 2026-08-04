"""Durable, paged Edge-local journal for normalized Coding activity."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path


class CodingActivityJournal:
    """Append activity without imposing a small event-count limit on active tasks."""

    def __init__(self, path: str | Path, *, quota_bytes: int = 2 * 1024**3) -> None:
        if quota_bytes < 1:
            raise ValueError("Coding activity quota must be positive.")
        self.path = Path(path).expanduser().resolve()
        self.quota_bytes = quota_bytes
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS coding_tasks (
                    interaction_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    workspace_ref TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS coding_activities (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    interaction_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    event_kind TEXT NOT NULL,
                    observation_json TEXT NOT NULL,
                    FOREIGN KEY(interaction_id) REFERENCES coding_tasks(interaction_id)
                );
                CREATE INDEX IF NOT EXISTS coding_activities_task_sequence
                ON coding_activities(interaction_id, sequence DESC);
                """
            )
        os.chmod(self.path, 0o600)

    def append(self, observation: dict) -> int:
        value = observation.get("value")
        if not isinstance(value, dict):
            raise ValueError("Coding activity observation value must be an object.")
        interaction_id = value.get("interaction_id")
        if not isinstance(interaction_id, str) or not interaction_id:
            raise ValueError("Coding activity requires an interaction_id.")
        required = ("agent_session_id", "agent_turn_id", "workspace_ref", "event_kind")
        if any(not isinstance(value.get(key), str) or not value[key] for key in required):
            raise ValueError("Coding activity is missing task lineage.")
        observed_at = observation.get("observed_at") or value.get("observed_at")
        if not isinstance(observed_at, str) or not observed_at:
            raise ValueError("Coding activity requires observed_at.")
        payload = json.dumps(observation, ensure_ascii=False, separators=(",", ":"))
        status = _task_status(value["event_kind"], value.get("phase"))
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO coding_tasks(
                    interaction_id, thread_id, turn_id, workspace_ref, status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(interaction_id) DO UPDATE SET
                    thread_id=excluded.thread_id,
                    turn_id=excluded.turn_id,
                    workspace_ref=excluded.workspace_ref,
                    status=CASE
                        WHEN coding_tasks.thread_id = excluded.thread_id
                            AND coding_tasks.turn_id = excluded.turn_id
                            AND coding_tasks.status = 'completed'
                            AND excluded.status = 'active'
                        THEN coding_tasks.status
                        ELSE excluded.status
                    END,
                    updated_at=excluded.updated_at
                """,
                (
                    interaction_id,
                    value["agent_session_id"],
                    value["agent_turn_id"],
                    value["workspace_ref"],
                    status,
                    observed_at,
                ),
            )
            cursor = connection.execute(
                """
                INSERT INTO coding_activities(
                    interaction_id, observed_at, event_kind, observation_json
                ) VALUES (?, ?, ?, ?)
                """,
                (interaction_id, observed_at, value["event_kind"], payload),
            )
            return int(cursor.lastrowid)

    def page(
        self,
        interaction_id: str,
        *,
        before_sequence: int | None = None,
        limit: int = 200,
    ) -> list[dict]:
        safe_limit = max(1, min(int(limit), 500))
        query = (
            "SELECT sequence, observation_json FROM coding_activities "
            "WHERE interaction_id = ?"
        )
        parameters: list[object] = [interaction_id]
        if before_sequence is not None:
            query += " AND sequence < ?"
            parameters.append(before_sequence)
        query += " ORDER BY sequence DESC LIMIT ?"
        parameters.append(safe_limit)
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        result = []
        for row in reversed(rows):
            observation = json.loads(row["observation_json"])
            observation["local_sequence"] = int(row["sequence"])
            result.append(observation)
        return result

    def tasks(self, *, active_only: bool = False, limit: int = 100) -> list[dict]:
        query = "SELECT * FROM coding_tasks"
        parameters: list[object] = []
        if active_only:
            query += " WHERE status = 'active'"
        query += " ORDER BY updated_at DESC LIMIT ?"
        parameters.append(max(1, min(int(limit), 500)))
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def prune_completed(self) -> int:
        """Remove oldest completed tasks until the quota is met; never remove active tasks."""

        removed = 0
        with self._lock, self._connect() as connection:
            while _database_bytes(connection) > self.quota_bytes:
                row = connection.execute(
                    """
                    SELECT interaction_id FROM coding_tasks
                    WHERE status = 'completed'
                    ORDER BY updated_at ASC
                    LIMIT 1
                    """
                ).fetchone()
                if row is None:
                    break
                interaction_id = row["interaction_id"]
                connection.execute(
                    "DELETE FROM coding_activities WHERE interaction_id = ?",
                    (interaction_id,),
                )
                connection.execute(
                    "DELETE FROM coding_tasks WHERE interaction_id = ?",
                    (interaction_id,),
                )
                removed += 1
        return removed

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection


def _database_bytes(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT COALESCE(SUM(length(observation_json)), 0) AS total "
        "FROM coding_activities"
    ).fetchone()
    return int(row["total"] if row is not None else 0)


def _task_status(event_kind: str, phase: object) -> str:
    if event_kind in {"turn_completed", "turn_failed", "turn_interrupted"}:
        return "completed"
    if phase in {"completed", "failed", "interrupted"}:
        return "completed"
    return "active"


__all__ = ["CodingActivityJournal"]
