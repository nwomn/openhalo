"""CLI edge surface implementation."""

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path

from device_edge.host.host_daemon import HostEdgeDaemon
from device_edge.shared.session_client import SessionClient
from openhalo_common.diagnostics import InMemoryDiagnosticRecorder
from personal_runtime.chain_inspection import build_chain_report
from personal_runtime.chain_inspection import format_chain_report
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.trace_recorder import TraceRecorder


class LocalCliSession:
    def __init__(
        self,
        token: str = "dev-token",
        trace: bool = False,
        config_path: Path | None = None,
        grounding_edge_history_fetcher=None,
        diagnostic_recorder=None,
    ) -> None:
        self.trace_recorder = TraceRecorder() if trace else None
        self.diagnostic_recorder = diagnostic_recorder
        self.gateway = RuntimeGateway(
            shared_token=token,
            trace_recorder=self.trace_recorder,
            persist_state=False,
            llm_config_path=config_path,
            grounding_edge_history_fetcher=grounding_edge_history_fetcher,
            diagnostic_recorder=diagnostic_recorder,
        )
        self.client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token=token,
            trace_recorder=self.trace_recorder,
            diagnostic_recorder=diagnostic_recorder,
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
        action_request = next(
            (reply for reply in reversed(replies) if reply["type"] == "action_request"),
            None,
        )
        interaction_update = next(
            (
                reply
                for reply in reversed(replies)
                if reply["type"] == "interaction_update"
            ),
            None,
        )
        if action_request is None:
            if interaction_update is not None:
                return {
                    "type": "action_result",
                    "device_id": self.client.device_id,
                    "result": {
                        "status": "completed",
                        "details": {
                            "message": interaction_update["interaction"].get(
                                "summary", ""
                            )
                        },
                    },
                }
            return {
                "type": "action_result",
                "device_id": self.client.device_id,
                "result": {"status": "suppressed"},
            }
        if action_request["action"]["capability"].startswith("runtime."):
            result = _InspectionRuntimeStatusAdapter().execute_action_request(
                action_request,
                action_request["device_id"],
            )
            follow_up = self.gateway.run_roundtrip([result])
            follow_up_action = next(
                (
                    reply
                    for reply in reversed(follow_up)
                    if reply["type"] == "action_request"
                ),
                None,
            )
            if follow_up_action is not None:
                follow_up_result = self.client.handle_action_request(follow_up_action)
                final_follow_up = self.gateway.run_roundtrip([follow_up_result])
                interaction_update = next(
                    (
                        reply
                        for reply in reversed(final_follow_up)
                        if reply["type"] == "interaction_update"
                    ),
                    None,
                )
                if interaction_update is not None:
                    result["interaction"] = interaction_update["interaction"]
                return result
            interaction_update = next(
                (
                    reply
                    for reply in reversed(follow_up)
                    if reply["type"] == "interaction_update"
                ),
                None,
            )
            if interaction_update is not None:
                result["interaction"] = interaction_update["interaction"]
            return result
        result = self.client.handle_action_request(action_request)
        follow_up = self.gateway.run_roundtrip([result])
        interaction_update = next(
            (
                reply
                for reply in reversed(follow_up)
                if reply["type"] == "interaction_update"
            ),
            interaction_update,
        )
        if interaction_update is not None:
            result["interaction"] = interaction_update["interaction"]
        return result

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
            result = action_handler(action_request)
        else:
            result = self.client.handle_action_request(action_request)
        if result.get("interaction_id"):
            follow_up = self.gateway.run_roundtrip([result])
            interaction_update = next(
                (
                    reply
                    for reply in reversed(follow_up)
                    if reply["type"] == "interaction_update"
                ),
                None,
            )
            if interaction_update is not None:
                result["interaction"] = interaction_update["interaction"]
        return result

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
    config_path: Path | None = None,
) -> dict | tuple[dict, list[str]]:
    session = LocalCliSession(token=token, trace=trace, config_path=config_path)
    result = session.send_text(text)
    if trace:
        return result, session.drain_trace_lines()
    return result


