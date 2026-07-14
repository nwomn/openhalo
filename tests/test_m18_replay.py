"""Regression coverage for safe chronological M18 offline replay."""

from __future__ import annotations

import json
import unittest

from personal_runtime.m18_replay import replay_m18_state_history


class M18ReplayTests(unittest.TestCase):
    def test_replay_sorts_batches_and_never_dispatches_actions(self) -> None:
        payload = {
            "observations": [
                {
                    "name": "runtime.process_present",
                    "value": True,
                    "source_device_id": "host-edge-1",
                    "source_capability": "runtime.health",
                    "source_event_id": "health-batch-1",
                    "observed_at": "2026-07-13T10:00:00Z",
                    "confidence": 1.0,
                },
                {
                    "name": "mobile.screen_context",
                    "value": {
                        "sensitivity": "low",
                        "capture_mode": "accessibility",
                        "visible_text": "banking balance 12345",
                    },
                    "source_device_id": "phone-edge-1",
                    "source_capability": "mobile.context",
                    "source_event_id": "screen-batch-1",
                    "observed_at": "2026-07-13T09:59:00Z",
                    "confidence": 1.0,
                },
                {
                    "name": "runtime.health_state",
                    "value": "degraded",
                    "source_device_id": "host-edge-1",
                    "source_capability": "runtime.health",
                    "source_event_id": "health-batch-1",
                    "observed_at": "2026-07-13T10:00:00Z",
                    "confidence": 1.0,
                },
            ]
        }

        report = replay_m18_state_history(payload)

        self.assertEqual(report["action_dispatch_count"], 0)
        self.assertEqual(
            report["decision_counts"],
            {"skip": 0, "defer": 1, "trigger": 1},
        )
        self.assertEqual(report["decisions"][0]["status"], "defer")
        self.assertEqual(report["decisions"][0]["source_event_id"], "screen-batch-1")
        self.assertEqual(report["decisions"][1]["status"], "trigger")
        self.assertEqual(report["decisions"][1]["source_event_id"], "health-batch-1")
        self.assertEqual(report["decisions"][1]["observation_count"], 2)
        self.assertEqual(report["interactions"][0]["origin"], "observation_driven")
        self.assertNotIn("banking balance 12345", json.dumps(report))

    def test_replay_orders_grouped_batches_by_decision_time(self) -> None:
        payload = {
            "observations": [
                {
                    "name": "runtime.process_present",
                    "value": True,
                    "source_device_id": "host-edge-1",
                    "source_capability": "runtime.health",
                    "source_event_id": "health-batch",
                    "observed_at": "2026-07-13T10:00:00Z",
                    "confidence": 1.0,
                },
                {
                    "name": "mobile.screen_context",
                    "value": {
                        "sensitivity": "normal",
                        "capture_mode": "accessibility_tree",
                    },
                    "source_device_id": "phone-edge-1",
                    "source_capability": "mobile.screen_context",
                    "source_event_id": "screen-batch",
                    "observed_at": "2026-07-13T10:01:00Z",
                    "confidence": 1.0,
                },
                {
                    "name": "runtime.health_state",
                    "value": "degraded",
                    "source_device_id": "host-edge-1",
                    "source_capability": "runtime.health",
                    "source_event_id": "health-batch",
                    "observed_at": "2026-07-13T10:02:00Z",
                    "confidence": 1.0,
                },
            ]
        }

        report = replay_m18_state_history(payload)

        self.assertEqual(
            [decision["source_event_id"] for decision in report["decisions"]],
            ["screen-batch", "health-batch"],
        )
        self.assertEqual(
            [decision["observed_at"] for decision in report["decisions"]],
            ["2026-07-13T10:01:00Z", "2026-07-13T10:02:00Z"],
        )

    def test_replay_skips_causally_linked_observation(self) -> None:
        report = replay_m18_state_history(
            {
                "observations": [
                    {
                        "name": "runtime.health_state",
                        "value": "degraded",
                        "source_device_id": "host-edge-1",
                        "source_capability": "runtime.health",
                        "source_event_id": "linked-health-batch",
                        "observed_at": "2026-07-13T10:00:00Z",
                        "confidence": 1.0,
                        "parent_event_id": "parent-event-1",
                    }
                ]
            }
        )

        self.assertEqual(report["decision_counts"]["trigger"], 0)
        self.assertEqual(report["interactions"], [])
        self.assertEqual(
            report["decisions"][0]["reason_code"],
            "causally_linked_observation",
        )


if __name__ == "__main__":
    unittest.main()
