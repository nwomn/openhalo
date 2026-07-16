import unittest

from personal_runtime.model_provider import ProposalPlan
from personal_runtime.proposal_harness import build_proposal_harness_case
from personal_runtime.proposal_harness import build_post_action_prompt_variant
from personal_runtime.proposal_harness import classify_proposal_outcome
from personal_runtime.proposal_harness import compare_prompt_variants
from personal_runtime.proposal_harness import load_harness_cases_from_runtime_state
from personal_runtime.proposal_harness import replay_proposal_harness_cases
from personal_runtime.proposal_harness import replay_prompt_variants_with_provider


class ProposalHarnessTests(unittest.TestCase):
    def test_build_case_preserves_prompt_context_without_provider_secret(self) -> None:
        case = build_proposal_harness_case(
            case_id="m17-6-phone-ack-1",
            scenario="terminal_to_phone_post_action_ack",
            phase="post_action",
            prompt_context_package={
                "version": "m12.v1",
                "user_text": "send hello to my phone",
                "sections": {"compact_snapshot": {"runtime.current_health_state": "healthy"}},
            },
            interaction={
                "interaction_id": "interaction-1",
                "source_device_id": "terminal-edge-1",
                "initiator_kind": "explicit_user_intent",
                "requesting_device_id": "terminal-edge-1",
                "outcome_delivery_required": True,
                "participant_device_ids": ["terminal-edge-1", "android-edge-1"],
                "primary_action": {"target_device_id": "android-edge-1"},
            },
            prior_proposal={"proposal_type": "action", "action_capability": "notification.show"},
            action_result={
                "status": "ok",
                "capability": "notification.show",
                "details": {
                    "title": "OpenHalo",
                    "body": "hello",
                    "provider_api_key": "secret",
                },
            },
            expected={
                "source_device_id": "terminal-edge-1",
                "requires_source_ack": True,
                "correct_action_capability": "notification.show",
            },
            provider_config={"api_key": "secret", "model": "gpt-test"},
        )

        self.assertEqual(case["case_id"], "m17-6-phone-ack-1")
        self.assertEqual(case["phase"], "post_action")
        self.assertEqual(case["prompt_context_package"]["version"], "m12.v1")
        self.assertEqual(case["expected"]["requires_source_ack"], True)
        rendered = repr(case)
        self.assertNotIn("secret", rendered)
        self.assertIn("redacted", rendered)

    def test_builds_post_action_decision_brief_variant_from_same_case(self) -> None:
        case = {
            "interaction": {
                "interaction_id": "interaction-1",
                "source_device_id": "terminal-edge-1",
                "initiator_kind": "explicit_user_intent",
                "requesting_device_id": "terminal-edge-1",
                "outcome_delivery_required": True,
                "participant_device_ids": ["terminal-edge-1", "android-edge-1"],
                "primary_action": {"target_device_id": "android-edge-1"},
            },
            "prior_proposal": {
                "proposal_type": "action",
                "action_capability": "notification.show",
            },
            "action_result": {
                "status": "ok",
                "capability": "notification.show",
                "details": {"title": "OpenHalo", "body": "hello"},
            },
        }

        raw_json_prompt = build_post_action_prompt_variant(case, variant="raw_json")
        decision_brief_prompt = build_post_action_prompt_variant(
            case,
            variant="decision_brief",
        )

        self.assertIn('"trigger": "action_result"', raw_json_prompt)
        self.assertIn("Decision task:", decision_brief_prompt)
        self.assertIn("source_device_id: terminal-edge-1", decision_brief_prompt)
        self.assertIn("target_device_id: android-edge-1", decision_brief_prompt)
        self.assertIn("source_outcome_required: true", decision_brief_prompt)
        self.assertIn("provider_failure_observed: false", decision_brief_prompt)
        self.assertIn("Evidence appendix:", decision_brief_prompt)

    def test_classifies_missing_source_ack_after_successful_phone_action(self) -> None:
        outcome = classify_proposal_outcome(
            case={
                "expected": {
                    "source_device_id": "terminal-edge-1",
                    "requires_source_ack": True,
                    "correct_action_capability": "notification.show",
                }
            },
            proposal=ProposalPlan(
                proposal_type="no_intervention",
                response_text="",
                action_capability=None,
                action_payload={},
                metadata={},
            ),
        )

        self.assertEqual(outcome["classification"], "semantically_incomplete")
        self.assertEqual(outcome["reason"], "source_ack_missing")
        self.assertFalse(outcome["correct"])

    def test_classifies_provider_error_notification_as_failure_containment_gap(self) -> None:
        outcome = classify_proposal_outcome(
            case={
                "action_result": {
                    "status": "ok",
                    "capability": "notification.show",
                    "details": {
                        "title": "OpenHalo",
                        "body": (
                            "Real model reply unavailable: provider returned an "
                            "incompatible response shape; please retry shortly"
                        )
                    },
                },
                "expected": {
                    "requires_source_ack": False,
                    "correct_action_capability": "notification.show",
                },
            },
            proposal=ProposalPlan(
                proposal_type="action",
                response_text=(
                    "Real model reply unavailable: provider returned an "
                    "incompatible response shape; please retry shortly"
                ),
                action_capability="notification.show",
                action_payload={},
                metadata={},
            ),
        )

        self.assertEqual(outcome["classification"], "validation_failure")
        self.assertEqual(outcome["reason"], "provider_error_routed_as_normal_action")

    def test_classifies_contained_provider_error_as_correct(self) -> None:
        outcome = classify_proposal_outcome(
            case={
                "action_result": {
                    "status": "ok",
                    "capability": "notification.show",
                    "details": {
                        "title": "OpenHalo",
                        "body": (
                            "Real model reply unavailable: provider returned an "
                            "incompatible response shape; please retry shortly"
                        )
                    },
                },
                "expected": {"requires_source_ack": False},
            },
            proposal=ProposalPlan(
                proposal_type="provider_failure",
                response_text=(
                    "I hit a model-provider issue while handling that step. "
                    "Please retry shortly."
                ),
                action_capability=None,
                action_payload={},
                metadata={
                    "runtime_message_channel": "provider_failure",
                    "provider_failure_observed": True,
                    "provider_failure_contained": True,
                    "provider_failure_class": "protocol_shape",
                },
            ),
        )

        self.assertEqual(outcome["classification"], "correct")
        self.assertEqual(outcome["reason"], "provider_failure_contained")
        self.assertTrue(outcome["correct"])

    def test_replay_summarizes_success_rate_and_failure_classes(self) -> None:
        cases = [
            {
                "case_id": "missing-ack",
                "expected": {
                    "requires_source_ack": True,
                    "source_device_id": "terminal-edge-1",
                    "correct_action_capability": "notification.show",
                },
            },
            {
                "case_id": "correct-ack",
                "expected": {
                    "requires_source_ack": True,
                    "source_device_id": "terminal-edge-1",
                    "correct_action_capability": "notification.show",
                },
            },
        ]

        def runner(case):
            if case["case_id"] == "missing-ack":
                return ProposalPlan(
                    proposal_type="no_intervention",
                    response_text="",
                    action_capability=None,
                    action_payload={},
                    metadata={},
                )
            return ProposalPlan(
                proposal_type="action",
                response_text="Delivered hello to your phone.",
                action_capability="notification.show",
                action_payload={
                    "title": "OpenHalo",
                    "body": "Delivered hello to your phone.",
                },
                metadata={},
            )

        report = replay_proposal_harness_cases(cases, runner)

        self.assertEqual(report["total_cases"], 2)
        self.assertEqual(report["correct_cases"], 1)
        self.assertEqual(report["success_rate"], 0.5)
        self.assertEqual(report["classifications"]["correct"], 1)
        self.assertEqual(report["classifications"]["semantically_incomplete"], 1)

    def test_compare_prompt_variants_reports_success_rate_per_variant(self) -> None:
        cases = [
            {
                "case_id": "terminal-phone-ack",
                "expected": {
                    "requires_source_ack": True,
                    "source_device_id": "terminal-edge-1",
                    "correct_action_capability": "notification.show",
                },
            }
        ]

        def raw_runner(case):
            return ProposalPlan(
                proposal_type="no_intervention",
                response_text="",
                action_capability=None,
                action_payload={},
                metadata={},
            )

        def brief_runner(case):
            return ProposalPlan(
                proposal_type="action",
                response_text="Delivered hello to your phone.",
                action_capability="notification.show",
                action_payload={
                    "title": "OpenHalo",
                    "body": "Delivered hello to your phone.",
                },
                metadata={},
            )

        report = compare_prompt_variants(
            cases,
            {
                "raw_json": raw_runner,
                "decision_brief": brief_runner,
            },
        )

        self.assertEqual(report["variants"]["raw_json"]["success_rate"], 0.0)
        self.assertEqual(
            report["variants"]["decision_brief"]["success_rate"],
            1.0,
        )
        self.assertEqual(report["best_variant"], "decision_brief")

    def test_loads_post_action_cases_from_runtime_state_payload(self) -> None:
        state = {
            "interventions": [
                {
                    "interaction_id": "interaction-1",
                    "proposal": {
                        "source": "post_action",
                        "proposal_type": "no_intervention",
                        "action_capability": None,
                        "metadata": {
                            "trigger": "action_result",
                            "source_device_id": "terminal-edge-1",
                            "previous_target_device_id": "android-edge-1",
                            "participant_device_ids": [
                                "terminal-edge-1",
                                "android-edge-1",
                            ],
                            "parent_proposal_type": "action",
                            "parent_action_capability": "notification.show",
                            "result_status": "ok",
                            "outcome_delivery": {
                                "initiator_kind": "explicit_user_intent",
                                "requesting_device_id": "terminal-edge-1",
                                "outcome_delivery_required": True,
                                "source_outcome_required": True,
                            },
                        },
                    },
                    "grounding_bundle": {"bundle_version": "m10.v1"},
                },
                {
                    "interaction_id": "interaction-2",
                    "proposal": {
                        "source": "post_action",
                        "proposal_type": "action",
                        "action_capability": "notification.show",
                        "metadata": {
                            "trigger": "action_result",
                            "source_device_id": "terminal-edge-1",
                            "previous_target_device_id": "android-edge-1",
                            "participant_device_ids": [
                                "terminal-edge-1",
                                "android-edge-1",
                            ],
                            "parent_proposal_type": "action",
                            "parent_action_capability": "notification.show",
                            "result_status": "ok",
                            "outcome_delivery": {
                                "initiator_kind": "explicit_user_intent",
                                "requesting_device_id": "terminal-edge-1",
                                "outcome_delivery_required": True,
                                "source_outcome_required": True,
                            },
                            "provider_failure_class": "protocol_shape",
                        },
                    },
                    "grounding_bundle": {"bundle_version": "m10.v1"},
                },
            ]
        }

        cases = load_harness_cases_from_runtime_state(state)

        self.assertEqual(len(cases), 2)
        self.assertEqual(cases[0]["case_id"], "runtime-state:interaction-1:0")
        self.assertTrue(cases[0]["expected"]["requires_source_ack"])
        self.assertEqual(
            cases[0]["interaction"]["primary_action"]["target_device_id"],
            "android-edge-1",
        )
        self.assertEqual(
            cases[1]["observed_proposal"]["metadata"]["provider_failure_class"],
            "protocol_shape",
        )

    def test_replays_prompt_variants_through_provider_runner(self) -> None:
        cases = [
            {
                "case_id": "terminal-phone-ack",
                "interaction": {
                    "interaction_id": "interaction-1",
                    "source_device_id": "terminal-edge-1",
                    "primary_action": {"target_device_id": "android-edge-1"},
                },
                "prior_proposal": {
                    "proposal_type": "action",
                    "action_capability": "notification.show",
                },
                "action_result": {
                    "status": "ok",
                    "capability": "notification.show",
                    "details": {"title": "OpenHalo", "body": "hello"},
                },
                "prompt_context_package": {
                    "sections": {
                        "compact_snapshot": {},
                        "recent_memory": {},
                        "active_goals": [],
                        "edge_evidence": {},
                    }
                },
                "expected": {
                    "requires_source_ack": True,
                    "source_device_id": "terminal-edge-1",
                    "correct_action_capability": "notification.show",
                },
            }
        ]

        def transport(provider, request_payload, api_key, headers):
            rendered = repr(request_payload)
            if "Decision task:" in rendered:
                text = (
                    '{"proposal_type":"action",'
                    '"response_text":"Delivered hello to your phone.",'
                    '"action":{"capability":"notification.show","payload":{}},'
                    '"rationale":{"summary":"ack source",'
                    '"intent_signals":["source ack"],'
                    '"grounding_signals":["decision brief"]}}'
                )
            else:
                text = (
                    '{"proposal_type":"no_intervention",'
                    '"response_text":"",'
                    '"action":null,'
                    '"rationale":{"summary":"target already visible",'
                    '"intent_signals":["target done"],'
                    '"grounding_signals":["raw json"]}}'
                )
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": text}],
                    }
                ]
            }

        report = replay_prompt_variants_with_provider(
            cases,
            config_path="tests/fixtures/llm-config-visible-error-test.toml",
            transport=transport,
        )

        self.assertEqual(report["variants"]["raw_json"]["success_rate"], 0.0)
        self.assertEqual(
            report["variants"]["decision_brief"]["success_rate"],
            1.0,
        )
        self.assertEqual(report["best_variant"], "decision_brief")


if __name__ == "__main__":
    unittest.main()
