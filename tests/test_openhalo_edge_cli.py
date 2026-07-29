from __future__ import annotations

import asyncio
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from device_edge.cli.terminal_daemon import TerminalEdgeDaemon
from openhalo.edge_cli import TerminalCredentials
from openhalo.edge_cli import main
from openhalo.edge_cli import pair_terminal_edge
from openhalo.home import PersonalHome
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.pairing_store import PairingStore


def test_setup_persists_public_terminal_identity_metadata_without_printing_private_data() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "setup",
                    "--url",
                    "wss://runtime.example.test/openhalo/edge",
                    "--pairing-code",
                    "one-time-code",
                    "--device-id",
                    "terminal-edge-9",
                ],
                home=home,
                pairing_exchange=lambda **kwargs: TerminalCredentials(
                    device_id=kwargs["device_id"],
                    display_name=kwargs["display_name"],
                    public_key_fingerprint="sha256:terminal-public-key",
                ),
            )
        payload = json.loads(output.getvalue())
        configuration = home.load_configuration()

    assert exit_code == 0
    assert payload == {
        "device_id": "terminal-edge-9",
        "state": "paired",
        "url": "wss://runtime.example.test/openhalo/edge",
    }
    assert "private" not in output.getvalue()
    assert configuration["terminal_edge"] == {
        "device_id": "terminal-edge-9",
        "display_name": "Terminal Edge",
        "public_key_fingerprint": "sha256:terminal-public-key",
        "url": "wss://runtime.example.test/openhalo/edge",
    }


def test_default_launch_uses_persisted_public_identity_without_printing_secrets() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        home.configure_terminal_edge(
            url="wss://runtime.example.test/openhalo/edge",
            device_id="terminal-edge-9",
            display_name="Maya's Terminal",
            public_key_fingerprint="sha256:terminal-public-key",
        )
        launched: list[list[str]] = []
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [],
                home=home,
                terminal_main=lambda argv: launched.append(argv),
            )

    assert exit_code == 0
    assert launched == [
        [
            "--url",
            "wss://runtime.example.test/openhalo/edge",
            "--device-id",
            "terminal-edge-9",
            "--display-name",
            "Maya's Terminal",
            "--home",
            str(home.root),
            "--tui",
        ]
    ]
    assert "private" not in output.getvalue()


def test_pair_terminal_edge_exchanges_the_one_time_code_with_the_real_gateway() -> None:
    async def scenario() -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = PairingStore(root / "pairing.json")
            pairing_code = store.create_pairing_code(ttl_seconds=300)
            gateway = RuntimeGateway(
                shared_token="development-token",
                state_path=root / "state.json",
                pairing_store=store,
            )

            async with gateway.run_test_server() as server_info:
                credentials = await pair_terminal_edge(
                    url=server_info["url"],
                    pairing_code=pairing_code,
                    device_id="terminal-edge-9",
                    display_name="Maya's Terminal",
                    identity_home=root / "home",
                )

            assert credentials.device_id == "terminal-edge-9"
            assert credentials.public_key_fingerprint.startswith("sha256:")
            assert store.get_device("terminal-edge-9")["display_name"] == "Maya's Terminal"

    asyncio.run(scenario())


def test_terminal_daemon_builds_an_uncredentialed_pre_auth_connect_frame() -> None:
    daemon = TerminalEdgeDaemon(
        device_id="terminal-edge-9",
        audience="wss://runtime.example.test/openhalo/edge",
    )

    connect = daemon.build_bootstrap_frames()[0]
    assert connect["audience"] == "wss://runtime.example.test/openhalo/edge"
    assert "auth" not in connect


def test_version_flag_prints_the_shared_development_identity() -> None:
    output = io.StringIO()
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        with redirect_stdout(output), pytest.raises(SystemExit) as exit_code:
            main(["--version"], home=home)

    assert exit_code.value.code == 0
    assert output.getvalue() == "openhalo-edge 0.1.0 (dev)\n"
