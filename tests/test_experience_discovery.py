from __future__ import annotations

import unittest

from personal_runtime.experience_discovery import ExperienceDecision
from personal_runtime.experience_discovery import validate_experience_decision


class ExperienceDiscoveryTests(unittest.TestCase):
    def test_accepts_a_bounded_observe_more_decision(self) -> None:
        decision = validate_experience_decision(
            {
                "status": "observe_more",
                "reason": "need_recent_process_evidence",
                "fact_ids": ["terminal-1/coding.activity.v1"],
                "evidence_refs": ["coding-evidence://interaction-1/3"],
            }
        )

        self.assertEqual(decision.status, "observe_more")
        self.assertEqual(decision.evidence_refs, ["coding-evidence://interaction-1/3"])

    def test_rejects_unbounded_or_unknown_attention_output(self) -> None:
        with self.assertRaisesRegex(ValueError, "status"):
            validate_experience_decision({"status": "intervene"})
        with self.assertRaisesRegex(ValueError, "bounded"):
            validate_experience_decision(
                {
                    "status": "observe_more",
                    "reason": "too much",
                    "fact_ids": [f"fact-{index}" for index in range(17)],
                    "evidence_refs": [],
                }
            )
