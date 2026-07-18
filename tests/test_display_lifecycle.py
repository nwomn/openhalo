import unittest

from personal_runtime.display_lifecycle import DisplayLifecycle


class DisplayLifecycleTests(unittest.TestCase):
    def test_projects_safe_sequenced_progress_for_one_interaction(self) -> None:
        lifecycle = DisplayLifecycle()

        first = lifecycle.advance(
            interaction_id="interaction-1",
            interaction_turn_id="interaction-turn-1",
            phase="deliberating",
            state="active",
            occurred_at="2026-07-18T10:00:00Z",
            presentation_hint="working",
        )
        second = lifecycle.advance(
            interaction_id="interaction-1",
            interaction_turn_id="interaction-turn-1",
            phase="planning",
            state="active",
            occurred_at="2026-07-18T10:00:01Z",
            presentation_hint="working",
        )

        self.assertEqual(first["sequence"], 1)
        self.assertEqual(second["sequence"], 2)
        self.assertEqual(second["phase"], "planning")
        self.assertEqual(
            set(second),
            {
                "version",
                "interaction_id",
                "interaction_turn_id",
                "sequence",
                "phase",
                "state",
                "occurred_at",
                "presentation_hint",
            },
        )

    def test_rejects_an_unsupported_public_phase(self) -> None:
        lifecycle = DisplayLifecycle()

        with self.assertRaisesRegex(ValueError, "unsupported progress phase"):
            lifecycle.advance(
                interaction_id="interaction-1",
                interaction_turn_id="interaction-turn-1",
                phase="raw_tool_output",
                state="active",
                occurred_at="2026-07-18T10:00:00Z",
                presentation_hint="working",
            )

    def test_rejects_a_free_text_presentation_hint(self) -> None:
        lifecycle = DisplayLifecycle()

        with self.assertRaisesRegex(ValueError, "unsupported presentation hint"):
            lifecycle.advance(
                interaction_id="interaction-1",
                interaction_turn_id="interaction-turn-1",
                phase="executing",
                state="active",
                occurred_at="2026-07-18T10:00:00Z",
                presentation_hint="tool args: secret=value",
            )