def inspect_cli_once(
    text: str,
    token: str = "dev-token",
    config_path: Path | None = None,
) -> dict:
    observed_at = (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    host_daemon = _build_inspection_host_daemon(
        token=token,
        observed_at=observed_at,
    )
    diagnostic_recorder = InMemoryDiagnosticRecorder()
    session = LocalCliSession(
        token=token,
        trace=True,
        config_path=config_path,
        grounding_edge_history_fetcher=lambda: _fetch_inspection_edge_history(
            host_daemon
        ),
        diagnostic_recorder=diagnostic_recorder,
    )
    session.gateway.state.upsert_goal(
        goal_id="goal-1",
        title="Keep runtime healthy",
        status="active",
        summary="Watch runtime health signals.",
        updated_at="2026-06-22T10:00:00Z",
    )
    session.gateway.run_roundtrip(
        host_daemon.build_bootstrap_frames() + host_daemon.build_observation_frames(observed_at=observed_at)
    )
    action_result = session.send_text(text)
    return build_chain_report(session, action_result)


def inspect_agent_initiative_once(
    action_capability: str = "runtime.status",
    token: str = "dev-token",
    config_path: Path | None = None,
) -> dict:
    observed_at = (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    host_daemon = _build_inspection_host_daemon(
        token=token,
        observed_at=observed_at,
    )
    diagnostic_recorder = InMemoryDiagnosticRecorder()
    session = LocalCliSession(
        token=token,
        trace=True,
        config_path=config_path,
        grounding_edge_history_fetcher=lambda: _fetch_inspection_edge_history(
            host_daemon
        ),
        diagnostic_recorder=diagnostic_recorder,
    )
    session.gateway.state.upsert_goal(
        goal_id="goal-1",
        title="Keep runtime healthy",
        status="active",
        summary="Watch runtime health signals.",
        updated_at="2026-06-22T10:00:00Z",
    )
    host_daemon.trace_recorder = session.trace_recorder
    host_daemon.client.trace_recorder = session.trace_recorder
    session.gateway.run_roundtrip(
        host_daemon.build_bootstrap_frames() + host_daemon.build_observation_frames(observed_at=observed_at)
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
        "--llm-config-path",
        help="Optional explicit runtime model config path for local inspection mode.",
    )
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
    parser.add_argument(
        "--inspect-prompt-contract",
        action="store_true",
        help="Print a human-readable M12 prompt/context contract report in local roundtrip mode.",
    )
    args = parser.parse_args()

    if args.inspect_agent_initiative:
        text = args.text or ""
    elif args.inspect_prompt_contract:
        if args.text is not None:
            text = args.text
        else:
            print("CLI edge ready. Type one line to send to the runtime:")
            text = input("> ").strip()
    elif args.inspect_chain:
        if args.text is not None:
            text = args.text
        else:
            print("CLI edge ready. Type one line to send to the runtime:")
            text = input("> ").strip()
    else:
        print("CLI edge ready. Type one line to send to the runtime:")
        text = args.text or input("> ").strip()
    if args.url:
        result = asyncio.run(
            run_cli_once_over_websocket(text=text, url=args.url, token=args.token)
        )
    else:
        config_path = Path(args.llm_config_path) if args.llm_config_path else None
        if args.inspect_agent_initiative:
            report = inspect_agent_initiative_once(
                token=args.token,
                config_path=config_path,
            )
            print(format_chain_report(report))
            result = report["action_result"]
            print(f"Action result: {result['result']['status']}")
            return
        if args.inspect_prompt_contract:
            report = inspect_cli_once(text, token=args.token, config_path=config_path)
            print(format_chain_report(report))
            result = report["action_result"]
            print(f"Action result: {result['result']['status']}")
            return
        if args.inspect_chain:
            report = inspect_cli_once(text, token=args.token, config_path=config_path)
            print(format_chain_report(report))
            result = report["action_result"]
            print(f"Action result: {result['result']['status']}")
            return
        local_result = run_cli_once(
            text,
            token=args.token,
            trace=args.trace,
            config_path=config_path,
        )
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
    def execute_action_request(self, frame: dict, device_id: str) -> dict:
        result = {
            "type": "action_result",
            "device_id": device_id,
            "result": self.execute(frame["action"]),
        }
        if frame.get("interaction_id"):
            result["interaction_id"] = frame["interaction_id"]
        if frame.get("interaction_turn_id"):
            result["interaction_turn_id"] = frame["interaction_turn_id"]
        if frame.get("request_id"):
            result["request_id"] = frame["request_id"]
        return result

    def execute(self, action: dict) -> dict:
        if action["capability"] == "runtime.edge_history":
            details = action["payload"]["history_supplier"](
                action["payload"].get("limit", 20),
                action["payload"].get("capability"),
            )
            return {
                "status": "ok",
                "capability": action["capability"],
                "details": details,
            }
        return {
            "status": "ok",
            "capability": action["capability"],
            "details": {"state": "running", "pid": 4242},
        }


def _build_inspection_host_daemon(
    token: str,
    observed_at: str,
) -> HostEdgeDaemon:
    return HostEdgeDaemon(
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
    )


def _fetch_inspection_edge_history(host_daemon: HostEdgeDaemon) -> dict:
    result = host_daemon.handle_action_request(
        {
            "type": "action_request",
            "device_id": host_daemon.client.device_id,
            "action": {
                "capability": "runtime.edge_history",
                "payload": {"limit": 2},
            },
        }
    )
    return result["result"]["details"]


if __name__ == "__main__":
    main()
