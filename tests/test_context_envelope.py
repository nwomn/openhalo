from __future__ import annotations

import unittest

from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.context_envelope import ContextEnvelopeCompiler
from personal_runtime.context_facts import ContextFactStore


class ContextEnvelopeCompilerTests(unittest.TestCase):
    def test_changes_are_prioritized_and_bounded(self) -> None:
        store = ContextFactStore()
        for index in range(40):
            store.materialize(
                RuntimeObservation(
                    name=f"sensor.{index}",
                    value={"value": index},
                    source_device_id="edge-1",
                    source_capability="sensor",
                    source_event_id=f"event-{index}",
                    observed_at="2026-08-23T10:00:00Z",
                    confidence=1.0,
                ),
                freshness_seconds=600,
            )

        envelope = ContextEnvelopeCompiler().compile(
            facts=store.query(now="2026-08-23T10:00:01Z"),
            processed_version=35,
            now="2026-08-23T10:00:01Z",
        )

        self.assertEqual(envelope.context_version, 40)
        self.assertEqual(len(envelope.facts), 32)
        self.assertEqual(
            [fact["version"] for fact in envelope.changed_facts],
            [40, 39, 38, 37, 36],
        )
        self.assertEqual(len(envelope.fact_sources), 40)

    def test_structural_and_unknown_facts_are_reported_as_uncertainty(self) -> None:
        store = ContextFactStore()
        store.materialize(
            RuntimeObservation(
                name="mobile.screen_context",
                value={"sensitivity": "blocked", "capture_mode": "health_only"},
                source_device_id="phone-1",
                source_capability="mobile.context",
                source_event_id="screen-1",
                observed_at="2026-08-23T10:00:00Z",
                confidence=1.0,
            ),
            freshness_seconds=1,
        )

        envelope = ContextEnvelopeCompiler().compile(
            facts=store.query(now="2026-08-23T10:00:02Z"),
            processed_version=0,
            now="2026-08-23T10:00:02Z",
        )

        self.assertEqual(envelope.facts[0]["value"], {"state": "unknown"})
        self.assertEqual(envelope.uncertainty[0]["reason"], "stale")
