from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from device_edge.cli.coding_activity import CodingActivityJournal


def _observation(
    sequence: int,
    *,
    event_kind: str = "reasoning_summary",
    phase: str = "in_progress",
    interaction_id: str = "interaction-1",
) -> dict:
    observed_at = f"2030-01-01T00:{sequence // 60:02d}:{sequence % 60:02d}Z"
    return {
        "name": "coding.activity.v1",
        "value": {
            "agent": "codex",
            "interaction_id": interaction_id,
            "agent_session_id": f"thread-{interaction_id}",
            "agent_turn_id": "turn-1",
            "event_kind": event_kind,
            "phase": phase,
            "observed_at": observed_at,
            "confidence": 1.0,
            "causal_parent": f"thread-{interaction_id}:turn-1",
            "workspace_ref": "project",
            "summary": f"activity {sequence}",
            "evidence_ref": f"coding-evidence://{interaction_id}/{sequence}",
        },
        "observed_at": observed_at,
        "confidence": 1.0,
    }


def test_active_task_history_is_not_truncated_at_a_small_event_count() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "coding.sqlite3"
        journal = CodingActivityJournal(path)

        for sequence in range(200):
            journal.append(_observation(sequence))

        newest = journal.page("interaction-1", limit=75)
        older = journal.page(
            "interaction-1", before_sequence=newest[0]["local_sequence"], limit=200
        )

        assert len(newest) == 75
        assert len(older) == 125
        assert oldest_summary(older) == "activity 0"
        assert journal.tasks(active_only=True)[0]["interaction_id"] == "interaction-1"

        reopened = CodingActivityJournal(path)
        assert len(reopened.page("interaction-1", limit=500)) == 200


def test_capacity_cleanup_only_removes_completed_tasks() -> None:
    with TemporaryDirectory() as directory:
        journal = CodingActivityJournal(Path(directory) / "coding.sqlite3", quota_bytes=1)
        journal.append(_observation(1, interaction_id="active"))
        journal.append(
            _observation(
                2,
                interaction_id="completed",
                event_kind="turn_completed",
                phase="completed",
            )
        )
        journal.prune_completed()

        assert journal.page("active")
        assert journal.page("completed") == []
        assert journal.tasks(active_only=True)[0]["interaction_id"] == "active"


def test_terminal_task_status_survives_late_activity_from_same_turn() -> None:
    with TemporaryDirectory() as directory:
        journal = CodingActivityJournal(Path(directory) / "coding.sqlite3")
        journal.append(
            _observation(
                1,
                event_kind="turn_interrupted",
                phase="interrupted",
            )
        )
        journal.append(
            _observation(
                2,
                event_kind="agent_message",
                phase="in_progress",
            )
        )

        assert journal.tasks()[0]["status"] == "completed"


def test_append_rejects_observations_without_task_lineage() -> None:
    with TemporaryDirectory() as directory:
        journal = CodingActivityJournal(Path(directory) / "coding.sqlite3")
        observation = _observation(1)
        del observation["value"]["interaction_id"]

        try:
            journal.append(observation)
        except ValueError as exc:
            assert "interaction_id" in str(exc)
        else:
            raise AssertionError("missing task lineage must be rejected")


def oldest_summary(entries: list[dict]) -> str:
    return entries[0]["value"].get("summary", "")
