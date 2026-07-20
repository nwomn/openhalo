from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from openhalo.home import PersonalHome
from openhalo.runtime_supervisor import RuntimeSupervisor


def _home() -> tuple[TemporaryDirectory, PersonalHome]:
    directory = TemporaryDirectory()
    home = PersonalHome(Path(directory.name) / "home")
    home.initialize_runtime(host="127.0.0.1", port=8765)
    return directory, home


def test_start_builds_home_derived_runtime_command_without_exposing_token() -> None:
    directory, home = _home()
    launches: list[tuple[list[str], dict]] = []
    try:
        supervisor = RuntimeSupervisor(
            home,
            launcher=lambda command, **kwargs: launches.append((command, kwargs))
            or type("Process", (), {"pid": 719})(),
            is_process_alive=lambda pid: pid == 719,
            process_command=lambda pid: "python -m personal_runtime.main",
            gateway_is_ready=lambda host, port: True,
        )

        status = supervisor.start()

        command, kwargs = launches[0]
        assert status == {"state": "running", "pid": 719}
        assert command[:3] == [sys.executable, "-m", "personal_runtime.main"]
        assert "--state-path" in command
        assert str(home.state_path) in command
        assert "--pairing-store-path" in command
        assert str(home.pairing_store_path) in command
        assert "--token-env" in command
        assert kwargs["env"]["OPENHALO_RUNTIME_TOKEN"]
        assert kwargs["env"]["OPENHALO_RUNTIME_TOKEN"] not in command
        assert home.runtime_pid_path.read_text(encoding="utf-8") == "719\n"
    finally:
        directory.cleanup()


def test_start_is_idempotent_for_a_running_openhalo_runtime() -> None:
    directory, home = _home()
    try:
        home.runtime_pid_path.write_text("42\n", encoding="utf-8")
        supervisor = RuntimeSupervisor(
            home,
            launcher=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("launched")),
            is_process_alive=lambda pid: pid == 42,
            process_command=lambda pid: "python -m personal_runtime.main",
            gateway_is_ready=lambda host, port: True,
        )

        assert supervisor.start() == {"state": "running", "pid": 42}
    finally:
        directory.cleanup()


def test_stop_refuses_to_signal_a_pid_that_is_not_an_openhalo_runtime() -> None:
    directory, home = _home()
    signals: list[tuple[int, int]] = []
    try:
        home.runtime_pid_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
        supervisor = RuntimeSupervisor(
            home,
            signal_sender=lambda pid, sig: signals.append((pid, sig)),
            is_process_alive=lambda pid: pid == os.getpid(),
            process_command=lambda pid: "python unrelated-program.py",
        )

        assert supervisor.stop() == {"state": "stale", "pid": os.getpid()}
        assert signals == []
        assert not home.runtime_pid_path.exists()
    finally:
        directory.cleanup()


def test_logs_returns_the_requested_tail() -> None:
    directory, home = _home()
    try:
        home.log_directory.mkdir(parents=True, exist_ok=True)
        home.runtime_log_path.write_text("one\ntwo\nthree\n", encoding="utf-8")
        supervisor = RuntimeSupervisor(home)

        assert supervisor.read_logs(lines=2) == "two\nthree\n"
    finally:
        directory.cleanup()


def test_start_rejects_a_runtime_that_exits_before_gateway_is_ready() -> None:
    directory, home = _home()
    try:
        supervisor = RuntimeSupervisor(
            home,
            launcher=lambda *args, **kwargs: type("Process", (), {"pid": 720})(),
            is_process_alive=lambda pid: False,
            process_command=lambda pid: "python -m personal_runtime.main",
            gateway_is_ready=lambda host, port: False,
        )

        with pytest.raises(RuntimeError, match="exited before becoming ready"):
            supervisor.start()

        assert not home.runtime_pid_path.exists()
    finally:
        directory.cleanup()
