from __future__ import annotations

import io
import queue
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from device_edge.cli.presentation import OutcomeReceipt
from device_edge.cli.presentation import ReceiptEntry
from device_edge.cli.terminal_daemon import TerminalEdgeDaemon
from device_edge.cli.terminal_tui import TerminalEdgeApp
from device_edge.cli.terminal_tui import OutcomeReceiptWidget
from textual.containers import VerticalScroll
from textual.widgets import Input
from textual.widgets import Static
from textual.widgets import Button
from textual.widgets import Select


def test_receipt_widget_shows_compact_line_then_expanded_safe_timeline() -> None:
    receipt = OutcomeReceipt(
        interaction_id="interaction-1",
        state="completed",
        entries=(
            ReceiptEntry(1, "request_received", "2030-01-01T10:42:00Z"),
            ReceiptEntry(2, "confirmed", "2030-01-01T10:43:00Z", "Maya's Phone"),
        ),
        summary="Friday 14:00-17:00 is reserved for writing.",
        compact_line="✓ Completed · Maya's Phone · 10:43",
    )
    toggled = []
    widget = OutcomeReceiptWidget(receipt, on_toggle=toggled.append)

    assert "Maya's Phone" in str(widget.render())
    assert "Friday" not in str(widget.render())

    widget.toggle()
    widget.set_receipt(OutcomeReceipt(**{**receipt.__dict__, "expanded": True}))

    assert toggled == ["interaction-1"]
    assert "Friday 14:00-17:00" in str(widget.render())
    assert "10:42" in str(widget.render())


def test_terminal_surface_restoration_clears_a_tty_after_textual_exits() -> None:
    from device_edge.cli.terminal_tui import restore_terminal_surface

    class TtyOutput(io.StringIO):
        def isatty(self) -> bool:
            return True

    output = TtyOutput()

    restore_terminal_surface(output)

    assert output.getvalue() == "\x1b[0m\x1b[?25h\x1b[2J\x1b[H"


def test_terminal_app_exposes_one_expandable_coding_panel_and_explicit_task_select() -> None:
    daemon = TerminalEdgeDaemon(device_id="terminal-edge-1")
    app = TerminalEdgeApp(
        daemon=daemon,
        input_queue=queue.Queue(),
        input_state_queue=queue.Queue(),
        transcript_queue=queue.Queue(),
    )

    async def run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.query_one("#coding-toggle"), Button)
            assert isinstance(app.query_one("#coding-task-select"), Select)
            assert app.coding_expanded is False
            await pilot.click("#coding-toggle")
            await pilot.pause()
            assert app.coding_expanded is True

    asyncio_run(run())


def test_expanded_coding_composer_queues_correction_instead_of_runtime_chat() -> None:
    with TemporaryDirectory() as directory:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            coding_activity_path=Path(directory) / "coding.sqlite3",
        )
        daemon.coding_activity_journal.append(
            {
                "name": "coding.activity.v1",
                "observed_at": "2030-01-01T00:00:00Z",
                "confidence": 1.0,
                "value": {
                    "agent": "codex",
                    "interaction_id": "interaction-1",
                    "agent_session_id": "thread-1",
                    "agent_turn_id": "turn-1",
                    "event_kind": "prompt_submitted",
                    "phase": "in_progress",
                    "observed_at": "2030-01-01T00:00:00Z",
                    "confidence": 1.0,
                    "causal_parent": "thread-1:turn-1",
                    "workspace_ref": "project",
                    "summary": "started",
                    "evidence_ref": "coding-evidence://interaction-1/1",
                },
            }
        )
        input_queue: queue.Queue[str | None] = queue.Queue()
        input_state_queue: queue.Queue[dict] = queue.Queue()
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=input_queue,
            input_state_queue=input_state_queue,
            transcript_queue=queue.Queue(),
        )

        async def run() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.click("#coding-toggle")
                await pilot.pause()
                select = app.query_one("#coding-task-select", Select)
                select.value = "interaction-1"
                composer = app.query_one("#command-input", Input)
                composer.focus()
                composer.value = "Run the focused test"
                await pilot.pause()
                assert input_state_queue.empty()
                await pilot.press("enter")
                await pilot.pause()

        asyncio_run(run())
        assert input_queue.empty()
        assert daemon.coding_control_queue.get_nowait() == {
            "kind": "steer",
            "interaction_id": "interaction-1",
            "text": "Run the focused test",
        }


