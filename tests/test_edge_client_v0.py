import unittest

from device_edge.capability_runtime import CapabilityRuntime
from device_edge.local_actions import execute_action
from device_edge.session_client import SessionClient


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


if __name__ == "__main__":
    unittest.main()
