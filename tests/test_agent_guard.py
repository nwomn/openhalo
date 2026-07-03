import unittest
from pathlib import Path

from agent_guard.codex_hooks import (
    REQUIRED_PROGRESS_LABELS,
    SessionState,
    TurnAudit,
    extract_project_phase,
    hash_file,
    is_project_progress_update_request,
    parse_project_check,
    validate_architecture_summary_response,
    validate_progress_update_response,
    validate_turn_audit,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


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

VALID_PROGRESS_MESSAGE = """## Goal 1
状态：已完成
架构位置：系统总边界与架构基线
本批完成：本轮没有新的 Goal 1 变更，继续沿用现有架构边界。
对整体链路的作用：保证后续实现仍然围绕既定 runtime 架构推进。
还缺什么：无新的 Goal 1 缺口。

## Goal 2
状态：已完成
架构位置：核心抽象与 context / presence 语义层
本批完成：本轮没有新的 Goal 2 变更，继续沿用现有抽象基线。
对整体链路的作用：保证 observation、snapshot、presence 的职责边界稳定。
还缺什么：无新的 Goal 2 缺口。

## Goal 3
状态：已完成
架构位置：实现路线与里程碑规划
本批完成：本轮没有新的 Goal 3 变更，继续沿用既定里程碑路线。
对整体链路的作用：保证当前实现仍按既定 M5 路线推进。
还缺什么：无新的 Goal 3 缺口。

## Goal 4
状态：进行中
架构位置：真实 runtime 主链路
本批完成：完成了本轮 runtime-ingestion 相关实现。
对整体链路的作用：让当前里程碑继续向端到端可运行路径收敛。
还缺什么：继续推进后续 M5 切片。
"""

VALID_ARCHITECTURE_SUMMARY = """架构实现小结:
- 架构位置: Backend / Personal Runtime -> State / Context -> Compact Context Snapshot Reducers
- 本步完成: 新增一个 freshness-aware compact snapshot 字段。
- 影响链路: normalized observations -> compact snapshot -> Agent Runtime / Presence Router
"""


VALID_PROGRESS_MESSAGE_WITH_GOAL5 = (
    VALID_PROGRESS_MESSAGE
    + "\n## Goal 5\n"
    + "\n".join(f"{label}: ok" for label in REQUIRED_PROGRESS_LABELS)
    + "\n"
)


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


class ProgressUpdateValidationTests(unittest.TestCase):
    def test_detects_chinese_project_progress_request(self) -> None:
        self.assertTrue(is_project_progress_update_request("汇报一下进度"))

    def test_accepts_valid_goal_structured_progress_update(self) -> None:
        self.assertIsNone(
            validate_progress_update_response(VALID_PROGRESS_MESSAGE_WITH_GOAL5)
        )

    def test_rejects_progress_update_missing_goal_section(self) -> None:
        invalid = VALID_PROGRESS_MESSAGE

        error = validate_progress_update_response(invalid)

        self.assertIn("Goal 5", error)

    def test_rejects_progress_update_missing_required_architecture_label(self) -> None:
        invalid = VALID_PROGRESS_MESSAGE_WITH_GOAL5.replace(
            f"{REQUIRED_PROGRESS_LABELS[1]}: ok", ""
        )
        error = validate_progress_update_response(invalid)
        self.assertIn(REQUIRED_PROGRESS_LABELS[1], error)
        return
        self.assertIn("鏋舵瀯浣嶇疆", error)
        return

        invalid = VALID_PROGRESS_MESSAGE.replace("架构位置：真实 runtime 主链路\n", "")

        error = validate_progress_update_response(invalid)

        self.assertIn("架构位置", error)


class ArchitectureSummaryValidationTests(unittest.TestCase):
    def test_accepts_valid_architecture_summary_block(self) -> None:
        self.assertIsNone(
            validate_architecture_summary_response(VALID_ARCHITECTURE_SUMMARY)
        )

    def test_rejects_architecture_summary_missing_required_label(self) -> None:
        invalid = VALID_ARCHITECTURE_SUMMARY.replace(
            "- 影响链路: normalized observations -> compact snapshot -> Agent Runtime / Presence Router\n",
            "",
        )

        error = validate_architecture_summary_response(invalid)

        self.assertIn("影响链路", error)


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
        path = REPO_ROOT / "Project.md"

        self.assertEqual(hash_file(path), hash_file(path))


if __name__ == "__main__":
    unittest.main()