def test_expanded_coding_escape_queues_interrupt_for_selected_task() -> None:
    with TemporaryDirectory() as directory:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            coding_activity_path=Path(directory) / "coding.sqlite3",
        )
        for interaction_id in ("interaction-1", "interaction-2"):
            daemon.coding_activity_journal.append(
                {
                    "name": "coding.activity.v1",
                    "observed_at": "2030-01-01T00:00:00Z",
                    "confidence": 1.0,
                    "value": {
                        "agent": "codex",
                        "interaction_id": interaction_id,
                        "agent_session_id": f"thread-{interaction_id}",
                        "agent_turn_id": "turn-1",
                        "event_kind": "prompt_submitted",
                        "phase": "in_progress",
                        "observed_at": "2030-01-01T00:00:00Z",
                        "confidence": 1.0,
                        "causal_parent": f"thread-{interaction_id}:turn-1",
                        "workspace_ref": "project",
                        "summary": "started",
                        "evidence_ref": f"coding-evidence://{interaction_id}/1",
                    },
                }
            )
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=queue.Queue(),
            transcript_queue=queue.Queue(),
        )

        async def run() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.click("#coding-toggle")
                await pilot.pause()
                assert app.selected_coding_task is None
                select = app.query_one("#coding-task-select", Select)
                select.value = "interaction-2"
                composer = app.query_one("#command-input", Input)
                composer.focus()
                await pilot.press("escape")
                await pilot.pause()

        asyncio_run(run())
        assert daemon.coding_control_queue.get_nowait() == {
            "kind": "interrupt",
            "interaction_id": "interaction-2",
            "text": "",
        }


def asyncio_run(coroutine) -> None:
    import asyncio

    asyncio.run(coroutine)


