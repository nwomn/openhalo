import unittest

from personal_runtime.prompt_context import (
    PROMPT_CONTEXT_VERSION,
    build_behavior_contract,
    build_prompt_context_package,
)
from personal_runtime.runtime_memory import build_model_grounding_bundle
from personal_runtime.runtime_state import RuntimeState


class PromptContextTests(unittest.TestCase):
    def test_build_prompt_context_package_exposes_version_and_grounded_sections(self) -> None:
        state = RuntimeState()
        state.upsert_goal(
            goal_id="goal-1",
            title="Keep runtime healthy",
            status="active",
            summary="Watch runtime health signals.",
            updated_at="2026-06-23T10:00:00Z",
        )
        state.events.append(
            {
                "type": "event_push",
                "device_id": "terminal-edge-1",
                "capability": "text.input",
                "payload": {
                    "text": "hello runtime",
                    "observed_at": "2026-06-23T10:01:00Z",
                },
            }
        )
        state.record_intervention(
            {
                "target_device_id": "terminal-edge-1",
                "action_capability": "notification.show",
                "decision": "allow",
                "reason": "context_clear",
                "proposal": {
                    "source": "sense_first",
                    "action_capability": "notification.show",
                    "message": "hello runtime",
                },
                "recorded_at": "2026-06-23T10:01:10Z",
            }
        )
        state.record_action_result(
            {
                "status": "ok",
                "capability": "notification.show",
                "details": {
                    "title": "OpenHalo",
                    "body": "Runtime heard: hello runtime",
                },
            }
        )
        grounding = build_model_grounding_bundle(
            state=state,
            snapshot={"runtime.current_health_state": "healthy"},
            edge_history={
                "history_kind": "observation_window",
                "entries": [
                    {
                        "capability": "runtime.health",
                        "observed_at": "2026-06-23T10:00:30Z",
                        "observations": [
                            {
                                "name": "runtime.health_state",
                                "value": "healthy",
                                "confidence": 1.0,
                            }
                        ],
                    }
                ],
                "returned_entries": 1,
                "available_entries": 2,
            },
        )

        package = build_prompt_context_package(
            user_text="hello runtime",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding_bundle=grounding,
        )

        self.assertEqual(package["version"], PROMPT_CONTEXT_VERSION)
        self.assertEqual(package["user_text"], "hello runtime")
        self.assertEqual(
            package["sections"]["compact_snapshot"]["runtime.current_health_state"],
            "healthy",
        )
        self.assertEqual(len(package["sections"]["active_goals"]), 1)
        self.assertEqual(
            package["sections"]["active_goals"][0]["goal_id"],
            "goal-1",
        )
        self.assertEqual(
            len(package["sections"]["recent_memory"]["user_inputs"]),
            1,
        )
        self.assertEqual(
            package["sections"]["edge_evidence"]["returned_entries"],
            1,
        )

    def test_build_behavior_contract_reports_required_grounding_checks(self) -> None:
        package = build_prompt_context_package(
            user_text="hello runtime",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding_bundle={
                "bundle_version": "m10.v1",
                "active_goals": [
                    {
                        "goal_id": "goal-1",
                        "title": "Keep runtime healthy",
                        "status": "active",
                        "summary": "Watch runtime health signals.",
                        "updated_at": "2026-06-23T10:00:00Z",
                    }
                ],
                "recent_memory": {
                    "user_inputs": [{"text": "hello runtime"}],
                    "interventions": [{"message": "hello runtime"}],
                    "action_results": [{"message": "Runtime heard: hello runtime"}],
                },
                "edge_history": {
                    "history_kind": "observation_window",
                    "entries": [{"capability": "runtime.health"}],
                    "returned_entries": 1,
                    "available_entries": 2,
                },
            },
        )

        contract = build_behavior_contract(
            prompt_context_package=package,
            grounding_bundle={
                "bundle_version": "m10.v1",
                "active_goals": package["sections"]["active_goals"],
                "recent_memory": package["sections"]["recent_memory"],
                "edge_history": package["sections"]["edge_evidence"],
            },
        )

        self.assertEqual(contract["prompt_context_version"], PROMPT_CONTEXT_VERSION)
        self.assertTrue(contract["checks"]["compact_snapshot_present"]["ok"])
        self.assertTrue(contract["checks"]["active_goals_present"]["ok"])
        self.assertTrue(contract["checks"]["recent_memory_present"]["ok"])
        self.assertTrue(contract["checks"]["edge_evidence_present"]["ok"])
        self.assertTrue(contract["checks"]["grounding_bundle_version_matches"]["ok"])
        self.assertEqual(
            contract["allowed_proposal_types"],
            ["action", "no_intervention", "provider_failure"],
        )
        self.assertEqual(
            contract["required_runtime_inputs"],
            ["compact_snapshot", "grounding_bundle"],
        )
        self.assertEqual(
            contract["action_governance"]["governed_action_route"],
            "presence_then_execution_planning",
        )

    def test_build_prompt_context_package_includes_explicit_harness_memory(self) -> None:
        package = build_prompt_context_package(
            user_text="status",
            snapshot={},
            grounding_bundle={},
            harness_memory={
                "working": {"operation": "normal"},
                "procedural": [{"memory_id": "procedure-1"}],
                "semantic": [{"memory_id": "fact-1"}],
                "episodic": [{"memory_id": "episode-1"}],
            },
        )

        self.assertEqual(
            package["sections"]["harness_memory"]["working"]["operation"],
            "normal",
        )
        self.assertEqual(
            package["sections"]["harness_memory"]["semantic"][0]["memory_id"],
            "fact-1",
        )


if __name__ == "__main__":
    unittest.main()
