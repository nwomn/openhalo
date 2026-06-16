"""CLI runner for the v0 single-edge loop."""

import argparse
import asyncio

from device_edge.session_client import SessionClient
from personal_runtime.gateway_server import RuntimeGateway


def run_cli_once(text: str, token: str = "dev-token") -> dict:
    gateway = RuntimeGateway(shared_token=token)
    client = SessionClient(
        device_id="desktop-dev-1",
        device_type="desktop-cli",
        token=token,
    )
    replies = gateway.run_roundtrip(
        [
            client.build_connect_frame(),
            client.build_capability_announce_frame(),
            client.build_text_event(text),
        ]
    )
    action_request = replies[-1]
    return client.handle_action_request(action_request)


async def run_cli_once_over_websocket(text: str, url: str, token: str = "dev-token") -> dict:
    client = SessionClient(
        device_id="desktop-dev-1",
        device_type="desktop-cli",
        token=token,
    )
    return await client.run_websocket_client(url=url, text=text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the v0 device edge CLI.")
    parser.add_argument("--url", help="Runtime WebSocket URL for real client/server mode.")
    parser.add_argument("--token", default="dev-token", help="Shared development token.")
    parser.add_argument("--text", help="Optional text input to send without prompting.")
    args = parser.parse_args()

    print("CLI edge ready. Type one line to send to the runtime:")
    text = args.text or input("> ").strip()
    if args.url:
        result = asyncio.run(
            run_cli_once_over_websocket(text=text, url=args.url, token=args.token)
        )
    else:
        result = run_cli_once(text, token=args.token)
    print(f"Action result: {result['result']['status']}")


if __name__ == "__main__":
    main()
