from __future__ import annotations

import unittest

from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.context_facts import ContextFactStore


def observation(
    *,
    device_id: str = "edge-1",
    name: str = "camera.person_presence.v1",
    value: object = None,
    observed_at: str = "2026-08-23T10:00:00Z",
    disposition: str = "full",
) -> RuntimeObservation:
    return RuntimeObservation(
        name=name,
        value={"state": "present"} if value is None else value,
        source_device_id=device_id,
        source_capability="camera.person_presence",
        source_event_id=f"{device_id}-event",
        observed_at=observed_at,
        confidence=0.9,
        context_disposition=disposition,
    )


class ContextFactStoreTests(unittest.TestCase):
    def test_materializes_same_observation_name_per_device(self) -> None:
        store = ContextFactStore()

        store.materialize(observation(device_id="camera-1"), freshness_seconds=60)
        store.materialize(observation(device_id="camera-2"), freshness_seconds=60)

        self.assertEqual(
            {fact.fact_id for fact in store.all_facts()},
            {
                "camera-1/camera.person_presence.v1",
                "camera-2/camera.person_presence.v1",
            },
        )

    def test_ignores_an_older_observation_for_the_same_fact(self) -> None:
        store = ContextFactStore()
        store.materialize(
            observation(value={"state": "present"}, observed_at="2026-08-23T10:01:00Z"),
            freshness_seconds=60,
        )

        changed = store.materialize(
            observation(value={"state": "absent"}, observed_at="2026-08-23T10:00:00Z"),
            freshness_seconds=60,
        )

        self.assertFalse(changed)
        self.assertEqual(store.all_facts()[0].value, {"state": "present"})

    def test_sensitive_or_health_only_value_becomes_structural(self) -> None:
        store = ContextFactStore()

        store.materialize(
            observation(
                name="mobile.screen_context",
                value={
                    "visible_text_summary": "bank account 1234",
                    "sensitivity": "blocked",
                    "capture_mode": "health_only",
                },
            ),
            freshness_seconds=60,
        )

        fact = store.all_facts()[0]
        self.assertEqual(fact.disposition, "structural")
        self.assertEqual(fact.value, {"state": "withheld"})
        self.assertEqual(fact.withheld_reason, "sensitive_or_health_only")

    def test_exposes_expired_fact_as_unknown_without_erasing_it(self) -> None:
        store = ContextFactStore()
        store.materialize(observation(), freshness_seconds=60)

        fact = store.query(
            now="2026-08-23T10:02:00Z",
            fact_ids=["edge-1/camera.person_presence.v1"],
        )[0]

        self.assertEqual(fact.disposition, "unknown")
        self.assertEqual(fact.value, {"state": "unknown"})
