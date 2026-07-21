"""Owner-facing setup and launch command for the personal Terminal Edge."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass

import websockets

from device_edge.cli.terminal_daemon import main as terminal_daemon_main
from edge_api.protocol import build_connect_frame
from openhalo.home import PersonalHome
from openhalo.version import format_cli_version


@dataclass(frozen=True)
class TerminalCredentials:
    device_id: str
    device_token: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Set up and run your OpenHalo Terminal Edge.")
    parser.add_argument(
        "--version",
        action="version",
        version=format_cli_version("openhalo-edge"),
        help="Show the installed OpenHalo Terminal Edge version.",
    )
    subparsers = parser.add_subparsers(dest="command")
    setup = subparsers.add_parser("setup", help="Pair this terminal with a Runtime.")
    setup.add_argument("--url", required=True, help="Runtime WebSocket URL.")
    setup.add_argument("--pairing-code", required=True, help="One-time code from openhalo pair.")
    setup.add_argument("--device-id", help="Stable device id for this terminal.")
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
    personal_home = home or PersonalHome.from_environment()
    if args.command == "setup":
        device_id = args.device_id or f"terminal-edge-{secrets.token_hex(4)}"
        credentials = _resolve_pairing_exchange(
            pairing_exchange or pair_terminal_edge,
            url=args.url,
            pairing_code=args.pairing_code,
            device_id=device_id,
        )
        personal_home.configure_terminal_edge(
            url=args.url,
            device_id=credentials.device_id,
            device_token=credentials.device_token,
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
) -> TerminalCredentials:
    frame = build_connect_frame(
        device_id=device_id,
        device_type="desktop-cli",
        token=pairing_code,
        auth_kind="pairing",
    )
    async with websockets.connect(url) as websocket:
        await websocket.send(json.dumps(frame))
        reply = json.loads(await websocket.recv())
    if reply.get("type") == "error":
        raise ValueError(reply.get("message", "Runtime did not accept the pairing code."))
    auth = reply.get("auth")
    if reply.get("type") != "connect_ok" or not isinstance(auth, dict):
        raise ValueError("Runtime did not return a paired-device credential.")
    device_token = auth.get("token")
    if auth.get("kind") != "device" or not isinstance(device_token, str) or not device_token:
        raise ValueError("Runtime returned an invalid paired-device credential.")
    return TerminalCredentials(device_id=device_id, device_token=device_token)


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
        "--token",
        configuration["device_token"],
        "--auth-kind",
        "device",
        "--device-id",
        configuration["device_id"],
    ]
    if tui:
        arguments.append("--tui")
    terminal_main(arguments)


def _emit(payload: dict) -> None:
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
