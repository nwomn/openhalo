"""CLI edge surface implementation."""

import argparse
import asyncio
from datetime import UTC, datetime

from device_edge.host.host_daemon import HostEdgeDaemon
from device_edge.shared.session_client import SessionClient
from personal_runtime.chain_inspection import build_chain_report
from personal_runtime.chain_inspection import format_chain_report
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

    def trigger_agent_initiative(
        self,
        action_capability: str,
        action_payload: dict | None = None,
        reason: str = "manual_check",
        observed_at: str | None = None,
        target_device_hint: str | None = None,
        action_handler=None,
    ) -> dict:
        initiative_payload = {
            "action_capability": action_capability,
            "action_payload": action_payload or {},
            "reason": reason,
        }
        if target_device_hint is not None:
            initiative_payload["target_device_hint"] = target_device_hint
        replies = self.gateway.trigger_agent_initiative(
            source_device_id=self.client.device_id,
            initiative_request=initiative_payload,
            observed_at=observed_at
            or (
                datetime.now(UTC)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            ),
        )
        action_request = next(
            (reply for reply in reversed(replies) if reply["type"] == "action_request"),
            None,
        )
        if action_request is None:
            return {"type": "action_result", "device_id": self.client.device_id, "result": {"status": "suppressed"}}
        if action_handler is not None:
            return action_handler(action_request)
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


def inspect_cli_once(text: str, token: str = "dev-token") -> dict:
    session = LocalCliSession(token=token, trace=True)
    observed_at = (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    session.gateway.run_roundtrip(
        [
            {
                "type": "event_push",
                "device_id": "host-edge-1",
                "capability": "runtime.health",
                "event_id": "inspect-runtime-health-1",
                "payload": {
                    "observations": [
                        {
                            "name": "runtime.health_state",
                            "value": "healthy",
                            "observed_at": observed_at,
                            "confidence": 1.0,
                        },
                        {
                            "name": "runtime.process_pid",
                            "value": 4242,
                            "observed_at": observed_at,
                            "confidence": 1.0,
                        },
                    ]
                },
            },
            {
                "type": "event_push",
                "device_id": "host-edge-1",
                "capability": "host.metrics",
                "event_id": "inspect-host-metrics-1",
                "payload": {
                    "observations": [
                        {
                            "name": "host.memory_pressure",
                            "value": "normal",
                            "observed_at": observed_at,
                            "confidence": 1.0,
                        }
                    ]
                },
            },
        ]
    )
    action_result = session.send_text(text)
    return build_chain_report(session, action_result)


def inspect_agent_initiative_once(
    action_capability: str = "runtime.status",
    token: str = "dev-token",
) -> dict:
    session = LocalCliSession(token=token, trace=True)
    observed_at = (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    session.gateway.run_roundtrip(
        [
            {
                "type": "connect",
                "device": {
                    "device_id": "host-edge-1",
                    "device_type": "server",
                },
                "auth": {"token": token},
            },
            {
                "type": "capability_announce",
                "device_id": "host-edge-1",
                "capabilities": ["host.metrics", "runtime.health", "runtime.control"],
            },
            {
                "type": "event_push",
                "device_id": "host-edge-1",
                "capability": "runtime.health",
                "event_id": "inspect-runtime-health-initiative-1",
                "payload": {
                    "observations": [
                        {
                            "name": "runtime.health_state",
                            "value": "healthy",
                            "observed_at": observed_at,
                            "confidence": 1.0,
                        }
                    ]
                },
            },
        ]
    )
    host_daemon = HostEdgeDaemon(
        device_id="host-edge-1",
        token=token,
        runtime_control_adapter=_InspectionRuntimeStatusAdapter(),
        host_metrics_provider=lambda: {
            "cpu_load_ratio": 0.31,
            "memory_used_bytes": 400,
            "memory_available_bytes": 600,
            "memory_pressure": "normal",
            "net_rx_bytes": 10,
            "net_tx_bytes": 12,
        },
        runtime_health_provider=lambda: {
            "health_state": "healthy",
            "process_pid": 4242,
            "process_present": True,
            "process_started_at": observed_at,
            "process_memory_rss_bytes": 28114944,
        },
        trace_recorder=session.trace_recorder,
    )
    action_result = session.trigger_agent_initiative(
        action_capability=action_capability,
        reason="manual_inspection",
        observed_at=observed_at,
        target_device_hint="host-edge-1",
        action_handler=host_daemon.handle_action_request,
    )
    return build_chain_report(session, action_result)


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
    parser.add_argument(
        "--inspect-chain",
        action="store_true",
        help="Print a human-readable M5 chain inspection report in local roundtrip mode.",
    )
    parser.add_argument(
        "--inspect-agent-initiative",
        action="store_true",
        help="Print a human-readable M6 initiative inspection report in local roundtrip mode.",
    )
    args = parser.parse_args()

    if not args.inspect_agent_initiative:
        print("CLI edge ready. Type one line to send to the runtime:")
        text = args.text or input("> ").strip()
    else:
        text = args.text or ""
    if args.url:
        result = asyncio.run(
            run_cli_once_over_websocket(text=text, url=args.url, token=args.token)
        )
    else:
        if args.inspect_agent_initiative:
            report = inspect_agent_initiative_once(token=args.token)
            print(format_chain_report(report))
            result = report["action_result"]
            print(f"Action result: {result['result']['status']}")
            return
        if args.inspect_chain:
            report = inspect_cli_once(text, token=args.token)
            print(format_chain_report(report))
            result = report["action_result"]
            print(f"Action result: {result['result']['status']}")
            return
        local_result = run_cli_once(text, token=args.token, trace=args.trace)
        if args.trace:
            result, trace_lines = local_result
            print("Trace:")
            for line in trace_lines:
                print(f"- {line}")
        else:
            result = local_result
    print(f"Action result: {result['result']['status']}")


__all__ = [
    "LocalCliSession",
    "inspect_agent_initiative_once",
    "inspect_cli_once",
    "main",
    "run_cli_once",
    "run_cli_once_over_websocket",
]


class _InspectionRuntimeStatusAdapter:
    def execute(self, action: dict) -> dict:
        return {
            "status": "ok",
            "capability": action["capability"],
            "details": {"state": "running", "pid": 4242},
        }


if __name__ == "__main__":
    main()
