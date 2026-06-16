import unittest
from pathlib import Path

from agent_guard.codex_hooks import (
    SessionState,
    TurnAudit,
    extract_project_phase,
    hash_file,
    parse_project_check,
    validate_turn_audit,
)


VALID_MESSAGE = """Implemented the requested change.

Project.md Check:
- meaningful: yes
- phase_changed: no
- architecture_changed: no
- milestone_changed: no
- subgoal_status_changed: no
- completed_work_changed: no
- acceptance_status_changed: no
- project_updated: no
- summary: No tracked project state changed in this interaction.
"""


class ParseProjectCheckTests(unittest.TestCase):
    def test_parses_footer_block(self) -> None:
        audit = parse_project_check(VALID_MESSAGE)

        self.assertEqual(
            audit,
            TurnAudit(
                meaningful=True,
                phase_changed=False,
                architecture_changed=False,
                milestone_changed=False,
                subgoal_status_changed=False,
                completed_work_changed=False,
                acceptance_status_changed=False,
                project_updated=False,
                summary="No tracked project state changed in this interaction.",
            ),
        )

    def test_returns_none_without_footer(self) -> None:
        self.assertIsNone(parse_project_check("No audit footer here."))


class ValidateTurnAuditTests(unittest.TestCase):
    def test_rejects_changed_project_state_without_project_update(self) -> None:
        audit = TurnAudit(
            meaningful=True,
            phase_changed=True,
            architecture_changed=False,
            milestone_changed=False,
            subgoal_status_changed=False,
            completed_work_changed=False,
            acceptance_status_changed=False,
            project_updated=False,
            summary="Phase changed but Project.md was not updated.",
        )

        error = validate_turn_audit(
            audit=audit,
            session=SessionState(session_id="s1", project_hash_at_start="before"),
            current_project_hash="before",
        )

        self.assertIn("Project.md must be updated", error)

    def test_rejects_claimed_project_update_without_hash_change(self) -> None:
        audit = TurnAudit(
            meaningful=True,
            phase_changed=False,
            architecture_changed=False,
            milestone_changed=False,
            subgoal_status_changed=False,
            completed_work_changed=False,
            acceptance_status_changed=False,
            project_updated=True,
            summary="Claimed Project.md update.",
        )

        error = validate_turn_audit(
            audit=audit,
            session=SessionState(session_id="s1", project_hash_at_start="same"),
            current_project_hash="same",
        )

        self.assertIn("claimed Project.md was updated", error)

    def test_rejects_project_hash_change_without_declared_update(self) -> None:
        audit = TurnAudit(
            meaningful=True,
            phase_changed=False,
            architecture_changed=False,
            milestone_changed=False,
            subgoal_status_changed=False,
            completed_work_changed=False,
            acceptance_status_changed=False,
            project_updated=False,
            summary="Forgot to declare the doc update.",
        )

        error = validate_turn_audit(
            audit=audit,
            session=SessionState(session_id="s1", project_hash_at_start="before"),
            current_project_hash="after",
        )

        self.assertIn("Project.md changed during this turn", error)

    def test_accepts_consistent_project_update(self) -> None:
        audit = TurnAudit(
            meaningful=True,
            phase_changed=False,
            architecture_changed=False,
            milestone_changed=True,
            subgoal_status_changed=False,
            completed_work_changed=False,
            acceptance_status_changed=False,
            project_updated=True,
            summary="Milestone definition changed and Project.md was updated.",
        )

        error = validate_turn_audit(
            audit=audit,
            session=SessionState(session_id="s1", project_hash_at_start="before"),
            current_project_hash="after",
        )

        self.assertIsNone(error)


class ProjectHelpersTests(unittest.TestCase):
    def test_extracts_current_phase(self) -> None:
        project_text = """## Current Project Progress

Current phase:

- Architecture framing and project setup
"""

        self.assertEqual(
            extract_project_phase(project_text),
            "Architecture framing and project setup",
        )

    def test_hash_file_is_stable(self) -> None:
        path = Path("/root/personal-runtime-agent/Project.md")

        self.assertEqual(hash_file(path), hash_file(path))


if __name__ == "__main__":
    unittest.main()
