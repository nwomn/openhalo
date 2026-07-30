"""Owner-facing setup and launch command for the personal Terminal Edge."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import websockets

from device_edge.cli.terminal_daemon import main as terminal_daemon_main
from device_edge.shared.identity import load_or_create_identity
from edge_api.auth import build_challenge_payload
from edge_api.auth import encode_base64url
from edge_api.auth import sign_challenge
from edge_api.endpoint import validate_runtime_endpoint
from edge_api.protocol import build_connect_frame
from openhalo.home import PersonalHome
from openhalo.version import format_cli_version


@dataclass(frozen=True)
class TerminalCredentials:
    device_id: str
    display_name: str
    public_key_fingerprint: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Set up and run your OpenHalo Terminal Edge.")
    parser.add_argument(
        "--version",
        action="version",
        version=format_cli_version("openhalo-edge"),
        help="Show the installed OpenHalo Terminal Edge version.",
    )
    parser.add_argument(
        "--home",
        help="OpenHalo home holding this terminal's paired configuration.",
    )
    subparsers = parser.add_subparsers(dest="command")
    setup = subparsers.add_parser("setup", help="Pair this terminal with a Runtime.")
    setup.add_argument("--url", required=True, help="Runtime WebSocket URL.")
    setup.add_argument("--pairing-code", required=True, help="One-time code from openhalo pair.")
    setup.add_argument("--device-id", help="Stable device id for this terminal.")
    setup.add_argument("--display-name", default="Terminal Edge", help="Visible device name.")
    subparsers.add_parser("status", help="Show saved Terminal Edge configuration.")
    run = subparsers.add_parser("run", help="Run the configured Terminal Edge.")
    run.add_argument("--line-mode", action="store_true", help="Use line mode instead of the terminal UI.")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    home: PersonalHome | None = None,
    pairing_exchange: Callable[..., TerminalCredentials] | None = None,
    terminal_main: Callable[[list[str]], None] = terminal_daemon_main,
) -> int:
    args = build_parser().parse_args(argv)
    personal_home = home or (
        PersonalHome(Path(args.home))
        if args.home
        else PersonalHome.from_environment()
    )
    if args.command == "setup":
        validate_runtime_endpoint(args.url)
        device_id = args.device_id or f"terminal-edge-{secrets.token_hex(4)}"
        credentials = _resolve_pairing_exchange(
            pairing_exchange or pair_terminal_edge,
            url=args.url,
            pairing_code=args.pairing_code,
            device_id=device_id,
            display_name=args.display_name,
            identity_home=personal_home.root,
        )
        personal_home.configure_terminal_edge(
            url=args.url,
            device_id=credentials.device_id,
            display_name=credentials.display_name,
            public_key_fingerprint=credentials.public_key_fingerprint,
        )
        _emit({"state": "paired", "url": args.url, "device_id": credentials.device_id})
        return 0
    if args.command == "status":
        configuration = personal_home.load_configuration().get("terminal_edge")
        if not isinstance(configuration, dict):
            _emit({"state": "needs_setup"})
            return 1
        _emit(
            {
                "state": "configured",
                "url": configuration["url"],
                "device_id": configuration["device_id"],
            }
        )
        return 0

    _launch_terminal_edge(personal_home, terminal_main, tui=not getattr(args, "line_mode", False))
    return 0


async def pair_terminal_edge(
    *,
    url: str,
    pairing_code: str,
    device_id: str,
    display_name: str,
    identity_home,
) -> TerminalCredentials:
    validate_runtime_endpoint(url)
    identity = load_or_create_identity(identity_home, device_id)
    frame = build_connect_frame(
        device_id=device_id,
        device_type="desktop-cli",
        audience=url,
        session_id=f"pair-{secrets.token_urlsafe(16)}",
        pairing_code=pairing_code,
        public_key=identity.public_key,
        display_name=display_name,
    )
    async with websockets.connect(url) as websocket:
        await websocket.send(json.dumps(frame))
        challenge = json.loads(await websocket.recv())
        if challenge.get("type") == "error":
            raise ValueError(challenge.get("message", "Runtime did not accept the pairing code."))
        if challenge.get("type") != "auth_challenge":
            raise ValueError("Runtime did not issue a pairing challenge.")
        challenge_body = challenge.get("challenge")
        if not isinstance(challenge_body, dict):
            raise ValueError("Runtime returned an invalid pairing challenge.")
        signature = sign_challenge(
            identity.private_key,
            build_challenge_payload(
                audience=challenge["audience"],
                device_id=challenge["device_id"],
                session_id=challenge["session_id"],
                challenge_id=challenge_body["challenge_id"],
                nonce=challenge_body["nonce"],
                expires_at=challenge_body["expires_at"],
            ),
        )
        await websocket.send(
            json.dumps(
                {
                    "api_version": frame["api_version"],
                    "type": "auth_proof",
                    "device_id": device_id,
                    "session_id": frame["session_id"],
                    "audience": url,
                    "challenge_id": challenge_body["challenge_id"],
                    "signature": encode_base64url(signature),
                }
            )
        )
        reply = json.loads(await websocket.recv())
    if reply.get("type") == "error":
        raise ValueError(reply.get("message", "Runtime did not accept the pairing code."))
    if reply.get("type") != "connect_ok":
        raise ValueError("Runtime did not accept the device proof.")
    return TerminalCredentials(
        device_id=device_id,
        display_name=display_name,
        public_key_fingerprint=identity.public_key_fingerprint,
    )


def _resolve_pairing_exchange(
    exchange: Callable[..., TerminalCredentials],
    **kwargs: str,
) -> TerminalCredentials:
    result = exchange(**kwargs)
    if inspect.isawaitable(result):
        result = asyncio.run(result)
    if not isinstance(result, TerminalCredentials):
        raise ValueError("Terminal pairing did not return device credentials.")
    return result


def _launch_terminal_edge(
    home: PersonalHome,
    terminal_main: Callable[[list[str]], None],
    *,
    tui: bool,
) -> None:
    configuration = home.load_configuration().get("terminal_edge")
    if not isinstance(configuration, dict):
        raise ValueError("Terminal Edge is not configured; run openhalo-edge setup")
    arguments = [
        "--url",
        configuration["url"],
        "--device-id",
        configuration["device_id"],
        "--display-name",
        configuration["display_name"],
        "--home",
        str(home.root),
    ]
    if tui:
        arguments.append("--tui")
    terminal_main(arguments)


def _emit(payload: dict) -> None:
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
