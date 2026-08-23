"""Safe one-shot pairing and reconnect CLI for the constrained MaixCAM image."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

try:  # Support both ``python -m`` and the copied single-directory device form.
    from .openssl_session import CameraEdgeCredentials
    from .openssl_session import OpenSslCameraSessionClient
except ImportError:  # pragma: no cover - exercised on the copied MaixCAM files.
    from openssl_session import CameraEdgeCredentials
    from openssl_session import OpenSslCameraSessionClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pair or reconnect a MaixCAM Camera Edge without exposing secrets."
    )
    parser.add_argument("--url", required=True, help="Exact owner Runtime ws:// or wss:// URL.")
    parser.add_argument("--device-id", default="camera-edge-1")
    parser.add_argument("--display-name", default="Desk Camera")
    parser.add_argument("--identity-home", default="/root/.openhalo-camera-edge")
    parser.add_argument(
        "--capability",
        action="append",
        dest="capabilities",
        default=None,
        help="Repeat to register another simple capability; defaults to camera.health.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    pair = commands.add_parser("pair", help="Use one one-time pairing code from standard input.")
    pair.add_argument(
        "--pairing-code-stdin",
        action="store_true",
        help="Read the pairing code from stdin. A code is never accepted as a command argument.",
    )
    commands.add_parser("reconnect", help="Authenticate with the retained P-256 identity.")
    return parser


def _client_from_args(args: argparse.Namespace) -> OpenSslCameraSessionClient:
    return OpenSslCameraSessionClient(
        device_id=args.device_id,
        audience=args.url,
        identity_home=Path(args.identity_home),
        display_name=args.display_name,
        device_type="camera-edge",
    )


async def _reconnect(client: OpenSslCameraSessionClient, capabilities: list[str]) -> str:
    import websockets

    async with websockets.connect(client.audience) as websocket:
        return await client.authenticate(websocket, capabilities)


def _safe_result(credentials: CameraEdgeCredentials) -> str:
    return json.dumps(
        {
            "state": "paired",
            "device_id": credentials.device_id,
            "display_name": credentials.display_name,
            "public_key_fingerprint": credentials.public_key_fingerprint,
        },
        sort_keys=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    capabilities = args.capabilities or ["camera.health"]
    client = _client_from_args(args)

    if args.command == "pair":
        if not args.pairing_code_stdin:
            parser.error("pair requires --pairing-code-stdin; pairing codes must not appear in shell history.")
        pairing_code = sys.stdin.readline().strip()
        if not pairing_code:
            parser.error("pairing code stdin was empty.")
        print(_safe_result(asyncio.run(client.pair(pairing_code, capabilities))))
        return 0

    session_id = asyncio.run(_reconnect(client, capabilities))
    print(json.dumps({"state": "authenticated", "device_id": client.device_id, "session_id": session_id}))
    return 0


if __name__ == "__main__":  # pragma: no cover - command-line entry point.
    raise SystemExit(main())
