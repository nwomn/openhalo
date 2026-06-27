import asyncio
import json
import io
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import websockets

from device_edge.cli.cli_edge import LocalCliSession
from device_edge.cli.cli_edge import run_cli_once, run_cli_once_over_websocket
from device_edge.cli.terminal_daemon import TerminalEdgeDaemon
from device_edge.host.host_daemon import HostEdgeDaemon
from device_edge.shared.session_client import SessionClient
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.main import build_runtime_server_message
from personal_runtime.main import build_runtime_server_parser
from personal_runtime.main import run_server
from personal_runtime.model_provider import ProposalPlan

ROOT = Path(__file__).resolve().parents[1]
TEST_LLM_CONFIG = ROOT / "tests" / "fixtures" / "llm-config-test.toml"
VISIBLE_ERROR_LLM_CONFIG = (
    ROOT / "tests" / "fixtures" / "llm-config-missing-key-test.toml"
)


class RoundtripTests(unittest.IsolatedAsyncioTestCase):
    async def test_user_text_roundtrips_back_to_same_edge(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )
        replies = await gateway.handle_test_frames(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
                client.build_text_event("status?"),
            ]
        )

        action = replies[-1]["action"]
        result = client.handle_action_request(
            {"type": "action_request", "device_id": "desktop-dev-1", "action": action}
        )
        self.assertEqual(result["type"], "action_result")
        self.assertEqual(result["result"]["status"], "ok")

    async def test_runtime_server_entrypoint_passes_runtime_config_to_ready_message(
        self,
    ) -> None:
        captured = {}

        class FakeGateway:
            def __init__(self, token, state_path, llm_config_path):
                self.token = token
                self.state_path = state_path
                self.llm_config_path = llm_config_path

            def run_server(self, host, port):
                captured["host"] = host
                captured["port"] = port

                class FakeServerContext:
                    async def __aenter__(self):
                        return {"url": f"ws://{host}:{port}"}

                    async def __aexit__(self, exc_type, exc, tb):
                        return False

                return FakeServerContext()

        async def stop_after_ready():
            await asyncio.sleep(0)
            raise RuntimeError("stop after ready")

        with patch("personal_runtime.main.build_gateway", FakeGateway), patch(
            "personal_runtime.main.asyncio.Future",
            side_effect=stop_after_ready,
        ), patch("builtins.print") as mocked_print:
            with self.assertRaisesRegex(RuntimeError, "stop after ready"):
                await run_server(
                    host="127.0.0.1",
                    port=8765,
                    token="dev-token",
                    state_path=Path(".runtime/test-state.json"),
                    llm_config_path=Path("tests/fixtures/llm-config-test.toml"),
                )

        self.assertEqual(captured["host"], "127.0.0.1")
        self.assertEqual(captured["port"], 8765)
        printed_message = mocked_print.call_args.args[0]
        self.assertIn(
            "Runtime config: tests/fixtures/llm-config-test.toml",
            printed_message,
        )
        self.assertNotIn("LLM config", printed_message)


