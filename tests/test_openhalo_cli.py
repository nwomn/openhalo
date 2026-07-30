from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from openhalo.cli import main
from openhalo.home import PersonalHome
from openhalo import version as version_module
from personal_runtime.pairing_store import PairingStore


class FakeSupervisor:
    def __init__(self, home: PersonalHome) -> None:
        self.home = home

    def start(self) -> dict:
        return {"state": "running", "pid": 777}

    def stop(self) -> dict:
        return {"state": "stopping", "pid": 777}

    def status(self) -> dict:
        return {"state": "stopped", "pid": None}

    def read_logs(self, *, lines: int) -> str:
        return "runtime log\n" * lines


class FakeUpdater:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def check(self) -> dict:
        self.calls.append("check")
        return {"current": "a" * 40, "state": "update_available", "target": "b" * 40}

    def update(self) -> dict:
        self.calls.append("update")
        return {"state": "updated", "target": "b" * 40}

    def rollback(self) -> dict:
        self.calls.append("rollback")
        return {"state": "rolled_back", "restored": "a" * 40}


class FailingUpdater:
    def check(self) -> dict:
        raise ValueError("GitHub Release is missing required asset: release-manifest.json")


class TarFailureUpdater:
    def check(self) -> dict:
        import tarfile

        raise tarfile.ReadError("not a tar archive")


def _run(home: PersonalHome, *argv: str) -> tuple[int, str]:
    output = io.StringIO()
    with redirect_stdout(output):
        exit_code = main(list(argv), home=home, supervisor_factory=FakeSupervisor)
    return exit_code, output.getvalue()


def test_setup_creates_private_runtime_config_without_printing_owner_token() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")

        exit_code, output = _run(home, "setup", "--host", "127.0.0.1", "--port", "8765")

        payload = json.loads(output)
        persisted = home.load_configuration()
        runtime_config_exists = home.runtime_config_path.exists()
        runtime_config = home.runtime_config_path.read_text(encoding="utf-8")

    assert exit_code == 0
    assert payload == {"host": "127.0.0.1", "port": 8765, "state": "configured"}
    assert "shared_token" not in persisted["runtime"]
    assert "shared_token" not in output
    assert runtime_config_exists
    assert "replace-with-provider-api-key" in runtime_config


def test_setup_defaults_to_a_direct_ip_runtime_bind() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")

        exit_code, output = _run(home, "setup")

    assert exit_code == 0
    assert json.loads(output) == {"host": "0.0.0.0", "port": 8765, "state": "configured"}


def test_pair_devices_and_revoke_use_the_personal_pairing_store_without_leaking_credentials() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        _run(home, "setup")

        exit_code, pair_output = _run(home, "pair", "--ttl-seconds", "120")
        pairing_code = json.loads(pair_output)["pairing_code"]
        PairingStore(home.pairing_store_path).claim_pairing_code(
            pairing_code,
            device_id="terminal-edge-1",
            device_type="terminal-edge",
            display_name="Workstation Terminal",
            audience="wss://runtime.example/openhalo/edge",
            public_key="terminal-public-key",
        )
        _, devices_output = _run(home, "devices")
        revoke_exit, revoke_output = _run(home, "revoke", "terminal-edge-1")

    assert exit_code == 0
    assert pairing_code not in devices_output
    assert "credential" not in devices_output
    assert json.loads(devices_output)["devices"][0]["device_id"] == "terminal-edge-1"
    assert revoke_exit == 0
    assert json.loads(revoke_output) == {"device_id": "terminal-edge-1", "revoked": True}


def test_rename_updates_the_owner_visible_device_name() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        _run(home, "setup")
        pairing_code = json.loads(_run(home, "pair")[1])["pairing_code"]
        PairingStore(home.pairing_store_path).claim_pairing_code(
            pairing_code,
            device_id="terminal-edge-1",
            device_type="terminal-edge",
            display_name="Workstation Terminal",
            audience="wss://runtime.example/openhalo/edge",
            public_key="terminal-public-key",
        )

        rename_exit, rename_output = _run(
            home,
            "rename",
            "terminal-edge-1",
            "Maya's Terminal",
        )
        _, devices_output = _run(home, "devices")

    assert rename_exit == 0
    assert json.loads(rename_output) == {
        "device_id": "terminal-edge-1",
        "renamed": True,
    }
    assert json.loads(devices_output)["devices"][0]["display_name"] == "Maya's Terminal"


