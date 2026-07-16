import unittest

from personal_runtime.agent_executor import InterventionProposal
from personal_runtime.agent_harness import ActionExecutorKind
from personal_runtime.agent_harness import ActionGovernance
from personal_runtime.agent_harness import ActionSideEffect
from personal_runtime.agent_harness import ActionVisibility
from personal_runtime.agent_harness import HarnessInput
from personal_runtime.agent_harness import LegacyProposalHarness
from personal_runtime.agent_harness import HarnessOperation
from personal_runtime.agent_harness import HarnessOutcome


class AgentHarnessContractTests(unittest.TestCase):
    def test_normal_input_preserves_runtime_lineage_and_grounding(self) -> None:
        harness_input = HarnessInput(
            operation=HarnessOperation.NORMAL,
            interaction_id="interaction-7",
            interaction_turn_id="interaction-turn-3",
            frame={"device_id": "terminal-edge-1", "payload": {"text": "status"}},
            snapshot={"terminal": {"activity": "active"}},
            grounding_bundle={"active_goals": [{"goal": "report status"}]},
            correlation={"trace_id": "trace-7"},
        )

        self.assertEqual(harness_input.operation, HarnessOperation.NORMAL)
        self.assertEqual(harness_input.interaction_id, "interaction-7")
        self.assertEqual(harness_input.frame["device_id"], "terminal-edge-1")
        self.assertEqual(
            harness_input.grounding_bundle["active_goals"][0]["goal"],
            "report status",
        )
        self.assertEqual(harness_input.correlation["trace_id"], "trace-7")

    def test_proposal_outcome_declares_action_intent_without_execution(self) -> None:
        proposal = InterventionProposal(
            kind="notification",
            proposal_type="action",
            source="agent",
            action_capability="notification.show",
            required_capability="notification.show",
            action_payload={"title": "OpenHalo", "body": "Runtime is healthy"},
            message="Runtime is healthy",
            metadata={"provider": "deterministic"},
        )

        outcome = HarnessOutcome.from_proposal(
            operation=HarnessOperation.NORMAL,
            proposal=proposal,
            metadata={"runner": "legacy"},
        )

        self.assertEqual(outcome.intent, "action")
        self.assertIs(outcome.proposal, proposal)
        self.assertEqual(outcome.metadata["runner"], "legacy")
        self.assertFalse(outcome.executed)

    def test_legacy_adapter_delegates_normal_input_without_executing_action(self) -> None:
        proposal = InterventionProposal(
            kind="notification",
            proposal_type="action",
            source="agent",
            action_capability="notification.show",
            required_capability="notification.show",
            action_payload={"title": "OpenHalo", "body": "Runtime is healthy"},
            message="Runtime is healthy",
            metadata={"provider": "deterministic"},
        )

        class CapturingProposalFormation:
            def __init__(self) -> None:
                self.calls = []

            def build_normal_path_proposal(
                self,
                frame: dict,
                snapshot: dict,
                grounding_bundle: dict,
                correlation: dict,
            ) -> InterventionProposal:
                self.calls.append(
                    {
                        "frame": frame,
                        "snapshot": snapshot,
                        "grounding_bundle": grounding_bundle,
                        "correlation": correlation,
                    }
                )
                return proposal

        proposal_formation = CapturingProposalFormation()
        runner = LegacyProposalHarness(lambda: proposal_formation)
        harness_input = HarnessInput(
            operation=HarnessOperation.NORMAL,
            interaction_id="interaction-8",
            interaction_turn_id="interaction-turn-4",
            frame={"device_id": "terminal-edge-1", "payload": {"text": "status"}},
            snapshot={"terminal": {"activity": "active"}},
            grounding_bundle={"active_goals": [{"goal": "report status"}]},
            correlation={"trace_id": "trace-8"},
        )

        outcome = runner.run(harness_input)

        self.assertEqual(len(proposal_formation.calls), 1)
        self.assertEqual(
            proposal_formation.calls[0]["frame"]["device_id"],
            "terminal-edge-1",
        )
        self.assertEqual(outcome.intent, "action")
        self.assertIs(outcome.proposal, proposal)
        self.assertEqual(outcome.metadata["runner"], "legacy_proposal_formation")
        self.assertIsNotNone(outcome.action_intent)
        self.assertEqual(
            outcome.action_intent.action_id,
            "legacy:interaction-turn-4",
        )
        self.assertEqual(
            outcome.action_intent.executor_kind,
            ActionExecutorKind.DEVICE_EDGE,
        )
        self.assertEqual(
            outcome.action_intent.side_effect_class,
            ActionSideEffect.EXTERNAL,
        )
        self.assertEqual(
            outcome.action_intent.visibility,
            ActionVisibility.USER_VISIBLE,
        )
        self.assertEqual(
            outcome.action_intent.governance,
            ActionGovernance.RUNTIME_GOVERNED,
        )
        self.assertEqual(
            outcome.action_intent.provenance["origin"],
            "legacy_proposal_formation",
        )
        self.assertEqual(
            outcome.action_intent.provenance["operation"],
            "normal",
        )
        self.assertEqual(
            outcome.action_intent.provenance["interaction_id"],
            "interaction-8",
        )
        self.assertEqual(
            outcome.action_intent.provenance["interaction_turn_id"],
            "interaction-turn-4",
        )
        self.assertEqual(
            outcome.action_intent.provenance["proposal_source"],
            "agent",
        )
        self.assertEqual(
            outcome.action_intent.provenance["trusted_user_intent"]["kind"],
            "normal_user_request",
        )
        self.assertFalse(outcome.executed)

    def test_legacy_adapter_delegates_post_action_input(self) -> None:
        proposal = InterventionProposal(
            kind="no_intervention",
            proposal_type="no_intervention",
            source="agent",
            action_capability=None,
            required_capability=None,
            action_payload={},
            message="Action result needs no follow-up",
            metadata={},
        )

        class CapturingProposalFormation:
            def __init__(self) -> None:
                self.call = None

            def build_post_action_proposal(self, **kwargs) -> InterventionProposal:
                self.call = kwargs
                return proposal

        proposal_formation = CapturingProposalFormation()
        runner = LegacyProposalHarness(lambda: proposal_formation)
        harness_input = HarnessInput(
            operation=HarnessOperation.POST_ACTION,
            interaction_id="interaction-9",
            interaction_turn_id="interaction-turn-5",
            interaction={"interaction_id": "interaction-9"},
            prior_proposal={"proposal_type": "action"},
            action_result={"status": "completed"},
            turn_index=2,
            snapshot={"runtime": {"health": "healthy"}},
            grounding_bundle={"recent_action_results": [{"status": "completed"}]},
            correlation={"trace_id": "trace-9"},
        )

        outcome = runner.run(harness_input)

        self.assertEqual(proposal_formation.call["interaction"]["interaction_id"], "interaction-9")
        self.assertEqual(proposal_formation.call["result"]["status"], "completed")
        self.assertEqual(proposal_formation.call["turn_index"], 2)
        self.assertEqual(outcome.intent, "no_intervention")
        self.assertFalse(outcome.executed)

    def test_legacy_adapter_delegates_post_observation_input(self) -> None:
        proposal = InterventionProposal(
            kind="no_intervention",
            proposal_type="no_intervention",
            source="agent",
            action_capability=None,
            required_capability=None,
            action_payload={},
            message="Observation needs no follow-up",
            metadata={},
        )

        class CapturingProposalFormation:
            def __init__(self) -> None:
                self.call = None

            def build_post_observation_proposal(self, **kwargs) -> InterventionProposal:
                self.call = kwargs
                return proposal

        proposal_formation = CapturingProposalFormation()
        runner = LegacyProposalHarness(lambda: proposal_formation)
        harness_input = HarnessInput(
            operation=HarnessOperation.POST_OBSERVATION,
            interaction_id="interaction-10",
            interaction_turn_id="interaction-turn-6",
            interaction={"interaction_id": "interaction-10"},
            prior_proposal={"proposal_type": "action"},
            observations=[{"name": "runtime.health_state", "value": "healthy"}],
            turn_index=3,
            snapshot={"runtime": {"health": "healthy"}},
            grounding_bundle={"edge_evidence": []},
            correlation={"trace_id": "trace-10"},
        )

        outcome = runner.run(harness_input)

        self.assertEqual(proposal_formation.call["interaction"]["interaction_id"], "interaction-10")
        self.assertEqual(proposal_formation.call["observations"][0]["value"], "healthy")
        self.assertEqual(proposal_formation.call["turn_index"], 3)
        self.assertEqual(outcome.intent, "no_intervention")
        self.assertFalse(outcome.executed)

    def test_legacy_adapter_delegates_observation_driven_input(self) -> None:
        proposal = InterventionProposal(
            kind="notification",
            proposal_type="action",
            source="agent",
            action_capability="notification.show",
            required_capability="notification.show",
            action_payload={"title": "OpenHalo", "body": "Runtime needs attention"},
            message="Runtime needs attention",
            metadata={},
        )

        class CapturingProposalFormation:
            def __init__(self) -> None:
                self.call = None

            def build_observation_driven_proposal(self, **kwargs) -> InterventionProposal:
                self.call = kwargs
                return proposal

        proposal_formation = CapturingProposalFormation()
        runner = LegacyProposalHarness(lambda: proposal_formation)
        harness_input = HarnessInput(
            operation=HarnessOperation.OBSERVATION_DRIVEN,
            interaction_id="interaction-11",
            interaction_turn_id="interaction-turn-7",
            interaction={"interaction_id": "interaction-11"},
            admission={"reason_code": "runtime_degraded"},
            observations=[{"name": "runtime.health_state", "value": "degraded"}],
            turn_index=1,
            snapshot={"runtime": {"health": "degraded"}},
            grounding_bundle={"edge_evidence": []},
            correlation={"trace_id": "trace-11"},
        )

        outcome = runner.run(harness_input)

        self.assertEqual(proposal_formation.call["admission"]["reason_code"], "runtime_degraded")
        self.assertEqual(proposal_formation.call["observations"][0]["value"], "degraded")
        self.assertEqual(proposal_formation.call["turn_index"], 1)
        self.assertEqual(outcome.intent, "action")
        self.assertFalse(outcome.executed)


if __name__ == "__main__":
    unittest.main()
