import unittest

from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.context_snapshot import build_context_snapshot_contract
from personal_runtime.context_snapshot import build_context_snapshot


class ContextSnapshotTests(unittest.TestCase):
    def test_builds_contract_for_fresh_location_evidence_at_snapshot_time(self) -> None:
        contract = build_context_snapshot_contract(
            [
                RuntimeObservation(
                    name="user.location",
                    value="office",
                    source_device_id="desktop-dev-1",
                    source_capability="desktop_context",
                    source_event_id="evt-1",
                    observed_at="2026-06-21T10:08:00Z",
                    confidence=0.90,
                )
            ],
            snapshot_time="2026-06-21T10:10:00Z",
        )

        self.assertEqual(contract["snapshot_time"], "2026-06-21T10:10:00Z")
        self.assertEqual(contract["fields"]["user.current_location"]["value"], "office")
        self.assertEqual(contract["fields"]["user.current_location"]["status"], "fresh")
        self.assertEqual(
            contract["fields"]["user.current_location"]["evidence"][0]["name"],
            "user.location",
        )

    def test_builds_contract_for_stale_runtime_health_evidence_at_snapshot_time(self) -> None:
        contract = build_context_snapshot_contract(
            [
                RuntimeObservation(
                    name="runtime.health_state",
                    value="healthy",
                    source_device_id="host-edge-1",
                    source_capability="runtime.health",
                    source_event_id="evt-rt-1",
                    observed_at="2026-06-21T10:00:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-21T10:10:00Z",
        )

        self.assertEqual(
            contract["fields"]["runtime.current_health_state"]["value"], "unknown"
        )
        self.assertEqual(
            contract["fields"]["runtime.current_health_state"]["status"], "stale"
        )
        self.assertEqual(
            contract["fields"]["runtime.current_health_state"]["evidence"][0]["observed_at"],
            "2026-06-21T10:00:00Z",
        )

    def test_builds_contract_for_missing_host_cpu_evidence(self) -> None:
        contract = build_context_snapshot_contract([])

        self.assertEqual(
            contract["fields"]["host.current_cpu_load_ratio"]["value"], "unknown"
        )
        self.assertEqual(
            contract["fields"]["host.current_cpu_load_ratio"]["status"], "missing"
        )
        self.assertEqual(
            contract["fields"]["host.current_cpu_load_ratio"]["evidence"], []
        )

    def test_builds_contract_for_ambiguous_location_evidence(self) -> None:
        contract = build_context_snapshot_contract(
            [
                RuntimeObservation(
                    name="user.location",
                    value="office",
                    source_device_id="desktop-dev-1",
                    source_capability="desktop_context",
                    source_event_id="evt-1",
                    observed_at="2026-06-21T10:09:00Z",
                    confidence=0.81,
                ),
                RuntimeObservation(
                    name="user.location",
                    value="train",
                    source_device_id="phone-1",
                    source_capability="mobile_context",
                    source_event_id="evt-2",
                    observed_at="2026-06-21T10:08:00Z",
                    confidence=0.80,
                ),
            ],
            snapshot_time="2026-06-21T10:10:00Z",
        )

        self.assertEqual(
            contract["fields"]["user.current_location"]["value"], "ambiguous"
        )
        self.assertEqual(
            contract["fields"]["user.current_location"]["status"], "ambiguous"
        )
        self.assertEqual(
            len(contract["fields"]["user.current_location"]["evidence"]), 2
        )

    def test_accepts_fractional_second_observation_timestamps(self) -> None:
        contract = build_context_snapshot_contract(
            [
                RuntimeObservation(
                    name="runtime.health_state",
                    value="healthy",
                    source_device_id="host-edge-1",
                    source_capability="runtime.health",
                    source_event_id="evt-rt-fractional",
                    observed_at="2026-06-21T10:08:36.843348Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-21T10:10:00Z",
        )

        self.assertEqual(
            contract["fields"]["runtime.current_health_state"]["value"], "healthy"
        )
        self.assertEqual(
            contract["fields"]["runtime.current_health_state"]["status"], "fresh"
        )

    def test_selects_current_location_from_most_recent_observation(self) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="user.location",
                    value="office",
                    source_device_id="desktop-dev-1",
                    source_capability="desktop_context",
                    source_event_id="evt-1",
                    observed_at="2026-06-18T10:00:00Z",
                    confidence=0.70,
                ),
                RuntimeObservation(
                    name="user.location",
                    value="home.office",
                    source_device_id="desktop-dev-1",
                    source_capability="desktop_context",
                    source_event_id="evt-2",
                    observed_at="2026-06-18T10:30:00Z",
                    confidence=0.60,
                ),
            ]
        )

        self.assertEqual(snapshot["user.current_location"], "home.office")

    def test_returns_unknown_when_location_evidence_is_missing(self) -> None:
        snapshot = build_context_snapshot([])

        self.assertEqual(snapshot["user.current_location"], "unknown")
        self.assertEqual(snapshot["runtime.current_health_state"], "unknown")
        self.assertEqual(snapshot["runtime.current_process_pid"], "unknown")
        self.assertEqual(snapshot["runtime.current_process_present"], "unknown")
        self.assertEqual(snapshot["runtime.current_process_memory_rss_bytes"], "unknown")
        self.assertEqual(snapshot["runtime.current_process_started_at"], "unknown")
        self.assertEqual(snapshot["host.current_cpu_load_ratio"], "unknown")
        self.assertEqual(snapshot["host.current_memory_available_bytes"], "unknown")
        self.assertEqual(snapshot["host.current_memory_used_bytes"], "unknown")
        self.assertEqual(snapshot["host.current_memory_pressure"], "unknown")

    def test_returns_ambiguous_when_recent_location_evidence_conflicts_tightly(self) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="user.location",
                    value="office",
                    source_device_id="desktop-dev-1",
                    source_capability="desktop_context",
                    source_event_id="evt-1",
                    observed_at="2026-06-18T10:30:00Z",
                    confidence=0.81,
                ),
                RuntimeObservation(
                    name="user.location",
                    value="train",
                    source_device_id="phone-1",
                    source_capability="mobile_context",
                    source_event_id="evt-2",
                    observed_at="2026-06-18T10:29:00Z",
                    confidence=0.80,
                ),
            ]
        )

        self.assertEqual(snapshot["user.current_location"], "ambiguous")

    def test_returns_unknown_when_location_evidence_is_stale_at_snapshot_time(self) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="user.location",
                    value="office",
                    source_device_id="desktop-dev-1",
                    source_capability="desktop_context",
                    source_event_id="evt-1",
                    observed_at="2026-06-18T10:00:00Z",
                    confidence=0.90,
                )
            ],
            snapshot_time="2026-06-18T10:10:00Z",
        )

        self.assertEqual(snapshot["user.current_location"], "unknown")

    def test_selects_location_from_fresh_evidence_at_snapshot_time(self) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="user.location",
                    value="office",
                    source_device_id="desktop-dev-1",
                    source_capability="desktop_context",
                    source_event_id="evt-1",
                    observed_at="2026-06-18T10:08:00Z",
                    confidence=0.90,
                )
            ],
            snapshot_time="2026-06-18T10:10:00Z",
        )

        self.assertEqual(snapshot["user.current_location"], "office")

    def test_selects_runtime_health_from_fresh_evidence_at_snapshot_time(self) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="runtime.health_state",
                    value="healthy",
                    source_device_id="host-edge-1",
                    source_capability="runtime.health",
                    source_event_id="evt-rt-1",
                    observed_at="2026-06-20T09:58:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-20T10:00:00Z",
        )

        self.assertEqual(snapshot["runtime.current_health_state"], "healthy")

    def test_returns_unknown_when_runtime_health_evidence_is_stale_at_snapshot_time(self) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="runtime.health_state",
                    value="healthy",
                    source_device_id="host-edge-1",
                    source_capability="runtime.health",
                    source_event_id="evt-rt-1",
                    observed_at="2026-06-20T09:50:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-20T10:00:00Z",
        )

        self.assertEqual(snapshot["runtime.current_health_state"], "unknown")

    def test_selects_runtime_process_pid_from_fresh_evidence_at_snapshot_time(
        self,
    ) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="runtime.process_pid",
                    value=4242,
                    source_device_id="host-edge-1",
                    source_capability="runtime.health",
                    source_event_id="evt-rt-5",
                    observed_at="2026-06-21T10:08:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-21T10:10:00Z",
        )

        self.assertEqual(snapshot["runtime.current_process_pid"], 4242)

    def test_returns_unknown_when_runtime_process_pid_evidence_is_stale_at_snapshot_time(
        self,
    ) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="runtime.process_pid",
                    value=4242,
                    source_device_id="host-edge-1",
                    source_capability="runtime.health",
                    source_event_id="evt-rt-5",
                    observed_at="2026-06-21T10:00:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-21T10:10:00Z",
        )

        self.assertEqual(snapshot["runtime.current_process_pid"], "unknown")

    def test_selects_runtime_process_presence_from_fresh_evidence_at_snapshot_time(
        self,
    ) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="runtime.process_present",
                    value=True,
                    source_device_id="host-edge-1",
                    source_capability="runtime.health",
                    source_event_id="evt-rt-2",
                    observed_at="2026-06-20T10:08:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-20T10:10:00Z",
        )

        self.assertTrue(snapshot["runtime.current_process_present"])

    def test_returns_unknown_when_runtime_process_presence_evidence_is_stale_at_snapshot_time(
        self,
    ) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="runtime.process_present",
                    value=True,
                    source_device_id="host-edge-1",
                    source_capability="runtime.health",
                    source_event_id="evt-rt-2",
                    observed_at="2026-06-20T10:00:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-20T10:10:00Z",
        )

        self.assertEqual(snapshot["runtime.current_process_present"], "unknown")

    def test_selects_runtime_process_memory_rss_from_fresh_evidence_at_snapshot_time(
        self,
    ) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="runtime.process_memory_rss_bytes",
                    value=28114944,
                    source_device_id="host-edge-1",
                    source_capability="runtime.health",
                    source_event_id="evt-rt-3",
                    observed_at="2026-06-20T10:08:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-20T10:10:00Z",
        )

        self.assertEqual(snapshot["runtime.current_process_memory_rss_bytes"], 28114944)

    def test_returns_unknown_when_runtime_process_memory_rss_evidence_is_stale_at_snapshot_time(
        self,
    ) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="runtime.process_memory_rss_bytes",
                    value=28114944,
                    source_device_id="host-edge-1",
                    source_capability="runtime.health",
                    source_event_id="evt-rt-3",
                    observed_at="2026-06-20T10:00:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-20T10:10:00Z",
        )

        self.assertEqual(
            snapshot["runtime.current_process_memory_rss_bytes"], "unknown"
        )

    def test_selects_runtime_process_started_at_from_fresh_evidence_at_snapshot_time(
        self,
    ) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="runtime.process_started_at",
                    value="2026-06-21T09:55:00Z",
                    source_device_id="host-edge-1",
                    source_capability="runtime.health",
                    source_event_id="evt-rt-4",
                    observed_at="2026-06-21T10:08:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-21T10:10:00Z",
        )

        self.assertEqual(
            snapshot["runtime.current_process_started_at"], "2026-06-21T09:55:00Z"
        )

    def test_returns_unknown_when_runtime_process_started_at_evidence_is_stale_at_snapshot_time(
        self,
    ) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="runtime.process_started_at",
                    value="2026-06-21T09:55:00Z",
                    source_device_id="host-edge-1",
                    source_capability="runtime.health",
                    source_event_id="evt-rt-4",
                    observed_at="2026-06-21T10:00:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-21T10:10:00Z",
        )

        self.assertEqual(snapshot["runtime.current_process_started_at"], "unknown")

    def test_selects_host_cpu_load_ratio_from_fresh_evidence_at_snapshot_time(
        self,
    ) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="host.cpu_load_ratio",
                    value=0.62,
                    source_device_id="host-edge-1",
                    source_capability="host.metrics",
                    source_event_id="evt-host-2",
                    observed_at="2026-06-21T09:58:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-21T10:00:00Z",
        )

        self.assertEqual(snapshot["host.current_cpu_load_ratio"], 0.62)

    def test_returns_unknown_when_host_cpu_load_ratio_evidence_is_stale_at_snapshot_time(
        self,
    ) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="host.cpu_load_ratio",
                    value=0.62,
                    source_device_id="host-edge-1",
                    source_capability="host.metrics",
                    source_event_id="evt-host-2",
                    observed_at="2026-06-21T09:50:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-21T10:00:00Z",
        )

        self.assertEqual(snapshot["host.current_cpu_load_ratio"], "unknown")

    def test_selects_host_memory_available_from_fresh_evidence_at_snapshot_time(
        self,
    ) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="host.memory_available_bytes",
                    value=17179869184,
                    source_device_id="host-edge-1",
                    source_capability="host.metrics",
                    source_event_id="evt-host-3",
                    observed_at="2026-06-21T10:08:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-21T10:10:00Z",
        )

        self.assertEqual(
            snapshot["host.current_memory_available_bytes"], 17179869184
        )

    def test_returns_unknown_when_host_memory_available_evidence_is_stale_at_snapshot_time(
        self,
    ) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="host.memory_available_bytes",
                    value=17179869184,
                    source_device_id="host-edge-1",
                    source_capability="host.metrics",
                    source_event_id="evt-host-3",
                    observed_at="2026-06-21T10:00:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-21T10:10:00Z",
        )

        self.assertEqual(snapshot["host.current_memory_available_bytes"], "unknown")

    def test_selects_host_memory_used_from_fresh_evidence_at_snapshot_time(
        self,
    ) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="host.memory_used_bytes",
                    value=34359738368,
                    source_device_id="host-edge-1",
                    source_capability="host.metrics",
                    source_event_id="evt-host-4",
                    observed_at="2026-06-21T10:08:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-21T10:10:00Z",
        )

        self.assertEqual(snapshot["host.current_memory_used_bytes"], 34359738368)

    def test_returns_unknown_when_host_memory_used_evidence_is_stale_at_snapshot_time(
        self,
    ) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="host.memory_used_bytes",
                    value=34359738368,
                    source_device_id="host-edge-1",
                    source_capability="host.metrics",
                    source_event_id="evt-host-4",
                    observed_at="2026-06-21T10:00:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-21T10:10:00Z",
        )

        self.assertEqual(snapshot["host.current_memory_used_bytes"], "unknown")

    def test_selects_host_memory_pressure_from_fresh_evidence_at_snapshot_time(self) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="host.memory_pressure",
                    value="elevated",
                    source_device_id="host-edge-1",
                    source_capability="host.metrics",
                    source_event_id="evt-host-1",
                    observed_at="2026-06-20T10:08:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-20T10:10:00Z",
        )

        self.assertEqual(snapshot["host.current_memory_pressure"], "elevated")

    def test_returns_unknown_when_host_memory_pressure_evidence_is_stale_at_snapshot_time(
        self,
    ) -> None:
        snapshot = build_context_snapshot(
            [
                RuntimeObservation(
                    name="host.memory_pressure",
                    value="high",
                    source_device_id="host-edge-1",
                    source_capability="host.metrics",
                    source_event_id="evt-host-1",
                    observed_at="2026-06-20T10:00:00Z",
                    confidence=1.0,
                )
            ],
            snapshot_time="2026-06-20T10:10:00Z",
        )

        self.assertEqual(snapshot["host.current_memory_pressure"], "unknown")


if __name__ == "__main__":
    unittest.main()
