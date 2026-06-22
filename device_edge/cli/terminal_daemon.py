"""Resident terminal-edge daemon for the M8 terminal interaction slice."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from datetime import timezone
from contextlib import suppress

import websockets

from device_edge.shared.local_actions import execute_action
from device_edge.shared.session_client import SessionClient


class TerminalEdgeDaemon:
    def __init__(
        self,
        device_id: str,
        token: str,
        output_stream=None,
        input_stream=None,
        timestamp_provider=None,
        stdin_observed_at: str | None = None,
    ) -> None:
        self.output_stream = output_stream or sys.stdout
        self.input_stream = input_stream or sys.stdin
        self.timestamp_provider = timestamp_provider or self._default_timestamp_provider
        self.stdin_observed_at = stdin_observed_at
        self.client = SessionClient(
            device_id=device_id,
            device_type="desktop-cli",
            token=token,
            capabilities=["text.input", "notification.show", "terminal.context"],
        )

    @staticmethod
    def _default_timestamp_provider() -> str:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def build_bootstrap_frames(self) -> list[dict]:
        return [
            self.client.build_connect_frame(),
            self.client.build_capability_announce_frame(),
        ]

    def build_terminal_activity_frame(
        self,
        activity_state: str,
        observed_at: str,
    ) -> dict:
        return self.client.build_terminal_activity_event(
            activity_state=activity_state,
            observed_at=observed_at,
        )

    def build_user_input_frames(
        self,
        text: str,
        observed_at: str,
    ) -> list[dict]:
        return [
            self.build_terminal_activity_frame(
                activity_state="active",
                observed_at=observed_at,
            ),
            {
                "type": "event_push",
                "device_id": self.client.device_id,
                "capability": "text.input",
                "payload": {
                    "text": text,
                    "observed_at": observed_at,
                },
            },
        ]

    def _next_observed_at(self, explicit_observed_at: str | None = None) -> str:
        if explicit_observed_at is not None:
            return explicit_observed_at
        return self.timestamp_provider()

    async def _read_live_input_line(self) -> str | None:
        loop = asyncio.get_running_loop()
        line = await loop.run_in_executor(None, self.input_stream.readline)
        if line == "":
            return None
        return line

    async def _send_user_input(
        self,
        websocket,
        text: str,
        observed_at: str | None = None,
        pending_frames: list[dict] | None = None,
    ) -> bool:
        normalized_text = text.strip()
        if not normalized_text:
            return False
        event_timestamp = self._next_observed_at(observed_at)
        for frame in self.build_user_input_frames(
            text=normalized_text,
            observed_at=event_timestamp,
        ):
            await self._send_frame(websocket, frame)
            if pending_frames is None:
                await self._recv_frame(websocket)
            else:
                await self._recv_expected_frame(
                    websocket,
                    pending_frames,
                    expected_type="event_ack",
                )
        return True

    async def _drain_live_input(self, websocket) -> bool:
        line = await self._read_live_input_line()
        if line is None:
            return False
        return await self._send_user_input(
            websocket,
            text=line,
        )

    async def _recv_expected_frame(
        self,
        websocket,
        pending_frames: list[dict],
        expected_type: str,
    ) -> dict:
        for index, frame in enumerate(pending_frames):
            if frame.get("type") == expected_type:
                return pending_frames.pop(index)
        while True:
            frame = await self._recv_frame(websocket)
            if frame.get("type") == expected_type:
                return frame
            pending_frames.append(frame)

    def handle_action_request(self, frame: dict) -> dict:
        result = execute_action(
            frame["action"],
            output_stream=self.output_stream,
            delivered_via="terminal.stdout",
        )
        return {
            "type": "action_result",
            "device_id": self.client.device_id,
            "result": result,
        }

    async def _send_frame(self, websocket, frame: dict) -> None:
        await websocket.send(json.dumps(frame))

    async def _recv_frame(self, websocket) -> dict:
        return json.loads(await websocket.recv())

    async def run_scripted_session(
        self,
        websocket,
        scripted_inputs: list[dict],
        startup_observed_at: str | None,
        idle_after_inputs: bool = False,
        idle_timeout_s: float = 30.0,
        idle_observed_at: str | None = None,
        max_idle_cycles: int | None = None,
        max_action_requests: int | None = None,
        enable_live_input: bool = False,
    ) -> list[dict]:
        results: list[dict] = []
        idle_cycles = 0
        pending_frames: list[dict] = []
        terminal_activity_state = "unknown"
        live_input_open = enable_live_input
        live_input_task = None

        for frame in self.build_bootstrap_frames():
            await self._send_frame(websocket, frame)
        await self._recv_frame(websocket)

        startup_timestamp = self._next_observed_at(startup_observed_at)
        await self._send_frame(
            websocket,
            self.build_terminal_activity_frame(
                activity_state="active",
                observed_at=startup_timestamp,
            ),
        )
        await self._recv_frame(websocket)
        terminal_activity_state = "active"

        for scripted_input in scripted_inputs:
            input_sent = await self._send_user_input(
                websocket,
                text=scripted_input["text"],
                observed_at=scripted_input["observed_at"],
                pending_frames=pending_frames,
            )
            if input_sent:
                terminal_activity_state = "active"

        if idle_after_inputs:
            while max_action_requests is None or len(results) < max_action_requests:
                recv_task = asyncio.create_task(self._recv_frame(websocket))
                if live_input_open and live_input_task is None:
                    live_input_task = asyncio.create_task(self._read_live_input_line())
                try:
                    wait_set = {recv_task}
                    if live_input_task is not None:
                        wait_set.add(live_input_task)
                    done, pending = await asyncio.wait(
                        wait_set,
                        timeout=idle_timeout_s,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                except asyncio.TimeoutError:
                    done = set()
                    pending = {recv_task}
                    if live_input_task is not None:
                        pending.add(live_input_task)

                if recv_task in pending:
                    recv_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await recv_task

                if not done:
                    if terminal_activity_state == "idle":
                        if max_idle_cycles is not None:
                            idle_cycles += 1
                            if idle_cycles >= max_idle_cycles:
                                return results
                        continue
                    idle_timestamp = self._next_observed_at(idle_observed_at)
                    await self._send_frame(
                        websocket,
                        self.build_terminal_activity_frame(
                            activity_state="idle",
                            observed_at=idle_timestamp,
                        ),
                    )
                    try:
                        await self._recv_expected_frame(
                            websocket,
                            pending_frames,
                            expected_type="event_ack",
                        )
                    except RuntimeError as exc:
                        if "StopIteration" not in str(exc):
                            raise
                        return results
                    terminal_activity_state = "idle"
                    idle_cycles += 1
                    if max_idle_cycles is not None and idle_cycles >= max_idle_cycles:
                        return results
                    continue

                if live_input_task is not None and live_input_task in done:
                    line = live_input_task.result()
                    live_input_task = None
                    if line is None:
                        live_input_open = False
                    else:
                        observed_at_override = self.stdin_observed_at
                        self.stdin_observed_at = None
                        input_sent = await self._send_user_input(
                            websocket,
                            text=line,
                            observed_at=observed_at_override,
                            pending_frames=pending_frames,
                        )
                        if input_sent:
                            terminal_activity_state = "active"
                            idle_cycles = 0

                if recv_task in done:
                    try:
                        frame = recv_task.result()
                    except RuntimeError as exc:
                        if "StopIteration" not in str(exc):
                            raise
                        break
                    pending_frames.append(frame)

                action_frame = next(
                    (
                        pending_frames.pop(index)
                        for index, candidate in enumerate(pending_frames)
                        if candidate.get("type") == "action_request"
                    ),
                    None,
                )
                if action_frame is None:
                    continue
                idle_cycles = 0
                result = self.handle_action_request(action_frame)
                results.append(result)
                await self._send_frame(websocket, result)

        return results

    async def run_forever(
        self,
        url: str,
        scripted_inputs: list[dict] | None = None,
        startup_observed_at: str | None = None,
        idle_timeout_s: float = 30.0,
        idle_observed_at: str | None = None,
        max_idle_cycles: int | None = None,
        max_action_requests: int | None = None,
        max_sessions: int | None = None,
        enable_live_input: bool = False,
    ) -> None:
        session_count = 0
        while max_sessions is None or session_count < max_sessions:
            async with websockets.connect(url) as websocket:
                await self.run_scripted_session(
                    websocket=websocket,
                    scripted_inputs=scripted_inputs or [],
                    startup_observed_at=startup_observed_at,
                    idle_after_inputs=True,
                    idle_timeout_s=idle_timeout_s,
                    idle_observed_at=idle_observed_at,
                    max_idle_cycles=max_idle_cycles,
                    max_action_requests=max_action_requests,
                    enable_live_input=enable_live_input,
                )
            session_count += 1


def build_terminal_daemon_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the M8 terminal edge daemon.")
    parser.add_argument("--url", required=True, help="Runtime WebSocket URL.")
    parser.add_argument("--token", default="dev-token", help="Shared development token.")
    parser.add_argument(
        "--device-id",
        default="terminal-edge-1",
        help="Terminal edge device id.",
    )
    parser.add_argument(
        "--startup-observed-at",
        help="Initial active terminal observation timestamp.",
    )
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=30.0,
        help="Seconds to wait before emitting idle terminal activity.",
    )
    parser.add_argument(
        "--idle-observed-at",
        help="Timestamp to use for scripted idle terminal activity.",
    )
    parser.add_argument(
        "--max-idle-cycles",
        type=int,
        help="Optional number of idle cycles before exiting.",
    )
    parser.add_argument(
        "--max-action-requests",
        type=int,
        help="Optional number of action requests to handle before exiting.",
    )
    parser.add_argument(
        "--max-sessions",
        type=int,
        help="Optional number of daemon sessions to run before exiting.",
    )
    parser.add_argument(
        "--stdin-observed-at",
        help="Optional fixed timestamp for the first live stdin input event.",
    )
    return parser


def main() -> None:
    parser = build_terminal_daemon_parser()
    args = parser.parse_args()
    daemon = TerminalEdgeDaemon(
        device_id=args.device_id,
        token=args.token,
        stdin_observed_at=args.stdin_observed_at,
    )
    scripted_inputs = []
    scripted_text = os.environ.get("TERMINAL_EDGE_SCRIPTED_TEXT")
    scripted_observed_at = os.environ.get("TERMINAL_EDGE_SCRIPTED_OBSERVED_AT")
    if scripted_text and scripted_observed_at:
        scripted_inputs.append(
            {
                "text": scripted_text,
                "observed_at": scripted_observed_at,
            }
        )
    asyncio.run(
        daemon.run_forever(
            url=args.url,
            scripted_inputs=scripted_inputs,
            startup_observed_at=args.startup_observed_at,
            idle_timeout_s=args.idle_timeout,
            idle_observed_at=args.idle_observed_at,
            max_idle_cycles=args.max_idle_cycles,
            max_action_requests=args.max_action_requests,
            max_sessions=args.max_sessions,
            enable_live_input=True,
        )
    )


__all__ = ["TerminalEdgeDaemon", "build_terminal_daemon_parser", "main"]


if __name__ == "__main__":
    main()
