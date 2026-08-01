"""Private per-owner paths and configuration for an OpenHalo installation."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from openhalo.outbound_proxy import validate_proxy_url


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
    def devices_directory(self) -> Path:
        return self.root / "devices"

    @property
    def log_directory(self) -> Path:
        return self.root / "logs"

    @property
    def state_path(self) -> Path:
        """Legacy JSON state path retained for migration and rollback."""
        return self.runtime_directory / "state.json"

    @property
    def legacy_state_path(self) -> Path:
        return self.state_path

    @property
    def state_database_path(self) -> Path:
        return self.runtime_directory / "state.sqlite3"

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
    def replay_directory(self) -> Path:
        return self.runtime_directory / "replays"

    @property
    def runtime_pid_path(self) -> Path:
        return self.runtime_directory / "runtime.pid"

    @property
    def runtime_ready_path(self) -> Path:
        return self.runtime_directory / "runtime.ready"

    def initialize_runtime(self, *, host: str, port: int) -> dict:
        if not host:
            raise ValueError("runtime host must not be empty")
        if not 1 <= port <= 65535:
            raise ValueError("runtime port must be between 1 and 65535")
        self._ensure_private_directories()
        configuration = self.load_configuration()
        runtime = dict(configuration.get("runtime", {}))
        runtime.update({"host": host, "port": port})
        runtime.pop("shared_token", None)
        configuration["runtime"] = runtime
        self._save_configuration(configuration)
        return runtime

    def outbound_proxy_url(self) -> str | None:
        runtime = self.load_configuration().get("runtime")
        if not isinstance(runtime, dict):
            return None
        outbound_proxy = runtime.get("outbound_proxy")
        if outbound_proxy is None:
            return None
        if not isinstance(outbound_proxy, dict) or not isinstance(
            outbound_proxy.get("url"), str
        ):
            raise ValueError("Runtime outbound proxy configuration is invalid")
        return validate_proxy_url(outbound_proxy["url"]).url

    def configure_outbound_proxy(self, url: str) -> None:
        validated_url = validate_proxy_url(url).url
        self._ensure_private_directories()
        configuration = self.load_configuration()
        runtime = configuration.get("runtime")
        if not isinstance(runtime, dict):
            raise ValueError("OpenHalo Runtime is not configured; run openhalo setup")
        runtime = dict(runtime)
        runtime["outbound_proxy"] = {"url": validated_url}
        configuration["runtime"] = runtime
        self._save_configuration(configuration)

    def clear_outbound_proxy(self) -> None:
        self._ensure_private_directories()
        configuration = self.load_configuration()
        runtime = configuration.get("runtime")
        if not isinstance(runtime, dict):
            raise ValueError("OpenHalo Runtime is not configured; run openhalo setup")
        runtime = dict(runtime)
        runtime.pop("outbound_proxy", None)
        configuration["runtime"] = runtime
        self._save_configuration(configuration)

    def configure_terminal_edge(
        self,
        *,
        url: str,
        device_id: str,
        display_name: str,
        public_key_fingerprint: str,
    ) -> None:
        if not url:
            raise ValueError("terminal Runtime URL must not be empty")
        if not device_id:
            raise ValueError("terminal device id must not be empty")
        if not display_name:
            raise ValueError("terminal display name must not be empty")
        if not public_key_fingerprint:
            raise ValueError("terminal public key fingerprint must not be empty")
        self._ensure_private_directories()
        configuration = self.load_configuration()
        configuration["terminal_edge"] = {
            "url": url,
            "device_id": device_id,
            "display_name": display_name,
            "public_key_fingerprint": public_key_fingerprint,
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
        migrated = False
        runtime = payload.get("runtime")
        if isinstance(runtime, dict) and "shared_token" in runtime:
            runtime.pop("shared_token")
            migrated = True
        terminal_edge = payload.get("terminal_edge")
        if isinstance(terminal_edge, dict) and "device_token" in terminal_edge:
            payload.pop("terminal_edge")
            migrated = True
        if migrated:
            self._save_configuration(payload)
        return payload

    def _ensure_private_directories(self) -> None:
        for directory in (
            self.root,
            self.runtime_directory,
            self.log_directory,
            self.devices_directory,
        ):
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
