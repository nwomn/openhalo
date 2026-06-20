"""Independent host-edge daemon helpers for the first host slice."""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import sys
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosed

from device_edge.host.host_observers import build_host_metric_observations
from device_edge.host.host_observers import build_runtime_health_observations
from device_edge.host.host_observers import read_host_metric_snapshot
from device_edge.host.runtime_control import PythonProcessAdapter
from device_edge.shared.session_client import SessionClient
from personal_runtime.trace_recorder import TraceRecorder


class HostEdgeDaemon:
    def __init__(
        self,
        device_id: str,
        token: str,
        runtime_control_adapter,
        host_metrics_provider,
        runtime_health_provider,
        history_limit: int = 20,
        trace_recorder: TraceRecorder | None = None,
    ) -> None:
        self.runtime_control_adapter = runtime_control_adapter
        self.host_metrics_provider = host_metrics_provider
        self.runtime_health_provider = runtime_health_provider
        self.history_limit = history_limit
        self.observation_history = deque(maxlen=history_limit)
        self.trace_recorder = trace_recorder
        self.client = SessionClient(
            device_id=device_id,
            device_type="server",
            token=token,
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
            trace_recorder=trace_recorder,
        )

    def build_bootstrap_frames(self) -> list[dict]:
        return [
            self.client.build_connect_frame(),
            self.client.build_capability_announce_frame(),
        ]

    def build_observation_frames(self, observed_at: str) -> list[dict]:
        frames = [
            self.client.build_observation_event(
                capability="host.metrics",
                observations=build_host_metric_observations(
                    self.host_metrics_provider(),
                    observed_at=observed_at,
                ),
            ),
            self.client.build_observation_event(
                capability="runtime.health",
                observations=build_runtime_health_observations(
                    self.runtime_health_provider(),
                    observed_at=observed_at,
                ),
            ),
        ]
        self._record_observation_history(frames, observed_at=observed_at)
        return frames

    def _record_observation_history(self, frames: list[dict], observed_at: str) -> None:
        for frame in frames:
            self.observation_history.append(
                {
                    "capability": frame["capability"],
                    "observed_at": observed_at,
                    "observations": [
                        {
                            "name": observation["name"],
                            "value": observation["value"],
                            "confidence": observation["confidence"],
                        }
                        for observation in frame["payload"]["observations"]
                    ],
                }
            )
            if self.trace_recorder is not None:
                self.trace_recorder.record(
                    "HOST",
                    "recorded local observation history",
                    capability=frame["capability"],
                    observed_at=observed_at,
                )

    def build_recent_history(
        self,
        limit: int,
        capability: str | None = None,
    ) -> dict:
        entries = list(self.observation_history)
        if capability is not None:
            entries = [
                entry for entry in entries if entry["capability"] == capability
            ]
        entries = entries[-limit:]
        return {
            "history_kind": "observation_window",
            "device_id": self.client.device_id,
            "entries": entries,
            "available_entries": len(
                [
                    entry
                    for entry in self.observation_history
                    if capability is None or entry["capability"] == capability
                ]
            ),
            "returned_entries": len(entries),
        }

    def handle_action_request(self, frame: dict) -> dict:
        action = frame["action"]
        if self.trace_recorder is not None:
            self.trace_recorder.record(
                "HOST",
                "handling action request",
                capability=action["capability"],
            )
        if action["capability"] == "runtime.edge_history":
            payload = dict(action.get("payload", {}))
            payload["history_supplier"] = self.build_recent_history
            action = dict(action)
            action["payload"] = payload
        result = self.runtime_control_adapter.execute(action)
        if self.trace_recorder is not None:
            self.trace_recorder.record(
                "HOST",
                "completed action request",
                capability=action["capability"],
                status=result["status"],
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

    async def _send_bootstrap(self, websocket) -> None:
        if self.trace_recorder is not None:
            self.trace_recorder.record(
                "HOST",
                "sending bootstrap frames",
                device_id=self.client.device_id,
            )
        for frame in self.build_bootstrap_frames():
            await self._send_frame(websocket, frame)

    async def _send_observation_cycle(self, websocket, observed_at: str) -> None:
        if self.trace_recorder is not None:
            self.trace_recorder.record(
                "HOST",
                "sending observation cycle",
                observed_at=observed_at,
            )
        for frame in self.build_observation_frames(observed_at=observed_at):
            await self._send_frame(websocket, frame)
            await self._recv_frame(websocket)

    async def _send_runtime_health_follow_up(
        self,
        websocket,
        observed_at: str,
    ) -> None:
        for frame in self.build_observation_frames(observed_at=observed_at):
            if frame["capability"] != "runtime.health":
                continue
            await self._send_frame(websocket, frame)
            await self._recv_frame(websocket)
            return

    async def run_websocket_daemon_session(
        self,
        url: str,
        observation_schedule: list[str],
        observation_timestamp_provider=None,
        idle_timeout_s: float = 30.0,
        max_idle_cycles: int | None = None,
        ready_event=None,
        max_action_requests: int | None = None,
        send_follow_up_after_action: bool = True,
    ) -> list[dict]:
        action_results: list[dict] = []
        observation_index = 0
        idle_cycles = 0

        async with websockets.connect(url) as websocket:
            await self._send_bootstrap(websocket)

            if ready_event is not None:
                ready_event.set()

            await self._recv_frame(websocket)

            if observation_index < len(observation_schedule):
                await self._send_observation_cycle(
                    websocket,
                    observed_at=observation_schedule[observation_index],
                )
                observation_index += 1

            while max_action_requests is None or len(action_results) < max_action_requests:
                try:
                    frame = await asyncio.wait_for(
                        self._recv_frame(websocket),
                        timeout=idle_timeout_s,
                    )
                except asyncio.TimeoutError:
                    if observation_index < len(observation_schedule):
                        observed_at = observation_schedule[observation_index]
                        observation_index += 1
                    elif observation_timestamp_provider is not None:
                        observed_at = observation_timestamp_provider()
                    else:
                        continue
                    await self._send_observation_cycle(
                        websocket,
                        observed_at=observed_at,
                    )
                    idle_cycles += 1
                    if max_idle_cycles is not None and idle_cycles >= max_idle_cycles:
                        return action_results
                    continue

                if frame.get("type") != "action_request":
                    continue

                idle_cycles = 0
                action_result = self.handle_action_request(frame)
                await self._send_frame(websocket, action_result)
                action_results.append(action_result)

                if (
                    send_follow_up_after_action
                    and observation_index < len(observation_schedule)
                ):
                    await self._send_runtime_health_follow_up(
                        websocket,
                        observed_at=observation_schedule[observation_index],
                    )
                    observation_index += 1

            return action_results

    async def run_websocket_control_session(
        self,
        url: str,
        observed_at: str,
        ready_event=None,
        follow_up_observed_at: str | None = None,
    ) -> dict:
        observation_schedule = [observed_at]
        if follow_up_observed_at is not None:
            observation_schedule.append(follow_up_observed_at)

        action_results = await self.run_websocket_daemon_session(
            url=url,
            observation_schedule=observation_schedule,
            ready_event=ready_event,
            max_action_requests=1,
            send_follow_up_after_action=follow_up_observed_at is not None,
        )
        return action_results[0]

    async def run_forever(
        self,
        url: str,
        observation_schedule_factory,
        observation_timestamp_provider=None,
        reconnect_delay_s: float = 5.0,
        reconnect_backoff_multiplier: float = 1.0,
        reconnect_max_delay_s: float | None = None,
        reconnect_jitter=None,
        idle_timeout_s: float = 30.0,
        max_idle_cycles: int | None = None,
        max_sessions: int | None = None,
    ) -> None:
        attempts = 0
        completed_sessions = 0
        consecutive_failures = 0

        while max_sessions is None or completed_sessions < max_sessions:
            try:
                if self.trace_recorder is not None:
                    self.trace_recorder.record(
                        "HOST",
                        "starting websocket daemon session",
                        attempt=str(attempts),
                    )
                await self.run_websocket_daemon_session(
                    url=url,
                    observation_schedule=observation_schedule_factory(attempts),
                    observation_timestamp_provider=observation_timestamp_provider,
                    idle_timeout_s=idle_timeout_s,
                    max_idle_cycles=max_idle_cycles,
                )
                consecutive_failures = 0
                completed_sessions += 1
            except (OSError, ConnectionClosed):
                delay = reconnect_delay_s * (
                    reconnect_backoff_multiplier ** consecutive_failures
                )
                if reconnect_max_delay_s is not None:
                    delay = min(delay, reconnect_max_delay_s)
                if reconnect_jitter is not None:
                    delay = reconnect_jitter(delay, attempts)
                if self.trace_recorder is not None:
                    self.trace_recorder.record(
                        "HOST",
                        "retrying websocket session",
                        delay_s=str(delay),
                        attempt=str(attempts),
                    )
                await asyncio.sleep(delay)
                consecutive_failures += 1
                completed_sessions += 1
            attempts += 1


def build_host_daemon_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the host edge daemon.")
    parser.add_argument("--url", required=True, help="Runtime WebSocket URL.")
    parser.add_argument("--token", default="dev-token", help="Shared development token.")
    parser.add_argument("--device-id", default="host-edge-1", help="Host edge device id.")
    parser.add_argument(
        "--reconnect-delay",
        type=float,
        default=5.0,
        help="Seconds to wait before reconnect attempts.",
    )
    parser.add_argument(
        "--reconnect-backoff-multiplier",
        type=float,
        default=1.0,
        help="Multiplier applied after consecutive reconnect failures.",
    )
    parser.add_argument(
        "--reconnect-max-delay",
        type=float,
        help="Maximum reconnect delay in seconds.",
    )
    parser.add_argument(
        "--reconnect-jitter-fixed",
        type=float,
        help="Optional fixed jitter added to reconnect delay.",
    )
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=30.0,
        help="Seconds to wait for activity before an idle observation cycle.",
    )
    parser.add_argument(
        "--max-idle-cycles",
        type=int,
        help="Optional number of idle observation cycles before exiting the daemon session.",
    )
    parser.add_argument(
        "--max-sessions",
        type=int,
        help="Optional number of daemon sessions to run before exiting.",
    )
    parser.add_argument(
        "--runtime-process-match",
        default="personal_runtime.main",
        help="Substring used to identify the runtime process.",
    )
    parser.add_argument(
        "--runtime-start-command",
        default="python -m personal_runtime.main",
        help="Command used to start the runtime process.",
    )
    parser.add_argument(
        "--runtime-reload-command",
        help="Optional command used for runtime reload.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        help="Optional runtime log path for collect_logs.",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=20,
        help="Maximum number of recent local observation-history entries to keep on the edge.",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Print live host-edge trace lines to stdout while the daemon runs.",
    )
    parser.add_argument(
        "--trace-file",
        type=Path,
        help="Optional file path for live host-edge trace output.",
    )
    return parser


