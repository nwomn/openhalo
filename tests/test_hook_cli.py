import json
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_guard import codex_hooks


class HookCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("/root/personal-runtime-agent")

    def run_main(self, event: str, payload: dict) -> int:
        with patch("sys.stdin.read", return_value=json.dumps(payload)):
            return codex_hooks.main([event, str(self.root)])

    def test_session_start_creates_state(self) -> None:
        with patch("agent_guard.codex_hooks.save_state") as save_state:
            exit_code = self.run_main("SessionStart", {"session_id": "session-1"})

        self.assertEqual(exit_code, 0)
        save_state.assert_called_once()

    def test_stop_blocks_when_audit_footer_is_missing(self) -> None:
        state = codex_hooks.SessionState(
            session_id="session-1",
            project_hash_at_start=codex_hooks.hash_file(self.root / "Project.md"),
            project_read=True,
            turn_active=True,
        )
        with (
            patch("agent_guard.codex_hooks.load_state", return_value=state),
            patch("agent_guard.codex_hooks.save_state"),
        ):
            exit_code = self.run_main(
                "Stop",
                {"last_assistant_message": "No footer present", "stop_hook_active": False},
            )

        self.assertEqual(exit_code, 0)

    def test_stop_blocks_when_project_changes_without_internal_audit(self) -> None:
        state = codex_hooks.SessionState(
            session_id="session-1",
            project_hash_at_start="before",
            project_read=True,
            turn_active=True,
        )
        with (
            patch("agent_guard.codex_hooks.load_state", return_value=state),
            patch("agent_guard.codex_hooks.hash_file", return_value="after"),
        ):
            exit_code = self.run_main(
                "Stop",
                {"last_assistant_message": "Changed Project.md but did not report it."},
            )

        self.assertNotEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
