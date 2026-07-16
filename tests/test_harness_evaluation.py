import unittest
from types import SimpleNamespace

from personal_runtime.harness_evaluation import build_harness_trace
from personal_runtime.harness_evaluation import evaluate_harness_traces
from personal_runtime.harness_evaluation import gate_harness_promotion


class HarnessEvaluationTests(unittest.TestCase):
    def test_evaluates_trace_outcomes_and_blocks_unsafe_promotion(self):
        report = evaluate_harness_traces(
            [
                {
                    "interaction_id": "interaction-1",
                    "outcome_intent": "action",
                    "validation": {"decision": "allowed"},
                    "terminal_reason": "complete",
                },
                {
                    "interaction_id": "interaction-2",
                    "outcome_intent": "action",
                    "validation": {
                        "decision": "rejected",
                        "reason": "unregistered_action_capability",
                    },
                    "terminal_reason": "suppressed",
                },
            ]
        )

        self.assertEqual(report["total_traces"], 2)
        self.assertEqual(report["classifications"]["governance_rejected"], 1)
        self.assertFalse(gate_harness_promotion(report)["eligible"])

    def test_allows_promotion_only_for_complete_safe_traces(self):
        report = evaluate_harness_traces(
            [
                {
                    "interaction_id": "interaction-1",
                    "outcome_intent": "action",
                    "validation": {"decision": "allowed"},
                    "terminal_reason": "complete",
                },
                {
                    "interaction_id": "interaction-2",
                    "outcome_intent": "no_intervention",
                    "validation": {"decision": "not_applicable"},
                    "terminal_reason": "no_intervention",
                },
            ]
        )

        decision = gate_harness_promotion(report)

        self.assertTrue(decision["eligible"])
        self.assertEqual(decision["decision"], "review_required")

    def test_trace_keeps_only_sanitized_internal_and_memory_provenance(self):
        trace = build_harness_trace(
            harness_input=SimpleNamespace(
                interaction_id="interaction-1",
                interaction_turn_id="interaction-turn-1",
                operation=SimpleNamespace(value="normal"),
                working_memory={},
                procedural_memory=[],
                semantic_memory=[],
                episodic_memory=[],
            ),
            outcome=SimpleNamespace(
                metadata={
                    "runner": "hermes",
                    "durable_memory_engine": "hermes_native",
                    "internal_tool_events": [
                        {
                            "tool_name": "openhalo_web_fetch",
                            "url": "https://example.test/article",
                            "content_sha256": "a" * 64,
                            "content_chars": 12,
                            "untrusted": True,
                            "content": "never in a replay trace",
                        }
                    ],
                    "hermes_memory_events": [
                        {
                            "tool_call_id": "memory-call-1",
                            "task_id": "interaction-turn-1",
                            "action": "add",
                            "target": "user",
                            "content_sha256": "b" * 64,
                            "content": "never in a replay trace",
                        }
                    ],
                    "browser_proxy": {
                        "connect_count": 1,
                        "tunneled_bytes": 512,
                        "ignored": "not replay evidence",
                    },
                },
                intent="no_intervention",
            ),
            validation={"reason": None, "action_intent": None},
            terminal_reason="no_intervention",
        )

        self.assertEqual(trace["internal_tool_events"][0]["tool_name"], "openhalo_web_fetch")
        self.assertEqual(trace["hermes_memory_events"][0]["target"], "user")
        self.assertEqual(trace["durable_memory_engine"], "hermes_native")
        self.assertNotIn("browser_proxy", trace)
        self.assertNotIn("content", trace["internal_tool_events"][0])
        self.assertNotIn("content", trace["hermes_memory_events"][0])
        self.assertNotIn("never in a replay trace", str(trace))

    def test_rejects_untrusted_or_malformed_internal_tool_audits(self):
        untrusted_missing_audit = evaluate_harness_traces(
            [
                {
                    "interaction_id": "interaction-1",
                    "outcome_intent": "no_intervention",
                    "validation": {"decision": "not_applicable"},
                    "terminal_reason": "no_intervention",
                    "internal_tool_events": [
                        {"tool_name": "openhalo_web_fetch", "untrusted": True}
                    ],
                }
            ]
        )
        malformed_audit = evaluate_harness_traces(
            [
                {
                    "interaction_id": "interaction-2",
                    "outcome_intent": "no_intervention",
                    "validation": {"decision": "not_applicable"},
                    "terminal_reason": "no_intervention",
                    "internal_tool_events": [{"content_sha256": "a" * 64}],
                }
            ]
        )

        self.assertEqual(
            untrusted_missing_audit["classifications"],
            {"untrusted_internal_tool_missing_audit": 1},
        )
        self.assertFalse(gate_harness_promotion(untrusted_missing_audit)["eligible"])
        self.assertEqual(
            malformed_audit["classifications"],
            {"malformed_internal_tool_audit": 1},
        )
        self.assertFalse(gate_harness_promotion(malformed_audit)["eligible"])