class TerminalTuiReceiptTests(unittest.IsolatedAsyncioTestCase):
    async def test_terminal_app_renders_a_quiet_edge_identity_and_connection_header(
        self,
    ) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            audience="ws://127.0.0.1:8765",
        )
        daemon.connection_state = "connected"
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=queue.Queue(),
            transcript_queue=queue.Queue(),
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            title = app.query_one("#edge-title", Static)
            context = app.query_one("#edge-context", Static)
            connection = app.query_one("#connection-status", Static)

            self.assertEqual(str(title.content), "OpenHalo")
            self.assertIn("Terminal Edge", str(context.content))
            self.assertEqual(str(connection.content), "● Connected")

    def test_transcript_lines_use_product_speakers_not_protocol_prefixes(self) -> None:
        user_line = TerminalEdgeApp._format_transcript_line("[user] Send the note")
        runtime_line = TerminalEdgeApp._format_transcript_line("[runtime] Note sent")

        self.assertIn("You", str(user_line))
        self.assertIn("OpenHalo", str(runtime_line))
        self.assertNotIn("[user]", str(user_line))
        self.assertNotIn("[runtime]", str(runtime_line))

    async def test_terminal_app_mounts_and_toggles_a_safe_receipt(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            audience="ws://127.0.0.1:8765",
        )
        daemon.handle_interaction_frame(
            {
                "interaction": {
                    "interaction_id": "interaction-1",
                    "status": "completed",
                    "summary": "Done.",
                    "outcome_receipt": {
                        "version": 1,
                        "state": "completed",
                        "entries": [
                            {
                                "sequence": 1,
                                "kind": "confirmed",
                                "occurred_at": "2030-01-01T10:43:00Z",
                                "device_name": "Maya's Phone",
                            }
                        ],
                    },
                }
            }
        )
        transcript_queue: queue.Queue[str] = queue.Queue()
        transcript_queue.put(daemon.transcript[-1])
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=queue.Queue(),
            transcript_queue=transcript_queue,
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            widget = app.query_one("#receipt-interaction-1", OutcomeReceiptWidget)
            widget.focus()
            await pilot.press("space")
            await pilot.pause()

        assert daemon.presentation.receipts["interaction-1"].expanded is True

    async def test_empty_composer_tab_focuses_receipt_for_keyboard_expansion(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            audience="ws://127.0.0.1:8765",
        )
        daemon.handle_interaction_frame(
            {
                "interaction": {
                    "interaction_id": "interaction-1",
                    "status": "completed",
                    "summary": "Done.",
                    "outcome_receipt": {
                        "version": 1,
                        "state": "completed",
                        "entries": [
                            {
                                "sequence": 1,
                                "kind": "confirmed",
                                "occurred_at": "2030-01-01T10:43:00Z",
                                "device_name": "Runtime Host",
                            }
                        ],
                    },
                }
            }
        )
        transcript_queue: queue.Queue[str] = queue.Queue()
        transcript_queue.put(daemon.transcript[-1])
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=queue.Queue(),
            transcript_queue=transcript_queue,
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#command-input", Input)
            widget = app.query_one("#receipt-interaction-1", OutcomeReceiptWidget)
            composer.focus()
            await pilot.press("tab")
            assert app.focused is widget
            await pilot.press("space")
            await pilot.pause()

        assert daemon.presentation.receipts["interaction-1"].expanded is True

    async def test_terminal_app_keeps_progress_in_one_active_row_outside_the_transcript(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            audience="ws://127.0.0.1:8765",
        )
        daemon.handle_interaction_progress_frame(
            {
                "progress": {
                    "version": 1,
                    "interaction_id": "interaction-1",
                    "sequence": 1,
                    "phase": "planning",
                    "state": "active",
                }
            }
        )
        transcript_queue: queue.Queue[str] = queue.Queue()
        transcript_queue.put("[progress] 正在准备下一步...")
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=queue.Queue(),
            transcript_queue=transcript_queue,
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            active_progress = app.query_one("#active-progress", Static)
            transcript = app.query_one("#transcript-log", VerticalScroll)
            assert "正在准备下一步" in str(active_progress.content)
            assert len(transcript.children) == 0

    async def test_terminal_app_preserves_draft_while_the_daemon_retries(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            audience="ws://127.0.0.1:8765",
        )
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=queue.Queue(),
            transcript_queue=queue.Queue(),
        )

        async with app.run_test() as pilot:
            composer = app.query_one("#command-input", Input)
            composer.value = "Keep this unfinished message"
            daemon.connection_state = "retrying"
            await pilot.pause()

            assert composer.value == "Keep this unfinished message"
            assert daemon.presentation.draft == "Keep this unfinished message"

    async def test_terminal_app_compacts_status_text_to_the_available_width(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-with-a-long-device-identifier",
            audience="ws://127.0.0.1:8765",
        )
        daemon.connection_state = "connected"
        daemon.terminal_activity_state = "active"
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=queue.Queue(),
            transcript_queue=queue.Queue(),
        )

        self.assertLessEqual(len(app.build_status_text(max_width=42)), 42)

    async def test_terminal_app_keeps_composer_help_within_a_narrow_terminal(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            audience="ws://127.0.0.1:8765",
        )
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=queue.Queue(),
            transcript_queue=queue.Queue(),
        )

        help_text = app.build_help_text(max_width=60)

        self.assertLessEqual(len(help_text), 60)
        self.assertIn("Enter", help_text)
        self.assertIn("Tab", help_text)

    async def test_terminal_app_completes_local_commands_and_navigates_input_history(
        self,
    ) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            audience="ws://127.0.0.1:8765",
        )
        input_queue: queue.Queue[str | None] = queue.Queue()
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=input_queue,
            input_state_queue=queue.Queue(),
            transcript_queue=queue.Queue(),
        )

        async with app.run_test() as pilot:
            composer = app.query_one("#command-input", Input)
            composer.value = "/he"
            await pilot.press("tab")
            assert composer.value == "/help"

            await pilot.press("enter")
            composer.value = "First request"
            await pilot.press("enter")
            composer.value = "Second request"
            await pilot.press("enter")
            await pilot.press("up")
            assert composer.value == "Second request"
            await pilot.press("up")
            assert composer.value == "First request"
            await pilot.press("down")
            assert composer.value == "Second request"
            await pilot.press("escape")
            assert composer.value == ""

        assert [input_queue.get_nowait() for _ in range(3)] == [
            "/help",
            "First request",
            "Second request",
        ]
