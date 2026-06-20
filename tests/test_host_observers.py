import unittest

from device_edge.host.host_observers import build_host_metric_observations
from device_edge.host.host_observers import build_runtime_health_observations


class HostObserverTests(unittest.TestCase):
    def test_builds_host_metric_observations_from_snapshot(self) -> None:
        observations = build_host_metric_observations(
            {
                "cpu_load_ratio": 0.31,
                "memory_used_bytes": 400,
                "memory_available_bytes": 600,
                "memory_pressure": "normal",
                "net_rx_bytes": 10,
                "net_tx_bytes": 12,
            },
            observed_at="2026-06-19T09:30:00Z",
        )

        self.assertEqual(observations[0]["name"], "host.cpu_load_ratio")
        self.assertEqual(observations[0]["value"], 0.31)
        self.assertEqual(
            observations[-1],
            {
                "name": "host.net_tx_bytes",
                "value": 12,
                "observed_at": "2026-06-19T09:30:00Z",
                "confidence": 1.0,
            },
        )

    def test_builds_runtime_health_observations_from_snapshot(self) -> None:
        observations = build_runtime_health_observations(
            {
                "health_state": "healthy",
                "process_pid": 42137,
                "process_present": True,
                "process_started_at": "2026-06-19T09:00:00Z",
                "process_memory_rss_bytes": 28114944,
            },
            observed_at="2026-06-19T09:30:00Z",
        )

        self.assertEqual(observations[0]["name"], "runtime.health_state")
        self.assertEqual(observations[1]["value"], 42137)
        self.assertEqual(
            observations[-1]["name"],
            "runtime.process_memory_rss_bytes",
        )


if __name__ == "__main__":
    unittest.main()
