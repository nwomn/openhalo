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

    def test_post_tool_use_marks_edit_activity_for_apply_patch(self) -> None:
        state = codex_hooks.SessionState(
            session_id="session-1",
            project_hash_at_start=codex_hooks.hash_file(self.root / "Project.md"),
            project_read=True,
            turn_active=True,
        )
        with (
            patch("agent_guard.codex_hooks.load_state", return_value=state),
            patch("agent_guard.codex_hooks.save_state") as save_state,
        ):
            exit_code = self.run_main(
                "PostToolUse",
                {"tool_name": "functions.apply_patch"},
            )

        self.assertEqual(exit_code, 0)
        saved_state = save_state.call_args.args[1]
        self.assertTrue(saved_state.edit_activity_since_check)

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

    def test_stop_blocks_progress_update_without_required_goal_structure(self) -> None:
        state = codex_hooks.SessionState(
            session_id="session-1",
            project_hash_at_start=codex_hooks.hash_file(self.root / "Project.md"),
            project_read=True,
            turn_active=True,
            last_user_prompt="汇报一下进度",
        )
        with (
            patch("agent_guard.codex_hooks.load_state", return_value=state),
            patch("agent_guard.codex_hooks.save_state"),
        ):
            exit_code = self.run_main(
                "Stop",
                {"last_assistant_message": "这轮主要推进了 M5。"},
            )

        self.assertNotEqual(exit_code, 0)

    def test_stop_allows_progress_update_with_required_goal_structure(self) -> None:
        state = codex_hooks.SessionState(
            session_id="session-1",
            project_hash_at_start=codex_hooks.hash_file(self.root / "Project.md"),
            project_read=True,
            turn_active=True,
            last_user_prompt="汇报一下进度",
        )
        valid_message = """## Goal 1
状态：已完成
架构位置：系统总边界
本批完成：本轮无新的 Goal 1 变化。
对整体链路的作用：保持架构边界稳定。
还缺什么：无。

## Goal 2
状态：已完成
架构位置：核心抽象层
本批完成：本轮无新的 Goal 2 变化。
对整体链路的作用：保持抽象语义稳定。
还缺什么：无。

## Goal 3
状态：已完成
架构位置：实现路径规划
本批完成：本轮无新的 Goal 3 变化。
对整体链路的作用：保持里程碑顺序稳定。
还缺什么：无。

## Goal 4
状态：进行中
架构位置：runtime 主链路
本批完成：推进了新的实现切片。
对整体链路的作用：让当前里程碑继续收敛。
还缺什么：继续推进后续切片。"""
        with (
            patch("agent_guard.codex_hooks.load_state", return_value=state),
            patch("agent_guard.codex_hooks.save_state"),
        ):
            exit_code = self.run_main(
                "Stop",
                {"last_assistant_message": valid_message},
            )

        self.assertEqual(exit_code, 0)

    def test_stop_blocks_edited_turn_without_architecture_summary(self) -> None:
        state = codex_hooks.SessionState(
            session_id="session-1",
            project_hash_at_start=codex_hooks.hash_file(self.root / "Project.md"),
            project_read=True,
            turn_active=True,
            edit_activity_since_check=True,
        )
        with (
            patch("agent_guard.codex_hooks.load_state", return_value=state),
            patch("agent_guard.codex_hooks.save_state"),
        ):
            exit_code = self.run_main(
                "Stop",
                {"last_assistant_message": "这轮完成了一个新的实现切片。"},
            )

        self.assertNotEqual(exit_code, 0)

    def test_stop_allows_edited_turn_with_architecture_summary(self) -> None:
        state = codex_hooks.SessionState(
            session_id="session-1",
            project_hash_at_start=codex_hooks.hash_file(self.root / "Project.md"),
            project_read=True,
            turn_active=True,
            edit_activity_since_check=True,
        )
        valid_message = """架构实现小结:
- 架构位置: Backend / Personal Runtime -> State / Context -> Compact Context Snapshot Reducers
- 本步完成: 新增了一个新的 compact snapshot 字段。
- 影响链路: normalized observations -> compact snapshot -> Agent Runtime / Presence Router
"""
        with (
            patch("agent_guard.codex_hooks.load_state", return_value=state),
            patch("agent_guard.codex_hooks.save_state"),
        ):
            exit_code = self.run_main(
                "Stop",
                {"last_assistant_message": valid_message},
            )

        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
