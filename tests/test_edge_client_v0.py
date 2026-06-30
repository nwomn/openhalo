import json
import importlib
import unittest
from pathlib import Path

import websockets

from device_edge.shared.capability_runtime import CapabilityRuntime
from device_edge.shared.local_actions import execute_action
from device_edge.shared.session_client import SessionClient
from openhalo_common.diagnostics import InMemoryDiagnosticRecorder
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.trace_recorder import TraceRecorder

TEST_LLM_CONFIG = Path("tests/fixtures/llm-config-test.toml")


class EdgeClientTests(unittest.TestCase):
    def test_new_edge_subpackages_expose_shared_cli_and_host_modules(self) -> None:
        shared_module = importlib.import_module("device_edge.shared.session_client")
        cli_module = importlib.import_module("device_edge.cli.cli_edge")
        host_module = importlib.import_module("device_edge.host.host_daemon")

        self.assertIs(shared_module.SessionClient, SessionClient)
        self.assertTrue(callable(cli_module.run_cli_once))
        self.assertTrue(hasattr(host_module, "HostEdgeDaemon"))

    def test_registers_minimal_capabilities(self) -> None:
        runtime = CapabilityRuntime()

        self.assertEqual(
            runtime.capabilities,
            ["text.input", "notification.show"],
        )

    def test_accepts_injected_capabilities(self) -> None:
        runtime = CapabilityRuntime(
            capabilities=["host.metrics", "runtime.health", "runtime.control"]
        )

        self.assertEqual(
            runtime.capabilities,
            ["host.metrics", "runtime.health", "runtime.control"],
        )

    def test_executes_notification_action(self) -> None:
        result = execute_action(
            {"capability": "notification.show", "payload": {"message": "hello"}}
        )

        self.assertEqual(result["status"], "ok")

    def test_builds_connect_and_capability_frames(self) -> None:
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )

        self.assertEqual(client.build_connect_frame()["type"], "connect")
        self.assertIn("session_id", client.build_connect_frame())
        self.assertEqual(
            client.build_capability_announce_frame()["capabilities"],
            ["text.input", "notification.show"],
        )

    def test_builds_observation_event_with_event_id(self) -> None:
        client = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics"],
        )

        frame = client.build_observation_event(
            capability="host.metrics",
            observations=[
                {
                    "name": "host.memory_pressure",
                    "value": "normal",
                    "observed_at": "2026-06-19T09:30:00Z",
                    "confidence": 0.9,
                }
            ],
        )

        self.assertEqual(frame["type"], "observation_push")
        self.assertRegex(frame["trace_id"], r"^trace-host-edge-1-\d+$")
        self.assertRegex(frame["turn_id"], r"^turn-host-edge-1-\d+$")
        self.assertEqual(frame["device_id"], "host-edge-1")
        self.assertEqual(frame["capability"], "host.metrics")
        self.assertIn("event_id", frame)
        self.assertEqual(
            frame["payload"]["observations"][0]["name"],
            "host.memory_pressure",
        )

    def test_returns_action_result_after_local_execution(self) -> None:
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )

        result = client.handle_action_request(
            {
                "type": "action_request",
                "device_id": "desktop-dev-1",
                "action": {
                    "capability": "notification.show",
                    "payload": {"message": "hello"},
                },
            }
        )

        self.assertEqual(result["type"], "action_result")
        self.assertEqual(result["result"]["status"], "ok")

    def test_action_result_preserves_correlation_from_action_request(self) -> None:
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )

        result = client.handle_action_request(
            {
                "type": "action_request",
                "trace_id": "trace-desktop-dev-1-1",
                "session_id": "session-desktop-dev-1",
                "turn_id": "turn-desktop-dev-1-1",
                "request_id": "action-1",
                "interaction_id": "interaction-1",
                "device_id": "desktop-dev-1",
                "action": {
                    "capability": "notification.show",
                    "payload": {"message": "hello"},
                },
            }
        )

        self.assertEqual(result["trace_id"], "trace-desktop-dev-1-1")
        self.assertEqual(result["session_id"], "session-desktop-dev-1")
        self.assertEqual(result["turn_id"], "turn-desktop-dev-1-1")
        self.assertEqual(result["request_id"], "action-1")
        self.assertEqual(result["interaction_id"], "interaction-1")

    def test_builds_direct_action_event(self) -> None:
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )

        frame = client.build_direct_action_event(
            capability="notification.show",
            payload={"message": "urgent ping"},
        )

        self.assertEqual(frame["type"], "event_push")
        self.assertRegex(frame["trace_id"], r"^trace-desktop-dev-1-\d+$")
        self.assertRegex(frame["turn_id"], r"^turn-desktop-dev-1-\d+$")
        self.assertEqual(
            frame["payload"]["direct_action"]["capability"],
            "notification.show",
        )
        self.assertEqual(
            frame["payload"]["direct_action"]["payload"]["message"],
            "urgent ping",
        )

    def test_builds_direct_action_event_with_explicit_target_device(self) -> None:
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )

        frame = client.build_direct_action_event(
            capability="runtime.status",
            payload={},
            target_device_id="host-edge-1",
        )

        self.assertEqual(frame["type"], "event_push")
        self.assertEqual(
            frame["payload"]["direct_action"]["target_device_id"],
            "host-edge-1",
        )
        self.assertEqual(
            frame["payload"]["direct_action"]["capability"],
            "runtime.status",
        )

    def test_builds_agent_initiative_event_with_target_hint(self) -> None:
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )

        frame = client.build_agent_initiative_event(
            action_capability="runtime.status",
            action_payload={},
            reason="runtime_health_check",
            observed_at="2026-06-21T10:10:00Z",
            target_device_hint="host-edge-1",
        )

        self.assertEqual(frame["type"], "event_push")
        self.assertEqual(frame["capability"], "agent.initiative")
        self.assertEqual(frame["payload"]["observed_at"], "2026-06-21T10:10:00Z")
        self.assertEqual(
            frame["payload"]["agent_initiative"]["action_capability"],
            "runtime.status",
        )
        self.assertEqual(
            frame["payload"]["agent_initiative"]["target_device_hint"],
            "host-edge-1",
        )

    def test_builds_terminal_activity_event(self) -> None:
        client = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show", "terminal.context"],
        )

        frame = client.build_terminal_activity_event(
            activity_state="active",
            observed_at="2026-06-22T10:10:00Z",
        )

        self.assertEqual(frame["type"], "observation_push")
        self.assertEqual(frame["device_id"], "terminal-edge-1")
        self.assertEqual(frame["capability"], "terminal.context")
        self.assertEqual(
            frame["payload"]["observations"][0]["name"],
            "terminal.activity_state",
        )
        self.assertEqual(
            frame["payload"]["observations"][0]["value"],
            "active",
        )

    def test_records_trace_for_edge_frame_build_and_action_execution(self) -> None:
        trace = TraceRecorder()
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            trace_recorder=trace,
        )

        client.build_connect_frame()
        client.build_capability_announce_frame()
        client.build_text_event("hello")
        client.handle_action_request(
            {
                "type": "action_request",
                "device_id": "desktop-dev-1",
                "action": {
                    "capability": "notification.show",
                    "payload": {"message": "hello"},
                },
            }
        )

        lines = trace.format_lines()

        self.assertIn("EDGE build connect frame", lines[0])
        self.assertTrue(
            any("EDGE build capability_announce frame" in line for line in lines)
        )
        self.assertTrue(any("EDGE build text.input event" in line for line in lines))
        self.assertTrue(
            any("EDGE executed notification.show" in line for line in lines)
        )

    def test_records_edge_diagnostics_for_local_capability_and_session_link(self) -> None:
        diagnostics = InMemoryDiagnosticRecorder(
            timestamp_provider=lambda: "2026-06-30T12:00:00Z"
        )
        client = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
            diagnostic_recorder=diagnostics,
        )

        frame = client.build_text_event("check runtime status")

        modules = [event.module for event in diagnostics.events]
        self.assertIn("Local Capability Runtime", modules)
        self.assertIn("Edge Session Link", modules)
        self.assertEqual(
            diagnostics.events[-1].correlation.trace_id,
            frame["trace_id"],
        )

    def test_records_edge_diagnostics_for_observation_frames(self) -> None:
        diagnostics = InMemoryDiagnosticRecorder(
            timestamp_provider=lambda: "2026-06-30T12:00:00Z"
        )
        client = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics"],
            diagnostic_recorder=diagnostics,
        )

        frame = client.build_observation_event(
            capability="host.metrics",
            observations=[
                {
                    "name": "host.memory_pressure",
                    "value": "normal",
                    "observed_at": "2026-06-30T12:00:00Z",
                    "confidence": 1.0,
                }
            ],
        )

        modules = [event.module for event in diagnostics.events]
        self.assertIn("Local Capability Runtime", modules)
        self.assertIn("Edge Session Link", modules)
        self.assertEqual(
            diagnostics.events[-1].correlation.trace_id,
            frame["trace_id"],
        )
        self.assertEqual(
            diagnostics.events[-1].output["capability"],
            "host.metrics",
        )


class EdgeWebSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_websocket_client_receives_action_and_returns_action_result(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )

        async with gateway.run_test_server() as server_info:
            async with websockets.connect(server_info["url"]) as websocket:
                await websocket.send(json.dumps(client.build_connect_frame()))
                await websocket.send(json.dumps(client.build_capability_announce_frame()))
                await websocket.send(json.dumps(client.build_text_event("hello")))

                await websocket.recv()
                await websocket.recv()
                action_request = json.loads(await websocket.recv())
                action_result = client.handle_action_request(action_request)

        self.assertEqual(action_request["type"], "action_request")
        self.assertEqual(action_result["type"], "action_result")
        self.assertEqual(action_result["result"]["status"], "ok")

    async def test_websocket_client_helper_uses_explicit_url(self) -> None:
        gateway = RuntimeGateway(
            shared_token="dev-token",
            llm_config_path=TEST_LLM_CONFIG,
        )
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )

        async with gateway.run_test_server() as server_info:
            action_result = await client.run_websocket_client(
                url=server_info["url"],
                text="hello explicit url",
            )

        self.assertEqual(action_result["type"], "action_result")
        self.assertEqual(action_result["result"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
