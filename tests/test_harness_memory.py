import unittest

from personal_runtime.agent_harness import HarnessInput
from personal_runtime.agent_harness import HarnessOperation
from personal_runtime.agent_harness import HarnessOutcome
from personal_runtime.agent_executor import InterventionProposal
from personal_runtime.harness_memory import MemoryKind
from personal_runtime.harness_memory import build_harness_memory_context
from personal_runtime.harness_memory import build_memory_consolidation_candidate
from personal_runtime.runtime_state import RuntimeState


class HarnessMemoryTests(unittest.TestCase):
    def test_builds_explicit_memory_context_without_promoting_working_memory(self):
        state = RuntimeState()
        state.record_harness_memory(
            MemoryKind.PROCEDURAL,
            memory_id="procedure-1",
            content={"instruction": "Use notification.show for terminal delivery."},
            source_refs=["docs/m20"],
            recorded_at="2026-07-15T10:00:00Z",
        )
        state.record_harness_memory(
            MemoryKind.SEMANTIC,
            memory_id="fact-1",
            content={"fact": "User prefers concise terminal notices."},
            source_refs=["interaction-4"],
            recorded_at="2026-07-15T10:01:00Z",
        )
        state.record_harness_memory(
            MemoryKind.EPISODIC,
            memory_id="episode-1",
            content={"summary": "runtime.status completed"},
            source_refs=["interaction-5"],
            recorded_at="2026-07-15T10:02:00Z",
        )

        context = build_harness_memory_context(
            state=state,
            interaction_id="interaction-6",
            interaction_turn_id="interaction-turn-2",
            working_memory={"current_goal": "report status"},
        )

        self.assertEqual(context["working"]["current_goal"], "report status")
        self.assertEqual(context["procedural"][0]["memory_id"], "procedure-1")
        self.assertEqual(context["semantic"][0]["memory_id"], "fact-1")
        self.assertEqual(context["episodic"][0]["memory_id"], "episode-1")
        self.assertNotIn("working", state.harness_memory)

    def test_consolidation_candidate_is_review_required_and_keeps_lineage(self):
        harness_input = HarnessInput(
            operation=HarnessOperation.POST_ACTION,
            interaction_id="interaction-7",
            interaction_turn_id="interaction-turn-3",
            action_result={
                "request_id": "request-7",
                "capability": "notification.show",
                "status": "ok",
            },
            working_memory={"current_goal": "notify user"},
        )
        outcome = HarnessOutcome.from_proposal(
            operation=HarnessOperation.POST_ACTION,
            proposal=InterventionProposal(
                kind="no_intervention",
                proposal_type="no_intervention",
                source="legacy_proposal_formation",
                action_capability=None,
                required_capability=None,
                action_payload={},
                message="",
                metadata={"harness_backend": "legacy_proposal_formation"},
                visibility_intent="silent",
            ),
            metadata={"runner": "legacy_proposal_formation"},
        )

        candidate = build_memory_consolidation_candidate(
            harness_input=harness_input,
            outcome=outcome,
            terminal_reason="complete",
        )

        self.assertEqual(candidate["review_status"], "review_required")
        self.assertEqual(candidate["interaction_id"], "interaction-7")
        self.assertEqual(candidate["interaction_turn_id"], "interaction-turn-3")
        self.assertEqual(candidate["source_action_result"]["request_id"], "request-7")
        self.assertEqual(candidate["memory_write_disposition"], "candidate_only")
