import unittest
from unittest.mock import AsyncMock
from unittest.mock import patch

from device_edge.host_daemon import HostEdgeDaemon


class FakeRuntimeControlAdapter:
    def execute(self, action: dict) -> dict:
        return {
            "status": "ok",
            "capability": action["capability"],
            "details": {"state": "running", "pid": 42137},
        }


class HostDaemonTests(unittest.TestCase):
    def test_builds_bootstrap_frames_for_host_edge(self) -> None:
        daemon = HostEdgeDaemon(
            device_id="host-edge-1",
            token="dev-token",
            runtime_control_adapter=FakeRuntimeControlAdapter(),
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

        bootstrap_frames = daemon.build_bootstrap_frames()

        self.assertEqual(bootstrap_frames[0]["type"], "connect")
        self.assertEqual(bootstrap_frames[1]["type"], "capability_announce")
        self.assertEqual(
            bootstrap_frames[1]["capabilities"],
            ["host.metrics", "runtime.health", "runtime.control"],
        )

    def test_builds_initial_observation_frames(self) -> None:
        daemon = HostEdgeDaemon(
            device_id="host-edge-1",
            token="dev-token",
            runtime_control_adapter=FakeRuntimeControlAdapter(),
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

        frames = daemon.build_observation_frames(observed_at="2026-06-19T09:30:00Z")

        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0]["capability"], "host.metrics")
        self.assertEqual(
            frames[0]["payload"]["observations"][0]["name"],
            "host.cpu_load_ratio",
        )
        self.assertEqual(frames[1]["capability"], "runtime.health")
        self.assertEqual(
            frames[1]["payload"]["observations"][0]["name"],
            "runtime.health_state",
        )

    def test_handles_runtime_status_action_request(self) -> None:
        daemon = HostEdgeDaemon(
            device_id="host-edge-1",
            token="dev-token",
            runtime_control_adapter=FakeRuntimeControlAdapter(),
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

        result = daemon.handle_action_request(
            {
                "type": "action_request",
                "device_id": "host-edge-1",
                "action": {"capability": "runtime.status", "payload": {}},
            }
        )

        self.assertEqual(result["type"], "action_result")
        self.assertEqual(result["device_id"], "host-edge-1")
        self.assertEqual(result["result"]["capability"], "runtime.status")
        self.assertEqual(result["result"]["details"]["pid"], 42137)

    def test_websocket_control_session_sends_bootstrap_observations_and_action_result(
        self,
    ) -> None:
        daemon = HostEdgeDaemon(
            device_id="host-edge-1",
            token="dev-token",
            runtime_control_adapter=FakeRuntimeControlAdapter(),
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

        websocket = AsyncMock()
        websocket.recv = AsyncMock(
            side_effect=[
                '{"type": "connect_ok"}',
                '{"type": "event_ack"}',
                '{"type": "event_ack"}',
                '{"type": "action_request", "device_id": "host-edge-1", "action": {"capability": "runtime.status", "payload": {}}}',
                '{"type": "event_ack"}',
            ]
        )
        connect_cm = AsyncMock()
        connect_cm.__aenter__.return_value = websocket
        connect_cm.__aexit__.return_value = False

        with patch("device_edge.host_daemon.websockets.connect", return_value=connect_cm):
            result = __import__("asyncio").run(
                daemon.run_websocket_control_session(
                    url="ws://127.0.0.1:8765",
                    observed_at="2026-06-19T09:30:00Z",
                    follow_up_observed_at="2026-06-19T09:31:00Z",
                )
            )

        self.assertEqual(result["result"]["capability"], "runtime.status")
        self.assertEqual(websocket.send.await_count, 6)


if __name__ == "__main__":
    unittest.main()