def build_trace_recorder(args) -> TraceRecorder | None:
    if not args.trace and args.trace_file is None:
        return None

    emitters = []
    if args.trace:
        emitters.append(print)
    if args.trace_file is not None:
        args.trace_file.parent.mkdir(parents=True, exist_ok=True)

        def append_trace_file(line: str) -> None:
            with args.trace_file.open("a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")

        emitters.append(append_trace_file)

    return TraceRecorder(emitters=emitters, retain_entries=True)


def build_runtime_control_adapter(args) -> PythonProcessAdapter:
    reload_command = (
        shlex.split(args.runtime_reload_command)
        if args.runtime_reload_command is not None
        else None
    )
    return PythonProcessAdapter(
        process_match_substring=args.runtime_process_match,
        start_command=shlex.split(args.runtime_start_command),
        reload_command=reload_command,
        log_path=args.log_path,
    )


def build_runtime_health_provider(runtime_control_adapter):
    def provider() -> dict:
        result = runtime_control_adapter.execute(
            {"capability": "runtime.status", "payload": {}}
        )
        details = result["details"]
        state = details.get("state")
        pid = details.get("pid")
        return {
            "health_state": "healthy" if state == "running" and pid is not None else "offline",
            "process_pid": pid,
            "process_present": pid is not None,
            "process_started_at": details.get("started_at"),
            "process_memory_rss_bytes": details.get("memory_rss_bytes") or 0,
        }

    return provider