class CliEntryTests(unittest.TestCase):
    def test_terminal_daemon_tracks_recent_transcript_for_runtime_and_user_lines(self) -> None:
        stdout = io.StringIO()
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=stdout,
        )

        daemon.render_status_line("Connected to runtime.")
        daemon.render_user_line("hello runtime")
        daemon.handle_action_request(
            {
                "type": "action_request",
                "device_id": "terminal-edge-1",
                "action": {
                    "capability": "notification.show",
                    "payload": {"message": "Runtime heard: hello runtime"},
                },
            }
        )

        self.assertEqual(
            list(daemon.transcript),
            [
                "[system] Connected to runtime.",
                "[user] hello runtime",
                "[runtime] Runtime heard: hello runtime",
            ],
        )
        self.assertEqual(daemon.user_request_count, 0)
        self.assertEqual(daemon.runtime_message_count, 1)

    def test_run_cli_once_returns_ok_action_result(self) -> None:
        result = run_cli_once("hello runtime", config_path=TEST_LLM_CONFIG)

        self.assertEqual(result["type"], "action_result")
        self.assertEqual(result["result"]["status"], "ok")

    def test_local_cli_session_stays_alive_across_multiple_inputs(self) -> None:
        session = LocalCliSession(
            token="dev-token",
            trace=True,
            config_path=TEST_LLM_CONFIG,
        )

        bootstrap_trace = session.drain_trace_lines()
        first_result = session.send_text("first message")
        first_trace = session.drain_trace_lines()
        second_result = session.send_text("second message")
        second_trace = session.drain_trace_lines()

        self.assertEqual(first_result["result"]["status"], "ok")
        self.assertEqual(second_result["result"]["status"], "ok")
        self.assertEqual(
            sum("GATEWAY received connect" in line for line in bootstrap_trace),
            1,
        )
        self.assertEqual(
            sum("GATEWAY received capability_announce" in line for line in bootstrap_trace),
            1,
        )
        self.assertEqual(
            sum("GATEWAY received connect" in line for line in first_trace + second_trace),
            0,
        )
        self.assertTrue(
            any("GATEWAY received event_push" in line for line in first_trace)
        )
        self.assertTrue(
            any("GATEWAY received event_push" in line for line in second_trace)
        )
        self.assertTrue(
            any("EDGE executed notification.show" in line for line in second_trace)
        )

    def test_run_cli_once_can_return_trace_steps_for_local_roundtrip(self) -> None:
        result, trace_lines = run_cli_once(
            "hello runtime",
            trace=True,
            config_path=TEST_LLM_CONFIG,
        )

        self.assertEqual(result["type"], "action_result")
        self.assertEqual(result["result"]["status"], "ok")
        self.assertGreaterEqual(len(trace_lines), 8)
        self.assertIn("EDGE build connect frame", trace_lines[0])
        self.assertTrue(
            any("GATEWAY received connect" in line for line in trace_lines)
        )
        self.assertTrue(
            any("STATE recorded event_push" in line for line in trace_lines)
        )
        self.assertTrue(
            any("AGENT built intervention proposal" in line for line in trace_lines)
        )
        self.assertTrue(
            any("PRESENCE selected target device" in line for line in trace_lines)
        )
        self.assertTrue(
            any("AGENT built intervention proposal" in line for line in trace_lines)
        )
        self.assertTrue(
            any("ACTION built notification.show request" in line for line in trace_lines)
        )
        self.assertTrue(
            any("EDGE executed notification.show" in line for line in trace_lines)
        )

    def test_runtime_server_message_mentions_websocket_url(self) -> None:
        message = build_runtime_server_message("ws://127.0.0.1:8765")

        self.assertIn("ws://127.0.0.1:8765", message)
        self.assertIn("Runtime config: config/runtime-config.toml", message)
        self.assertNotIn("LLM config", message)
        self.assertNotIn("Connect an edge client", message)

    def test_runtime_server_parser_accepts_explicit_runtime_config_path(self) -> None:
        parser = build_runtime_server_parser()

        args = parser.parse_args(
            [
                "--runtime-config-path",
                "tests/fixtures/llm-config-test.toml",
            ]
        )

        self.assertEqual(
            args.runtime_config_path,
            "tests/fixtures/llm-config-test.toml",
        )

    def test_runtime_server_parser_accepts_explicit_llm_config_path(self) -> None:
        parser = build_runtime_server_parser()

        args = parser.parse_args(
            [
                "--llm-config-path",
                "tests/fixtures/llm-config-test.toml",
            ]
        )

        self.assertEqual(
            args.runtime_config_path,
            "tests/fixtures/llm-config-test.toml",
        )

    def test_local_cli_session_records_llm_profile_metadata_on_text_reply(self) -> None:
        session = LocalCliSession(
            token="dev-token",
            trace=True,
            config_path=TEST_LLM_CONFIG,
        )

        result = session.send_text("hello runtime")
        proposal = session.gateway.state.interventions[-1]["proposal"]

        self.assertEqual(result["result"]["status"], "ok")
        self.assertEqual(proposal["proposal_type"], "reply")
        self.assertEqual(proposal["metadata"]["llm_profile"], "proposal_formation")
        self.assertTrue(proposal["metadata"]["used_deterministic_fallback"])
        self.assertIn("proposal_rationale", proposal["metadata"])
        self.assertEqual(proposal["metadata"]["prompt_context_version"], "m12.v1")
        self.assertEqual(
            proposal["metadata"]["prompt_context_sections"],
            [
                "active_goals",
                "compact_snapshot",
                "edge_evidence",
                "recent_memory",
            ],
        )
        self.assertEqual(proposal["action_payload"]["message"], "Runtime heard: hello runtime")

    def test_local_cli_session_can_form_clarification_proposal_from_user_text(self) -> None:
        session = LocalCliSession(
            token="dev-token",
            trace=True,
            config_path=TEST_LLM_CONFIG,
        )

        result = session.send_text("help")
        proposal = session.gateway.state.interventions[-1]["proposal"]

        self.assertEqual(result["result"]["status"], "ok")
        self.assertEqual(proposal["proposal_type"], "clarification")
        self.assertEqual(proposal["action_capability"], "notification.show")
        self.assertIn("proposal_rationale", proposal["metadata"])

    def test_local_cli_session_can_form_no_intervention_proposal_from_user_text(self) -> None:
        session = LocalCliSession(
            token="dev-token",
            trace=True,
            config_path=TEST_LLM_CONFIG,
        )

        result = session.send_text("thanks")
        proposal = session.gateway.state.interventions[-1]["proposal"]

        self.assertEqual(result["result"]["status"], "completed")
        self.assertEqual(proposal["proposal_type"], "no_intervention")
        self.assertIsNone(proposal["action_capability"])

    def test_local_cli_session_surfaces_provider_failure_reason_in_visible_reply_mode(
        self,
    ) -> None:
        session = LocalCliSession(
            token="dev-token",
            trace=True,
            config_path=VISIBLE_ERROR_LLM_CONFIG,
        )

        result = session.send_text("hello runtime")
        proposal = session.gateway.state.interventions[-1]["proposal"]

        self.assertEqual(result["result"]["status"], "ok")
        self.assertEqual(proposal["proposal_type"], "reply")
        self.assertEqual(proposal["action_capability"], "notification.show")
        self.assertIn(
            "Real model reply unavailable",
            proposal["action_payload"]["message"],
        )
        self.assertIn(
            "missing provider credential: openai_main",
            proposal["action_payload"]["message"],
        )
        self.assertEqual(
            proposal["metadata"]["provider_failure_behavior"],
            "user_visible_error",
        )
        self.assertFalse(proposal["metadata"]["used_deterministic_fallback"])

    def test_local_cli_session_can_trigger_agent_initiative(self) -> None:
        session = LocalCliSession(
            token="dev-token",
            trace=True,
            config_path=TEST_LLM_CONFIG,
        )

        result = session.trigger_agent_initiative(
            action_capability="notification.show",
            action_payload={"message": "initiative ping"},
            reason="manual_check",
            observed_at="2026-06-21T10:10:00Z",
        )
        trace_lines = session.drain_trace_lines()

        self.assertEqual(result["type"], "action_result")
        self.assertEqual(result["result"]["status"], "ok")
        self.assertTrue(
            any("GATEWAY triggered agent initiative" in line for line in trace_lines)
        )
        self.assertTrue(
            any("AGENT built intervention proposal [source=agent_initiative" in line for line in trace_lines)
        )

    def test_terminal_daemon_executes_notification_show_with_terminal_details(self) -> None:
        stdout = io.StringIO()
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=stdout,
        )

        result = daemon.handle_action_request(
            {
                "type": "action_request",
                "device_id": "terminal-edge-1",
                "action": {
                    "capability": "notification.show",
                    "payload": {"message": "runtime push"},
                },
            }
        )

        self.assertEqual(result["type"], "action_result")
        self.assertEqual(result["result"]["status"], "ok")
        self.assertEqual(
            result["result"]["details"]["delivered_via"],
            "terminal.stdout",
        )
        self.assertIn("runtime push", stdout.getvalue())


