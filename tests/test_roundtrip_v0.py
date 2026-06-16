import asyncio
import json
import unittest

import websockets

from device_edge.cli_edge import run_cli_once, run_cli_once_over_websocket
from device_edge.session_client import SessionClient
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.main import build_runtime_server_message


class RoundtripTests(unittest.IsolatedAsyncioTestCase):
    async def test_user_text_roundtrips_back_to_same_edge(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token")
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


class CliEntryTests(unittest.TestCase):
    def test_run_cli_once_returns_ok_action_result(self) -> None:
        result = run_cli_once("hello runtime")

        self.assertEqual(result["type"], "action_result")
        self.assertEqual(result["result"]["status"], "ok")

    def test_runtime_server_message_mentions_websocket_url(self) -> None:
        message = build_runtime_server_message("ws://127.0.0.1:8765")

        self.assertIn("ws://127.0.0.1:8765", message)


class WebSocketRoundtripTests(unittest.IsolatedAsyncioTestCase):
    async def test_websocket_roundtrip_records_action_result_on_gateway(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token")
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

    async def test_websocket_roundtrip_routes_action_to_other_connected_edge(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token")
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
        gateway = RuntimeGateway(shared_token="dev-token")
        async with gateway.run_test_server() as server_info:
            result = await run_cli_once_over_websocket(
                text="hello runtime",
                url=server_info["url"],
                token="dev-token",
            )

        self.assertEqual(result["type"], "action_result")
        self.assertEqual(result["result"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
