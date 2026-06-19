import unittest

from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.context_snapshot import build_context_snapshot


class ContextSnapshotTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
