"""Streaming migration from the legacy JSON state file to SQLite."""

from __future__ import annotations

import json
import hashlib
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from personal_runtime.sqlite_state_store import SQLiteRuntimeStateStore
from personal_runtime.sqlite_state_store import SCHEMA_VERSION


_ARRAY_COLLECTIONS = {
    "events",
    "action_results",
    "interactions",
    "observations",
    "interventions",
    "memory_consolidation_candidates",
    "harness_traces",
    "internal_tool_events",
    "hermes_memory_events",
}
_STATE_VALUE_KEYS = {
    "devices",
    "tasks",
    "device_registry",
    "capability_registry",
    "observation_registry",
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
}


def migrate_json_to_sqlite(source: Path, target: Path) -> dict[str, Any]:
    """Convert one legacy state file without materializing its full document."""

    source = Path(source)
    target = Path(target)
    temporary_target = Path(f"{target}.migrating")
    if not source.is_file():
        raise FileNotFoundError(source)
    if target.exists():
        raise FileExistsError(target)
    _remove_sqlite_artifacts(temporary_target)
    temporary_target.parent.mkdir(parents=True, exist_ok=True)
    store = None
    target_created = False
    try:
        store = SQLiteRuntimeStateStore(temporary_target)
        store.import_legacy(_legacy_entries(source))
        store.set_metadata("legacy_source_sha256", sha256_file(source))
        status = store.storage_status()
        store.close()
        store = None
        os.replace(temporary_target, target)
        target_created = True
        os.chmod(target, 0o600)
        return {
            "schema_version": SCHEMA_VERSION,
            "source": str(source),
            "target": str(target),
            "counts": status["counts"],
        }
    except Exception as exc:
        if store is not None:
            try:
                store.close()
            except Exception:
                pass
        _remove_sqlite_artifacts(temporary_target)
        if target_created:
            _remove_sqlite_artifacts(target)
        raise ValueError(f"state migration failed: {exc}") from exc


def export_sqlite_to_json(source: Path, target: Path) -> dict[str, Any]:
    """Create a compatibility JSON snapshot for a pre-SQLite Runtime."""

    source = Path(source)
    target = Path(target)
    if not source.is_file():
        raise FileNotFoundError(source)
    store = SQLiteRuntimeStateStore(source)
    temporary = Path(f"{target}.rollback")
    try:
        store.export_json(temporary, include_metadata=False)
        os.replace(temporary, target)
        os.chmod(target, 0o600)
        return {
            "schema_version": "json-v1",
            "source": str(source),
            "target": str(target),
        }
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise ValueError(f"state rollback export failed: {exc}") from exc
    finally:
        store.close()


def write_bounded_legacy_snapshot(source: Path, target: Path) -> bool:
    """Replace a migrated JSON source with a bounded rollback-compatible view."""

    source = Path(source)
    target = Path(target)
    if not source.is_file() or not target.is_file():
        return False
    store = SQLiteRuntimeStateStore(source)
    temporary = Path(f"{target}.bounded")
    try:
        metadata = store.metadata()
        if metadata.get("legacy_source_sha256") != sha256_file(target):
            return False
        payload = store.load().to_dict()
        temporary.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)
        os.chmod(target, 0o600)
        store.set_metadata("legacy_source_sha256", sha256_file(target))
        return True
    finally:
        temporary.unlink(missing_ok=True)
        store.close()


def _legacy_entries(source: Path) -> Iterator[tuple[str, str, Any, int]]:
    reader = _JSONStream(source)
    ordinals: dict[str, int] = {}
    seen_keys: set[str] = set()
    for key, value in reader.members():
        if key in seen_keys:
            raise ValueError(f"duplicate legacy state key: {key}")
        seen_keys.add(key)
        if key in _ARRAY_COLLECTIONS:
            for item in value:
                ordinal = ordinals.get(key, 0)
                ordinals[key] = ordinal + 1
                if not isinstance(item, dict):
                    raise ValueError(f"legacy collection {key} contains a non-object")
                yield "record", key, item, ordinal
        elif key in _STATE_VALUE_KEYS:
            if isinstance(value, Iterator):
                value = list(value)
            yield "state_value", key, value, 0
        elif key == "context_facts":
            values = value.values() if isinstance(value, dict) else value
            for fact in values:
                if not isinstance(fact, dict):
                    raise ValueError("legacy context_facts contains a non-object")
                yield "context_fact", key, fact, 0
        else:
            raise ValueError(f"unsupported legacy state key: {key}")


class _JSONStream:
    def __init__(self, path: Path, *, chunk_size: int = 64 * 1024) -> None:
        self.handle = path.open("rb")
        self.chunk_size = chunk_size
        self.buffer = ""
        self.eof = False
        self.decoder = json.JSONDecoder()

    def members(self):
        try:
            self._consume("{")
            if self._peek() == "}":
                self._consume("}")
                self._ensure_document_end()
                return
            while True:
                key = self._decode()
                if not isinstance(key, str):
                    raise ValueError("legacy state object key must be a string")
                self._consume(":")
                if self._peek() == "[":
                    value = self._array_items()
                else:
                    value = self._decode()
                yield key, value
                delimiter = self._peek()
                if delimiter == "}":
                    self._consume("}")
                    self._ensure_document_end()
                    break
                self._consume(",")
        finally:
            self.handle.close()

    def _array_items(self):
        self._consume("[")
        if self._peek() == "]":
            self._consume("]")
            return
        while True:
            yield self._decode()
            delimiter = self._peek()
            if delimiter == "]":
                self._consume("]")
                break
            self._consume(",")

    def _decode(self):
        while True:
            self._skip_whitespace()
            try:
                value, position = self.decoder.raw_decode(self.buffer)
            except json.JSONDecodeError as exc:
                if self.eof:
                    raise ValueError(f"invalid legacy JSON: {exc}") from exc
                self._read_more()
                continue
            self.buffer = self.buffer[position:]
            return value

    def _consume(self, expected: str) -> None:
        self._skip_whitespace()
        if not self.buffer.startswith(expected):
            if not self.eof:
                self._read_more()
                return self._consume(expected)
            raise ValueError(f"invalid legacy JSON: expected {expected!r}")
        self.buffer = self.buffer[len(expected):]

    def _peek(self) -> str:
        self._skip_whitespace()
        if not self.buffer and self.eof:
            raise ValueError("invalid legacy JSON: unexpected end of document")
        if not self.buffer:
            self._read_more()
        return self.buffer[0]

    def _skip_whitespace(self) -> None:
        while True:
            self.buffer = self.buffer.lstrip()
            if self.buffer or self.eof:
                return
            self._read_more()

    def _ensure_document_end(self) -> None:
        self._skip_whitespace()
        if self.buffer:
            raise ValueError("invalid legacy JSON: trailing data")

    def _read_more(self) -> None:
        chunk = self.handle.read(self.chunk_size)
        if not chunk:
            self.eof = True
            return
        self.buffer += chunk.decode("utf-8")


__all__ = [
    "export_sqlite_to_json",
    "migrate_json_to_sqlite",
    "sha256_file",
    "write_bounded_legacy_snapshot",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_sqlite_artifacts(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(f"{path}{suffix}").unlink(missing_ok=True)
        except OSError:
            pass
