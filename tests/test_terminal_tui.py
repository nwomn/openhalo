import asyncio
import io
import queue
import unittest

from textual.containers import Horizontal
from textual.widgets import Button
from textual.widgets import Input
from textual.widgets import RichLog
from textual.widgets import Static

from device_edge.cli.terminal_daemon import TerminalEdgeDaemon
from device_edge.cli.terminal_tui import QueueLineInput
from device_edge.cli.terminal_tui import TerminalEdgeApp
from device_edge.cli.terminal_ui_state import DaemonUiSnapshot
from device_edge.cli.terminal_ui_state import InputHistory
from device_edge.cli.terminal_ui_state import SlashCommandCatalog
from device_edge.cli.terminal_ui_state import TerminalUiReducer
from device_edge.cli.terminal_ui_state import parse_terminal_line


class TerminalUiStateTests(unittest.TestCase):
    def test_parses_known_and_unknown_terminal_lines(self) -> None:
        self.assertEqual(parse_terminal_line("[user] hello").role, "user")
        self.assertEqual(parse_terminal_line("[runtime] reply").body, "reply")
        self.assertEqual(parse_terminal_line("plain output").role, "system")

    def test_progress_updates_do_not_enter_tui_transcript(self) -> None:
        reducer = TerminalUiReducer()

        entry = reducer.consume_line("[progress] 正在准备下一步...")

        self.assertIsNone(entry)

    def test_active_view_uses_daemon_progress_and_connection_priority(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=io.StringIO(),
        )
        daemon.connection_state = "connected"
        daemon.pending_runtime_reply = True
        daemon.active_progress_interaction_id = "interaction-1"
        daemon.active_progress_phase = "executing"

        active = TerminalUiReducer.active_interaction(
            DaemonUiSnapshot.from_daemon(daemon)
        )
        daemon.connection_state = "reconnecting"
        reconnecting = TerminalUiReducer.active_interaction(
            DaemonUiSnapshot.from_daemon(daemon)
        )

        self.assertEqual(active.state, "active")
        self.assertIn("执行", active.title)
        self.assertEqual(reconnecting.state, "reconnecting")

    def test_runtime_failure_summary_is_presented_as_error(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=io.StringIO(),
        )
        daemon.connection_state = "connected"
        daemon.latest_runtime_summary = {
            "summary": "Runtime provider is unavailable.",
            "result_status": "failed",
            "terminal_reason": "provider_failure",
        }
        snapshot = DaemonUiSnapshot.from_daemon(daemon)
        reducer = TerminalUiReducer()

        entry = reducer.consume_line(
            "[runtime] Runtime provider is unavailable.",
            snapshot,
        )
        active = reducer.active_interaction(snapshot)

        self.assertIsNotNone(entry)
        self.assertEqual(entry.role, "error")
        self.assertEqual(active.state, "error")

    def test_device_summary_overview_and_cross_device_route(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=io.StringIO(),
        )
        daemon.connection_state = "connected"
        daemon.device_roster = (
            {
                "device_id": "terminal-edge-1",
                "device_type": "desktop-cli",
                "role": "computer_edge",
                "online": True,
                "action_capabilities": ("notification.show",),
            },
            {
                "device_id": "phone-edge-1",
                "device_type": "android-phone",
                "role": "phone_edge",
                "online": True,
                "action_capabilities": ("notification.show",),
            },
            {
                "device_id": "earbuds-edge-1",
                "device_type": "earbuds",
                "role": None,
                "online": False,
                "action_capabilities": (),
            },
        )
        daemon.active_interaction_route = {
            "interaction_id": "interaction-1",
            "source_device_id": "terminal-edge-1",
            "routes": (
                {
                    "target_device_id": "phone-edge-1",
                    "capability": "notification.show",
                    "presence_decision": "allow",
                },
            ),
        }
        snapshot = DaemonUiSnapshot.from_daemon(daemon)

        summary = TerminalUiReducer.device_summary(snapshot)
        overview = TerminalUiReducer.device_overview(snapshot, daemon.client.device_id)
        active = TerminalUiReducer.active_interaction(snapshot)

        self.assertEqual(summary, "Global thread · 2/3 edges")
        self.assertIn("terminal-edge-1", overview)
        self.assertIn("you are here", overview)
        self.assertIn("○ earbuds-edge-1", overview)
        self.assertEqual(active.state, "route")
        self.assertIn("terminal-edge-1 → Personal Runtime", active.title)
        self.assertIn("phone-edge-1", active.title)
        self.assertEqual(active.detail, "notification.show")

    def test_reconnect_view_uses_attempt_and_delay(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=io.StringIO(),
        )
        daemon.connection_state = "reconnecting"
        daemon.reconnect_attempt = 3
        daemon.reconnect_delay_s = 15.0

        active = TerminalUiReducer.active_interaction(
            DaemonUiSnapshot.from_daemon(daemon)
        )

        self.assertEqual(active.state, "reconnecting")
        self.assertIn("第 3 次重试", active.detail)
        self.assertIn("15 秒后继续", active.detail)

    def test_input_history_restores_original_draft(self) -> None:
        history = InputHistory()
        history.record("first")
        history.record("second")

        self.assertEqual(history.previous("draft"), "second")
        self.assertEqual(history.previous("second"), "first")
        self.assertEqual(history.next("first"), "second")
        self.assertEqual(history.next("second"), "draft")

    def test_slash_catalog_matches_and_completes(self) -> None:
        catalog = SlashCommandCatalog()

        self.assertEqual(catalog.complete("/st"), "/status")
        self.assertEqual(catalog.matches("/rec")[0].name, "/reconnect")


class QueueLineInputAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_queue_input_async_reader_is_cancellable(self) -> None:
        stream = QueueLineInput(queue.Queue())
        task = asyncio.create_task(stream.readline_async())
        await asyncio.sleep(0)

        task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await task


class TerminalTuiInteractionTests(unittest.IsolatedAsyncioTestCase):
    def build_app(self, daemon=None):
        daemon = daemon or TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=io.StringIO(),
        )
        return TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=queue.Queue(),
            transcript_queue=queue.Queue(),
        )

    async def test_layout_exposes_header_active_panel_and_composer(self) -> None:
        app = self.build_app()

        async with app.run_test(size=(110, 32)) as pilot:
            await pilot.pause()
            self.assertIsNotNone(app.query_one("#connection-chip", Static))
            self.assertIsNotNone(app.query_one("#active-interaction", Horizontal))
            self.assertIsNotNone(app.query_one("#command-input", Input))
            self.assertIsNotNone(app.query_one("#transcript-log", RichLog))

    async def test_progress_is_shown_in_active_panel_not_transcript(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=io.StringIO(),
        )
        daemon.connection_state = "connected"
        daemon.active_progress_interaction_id = "interaction-1"
        daemon.active_progress_phase = "planning"
        transcript_queue = queue.Queue()
        transcript_queue.put("[progress] 正在准备下一步...")
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=queue.Queue(),
            transcript_queue=transcript_queue,
        )

        async with app.run_test(size=(110, 32)) as pilot:
            await pilot.pause()
            app._refresh_ui()
            active_strip = app.query_one("#active-interaction", Horizontal)
            active_title = app.query_one("#active-title", Static)
            active_detail = app.query_one("#active-detail", Static)
            self.assertIn("准备", str(active_title.content))
            self.assertIn("设备", str(active_detail.content))
            self.assertEqual(active_strip.region.height, 1)
            self.assertEqual(active_title.region.y, active_detail.region.y)
            self.assertEqual(len(app.query_one("#transcript-log", RichLog).lines), 0)

    async def test_idle_active_status_strip_is_hidden(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=io.StringIO(),
        )
        daemon.connection_state = "connected"
        app = self.build_app(daemon)

        async with app.run_test(size=(110, 32)) as pilot:
            await pilot.pause()
            active_strip = app.query_one("#active-interaction", Horizontal)
            self.assertFalse(active_strip.display)
            self.assertEqual(active_strip.region.height, 0)

    async def test_device_overview_opens_on_ctrl_d_and_closes_on_escape(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=io.StringIO(),
        )
        daemon.connection_state = "connected"
        daemon.device_roster = (
            {
                "device_id": "terminal-edge-1",
                "device_type": "desktop-cli",
                "role": "computer_edge",
                "online": True,
                "action_capabilities": ("notification.show",),
            },
            {
                "device_id": "phone-edge-1",
                "device_type": "android-phone",
                "role": "phone_edge",
                "online": True,
                "action_capabilities": ("notification.show",),
            },
        )
        app = self.build_app(daemon)

        async with app.run_test(size=(110, 32)) as pilot:
            await pilot.pause()
            summary = app.query_one("#device-summary", Button)
            overview = app.query_one("#device-overview", Static)
            self.assertEqual(str(summary.label), "Global thread · 2/2 edges")
            self.assertFalse(overview.has_class("visible"))
            await pilot.click("#device-summary")
            await pilot.pause()
            self.assertTrue(overview.has_class("visible"))
            self.assertIn("phone-edge-1", str(overview.content))
            await pilot.press("escape")
            await pilot.pause()
            self.assertFalse(overview.has_class("visible"))

    async def test_offline_composer_note_replaces_repeated_transcript_notice(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=io.StringIO(),
        )
        daemon.connection_state = "reconnecting"
        app = self.build_app(daemon)

        async with app.run_test(size=(110, 32)) as pilot:
            await pilot.pause()
            input_widget = app.query_one("#command-input", Input)
            input_widget.value = "keep this draft"
            await pilot.press("enter")
            await pilot.press("enter")
            await pilot.pause()
            note = app.query_one("#composer-note", Static)
            transcript = app.query_one("#transcript-log", RichLog)
            self.assertTrue(note.has_class("visible"))
            self.assertIn("draft preserved", str(note.content))
            self.assertEqual(input_widget.value, "keep this draft")
            self.assertEqual(len(transcript.lines), 0)

    async def test_clear_command_clears_visible_transcript_locally(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=io.StringIO(),
        )
        daemon.connection_state = "connected"
        transcript_queue = queue.Queue()
        transcript_queue.put("[user] hello")
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=queue.Queue(),
            transcript_queue=transcript_queue,
        )

        async with app.run_test(size=(110, 32)) as pilot:
            await pilot.pause()
            app._refresh_ui()
            self.assertGreater(len(app.query_one("#transcript-log", RichLog).lines), 0)
            input_widget = app.query_one("#command-input", Input)
            input_widget.value = "/clear"
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(len(app.query_one("#transcript-log", RichLog).lines), 0)
            self.assertEqual(daemon.local_command_count, 1)

    async def test_disconnected_submit_preserves_draft(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=io.StringIO(),
        )
        daemon.connection_state = "reconnecting"
        app = self.build_app(daemon)

        async with app.run_test(size=(110, 32)) as pilot:
            input_widget = app.query_one("#command-input", Input)
            input_widget.value = "keep this draft"
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(input_widget.value, "keep this draft")
            self.assertTrue(app.input_queue.empty())

    async def test_input_history_uses_up_and_down_without_sending(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=io.StringIO(),
        )
        daemon.connection_state = "connected"
        app = self.build_app(daemon)
        app.input_history.record("first command")
        app.input_history.record("second command")

        async with app.run_test(size=(110, 32)) as pilot:
            await pilot.press("up")
            await pilot.pause()
            input_widget = app.query_one("#command-input", Input)
            self.assertEqual(input_widget.value, "second command")
            await pilot.press("up")
            await pilot.pause()
            self.assertEqual(input_widget.value, "first command")
            self.assertTrue(app.input_queue.empty())

    async def test_slash_command_menu_and_tab_completion(self) -> None:
        app = self.build_app()

        async with app.run_test(size=(110, 32)) as pilot:
            input_widget = app.query_one("#command-input", Input)
            input_widget.value = "/st"
            await pilot.pause()
            suggestions = app.query_one("#command-suggestions", Static)
            self.assertTrue(suggestions.has_class("visible"))
            await pilot.press("tab")
            await pilot.pause()
            self.assertEqual(input_widget.value, "/status")

    async def test_resize_applies_narrow_and_short_classes(self) -> None:
        app = self.build_app()

        async with app.run_test(size=(110, 32)) as pilot:
            await pilot.resize_terminal(60, 16)
            await pilot.pause()
            self.assertTrue(app.screen.has_class("narrow"))
            self.assertTrue(app.screen.has_class("short"))
