"""CLI runner for the v0 single-edge loop."""

import argparse
import asyncio

from device_edge.session_client import SessionClient
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.trace_recorder import TraceRecorder


class LocalCliSession:
    def __init__(self, token: str = "dev-token", trace: bool = False) -> None:
        self.trace_recorder = TraceRecorder() if trace else None
        self.gateway = RuntimeGateway(
            shared_token=token,
            trace_recorder=self.trace_recorder,
            persist_state=False,
        )
        self.client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token=token,
            trace_recorder=self.trace_recorder,
        )
        self.gateway.run_roundtrip(
            [
                self.client.build_connect_frame(),
                self.client.build_capability_announce_frame(),
            ]
        )
        self._trace_offset = 0

    def send_text(self, text: str) -> dict:
        replies = self.gateway.run_roundtrip(
            [
                self.client.build_text_event(text),
            ]
        )
        action_request = replies[-1]
        return self.client.handle_action_request(action_request)

    def drain_trace_lines(self) -> list[str]:
        if self.trace_recorder is None:
            return []
        lines = self.trace_recorder.format_lines()
        new_lines = lines[self._trace_offset :]
        self._trace_offset = len(lines)
        return new_lines


def run_cli_once(
    text: str,
    token: str = "dev-token",
    trace: bool = False,
) -> dict | tuple[dict, list[str]]:
    session = LocalCliSession(token=token, trace=trace)
    result = session.send_text(text)
    if trace:
        return result, session.drain_trace_lines()
    return result


async def run_cli_once_over_websocket(
    text: str,
    url: str,
    token: str = "dev-token",
) -> dict:
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
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Print a human-readable execution trace in local roundtrip mode.",
    )
    args = parser.parse_args()

    print("CLI edge ready. Type one line to send to the runtime:")
    text = args.text or input("> ").strip()
    if args.url:
        result = asyncio.run(
            run_cli_once_over_websocket(text=text, url=args.url, token=args.token)
        )
    else:
        local_result = run_cli_once(text, token=args.token, trace=args.trace)
        if args.trace:
            result, trace_lines = local_result
            print("Trace:")
            for line in trace_lines:
                print(f"- {line}")
        else:
            result = local_result
    print(f"Action result: {result['result']['status']}")


if __name__ == "__main__":
    main()
