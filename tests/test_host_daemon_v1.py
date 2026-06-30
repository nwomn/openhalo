import asyncio
import io
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from tempfile import NamedTemporaryFile
from unittest.mock import AsyncMock
from unittest.mock import patch

from websockets.exceptions import ConnectionClosedOK

from device_edge.host.host_daemon import HostEdgeDaemon
from device_edge.host.host_daemon import build_host_daemon_parser
from device_edge.host.host_daemon import build_observation_timestamp_provider
from device_edge.host.host_daemon import build_trace_recorder
from device_edge.host.host_daemon import build_runtime_health_provider
from device_edge.host.host_daemon import build_runtime_control_adapter
from device_edge.host.host_daemon import main
from device_edge.host.runtime_control import PythonProcessAdapter
from personal_runtime.trace_recorder import TraceRecorder
from openhalo_common.diagnostics import InMemoryDiagnosticRecorder


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

    def test_building_observation_frames_records_host_edge_diagnostics(self) -> None:
        diagnostics = InMemoryDiagnosticRecorder(
            timestamp_provider=lambda: "2026-06-30T12:00:00Z"
        )
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
            diagnostic_recorder=diagnostics,
        )

        daemon.build_observation_frames(observed_at="2026-06-19T09:30:00Z")

        self.assertTrue(diagnostics.events)
        modules = [event.module for event in diagnostics.events]
        self.assertIn("Local Capability Runtime", modules)
        self.assertIn("Edge Session Link", modules)

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

    def test_records_bounded_local_observation_history_and_returns_it(self) -> None:
        captured_histories: list[dict] = []

        class HistoryAwareAdapter:
            def execute(self, action: dict) -> dict:
                if action["capability"] == "runtime.edge_history":
                    history = action["payload"]["history_supplier"](
                        action["payload"].get("limit", 10)
                    )
                    captured_histories.append(history)
                    return {
                        "status": "ok",
                        "capability": action["capability"],
                        "details": history,
                    }
                return {
                    "status": "ok",
                    "capability": action["capability"],
                    "details": {"state": "running", "pid": 42137},
                }

        daemon = HostEdgeDaemon(
            device_id="host-edge-1",
            token="dev-token",
            runtime_control_adapter=HistoryAwareAdapter(),
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
            history_limit=2,
        )

        daemon.build_observation_frames(observed_at="2026-06-19T09:30:00Z")
        daemon.build_observation_frames(observed_at="2026-06-19T09:31:00Z")

        result = daemon.handle_action_request(
            {
                "type": "action_request",
                "device_id": "host-edge-1",
                "action": {"capability": "runtime.edge_history", "payload": {"limit": 1}},
            }
        )

        self.assertEqual(result["type"], "action_result")
        self.assertEqual(result["result"]["capability"], "runtime.edge_history")
        self.assertEqual(result["result"]["details"]["returned_entries"], 1)
        self.assertEqual(result["result"]["details"]["available_entries"], 2)
        self.assertEqual(
            result["result"]["details"]["entries"][0]["observed_at"],
            "2026-06-19T09:31:00Z",
        )
        self.assertEqual(captured_histories[0]["returned_entries"], 1)

    def test_edge_history_can_filter_entries_by_capability(self) -> None:
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
            history_limit=4,
        )

        daemon.build_observation_frames(observed_at="2026-06-19T09:30:00Z")
        history = daemon.build_recent_history(limit=4, capability="runtime.health")

        self.assertEqual(history["returned_entries"], 1)
        self.assertEqual(history["entries"][0]["capability"], "runtime.health")

    def test_build_observation_frames_records_trace_for_local_history_visibility(
        self,
    ) -> None:
        trace = TraceRecorder()
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
            history_limit=4,
            trace_recorder=trace,
        )

        daemon.build_observation_frames(observed_at="2026-06-19T09:30:00Z")

        lines = trace.format_lines()

        self.assertTrue(
            any("HOST recorded local observation history" in line for line in lines)
        )

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

        with patch("device_edge.host.host_daemon.websockets.connect", return_value=connect_cm):
            result = asyncio.run(
                daemon.run_websocket_control_session(
                    url="ws://127.0.0.1:8765",
                    observed_at="2026-06-19T09:30:00Z",
                    follow_up_observed_at="2026-06-19T09:31:00Z",
                )
            )

        self.assertEqual(result["result"]["capability"], "runtime.status")
        self.assertEqual(websocket.send.await_count, 6)

    def test_daemon_session_handles_multiple_actions_and_idle_observation_cycles(
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
                asyncio.TimeoutError(),
                '{"type": "event_ack"}',
                '{"type": "event_ack"}',
                '{"type": "action_request", "device_id": "host-edge-1", "action": {"capability": "runtime.status", "payload": {}}}',
                asyncio.TimeoutError(),
                '{"type": "event_ack"}',
                '{"type": "event_ack"}',
                '{"type": "action_request", "device_id": "host-edge-1", "action": {"capability": "runtime.collect_logs", "payload": {}}}',
            ]
        )
        connect_cm = AsyncMock()
        connect_cm.__aenter__.return_value = websocket
        connect_cm.__aexit__.return_value = False

        with patch("device_edge.host.host_daemon.websockets.connect", return_value=connect_cm):
            results = asyncio.run(
                daemon.run_websocket_daemon_session(
                    url="ws://127.0.0.1:8765",
                    observation_schedule=[
                        "2026-06-19T09:30:00Z",
                        "2026-06-19T09:31:00Z",
                        "2026-06-19T09:32:00Z",
                    ],
                    idle_timeout_s=0.01,
                    max_action_requests=2,
                    send_follow_up_after_action=False,
                )
            )

        self.assertEqual(
            [result["result"]["capability"] for result in results],
            ["runtime.status", "runtime.collect_logs"],
        )
        self.assertEqual(websocket.send.await_count, 10)

    def test_daemon_session_handles_action_request_interleaved_while_waiting_for_observation_ack(
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
                asyncio.TimeoutError(),
                '{"type": "action_request", "device_id": "host-edge-1", "action": {"capability": "runtime.status", "payload": {}}}',
                '{"type": "event_ack"}',
                '{"type": "event_ack"}',
            ]
        )
        connect_cm = AsyncMock()
        connect_cm.__aenter__.return_value = websocket
        connect_cm.__aexit__.return_value = False

        with patch("device_edge.host.host_daemon.websockets.connect", return_value=connect_cm):
            results = asyncio.run(
                daemon.run_websocket_daemon_session(
                    url="ws://127.0.0.1:8765",
                    observation_schedule=[
                        "2026-06-19T09:30:00Z",
                        "2026-06-19T09:31:00Z",
                    ],
                    idle_timeout_s=0.01,
                    max_action_requests=1,
                    send_follow_up_after_action=False,
                )
            )

        self.assertEqual(results[0]["result"]["capability"], "runtime.status")
        sent_frames = [
            __import__("json").loads(call.args[0])
            for call in websocket.send.await_args_list
        ]
        self.assertTrue(
            any(frame.get("type") == "action_result" for frame in sent_frames)
        )

    def test_run_forever_retries_after_connection_failure(self) -> None:
        trace = TraceRecorder()
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
            trace_recorder=trace,
        )

        session_calls: list[list[str]] = []
        sleep_calls: list[float] = []

        async def fake_session(**kwargs):
            session_calls.append(kwargs["observation_schedule"])
            if len(session_calls) == 1:
                raise OSError("runtime offline")
            return []

        async def fake_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        with patch.object(
            daemon,
            "run_websocket_daemon_session",
            side_effect=fake_session,
        ):
            with patch("device_edge.host.host_daemon.asyncio.sleep", side_effect=fake_sleep):
                asyncio.run(
                    daemon.run_forever(
                        url="ws://127.0.0.1:8765",
                        observation_schedule_factory=lambda attempt: [
                            f"2026-06-19T09:3{attempt}:00Z"
                        ],
                        reconnect_delay_s=2.5,
                        max_sessions=2,
                    )
                )

        self.assertEqual(
            session_calls,
            [["2026-06-19T09:30:00Z"], ["2026-06-19T09:31:00Z"]],
        )
        self.assertEqual(sleep_calls, [2.5])
        self.assertTrue(
            any("HOST retrying websocket session" in line for line in trace.format_lines())
        )
        self.assertTrue(
            any(
                "HOST starting websocket daemon session" in line
                for line in trace.format_lines()
            )
        )

    def test_run_forever_retries_after_runtime_closes_websocket_cleanly(self) -> None:
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

        session_calls: list[list[str]] = []
        sleep_calls: list[float] = []

        async def fake_session(**kwargs):
            session_calls.append(kwargs["observation_schedule"])
            if len(session_calls) == 1:
                raise ConnectionClosedOK(None, None)
            return []

        async def fake_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        with patch.object(
            daemon,
            "run_websocket_daemon_session",
            side_effect=fake_session,
        ):
            with patch("device_edge.host.host_daemon.asyncio.sleep", side_effect=fake_sleep):
                asyncio.run(
                    daemon.run_forever(
                        url="ws://127.0.0.1:8765",
                        observation_schedule_factory=lambda attempt: [
                            f"2026-06-19T09:4{attempt}:00Z"
                        ],
                        reconnect_delay_s=2.0,
                        max_sessions=2,
                    )
                )

        self.assertEqual(
            session_calls,
            [["2026-06-19T09:40:00Z"], ["2026-06-19T09:41:00Z"]],
        )
        self.assertEqual(sleep_calls, [2.0])

    def test_run_forever_uses_bounded_exponential_backoff_after_repeated_failures(
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

        sleep_calls: list[float] = []

        async def always_fail_session(**kwargs):
            raise OSError("runtime offline")

        async def fake_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        with patch.object(
            daemon,
            "run_websocket_daemon_session",
            side_effect=always_fail_session,
        ):
            with patch("device_edge.host.host_daemon.asyncio.sleep", side_effect=fake_sleep):
                asyncio.run(
                    daemon.run_forever(
                        url="ws://127.0.0.1:8765",
                        observation_schedule_factory=lambda attempt: [
                            f"2026-06-20T09:0{attempt}:00Z"
                        ],
                        reconnect_delay_s=1.0,
                        reconnect_backoff_multiplier=2.0,
                        reconnect_max_delay_s=5.0,
                        max_sessions=4,
                    )
                )

        self.assertEqual(sleep_calls, [1.0, 2.0, 4.0, 5.0])

    def test_run_forever_applies_jitter_to_backoff_delay(self) -> None:
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

        sleep_calls: list[float] = []

        async def always_fail_session(**kwargs):
            raise OSError("runtime offline")

        async def fake_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        with patch.object(
            daemon,
            "run_websocket_daemon_session",
            side_effect=always_fail_session,
        ):
            with patch("device_edge.host.host_daemon.asyncio.sleep", side_effect=fake_sleep):
                asyncio.run(
                    daemon.run_forever(
                        url="ws://127.0.0.1:8765",
                        observation_schedule_factory=lambda attempt: [
                            f"2026-06-20T10:0{attempt}:00Z"
                        ],
                        reconnect_delay_s=2.0,
                        reconnect_backoff_multiplier=2.0,
                        reconnect_max_delay_s=10.0,
                        reconnect_jitter=lambda base_delay, attempt: base_delay + 0.25,
                        max_sessions=2,
                    )
                )

        self.assertEqual(sleep_calls, [2.25, 4.25])

    def test_daemon_session_continues_periodic_observations_from_timestamp_provider(
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
                asyncio.TimeoutError(),
                '{"type": "event_ack"}',
                '{"type": "event_ack"}',
                '{"type": "action_request", "device_id": "host-edge-1", "action": {"capability": "runtime.status", "payload": {}}}',
            ]
        )
        connect_cm = AsyncMock()
        connect_cm.__aenter__.return_value = websocket
        connect_cm.__aexit__.return_value = False
        provided_timestamps: list[str] = []

        def timestamp_provider() -> str:
            provided_timestamps.append("2026-06-19T09:31:00Z")
            return provided_timestamps[-1]

        with patch("device_edge.host.host_daemon.websockets.connect", return_value=connect_cm):
            results = asyncio.run(
                daemon.run_websocket_daemon_session(
                    url="ws://127.0.0.1:8765",
                    observation_schedule=["2026-06-19T09:30:00Z"],
                    observation_timestamp_provider=timestamp_provider,
                    idle_timeout_s=0.01,
                    max_action_requests=1,
                    send_follow_up_after_action=False,
                )
            )

        self.assertEqual(provided_timestamps, ["2026-06-19T09:31:00Z"])
        self.assertEqual(results[0]["result"]["capability"], "runtime.status")
        self.assertEqual(websocket.send.await_count, 7)

    def test_daemon_session_stops_after_max_idle_cycles_without_actions(self) -> None:
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
                asyncio.TimeoutError(),
                '{"type": "event_ack"}',
                '{"type": "event_ack"}',
            ]
        )
        connect_cm = AsyncMock()
        connect_cm.__aenter__.return_value = websocket
        connect_cm.__aexit__.return_value = False

        with patch("device_edge.host.host_daemon.websockets.connect", return_value=connect_cm):
            results = asyncio.run(
                daemon.run_websocket_daemon_session(
                    url="ws://127.0.0.1:8765",
                    observation_schedule=["2026-06-19T09:30:00Z"],
                    observation_timestamp_provider=lambda: "2026-06-19T09:31:00Z",
                    idle_timeout_s=0.01,
                    max_idle_cycles=1,
                    send_follow_up_after_action=False,
                )
            )

        self.assertEqual(results, [])
        self.assertEqual(websocket.send.await_count, 6)

    def test_build_host_daemon_parser_reads_runtime_options(self) -> None:
        parser = build_host_daemon_parser()

        args = parser.parse_args(
            [
                "--url",
                "ws://127.0.0.1:8765",
                "--token",
                "dev-token",
                "--device-id",
                "host-edge-9",
                "--reconnect-delay",
                "4.5",
                "--reconnect-backoff-multiplier",
                "2.0",
                "--reconnect-max-delay",
                "15.0",
                "--reconnect-jitter-fixed",
                "0.4",
                "--idle-timeout",
                "1.5",
                "--max-idle-cycles",
                "2",
                "--max-action-requests",
                "3",
                "--max-sessions",
                "4",
                "--history-limit",
                "7",
                "--trace",
                "--trace-file",
                "/tmp/host-edge.trace",
                "--log-path",
                "/tmp/runtime.log",
            ]
        )

        self.assertEqual(args.url, "ws://127.0.0.1:8765")
        self.assertEqual(args.device_id, "host-edge-9")
        self.assertEqual(args.reconnect_delay, 4.5)
        self.assertEqual(args.reconnect_backoff_multiplier, 2.0)
        self.assertEqual(args.reconnect_max_delay, 15.0)
        self.assertEqual(args.reconnect_jitter_fixed, 0.4)
        self.assertEqual(args.idle_timeout, 1.5)
        self.assertEqual(args.max_idle_cycles, 2)
        self.assertEqual(args.max_action_requests, 3)
        self.assertEqual(args.max_sessions, 4)
        self.assertEqual(args.history_limit, 7)
        self.assertTrue(args.trace)
        self.assertEqual(str(args.trace_file), "/tmp/host-edge.trace")
        self.assertEqual(str(args.log_path), "/tmp/runtime.log")

    def test_parser_accepts_diagnostic_log_path(self) -> None:
        args = build_host_daemon_parser().parse_args(
            [
                "--url",
                "ws://127.0.0.1:8765",
                "--diagnostic-log-path",
                ".runtime/diagnostics/host-edge-1.jsonl",
            ]
        )

        self.assertEqual(
            args.diagnostic_log_path,
            Path(".runtime/diagnostics/host-edge-1.jsonl"),
        )

    def test_build_trace_recorder_can_write_live_trace_file(self) -> None:
        with NamedTemporaryFile("r+", encoding="utf-8") as trace_file:
            args = build_host_daemon_parser().parse_args(
                [
                    "--url",
                    "ws://127.0.0.1:8765",
                    "--trace-file",
                    trace_file.name,
                ]
            )

            recorder = build_trace_recorder(args)
            self.assertIsNotNone(recorder)

            recorder.record("HOST", "manual trace sample", status="ok")
            trace_file.seek(0)

            self.assertIn(
                "HOST manual trace sample [status=ok]",
                trace_file.read(),
            )

    def test_build_runtime_control_adapter_uses_runtime_options(self) -> None:
        args = build_host_daemon_parser().parse_args(
            [
                "--url",
                "ws://127.0.0.1:8765",
                "--runtime-process-match",
                "personal_runtime.main",
                "--runtime-start-command",
                "python -m personal_runtime.main --host 127.0.0.1",
                "--runtime-reload-command",
                "kill -HUP 42137",
                "--log-path",
                "/tmp/runtime.log",
            ]
        )

        adapter = build_runtime_control_adapter(args)

        self.assertEqual(adapter.process_match_substring, "personal_runtime.main")
        self.assertEqual(
            adapter.start_command,
            ["python", "-m", "personal_runtime.main", "--host", "127.0.0.1"],
        )
        self.assertEqual(adapter.reload_command, ["kill", "-HUP", "42137"])
        self.assertEqual(str(adapter.log_path), "/tmp/runtime.log")

    def test_main_starts_host_daemon_runtime(self) -> None:
        stdout = io.StringIO()

        with patch("device_edge.host.host_daemon.read_host_metric_snapshot", return_value={}):
            with patch.object(
                HostEdgeDaemon,
                "run_forever",
                new_callable=AsyncMock,
            ) as run_forever:
                with redirect_stdout(stdout):
                    main(
                        [
                            "--url",
                            "ws://127.0.0.1:8765",
                            "--runtime-start-command",
                            "python -m personal_runtime.main",
                            "--reconnect-delay",
                            "3.0",
                            "--reconnect-backoff-multiplier",
                            "2.5",
                            "--reconnect-max-delay",
                            "12.0",
                            "--reconnect-jitter-fixed",
                            "0.5",
                            "--idle-timeout",
                            "2.0",
                            "--max-idle-cycles",
                            "3",
                            "--max-action-requests",
                            "4",
                            "--max-sessions",
                            "5",
                            "--history-limit",
                            "9",
                            "--trace",
                        ]
                    )

        run_forever.assert_awaited_once()
        _, kwargs = run_forever.await_args
        self.assertEqual(kwargs["reconnect_delay_s"], 3.0)
        self.assertEqual(kwargs["reconnect_backoff_multiplier"], 2.5)
        self.assertEqual(kwargs["reconnect_max_delay_s"], 12.0)
        self.assertAlmostEqual(kwargs["reconnect_jitter"](4.0, 2), 4.5)
        self.assertEqual(kwargs["idle_timeout_s"], 2.0)
        self.assertEqual(kwargs["max_idle_cycles"], 3)
        self.assertEqual(kwargs["max_action_requests"], 4)
        self.assertEqual(kwargs["max_sessions"], 5)
        self.assertNotIn("history_limit", kwargs)
        self.assertIn("Host edge daemon connecting", stdout.getvalue())
        self.assertIn("Trace enabled", stdout.getvalue())

    def test_module_execution_invokes_cli_entrypoint(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "device_edge.host.host_daemon",
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[1],
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Run the host edge daemon.", result.stdout)
        self.assertIn("--url", result.stdout)

    def test_python_process_adapter_discovers_runtime_process_from_proc_root(self) -> None:
        with TemporaryDirectory() as tmpdir:
            proc_root = Path(tmpdir)
            pid_dir = proc_root / "42137"
            pid_dir.mkdir()
            (pid_dir / "cmdline").write_text(
                "python\0-m\0personal_runtime.main\0--host\0127.0.0.1\0",
                encoding="utf-8",
            )
            (pid_dir / "statm").write_text("100 20 0 0 0 0 0\n", encoding="utf-8")

            adapter = PythonProcessAdapter(
                process_match_substring="personal_runtime.main",
                start_command=["python", "-m", "personal_runtime.main"],
                proc_root=proc_root,
            )

            result = adapter.execute({"capability": "runtime.status", "payload": {}})

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["details"]["state"], "running")
        self.assertEqual(result["details"]["pid"], 42137)
        self.assertEqual(result["details"]["memory_rss_bytes"], 20 * 4096)

    def test_build_runtime_health_provider_maps_runtime_status_details(self) -> None:
        class StatusAdapter:
            def execute(self, action: dict) -> dict:
                return {
                    "status": "ok",
                    "capability": action["capability"],
                    "details": {
                        "state": "running",
                        "pid": 42137,
                        "memory_rss_bytes": 28114944,
                        "started_at": "2026-06-19T09:00:00Z",
                    },
                }

        provider = build_runtime_health_provider(StatusAdapter())

        snapshot = provider()

        self.assertEqual(snapshot["health_state"], "healthy")
        self.assertEqual(snapshot["process_pid"], 42137)
        self.assertTrue(snapshot["process_present"])
        self.assertEqual(snapshot["process_started_at"], "2026-06-19T09:00:00Z")
        self.assertEqual(snapshot["process_memory_rss_bytes"], 28114944)

    def test_build_observation_timestamp_provider_returns_current_utc_timestamp(
        self,
    ) -> None:
        provider = build_observation_timestamp_provider(
            now_supplier=lambda: "2026-06-19T10:15:30Z"
        )

        timestamp = provider()

        self.assertEqual(timestamp, "2026-06-19T10:15:30Z")


if __name__ == "__main__":
    unittest.main()
