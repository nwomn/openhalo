"""CLI edge surface implementation."""

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from device_edge.host.host_daemon import HostEdgeDaemon
from device_edge.shared.identity import create_ephemeral_identity
from device_edge.shared.session_client import SessionClient
from edge_api.protocol import build_connect_frame
from openhalo_common.diagnostics import InMemoryDiagnosticRecorder
from personal_runtime.chain_inspection import build_chain_report
from personal_runtime.chain_inspection import format_chain_report
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.pairing_store import PairingStore
from personal_runtime.trace_recorder import TraceRecorder


LOCAL_CLI_AUDIENCE = "ws://127.0.0.1:18765"


class LocalCliSession:
    def __init__(
        self,
        trace: bool = False,
        config_path: Path | None = None,
        grounding_edge_history_fetcher=None,
        diagnostic_recorder=None,
    ) -> None:
        self.trace_recorder = TraceRecorder() if trace else None
        self.diagnostic_recorder = diagnostic_recorder
        self._temporary_directory = TemporaryDirectory()
        self.pairing_store = PairingStore(
            Path(self._temporary_directory.name) / "pairing.json"
        )
        self.gateway = RuntimeGateway(
            trace_recorder=self.trace_recorder,
            persist_state=False,
            llm_config_path=config_path,
            grounding_edge_history_fetcher=grounding_edge_history_fetcher,
            diagnostic_recorder=diagnostic_recorder,
            pairing_store=self.pairing_store,
            audience=LOCAL_CLI_AUDIENCE,
        )
        self.client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            audience=LOCAL_CLI_AUDIENCE,
            identity=create_ephemeral_identity(),
            display_name="Local CLI",
            trace_recorder=self.trace_recorder,
            diagnostic_recorder=diagnostic_recorder,
        )
        self.register_edge(self.client)
        self._trace_offset = 0

    def register_edge(self, client: SessionClient) -> None:
        self.pairing_store.provision_local_device(
            device_id=client.device_id,
            device_type=client.device_type,
            display_name=client.session_link.display_name,
            audience=client.audience,
            public_key=client.identity.public_key,
        )
        challenge = self.gateway.run_roundtrip([client.build_connect_frame()])[-1]
        if challenge.get("type") != "auth_challenge":
            raise RuntimeError("Local CLI did not receive an authentication challenge.")
        connect_ok = self.gateway.run_roundtrip(
            [client.build_auth_proof_frame(challenge)]
        )[-1]
        if connect_ok.get("type") != "connect_ok":
            raise RuntimeError("Local CLI authentication was not accepted.")
        self.gateway.run_roundtrip([client.build_capability_announce_frame()])

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
    trace: bool = False,
    config_path: Path | None = None,
) -> dict | tuple[dict, list[str]]:
    session = LocalCliSession(trace=trace, config_path=config_path)
    result = session.send_text(text)
    if trace:
        return result, session.drain_trace_lines()
    return result


def inspect_cli_once(
    text: str,
    config_path: Path | None = None,
) -> dict:
    observed_at = (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    diagnostic_recorder = InMemoryDiagnosticRecorder()
    session = LocalCliSession(
        trace=True,
        config_path=config_path,
        diagnostic_recorder=diagnostic_recorder,
    )
    host_daemon = _build_inspection_host_daemon(
        audience=session.client.audience,
        observed_at=observed_at,
    )
    session.gateway.grounding_edge_history_fetcher = lambda: _fetch_inspection_edge_history(
        host_daemon
    )
    session.gateway.state.upsert_goal(
        goal_id="goal-1",
        title="Keep runtime healthy",
        status="active",
        summary="Watch runtime health signals.",
        updated_at="2026-06-22T10:00:00Z",
    )
    session.register_edge(host_daemon.client)
    session.gateway.run_roundtrip(host_daemon.build_observation_frames(observed_at=observed_at))
    action_result = session.send_text(text)
    return build_chain_report(session, action_result)


def inspect_agent_initiative_once(
    action_capability: str = "runtime.status",
    config_path: Path | None = None,
) -> dict:
    observed_at = (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    diagnostic_recorder = InMemoryDiagnosticRecorder()
    session = LocalCliSession(
        trace=True,
        config_path=config_path,
        diagnostic_recorder=diagnostic_recorder,
    )
    host_daemon = _build_inspection_host_daemon(
        audience=session.client.audience,
        observed_at=observed_at,
    )
    session.gateway.grounding_edge_history_fetcher = lambda: _fetch_inspection_edge_history(
        host_daemon
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
    session.register_edge(host_daemon.client)
    session.gateway.run_roundtrip(host_daemon.build_observation_frames(observed_at=observed_at))
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
    pairing_code: str,
) -> dict:
    identity = create_ephemeral_identity()
    client = SessionClient(
        device_id="desktop-dev-1",
        device_type="desktop-cli",
        audience=url,
        identity=identity,
        display_name="Local CLI",
    )
    pairing_connect = build_connect_frame(
        device_id=client.device_id,
        device_type=client.device_type,
        audience=url,
        session_id=client.session_id,
        pairing_code=pairing_code,
        public_key=identity.public_key,
        display_name="Local CLI",
    )
    import json
    import websockets

    async with websockets.connect(url) as websocket:
        await websocket.send(json.dumps(pairing_connect))
        challenge = json.loads(await websocket.recv())
        await websocket.send(json.dumps(client.build_auth_proof_frame(challenge)))
        connect_ok = json.loads(await websocket.recv())
        if connect_ok.get("type") != "connect_ok":
            raise RuntimeError("Runtime rejected Local CLI authentication.")
        await websocket.send(json.dumps(client.build_capability_announce_frame()))
        await websocket.send(json.dumps(client.build_text_event(text)))
        await websocket.recv()
        action_request = json.loads(await websocket.recv())
        action_result = client.handle_action_request(action_request)
        await websocket.send(json.dumps(action_result))
        return action_result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the v0 device edge CLI.")
    parser.add_argument("--url", help="Runtime WebSocket URL for real client/server mode.")
    parser.add_argument(
        "--pairing-code",
        help="One-time pairing code required for real client/server mode.",
    )
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
        if not args.pairing_code:
            parser.error("--url requires --pairing-code")
        result = asyncio.run(
            run_cli_once_over_websocket(
                text=text,
                url=args.url,
                pairing_code=args.pairing_code,
            )
        )
    else:
        config_path = Path(args.llm_config_path) if args.llm_config_path else None
        if args.inspect_agent_initiative:
            report = inspect_agent_initiative_once(
                config_path=config_path,
            )
            print(format_chain_report(report))
            result = report["action_result"]
            print(f"Action result: {result['result']['status']}")
            return
        if args.inspect_prompt_contract:
            report = inspect_cli_once(text, config_path=config_path)
            print(format_chain_report(report))
            result = report["action_result"]
            print(f"Action result: {result['result']['status']}")
            return
        if args.inspect_chain:
            report = inspect_cli_once(text, config_path=config_path)
            print(format_chain_report(report))
            result = report["action_result"]
            print(f"Action result: {result['result']['status']}")
            return
        local_result = run_cli_once(
            text,
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
    audience: str,
    observed_at: str,
) -> HostEdgeDaemon:
    return HostEdgeDaemon(
        device_id="host-edge-1",
        audience=audience,
        identity=create_ephemeral_identity(),
        display_name="Runtime Host",
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
