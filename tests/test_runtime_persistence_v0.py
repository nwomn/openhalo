import unittest
from pathlib import Path

from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.main import build_gateway


class RuntimePersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_gateway_restores_state_from_disk(self) -> None:
        state_path = Path(
            "/root/personal-runtime-agent/.worktrees/v0-single-edge-loop/.runtime-test/restored-state.json"
        )
        first_gateway = RuntimeGateway(shared_token="dev-token", state_path=state_path)
        await first_gateway.handle_test_frames(
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
                    "payload": {"text": "hello after restart"},
                },
                {
                    "type": "action_result",
                    "device_id": "desktop-dev-1",
                    "result": {"status": "ok"},
                },
            ]
        )

        restored_gateway = build_gateway(token="dev-token", state_path=state_path)

        self.assertIn("desktop-dev-1", restored_gateway.state.devices)
        self.assertEqual(
            restored_gateway.state.events[-1]["payload"]["text"],
            "hello after restart",
        )
        self.assertEqual(restored_gateway.state.action_results[-1]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
