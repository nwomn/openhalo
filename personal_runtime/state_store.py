"""File-backed runtime state persistence for the v0 runtime."""

import os
import json
import tempfile
from pathlib import Path
from threading import Lock

from personal_runtime.runtime_state import RuntimeState


class JsonStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._save_lock = Lock()

    def load(self) -> RuntimeState:
        if not self.path.exists():
            return RuntimeState()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return RuntimeState.from_dict(payload)

    def save(self, state: RuntimeState, *, deferred: bool = False) -> None:
        del deferred
        with self._save_lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, raw_temp_path = tempfile.mkstemp(
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
            )
            temp_path = Path(raw_temp_path)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                    output.write(json.dumps(state.to_dict(), indent=2) + "\n")
                temp_path.replace(self.path)
                os.chmod(self.path, 0o600)
                drain = getattr(state, "drain_storage_operations", None)
                if drain is not None:
                    drain()
            finally:
                if temp_path.exists():
                    temp_path.unlink()


def build_state_store(path: Path):
    """Select the durable store from the explicit runtime path."""

    path = Path(path)
    if path.suffix in {".sqlite", ".sqlite3", ".db"}:
        legacy_path = path.with_suffix(".json")
        if not path.exists() and legacy_path.exists():
            raise ValueError(
                f"legacy Runtime state requires migration before SQLite startup: {legacy_path}"
            )
        from personal_runtime.sqlite_state_store import SQLiteRuntimeStateStore

        store = SQLiteRuntimeStateStore(path)
        if legacy_path.exists():
            try:
                metadata = store.metadata()
            except Exception:
                store.close()
                raise
            if metadata.get("legacy_source_sha256") is None:
                store.close()
                raise ValueError(
                    f"SQLite Runtime state requires migration from legacy JSON: {legacy_path}"
                )
        return store
    return JsonStateStore(path)
