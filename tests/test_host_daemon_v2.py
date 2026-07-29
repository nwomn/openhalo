import asyncio
import json
import unittest
from unittest.mock import AsyncMock
from unittest.mock import patch

from device_edge.host.host_daemon import HostEdgeDaemon


class FakeRuntimeControlAdapter:
    def execute(self, action: dict) -> dict:
        return {
            "status": "ok",
            "capability": action["capability"],
            "details": {"state": "running"},
        }


class HostDaemonV2Tests(unittest.TestCase):
    def test_v2_bootstrap_processes_actions_without_a_second_connect_ack(self) -> None:
        audience = "ws://127.0.0.1:18765"
        daemon = HostEdgeDaemon(
            device_id="host-edge-1",
            audience=audience,
            runtime_control_adapter=FakeRuntimeControlAdapter(),
            host_metrics_provider=lambda: {},
            runtime_health_provider=lambda: {},
        )
        websocket = AsyncMock()
        websocket.recv = AsyncMock(
            side_effect=[
                json.dumps(
                    {
                        "type": "auth_challenge",
                        "device_id": daemon.client.device_id,
                        "session_id": daemon.client.session_id,
                        "audience": audience,
                        "challenge": {
                            "challenge_id": "challenge-1",
                            "nonce": "nonce-1",
                            "expires_at": "2026-07-29T12:01:00Z",
                        },
                    }
                ),
                json.dumps({"type": "connect_ok"}),
                json.dumps(
                    {
                        "type": "action_request",
                        "device_id": "host-edge-1",
                        "action": {
                            "capability": "runtime.status",
                            "payload": {},
                        },
                    }
                ),
            ]
        )
        connect_cm = AsyncMock()
        connect_cm.__aenter__.return_value = websocket
        connect_cm.__aexit__.return_value = False
        connected: list[bool] = []

        with patch(
            "device_edge.host.host_daemon.websockets.connect",
            return_value=connect_cm,
        ):
            results = asyncio.run(
                daemon.run_websocket_daemon_session(
                    url=audience,
                    observation_schedule=[],
                    max_action_requests=1,
                    on_connected=lambda: connected.append(True),
                )
            )

        self.assertEqual([result["result"]["capability"] for result in results], ["runtime.status"])
        self.assertEqual(connected, [True])
        sent_frames = [
            json.loads(call.args[0]) for call in websocket.send.await_args_list
        ]
        self.assertEqual(
            [frame["type"] for frame in sent_frames],
            ["connect", "auth_proof", "capability_announce", "action_result"],
        )