class WebSocketRoundtripTests(unittest.IsolatedAsyncioTestCase):
    async def test_websocket_connect_emits_runtime_connection_event(self) -> None:
        events: list[str] = []
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        gateway.runtime_event_emitter = events.append
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )

        async with gateway.run_test_server() as server_info:
            async with websockets.connect(server_info["url"]) as websocket:
                await websocket.send(json.dumps(client.build_connect_frame()))
                connect_ok = json.loads(await websocket.recv())

        self.assertEqual(connect_ok["type"], "connect_ok")
        self.assertEqual(
            events,
            ["Edge connected: desktop-dev-1 (desktop-cli)"],
        )

    async def test_websocket_roundtrip_records_action_result_on_gateway(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )

        result = await client.run_websocket_roundtrip(
            server_factory=gateway.run_test_server,
            text="hello runtime",
        )

        self.assertEqual(result["type"], "action_result")
        self.assertEqual(result["result"]["status"], "ok")
        self.assertEqual(gateway.state.action_results[-1]["status"], "ok")

    async def test_websocket_ping_stays_responsive_during_slow_proposal_generation(
        self,
    ) -> None:
        def slow_generate_text_proposal_plan(*_args, **_kwargs):
            time.sleep(0.5)
            return ProposalPlan(
                proposal_type="reply",
                response_text="Slow model reply.",
                action_capability="notification.show",
                action_payload={},
                metadata={
                    "llm_profile": "proposal_formation",
                    "llm_provider": "test_provider",
                    "llm_model": "test_model",
                    "used_deterministic_fallback": False,
                },
            )

        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )

        with patch(
            "personal_runtime.agent_executor.generate_text_proposal_plan",
            side_effect=slow_generate_text_proposal_plan,
        ):
            async with gateway.run_test_server() as server_info:
                async with websockets.connect(
                    server_info["url"],
                    ping_timeout=0.2,
                ) as websocket:
                    await websocket.send(json.dumps(client.build_connect_frame()))
                    connect_ok = json.loads(await websocket.recv())
                    await websocket.send(
                        json.dumps(client.build_capability_announce_frame())
                    )
                    await websocket.send(
                        json.dumps(client.build_text_event("slow provider check"))
                    )

                    pong_waiter = await asyncio.wait_for(
                        websocket.ping(),
                        timeout=0.2,
                    )
                    pong_latency = await asyncio.wait_for(
                        pong_waiter,
                        timeout=0.2,
                    )
                    event_ack = json.loads(
                        await asyncio.wait_for(websocket.recv(), timeout=1)
                    )
                    action_request = json.loads(
                        await asyncio.wait_for(websocket.recv(), timeout=1)
                    )

        self.assertEqual(connect_ok["type"], "connect_ok")
        self.assertIsInstance(pong_latency, float)
        self.assertEqual(event_ack["type"], "event_ack")
        self.assertEqual(action_request["type"], "action_request")
        self.assertEqual(
            action_request["action"]["payload"]["message"],
            "Slow model reply.",
        )

    async def test_websocket_roundtrip_routes_action_to_other_connected_edge(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            llm_config_path=TEST_LLM_CONFIG,
        )
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )
        target = SessionClient(
            device_id="desktop-dev-2",
            device_type="desktop-cli",
            token="dev-token",
        )

        async with gateway.run_test_server() as server_info:
            async with websockets.connect(server_info["url"]) as source_ws:
                async with websockets.connect(server_info["url"]) as target_ws:
                    await source_ws.send(json.dumps(source.build_connect_frame()))
                    await target_ws.send(json.dumps(target.build_connect_frame()))

                    source_connect_ok = json.loads(await source_ws.recv())
                    target_connect_ok = json.loads(await target_ws.recv())

                    await source_ws.send(
                        json.dumps(source.build_capability_announce_frame())
                    )
                    await target_ws.send(
                        json.dumps(target.build_capability_announce_frame())
                    )
                    await source_ws.send(
                        json.dumps(source.build_text_event("hello routed runtime"))
                    )

                    source_event_ack = json.loads(await asyncio.wait_for(source_ws.recv(), timeout=1))
                    action_request = json.loads(
                        await asyncio.wait_for(target_ws.recv(), timeout=1)
                    )
                    action_result = target.handle_action_request(action_request)
                    await target_ws.send(json.dumps(action_result))

        self.assertEqual(source_connect_ok["type"], "connect_ok")
        self.assertEqual(target_connect_ok["type"], "connect_ok")
        self.assertEqual(source_event_ack["type"], "event_ack")
        self.assertEqual(action_request["type"], "action_request")
        self.assertEqual(action_request["device_id"], "desktop-dev-2")
        self.assertEqual(action_request["action"]["capability"], "notification.show")
        self.assertEqual(action_result["result"]["status"], "ok")
        self.assertEqual(gateway.state.action_results[-1]["status"], "ok")

    async def test_cli_websocket_helper_uses_real_gateway_server(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            llm_config_path=TEST_LLM_CONFIG,
        )
        async with gateway.run_test_server() as server_info:
            result = await run_cli_once_over_websocket(
                text="hello runtime",
                url=server_info["url"],
                token="dev-token",
            )

        self.assertEqual(result["type"], "action_result")
        self.assertEqual(result["result"]["status"], "ok")

    async def test_websocket_agent_initiative_can_route_runtime_status_to_host_edge(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        class RuntimeStatusAdapter:
            def execute(self, action: dict) -> dict:
                return {
                    "status": "ok",
                    "capability": action["capability"],
                    "details": {"state": "running", "pid": 42137},
                }

        host_daemon = HostEdgeDaemon(
            device_id="host-edge-1",
            token="dev-token",
            runtime_control_adapter=RuntimeStatusAdapter(),
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
                "process_pid": 42137,
                "process_present": True,
                "process_started_at": "2026-06-19T09:00:00Z",
                "process_memory_rss_bytes": 28114944,
            },
        )
        ready = asyncio.Event()

        async with gateway.run_test_server() as server_info:
            daemon_task = asyncio.create_task(
                host_daemon.run_websocket_control_session(
                    url=server_info["url"],
                    observed_at="2026-06-21T10:08:00Z",
                    ready_event=ready,
                )
            )
            await ready.wait()
            async with websockets.connect(server_info["url"]) as source_ws:
                source = SessionClient(
                    device_id="desktop-dev-1",
                    device_type="desktop-cli",
                    token="dev-token",
                )
                await source_ws.send(json.dumps(source.build_connect_frame()))
                await source_ws.send(json.dumps(source.build_capability_announce_frame()))
                source_connect_ok = json.loads(await source_ws.recv())
                await gateway.dispatch_agent_initiative(
                    source_device_id="desktop-dev-1",
                    initiative_request={
                        "action_capability": "runtime.status",
                        "action_payload": {},
                        "reason": "runtime_health_check",
                        "target_device_hint": "host-edge-1",
                    },
                    observed_at="2026-06-21T10:10:00Z",
                )
            action_result = await asyncio.wait_for(daemon_task, timeout=1)

        self.assertEqual(source_connect_ok["type"], "connect_ok")
        self.assertEqual(action_result["result"]["status"], "ok")
        self.assertEqual(action_result["result"]["capability"], "runtime.status")
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["source"],
            "agent_initiative",
        )
        self.assertEqual(
            gateway.state.action_results[-1]["capability"],
            "runtime.status",
        )

    async def test_websocket_roundtrip_can_route_runtime_status_from_normal_text(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            llm_config_path=TEST_LLM_CONFIG,
        )

        class RuntimeStatusAdapter:
            def execute(self, action: dict) -> dict:
                return {
                    "status": "ok",
                    "capability": action["capability"],
                    "details": {"state": "running", "pid": 42137},
                }

        host_daemon = HostEdgeDaemon(
            device_id="host-edge-1",
            token="dev-token",
            runtime_control_adapter=RuntimeStatusAdapter(),
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
                "process_pid": 42137,
                "process_present": True,
                "process_started_at": "2026-06-19T09:00:00Z",
                "process_memory_rss_bytes": 28114944,
            },
        )
        ready = asyncio.Event()

        async with gateway.run_test_server() as server_info:
            daemon_task = asyncio.create_task(
                host_daemon.run_websocket_control_session(
                    url=server_info["url"],
                    observed_at="2026-06-21T10:08:00Z",
                    ready_event=ready,
                )
            )
            await ready.wait()
            async with websockets.connect(server_info["url"]) as websocket:
                client = SessionClient(
                    device_id="desktop-dev-1",
                    device_type="desktop-cli",
                    token="dev-token",
                )
                await websocket.send(json.dumps(client.build_connect_frame()))
                await websocket.send(
                    json.dumps(client.build_capability_announce_frame())
                )
                await websocket.send(
                    json.dumps(client.build_text_event("check runtime status"))
                )
                await websocket.recv()
                await websocket.recv()
            action_result = await asyncio.wait_for(daemon_task, timeout=1)

        self.assertEqual(action_result["result"]["status"], "ok")
        self.assertEqual(action_result["result"]["capability"], "runtime.status")
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["proposal_type"],
            "action",
        )

    async def test_terminal_daemon_runtime_status_request_completes_without_local_action_request(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        class RuntimeStatusAdapter:
            def execute(self, action: dict) -> dict:
                return {
                    "status": "ok",
                    "capability": action["capability"],
                    "details": {"state": "running", "pid": 42137},
                }

        host_daemon = HostEdgeDaemon(
            device_id="host-edge-1",
            token="dev-token",
            runtime_control_adapter=RuntimeStatusAdapter(),
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
                "process_pid": 42137,
                "process_present": True,
                "process_started_at": "2026-06-19T09:00:00Z",
                "process_memory_rss_bytes": 28114944,
            },
        )
        ready = asyncio.Event()
        terminal_stdout = io.StringIO()
        terminal_daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=terminal_stdout,
        )

        async with gateway.run_test_server() as server_info:
            daemon_task = asyncio.create_task(
                host_daemon.run_websocket_control_session(
                    url=server_info["url"],
                    observed_at="2026-06-21T10:08:00Z",
                    ready_event=ready,
                )
            )
            await ready.wait()
            async with websockets.connect(server_info["url"]) as websocket:
                results = await terminal_daemon.run_scripted_session(
                    websocket=websocket,
                    scripted_inputs=[
                        {
                            "text": "check runtime status",
                            "observed_at": "2026-06-21T10:09:30Z",
                        }
                    ],
                    startup_observed_at="2026-06-21T10:09:00Z",
                    idle_after_inputs=True,
                    max_idle_cycles=1,
                    idle_timeout_s=0.05,
                )
            action_result = await asyncio.wait_for(daemon_task, timeout=1)

        self.assertEqual(results, [])
        self.assertFalse(terminal_daemon.pending_runtime_reply)
        self.assertEqual(action_result["result"]["capability"], "runtime.status")
        self.assertIn("Runtime status: running (pid 42137).", terminal_stdout.getvalue())


class HostEdgeWebSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_host_edge_receives_runtime_status_over_websocket(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        class RuntimeStatusAdapter:
            def execute(self, action: dict) -> dict:
                return {
                    "status": "ok",
                    "capability": action["capability"],
                    "details": {"state": "running", "pid": 42137},
                }

        host_daemon = HostEdgeDaemon(
            device_id="host-edge-1",
            token="dev-token",
            runtime_control_adapter=RuntimeStatusAdapter(),
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
                "process_pid": 42137,
                "process_present": True,
                "process_started_at": "2026-06-19T09:00:00Z",
                "process_memory_rss_bytes": 28114944,
            },
        )
        ready = asyncio.Event()

        async with gateway.run_test_server() as server_info:
            daemon_task = asyncio.create_task(
                host_daemon.run_websocket_control_session(
                    url=server_info["url"],
                    observed_at="2026-06-19T09:30:00Z",
                    ready_event=ready,
                )
            )
            await ready.wait()
            async with websockets.connect(server_info["url"]) as source_ws:
                source = SessionClient(
                    device_id="desktop-dev-1",
                    device_type="desktop-cli",
                    token="dev-token",
                )
                await source_ws.send(json.dumps(source.build_connect_frame()))
                await source_ws.send(json.dumps(source.build_capability_announce_frame()))
                await source_ws.send(
                    json.dumps(
                        {
                            "type": "event_push",
                            "device_id": "desktop-dev-1",
                            "capability": "text.input",
                            "payload": {
                                "text": "",
                                "direct_action": {
                                    "target_device_id": "host-edge-1",
                                    "capability": "runtime.status",
                                    "payload": {},
                                },
                            },
                        }
                    )
                )
                source_connect_ok = json.loads(await source_ws.recv())
                source_event_ack = json.loads(await source_ws.recv())
            action_result = await asyncio.wait_for(daemon_task, timeout=1)

        self.assertEqual(source_connect_ok["type"], "connect_ok")
        self.assertEqual(source_event_ack["type"], "event_ack")
        self.assertEqual(action_result["type"], "action_result")
        self.assertEqual(action_result["result"]["capability"], "runtime.status")
        self.assertEqual(action_result["result"]["details"]["pid"], 42137)
        self.assertEqual(gateway.state.action_results[-1]["capability"], "runtime.status")

    async def test_host_edge_daemon_session_handles_multiple_runtime_control_actions(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        class MultiActionAdapter:
            def execute(self, action: dict) -> dict:
                details_by_capability = {
                    "runtime.status": {"state": "running", "pid": 42137},
                    "runtime.collect_logs": {
                        "entries": [{"line": "Runtime ready", "line_number": 1}],
                        "tail_text": "Runtime ready\n",
                    },
                }
                return {
                    "status": "ok",
                    "capability": action["capability"],
                    "details": details_by_capability[action["capability"]],
                }

        host_daemon = HostEdgeDaemon(
            device_id="host-edge-1",
            token="dev-token",
            runtime_control_adapter=MultiActionAdapter(),
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
                "process_pid": 42137,
                "process_present": True,
                "process_started_at": "2026-06-19T09:00:00Z",
                "process_memory_rss_bytes": 28114944,
            },
        )
        ready = asyncio.Event()

        async with gateway.run_test_server() as server_info:
            daemon_task = asyncio.create_task(
                host_daemon.run_websocket_daemon_session(
                    url=server_info["url"],
                    observation_schedule=[
                        "2026-06-19T09:30:00Z",
                        "2026-06-19T09:31:00Z",
                    ],
                    idle_timeout_s=0.05,
                    ready_event=ready,
                    max_action_requests=2,
                    send_follow_up_after_action=False,
                )
            )
            await ready.wait()
            async with websockets.connect(server_info["url"]) as source_ws:
                source = SessionClient(
                    device_id="desktop-dev-1",
                    device_type="desktop-cli",
                    token="dev-token",
                )
                await source_ws.send(json.dumps(source.build_connect_frame()))
                await source_ws.send(json.dumps(source.build_capability_announce_frame()))
                await source_ws.send(
                    json.dumps(
                        {
                            "type": "event_push",
                            "device_id": "desktop-dev-1",
                            "capability": "text.input",
                            "payload": {
                                "text": "",
                                "direct_action": {
                                    "target_device_id": "host-edge-1",
                                    "capability": "runtime.status",
                                    "payload": {},
                                },
                            },
                        }
                    )
                )
                await source_ws.recv()
                await source_ws.recv()
                await source_ws.send(
                    json.dumps(
                        {
                            "type": "event_push",
                            "device_id": "desktop-dev-1",
                            "capability": "text.input",
                            "payload": {
                                "text": "",
                                "direct_action": {
                                    "target_device_id": "host-edge-1",
                                    "capability": "runtime.collect_logs",
                                    "payload": {},
                                },
                            },
                        }
                    )
                )
                await source_ws.recv()
            action_results = await asyncio.wait_for(daemon_task, timeout=2)

        self.assertEqual(
            [result["result"]["capability"] for result in action_results],
            ["runtime.status", "runtime.collect_logs"],
        )
        self.assertEqual(
            [result["capability"] for result in gateway.state.action_results[-2:]],
            ["runtime.status", "runtime.collect_logs"],
        )

    async def test_host_edge_restart_returns_accepted_and_later_health_confirms_recovery(
        self,
    ) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            llm_config_path=TEST_LLM_CONFIG,
        )

        class RestartState:
            def __init__(self) -> None:
                self.restarted = False

            def health_snapshot(self) -> dict:
                if self.restarted:
                    return {
                        "health_state": "healthy",
                        "process_pid": 42138,
                        "process_present": True,
                        "process_started_at": "2026-06-19T09:31:00Z",
                        "process_memory_rss_bytes": 30114944,
                    }
                return {
                    "health_state": "healthy",
                    "process_pid": 42137,
                    "process_present": True,
                    "process_started_at": "2026-06-19T09:00:00Z",
                    "process_memory_rss_bytes": 28114944,
                }

        restart_state = RestartState()

        class RestartAdapter:
            def execute(self, action: dict) -> dict:
                restart_state.restarted = True
                return {
                    "status": "accepted",
                    "capability": action["capability"],
                    "details": {"handoff_expected": True},
                }

        host_daemon = HostEdgeDaemon(
            device_id="host-edge-1",
            token="dev-token",
            runtime_control_adapter=RestartAdapter(),
            host_metrics_provider=lambda: {
                "cpu_load_ratio": 0.31,
                "memory_used_bytes": 400,
                "memory_available_bytes": 600,
                "memory_pressure": "normal",
                "net_rx_bytes": 10,
                "net_tx_bytes": 12,
            },
            runtime_health_provider=restart_state.health_snapshot,
        )
        ready = asyncio.Event()

        async with gateway.run_test_server() as server_info:
            daemon_task = asyncio.create_task(
                host_daemon.run_websocket_control_session(
                    url=server_info["url"],
                    observed_at="2026-06-19T09:30:00Z",
                    ready_event=ready,
                    follow_up_observed_at="2026-06-19T09:31:00Z",
                )
            )
            await ready.wait()
            async with websockets.connect(server_info["url"]) as source_ws:
                source = SessionClient(
                    device_id="desktop-dev-1",
                    device_type="desktop-cli",
                    token="dev-token",
                )
                await source_ws.send(json.dumps(source.build_connect_frame()))
                await source_ws.send(json.dumps(source.build_capability_announce_frame()))
                await source_ws.send(
                    json.dumps(
                        {
                            "type": "event_push",
                            "device_id": "desktop-dev-1",
                            "capability": "text.input",
                            "payload": {
                                "text": "",
                                "direct_action": {
                                    "target_device_id": "host-edge-1",
                                    "capability": "runtime.restart",
                                    "payload": {},
                                },
                            },
                        }
                    )
                )
                await source_ws.recv()
                await source_ws.recv()
            action_result = await asyncio.wait_for(daemon_task, timeout=1)

        pid_observations = [
            observation
            for observation in gateway.state.observations
            if observation.name == "runtime.process_pid"
        ]

        self.assertEqual(action_result["result"]["status"], "accepted")
        self.assertEqual(action_result["result"]["capability"], "runtime.restart")
        self.assertTrue(action_result["result"]["details"]["handoff_expected"])
        self.assertEqual(gateway.state.action_results[-1]["status"], "accepted")
        self.assertEqual(pid_observations[-1].value, 42138)


if __name__ == "__main__":
    unittest.main()
