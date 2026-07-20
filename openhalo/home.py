"""Private per-owner paths and configuration for an OpenHalo installation."""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from collections.abc import Mapping
from pathlib import Path


class PersonalHome:
    """Resolve and manage persistent data that belongs to one OpenHalo owner."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser()

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "PersonalHome":
        values = environment if environment is not None else os.environ
        configured_home = values.get("OPENHALO_HOME")
        root = Path(configured_home) if configured_home else Path.home() / ".openhalo"
        return cls(root)

    @property
    def config_path(self) -> Path:
        return self.root / "config.json"

    @property
    def runtime_directory(self) -> Path:
        return self.root / "runtime"

    @property
    def log_directory(self) -> Path:
        return self.root / "logs"

    @property
    def state_path(self) -> Path:
        return self.runtime_directory / "state.json"

    @property
    def pairing_store_path(self) -> Path:
        return self.runtime_directory / "pairing.json"

    @property
    def runtime_config_path(self) -> Path:
        return self.root / "runtime-config.toml"

    @property
    def runtime_log_path(self) -> Path:
        return self.log_directory / "runtime.log"

    @property
    def runtime_diagnostic_log_path(self) -> Path:
        return self.log_directory / "runtime-diagnostics.jsonl"

    @property
    def runtime_pid_path(self) -> Path:
        return self.runtime_directory / "runtime.pid"

    def initialize_runtime(self, *, host: str, port: int) -> dict:
        if not host:
            raise ValueError("runtime host must not be empty")
        if not 1 <= port <= 65535:
            raise ValueError("runtime port must be between 1 and 65535")
        self._ensure_private_directories()
        configuration = self.load_configuration()
        runtime = dict(configuration.get("runtime", {}))
        runtime.update({"host": host, "port": port})
        runtime.setdefault("shared_token", secrets.token_urlsafe(32))
        configuration["runtime"] = runtime
        self._save_configuration(configuration)
        return runtime

    def configure_terminal_edge(
        self,
        *,
        url: str,
        device_id: str,
        device_token: str,
    ) -> None:
        if not url:
            raise ValueError("terminal Runtime URL must not be empty")
        if not device_id:
            raise ValueError("terminal device id must not be empty")
        if not device_token:
            raise ValueError("terminal device token must not be empty")
        self._ensure_private_directories()
        configuration = self.load_configuration()
        configuration["terminal_edge"] = {
            "url": url,
            "device_id": device_id,
            "device_token": device_token,
        }
        self._save_configuration(configuration)

    def load_configuration(self) -> dict:
        if not self.config_path.exists():
            return {"version": 1}
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("configuration root must be an object")
        version = payload.get("version", 1)
        if version != 1:
            raise ValueError(f"unsupported configuration version: {version}")
        payload.setdefault("version", 1)
        return payload

    def _ensure_private_directories(self) -> None:
        for directory in (self.root, self.runtime_directory, self.log_directory):
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 0o700)

    def _save_configuration(self, configuration: dict) -> None:
        self._ensure_private_directories()
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.root,
            prefix=f".{self.config_path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(configuration, output, indent=2, sort_keys=True)
                output.write("\n")
            os.replace(temporary_path, self.config_path)
            os.chmod(self.config_path, 0o600)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
