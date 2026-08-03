from __future__ import annotations

import asyncio
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from device_edge.cli.terminal_daemon import TerminalEdgeDaemon
from device_edge.shared.identity import load_or_create_identity
from openhalo.edge_cli import TerminalCredentials
from openhalo.edge_cli import main
from openhalo.edge_cli import pair_terminal_edge
from openhalo.home import PersonalHome
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.pairing_store import PairingStore


TEST_LLM_CONFIG = Path(__file__).parent / "fixtures" / "llm-config-test.toml"


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


def test_setup_accepts_a_public_plaintext_runtime_endpoint() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        exit_code = main(
            [
                "setup",
                "--url",
                "ws://198.51.100.15:8765",
                "--pairing-code",
                "one-time-code",
            ],
            home=home,
            pairing_exchange=lambda **kwargs: TerminalCredentials(
                device_id=kwargs["device_id"],
                display_name=kwargs["display_name"],
                public_key_fingerprint="sha256:terminal-public-key",
            ),
        )
        configuration = home.load_configuration()

    assert exit_code == 0
    assert configuration["terminal_edge"]["url"] == "ws://198.51.100.15:8765"


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


def test_explicit_home_reuses_a_paired_terminal_from_a_new_shell() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "terminal-edge-home")
        home.configure_terminal_edge(
            url="wss://runtime.example.test/openhalo/edge",
            device_id="terminal-edge-9",
            display_name="Maya's Terminal",
            public_key_fingerprint="sha256:terminal-public-key",
        )
        launched: list[list[str]] = []

        exit_code = main(
            ["--home", str(home.root), "run"],
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


def test_coding_workspace_is_forwarded_to_the_terminal_daemon() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "terminal-edge-home")
        home.configure_terminal_edge(
            url="wss://runtime.example.test/openhalo/edge",
            device_id="terminal-edge-9",
            display_name="Maya's Terminal",
            public_key_fingerprint="sha256:terminal-public-key",
        )
        launched: list[list[str]] = []

        exit_code = main(
            ["--home", str(home.root), "run", "--coding-workspace", "/workspace/project"],
            terminal_main=lambda argv: launched.append(argv),
        )

    assert exit_code == 0
    assert launched[0][-2:] == ["--coding-workspace", "/workspace/project"]


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


def test_paired_terminal_completes_a_real_v2_websocket_interaction() -> None:
    async def scenario() -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory) / "home"
            store = PairingStore(root / "runtime" / "pairing.json")
            gateway = RuntimeGateway(
                pairing_store=store,
                persist_state=False,
                llm_config_path=TEST_LLM_CONFIG,
            )
            pairing_code = store.create_pairing_code(ttl_seconds=300)

            async with gateway.run_test_server() as server_info:
                await pair_terminal_edge(
                    url=server_info["url"],
                    pairing_code=pairing_code,
                    device_id="terminal-edge-9",
                    display_name="Maya's Terminal",
                    identity_home=root,
                )
                daemon = TerminalEdgeDaemon(
                    device_id="terminal-edge-9",
                    audience=server_info["url"],
                    identity=load_or_create_identity(root, "terminal-edge-9"),
                    display_name="Maya's Terminal",
                )
                await asyncio.wait_for(
                    daemon.run_forever(
                        url=server_info["url"],
                        scripted_inputs=[
                            {
                                "text": "hello runtime",
                                "observed_at": "2030-01-01T12:00:00Z",
                            }
                        ],
                        startup_observed_at="2030-01-01T11:59:00Z",
                        max_action_requests=1,
                        max_sessions=1,
                    ),
                    timeout=5,
                )

            assert gateway.state.device_registry["terminal-edge-9"]["display_name"] == "Maya's Terminal"
            assert any("Runtime heard: hello runtime" in line for line in daemon.transcript)

    asyncio.run(scenario())


def test_version_flag_prints_the_shared_development_identity() -> None:
    output = io.StringIO()
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        with redirect_stdout(output), pytest.raises(SystemExit) as exit_code:
            main(["--version"], home=home)

    assert exit_code.value.code == 0
    assert output.getvalue() == "openhalo-edge 0.1.13 (dev)\n"
