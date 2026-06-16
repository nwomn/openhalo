import unittest

from device_edge.cli_edge import run_cli_once
from device_edge.session_client import SessionClient
from personal_runtime.gateway_server import RuntimeGateway


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


if __name__ == "__main__":
    unittest.main()
