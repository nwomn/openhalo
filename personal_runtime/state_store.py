"""File-backed runtime state persistence for the v0 runtime."""

import json
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

    def save(self, state: RuntimeState) -> None:
        with self._save_lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
            temp_path.write_text(
                json.dumps(state.to_dict(), indent=2) + "\n",
                encoding="utf-8",
            )
            temp_path.replace(self.path)
