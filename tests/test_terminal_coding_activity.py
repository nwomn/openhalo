from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from device_edge.cli.coding_activity import CodingActivityJournal
from device_edge.cli.terminal_daemon import TerminalEdgeDaemon
from device_edge.cli.terminal_daemon import build_coding_activity_path


def _observation(interaction_id: str, event_kind: str = "agent_message") -> dict:
    return {
        "name": "coding.activity.v1",
        "observed_at": "2030-01-01T00:00:00Z",
        "confidence": 1.0,
        "value": {
            "agent": "codex",
            "interaction_id": interaction_id,
            "agent_session_id": "thread-1",
            "agent_turn_id": "turn-1",
            "event_kind": event_kind,
            "phase": "in_progress",
            "observed_at": "2030-01-01T00:00:00Z",
            "confidence": 1.0,
            "causal_parent": "thread-1:turn-1",
            "workspace_ref": "project",
            "summary": "ordinary coding observation",
            "evidence_ref": "coding-evidence://interaction-1/1",
        },
    }


def test_terminal_daemon_persists_coding_observation_without_record_only_bypass() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "coding.sqlite3"
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            coding_activity_path=path,
        )

        daemon._receive_coding_observation(_observation("interaction-1"))

        assert daemon.coding_observations[0]["name"] == "coding.activity.v1"
        journal = CodingActivityJournal(path)
        entries = journal.page("interaction-1")
        assert len(entries) == 1
        assert entries[0]["value"]["event_kind"] == "agent_message"


def test_terminal_daemon_keeps_runtime_queue_and_local_journal_in_step() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "coding.sqlite3"
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            coding_activity_path=path,
        )
        observation = _observation("interaction-1", event_kind="turn_completed")
        observation["value"]["phase"] = "completed"

        daemon._receive_coding_observation(observation)

        frame = daemon._drain_coding_observation_frames()[0]
        assert frame["payload"]["observations"][0] == observation
        assert CodingActivityJournal(path).tasks()[0]["status"] == "completed"


def test_coding_activity_path_is_scoped_to_openhalo_home_and_device() -> None:
    path = build_coding_activity_path(Path("/var/lib/openhalo"), "terminal-edge-1")

    assert path == Path("/var/lib/openhalo/terminal/terminal-edge-1/coding-activity.sqlite3")


def test_foreground_coding_control_is_queued_without_using_runtime_chat_input() -> None:
    daemon = TerminalEdgeDaemon(device_id="terminal-edge-1")

    daemon.queue_coding_control(
        "steer", interaction_id="interaction-1", text="Run the focused test"
    )

    assert daemon.coding_control_queue.get_nowait() == {
        "kind": "steer",
        "interaction_id": "interaction-1",
        "text": "Run the focused test",
    }


def test_line_mode_coding_commands_require_explicit_task_selection() -> None:
    daemon = TerminalEdgeDaemon(device_id="terminal-edge-1")

    assert daemon.handle_local_input("/coding tasks") is True
    assert daemon.handle_local_input("/coding send interaction-1 Run tests") is True

    assert daemon.coding_control_queue.empty()
    assert "selected active task" in daemon.transcript[-1]