def test_lifecycle_and_doctor_commands_report_safe_owner_facing_state() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        _run(home, "setup")

        start_exit, start_output = _run(home, "start")
        status_exit, status_output = _run(home, "status")
        logs_exit, logs_output = _run(home, "logs", "--lines", "2")
        doctor_exit, doctor_output = _run(home, "doctor")

    assert start_exit == status_exit == logs_exit == doctor_exit == 0
    assert json.loads(start_output) == {"pid": 777, "state": "running"}
    assert json.loads(status_output) == {"pid": None, "state": "stopped"}
    assert logs_output == "runtime log\nruntime log\n"
    doctor = json.loads(doctor_output)
    assert doctor["state"] == "ready"
    assert "shared_token" not in doctor_output


def test_version_flag_reports_the_installed_release_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    release_commit = "a" * 40
    executable = Path(
        "/home/alice/.local/share/openhalo/releases"
    ) / release_commit / "venv/bin/python"
    monkeypatch.setattr(sys, "executable", str(executable))
    output = io.StringIO()

    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        with redirect_stdout(output), pytest.raises(SystemExit) as exit_code:
            main(["--version"], home=home, supervisor_factory=FakeSupervisor)

    assert exit_code.value.code == 0
    assert output.getvalue() == "openhalo 0.1.3 (aaaaaaa)\n"


def test_version_flag_prints_a_development_identity_outside_a_release_layout() -> None:
    output = io.StringIO()
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        with redirect_stdout(output), pytest.raises(SystemExit) as exit_code:
            main(["--version"], home=home, supervisor_factory=FakeSupervisor)

    assert exit_code.value.code == 0
    assert output.getvalue() == "openhalo 0.1.3 (dev)\n"


def test_version_fallback_matches_the_release_package_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def package_not_installed(_: str) -> str:
        raise version_module.PackageNotFoundError

    monkeypatch.setattr(version_module, "distribution_version", package_not_installed)

    assert version_module.format_cli_version("openhalo", executable="/tmp/python") == (
        "openhalo 0.1.3 (dev)"
    )


def test_update_commands_delegate_to_the_owner_release_updater() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        updater = FakeUpdater()
        output = io.StringIO()
        with redirect_stdout(output):
            check_exit = main(
                ["update", "--check"],
                home=home,
                supervisor_factory=FakeSupervisor,
                updater_factory=lambda _: updater,
            )
            update_exit = main(
                ["update"],
                home=home,
                supervisor_factory=FakeSupervisor,
                updater_factory=lambda _: updater,
            )
            rollback_exit = main(
                ["rollback"],
                home=home,
                supervisor_factory=FakeSupervisor,
                updater_factory=lambda _: updater,
            )

    payloads = [json.loads(line) for line in output.getvalue().splitlines()]
    assert check_exit == update_exit == rollback_exit == 0
    assert updater.calls == ["check", "update", "rollback"]
    assert payloads == [
        {"current": "a" * 40, "state": "update_available", "target": "b" * 40},
        {"state": "updated", "target": "b" * 40},
        {"restored": "a" * 40, "state": "rolled_back"},
    ]


def test_update_check_reports_release_validation_failure_without_a_traceback() -> None:
    with TemporaryDirectory() as directory:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                ["update", "--check"],
                home=PersonalHome(Path(directory) / "home"),
                supervisor_factory=FakeSupervisor,
                updater_factory=lambda _: FailingUpdater(),
            )

    assert exit_code == 1
    assert json.loads(output.getvalue()) == {
        "reason": "GitHub Release is missing required asset: release-manifest.json",
        "state": "update_failed",
    }


def test_update_check_reports_archive_failure_without_a_traceback() -> None:
    with TemporaryDirectory() as directory:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                ["update", "--check"],
                home=PersonalHome(Path(directory) / "home"),
                supervisor_factory=FakeSupervisor,
                updater_factory=lambda _: TarFailureUpdater(),
            )

    assert exit_code == 1
    assert json.loads(output.getvalue()) == {
        "reason": "not a tar archive",
        "state": "update_failed",
    }
