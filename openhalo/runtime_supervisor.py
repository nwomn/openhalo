"""Private lifecycle management for an installed Personal Runtime."""

from __future__ import annotations

import errno
import os
import signal
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from openhalo.home import PersonalHome


class RuntimeSupervisor:
    """Start and stop only the Runtime process owned by one personal home."""

    def __init__(
        self,
        home: PersonalHome,
        *,
        launcher: Callable[..., object] = subprocess.Popen,
        is_process_alive: Callable[[int], bool] | None = None,
        process_command: Callable[[int], str] | None = None,
        signal_sender: Callable[[int, int], None] = os.kill,
    ) -> None:
        self.home = home
        self._launcher = launcher
        self._is_process_alive = is_process_alive or _is_process_alive
        self._process_command = process_command or _read_process_command
        self._signal_sender = signal_sender

    def build_command(self) -> list[str]:
        runtime = self._runtime_configuration()
        return [
            sys.executable,
            "-m",
            "personal_runtime.main",
            "--host",
            runtime["host"],
            "--port",
            str(runtime["port"]),
            "--token-env",
            "OPENHALO_RUNTIME_TOKEN",
            "--state-path",
            str(self.home.state_path),
            "--pairing-store-path",
            str(self.home.pairing_store_path),
            "--runtime-config-path",
            str(self.home.runtime_config_path),
            "--diagnostic-log-path",
            str(self.home.runtime_diagnostic_log_path),
        ]

    def start(self) -> dict:
        status = self.status()
        if status["state"] == "running":
            return status

        runtime = self._runtime_configuration()
        self.home.initialize_runtime(host=runtime["host"], port=runtime["port"])
        environment = dict(os.environ)
        environment["OPENHALO_RUNTIME_TOKEN"] = runtime["shared_token"]
        self.home.log_directory.mkdir(parents=True, exist_ok=True)
        with self.home.runtime_log_path.open("a", encoding="utf-8") as log_file:
            process = self._launcher(
                self.build_command(),
                cwd=self.home.root,
                env=environment,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        pid = getattr(process, "pid", None)
        if not isinstance(pid, int) or pid <= 0:
            raise RuntimeError("Runtime launcher did not return a process id")
        self.home.runtime_pid_path.write_text(f"{pid}\n", encoding="utf-8")
        os.chmod(self.home.runtime_pid_path, 0o600)
        return {"state": "running", "pid": pid}

    def status(self) -> dict:
        pid = self._read_pid()
        if pid is None:
            return {"state": "stopped", "pid": None}
        if not self._is_process_alive(pid):
            self._remove_pid_file()
            return {"state": "stopped", "pid": None}
        if not _is_openhalo_runtime_command(self._process_command(pid)):
            self._remove_pid_file()
            return {"state": "stale", "pid": pid}
        return {"state": "running", "pid": pid}

    def stop(self) -> dict:
        status = self.status()
        if status["state"] != "running":
            return status
        pid = status["pid"]
        assert isinstance(pid, int)
        self._signal_sender(pid, signal.SIGTERM)
        return {"state": "stopping", "pid": pid}

    def read_logs(self, *, lines: int = 100) -> str:
        if lines <= 0:
            raise ValueError("log line count must be positive")
        if not self.home.runtime_log_path.exists():
            return ""
        content = self.home.runtime_log_path.read_text(encoding="utf-8", errors="replace")
        return "".join(content.splitlines(keepends=True)[-lines:])

    def _runtime_configuration(self) -> dict:
        configuration = self.home.load_configuration()
        runtime = configuration.get("runtime")
        if not isinstance(runtime, dict):
            raise ValueError("OpenHalo Runtime is not configured; run openhalo setup")
        host = runtime.get("host")
        port = runtime.get("port")
        shared_token = runtime.get("shared_token")
        if not isinstance(host, str) or not host:
            raise ValueError("Runtime configuration has no bind host")
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("Runtime configuration has an invalid port")
        if not isinstance(shared_token, str) or not shared_token:
            raise ValueError("Runtime configuration has no owner token")
        return {"host": host, "port": port, "shared_token": shared_token}

    def _read_pid(self) -> int | None:
        try:
            value = self.home.runtime_pid_path.read_text(encoding="utf-8").strip()
            pid = int(value)
        except (FileNotFoundError, ValueError):
            return None
        return pid if pid > 0 else None

    def _remove_pid_file(self) -> None:
        self.home.runtime_pid_path.unlink(missing_ok=True)


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        if exc.errno == errno.EPERM:
            return True
        raise
    return True


def _read_process_command(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_text(encoding="utf-8").replace("\0", " ")
    except OSError:
        return ""


def _is_openhalo_runtime_command(command: str) -> bool:
    return "personal_runtime.main" in command
