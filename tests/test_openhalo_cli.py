from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from openhalo.cli import main
from openhalo.home import PersonalHome
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
    assert persisted["runtime"]["shared_token"] not in output
    assert runtime_config_exists
    assert "replace-with-provider-api-key" in runtime_config


def test_pair_devices_and_revoke_use_the_personal_pairing_store_without_leaking_credentials() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        _run(home, "setup")

        exit_code, pair_output = _run(home, "pair", "--ttl-seconds", "120")
        pairing_code = json.loads(pair_output)["pairing_code"]
        device_token = PairingStore(home.pairing_store_path).claim_pairing_code(
            pairing_code,
            device_id="terminal-edge-1",
            device_type="terminal-edge",
        )
        _, devices_output = _run(home, "devices")
        revoke_exit, revoke_output = _run(home, "revoke", "terminal-edge-1")

    assert exit_code == 0
    assert pairing_code not in devices_output
    assert device_token not in devices_output
    assert json.loads(devices_output)["devices"][0]["device_id"] == "terminal-edge-1"
    assert revoke_exit == 0
    assert json.loads(revoke_output) == {"device_id": "terminal-edge-1", "revoked": True}


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
