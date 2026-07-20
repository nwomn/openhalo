from __future__ import annotations

import json
import stat
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from openhalo.home import PersonalHome


def test_environment_override_keeps_runtime_and_terminal_configuration_together() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory) / "chosen-home"
        home = PersonalHome.from_environment({"OPENHALO_HOME": str(root)})

        runtime = home.initialize_runtime(host="127.0.0.1", port=8765)
        home.configure_terminal_edge(
            url="wss://runtime.example.test/openhalo/edge",
            device_id="terminal-edge-7",
            device_token="device-secret",
        )

        payload = json.loads(home.config_path.read_text(encoding="utf-8"))

    assert home.root == root
    assert runtime["shared_token"]
    assert payload["runtime"] == runtime
    assert payload["terminal_edge"] == {
        "url": "wss://runtime.example.test/openhalo/edge",
        "device_id": "terminal-edge-7",
        "device_token": "device-secret",
    }
    assert home.state_path == root / "runtime" / "state.json"
    assert home.pairing_store_path == root / "runtime" / "pairing.json"


def test_configuration_and_private_directories_are_owner_only() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")

        home.initialize_runtime(host="127.0.0.1", port=8765)

        assert stat.S_IMODE(home.root.stat().st_mode) == 0o700
        assert stat.S_IMODE(home.config_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(home.runtime_directory.stat().st_mode) == 0o700
        assert stat.S_IMODE(home.log_directory.stat().st_mode) == 0o700


def test_invalid_configuration_is_rejected_without_replacing_private_file() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        home.initialize_runtime(host="127.0.0.1", port=8765)
        original = home.config_path.read_text(encoding="utf-8")
        home.config_path.write_text("[]", encoding="utf-8")

        with pytest.raises(ValueError, match="configuration root"):
            home.load_configuration()

        home.config_path.write_text(original, encoding="utf-8")
        assert home.load_configuration()["runtime"]["port"] == 8765