def _build_observation_schedule(attempt: int) -> list[str]:
    minute = 30 + attempt
    return [f"2026-06-19T09:{minute:02d}:00Z"]


def build_observation_timestamp_provider(now_supplier=None):
    supplier = now_supplier or (
        lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )

    def provider() -> str:
        return supplier()

    return provider


def build_reconnect_jitter(args):
    if args.reconnect_jitter_fixed is None:
        return None

    def jitter(base_delay: float, attempt: int) -> float:
        del attempt
        return base_delay + args.reconnect_jitter_fixed

    return jitter


def main(argv: list[str] | None = None) -> None:
    parser = build_host_daemon_parser()
    args = parser.parse_args(argv)

    runtime_control_adapter = build_runtime_control_adapter(args)
    trace_recorder = build_trace_recorder(args)
    daemon = HostEdgeDaemon(
        device_id=args.device_id,
        token=args.token,
        runtime_control_adapter=runtime_control_adapter,
        host_metrics_provider=read_host_metric_snapshot,
        runtime_health_provider=build_runtime_health_provider(runtime_control_adapter),
        history_limit=args.history_limit,
        trace_recorder=trace_recorder,
    )

    print(f"Host edge daemon connecting to {args.url} as {args.device_id}")
    if args.trace or args.trace_file is not None:
        print("Trace enabled for host edge daemon.", file=sys.stdout)
    asyncio.run(
        daemon.run_forever(
            url=args.url,
            observation_schedule_factory=_build_observation_schedule,
            observation_timestamp_provider=build_observation_timestamp_provider(),
            reconnect_delay_s=args.reconnect_delay,
            reconnect_backoff_multiplier=args.reconnect_backoff_multiplier,
            reconnect_max_delay_s=args.reconnect_max_delay,
            reconnect_jitter=build_reconnect_jitter(args),
            idle_timeout_s=args.idle_timeout,
            max_idle_cycles=args.max_idle_cycles,
            max_sessions=args.max_sessions,
        )
    )


__all__ = [
    "HostEdgeDaemon",
    "build_host_daemon_parser",
    "build_observation_timestamp_provider",
    "build_reconnect_jitter",
    "build_runtime_control_adapter",
    "build_runtime_health_provider",
    "build_trace_recorder",
    "main",
]


if __name__ == "__main__":
    main()
