"""Manual demo entrypoint for the v0 personal runtime."""

import argparse
import asyncio

from personal_runtime.gateway_server import RuntimeGateway


def build_runtime_server_message(url: str) -> str:
    return (
        "Personal runtime WebSocket server is ready.\n"
        f"Connect an edge client to {url}"
    )


async def run_server(host: str, port: int, token: str) -> None:
    gateway = RuntimeGateway(shared_token=token)
    async with gateway.run_server(host=host, port=port) as server_info:
        print(build_runtime_server_message(server_info["url"]))
        await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the v0 personal runtime server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind.")
    parser.add_argument("--token", default="dev-token", help="Shared development token.")
    args = parser.parse_args()

    asyncio.run(run_server(host=args.host, port=args.port, token=args.token))


if __name__ == "__main__":
    main()
