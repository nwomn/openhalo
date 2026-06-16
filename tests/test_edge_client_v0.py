import json
import unittest

import websockets

from device_edge.capability_runtime import CapabilityRuntime
from device_edge.local_actions import execute_action
from device_edge.session_client import SessionClient
from personal_runtime.gateway_server import RuntimeGateway


class EdgeClientTests(unittest.TestCase):
    def test_registers_minimal_capabilities(self) -> None:
        runtime = CapabilityRuntime()

        self.assertEqual(
            runtime.capabilities,
            ["text.input", "notification.show"],
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
        self.assertEqual(
            client.build_capability_announce_frame()["capabilities"],
            ["text.input", "notification.show"],
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
        self.assertEqual(
            frame["payload"]["direct_action"]["capability"],
            "notification.show",
        )
        self.assertEqual(
            frame["payload"]["direct_action"]["payload"]["message"],
            "urgent ping",
        )


class EdgeWebSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_websocket_client_receives_action_and_returns_action_result(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token")
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
        gateway = RuntimeGateway(shared_token="dev-token")
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
