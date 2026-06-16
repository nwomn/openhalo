import unittest

from personal_runtime.gateway_server import RuntimeGateway


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_connect_event_and_action_roundtrip(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token")
        reply = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "hello"},
                },
            ]
        )

        self.assertEqual(reply[-1]["type"], "action_request")
        self.assertEqual(reply[-1]["action"]["capability"], "notification.show")

    async def test_sync_roundtrip_wrapper_returns_replies(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token")
        replies = gateway.run_roundtrip(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "hello"},
                },
            ]
        )

        self.assertEqual(replies[-1]["type"], "action_request")


if __name__ == "__main__":
    unittest.main()
