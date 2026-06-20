"""Manual demo entrypoint for the v0 personal runtime."""

import argparse
import asyncio
from pathlib import Path

from personal_runtime.gateway_server import RuntimeGateway


def build_runtime_server_message(url: str) -> str:
    return (
        "Personal runtime WebSocket server is ready.\n"
        f"WebSocket URL: {url}"
    )


def build_gateway(token: str, state_path: Path) -> RuntimeGateway:
    return RuntimeGateway(
        shared_token=token,
        state_path=state_path,
        runtime_event_emitter=print,
    )


async def run_server(host: str, port: int, token: str, state_path: Path) -> None:
    gateway = build_gateway(token=token, state_path=state_path)
    async with gateway.run_server(host=host, port=port) as server_info:
        print(build_runtime_server_message(server_info["url"]))
        await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the v0 personal runtime server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind.")
    parser.add_argument("--token", default="dev-token", help="Shared development token.")
    parser.add_argument(
        "--state-path",
        default=".runtime/state.json",
        help="Path to the persisted runtime state file.",
    )
    args = parser.parse_args()

    asyncio.run(
        run_server(
            host=args.host,
            port=args.port,
            token=args.token,
            state_path=Path(args.state_path),
        )
    )


if __name__ == "__main__":
    main()
