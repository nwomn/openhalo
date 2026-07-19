import asyncio
from collections import deque
from contextlib import suppress
import io
import json
from pathlib import Path
import queue
import tomllib
import unittest
from unittest import mock

import websockets
from textual.widgets import Input
from textual.widgets import RichLog
from textual.widgets import Static

from device_edge.cli.terminal_daemon import TerminalEdgeDaemon
from device_edge.cli.terminal_daemon import build_terminal_daemon_parser
from device_edge.cli.terminal_daemon import main

ROOT = Path(__file__).resolve().parents[1]


class TerminalEdgeDaemonTests(unittest.TestCase):
    def test_progress_frame_renders_a_local_phase_and_replaces_current_phase(self) -> None:
        stdout = io.StringIO()
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=stdout,
        )

        daemon.handle_interaction_progress_frame(
            {
                "type": "interaction_progress",
                "device_id": "terminal-edge-1",
                "progress": {
                    "version": 1,
                    "interaction_id": "interaction-1",
                    "interaction_turn_id": "interaction-turn-1",
                    "sequence": 1,
                    "phase": "deliberating",
                    "state": "active",
                    "occurred_at": "2026-07-18T10:00:00Z",
                    "presentation_hint": "working",
                },
            }
        )
        daemon.handle_interaction_progress_frame(
            {
                "type": "interaction_progress",
                "device_id": "terminal-edge-1",
                "progress": {
                    "version": 1,
                    "interaction_id": "interaction-1",
                    "interaction_turn_id": "interaction-turn-1",
                    "sequence": 2,
                    "phase": "planning",
                    "state": "active",
                    "occurred_at": "2026-07-18T10:00:01Z",
                    "presentation_hint": "working",
                },
            }
        )

        self.assertEqual(daemon.active_progress_phase, "planning")
        self.assertIn("[progress] 正在理解你的请求...", stdout.getvalue())
        self.assertIn("[progress] 正在准备下一步...", stdout.getvalue())

    def test_progress_frame_ignores_a_stale_sequence_and_clears_when_settled(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=io.StringIO(),
        )
        active = {
            "type": "interaction_progress",
            "device_id": "terminal-edge-1",
            "progress": {
                "version": 1,
                "interaction_id": "interaction-1",
                "interaction_turn_id": "interaction-turn-1",
                "sequence": 2,
                "phase": "executing",
                "state": "active",
                "occurred_at": "2026-07-18T10:00:02Z",
                "presentation_hint": "working",
            },
        }
        stale = {
            **active,
            "progress": {**active["progress"], "sequence": 1, "phase": "planning"},
        }
        settled = {
            **active,
            "progress": {
                **active["progress"],
                "sequence": 3,
                "phase": "completed",
                "state": "settled",
            },
        }

        daemon.handle_interaction_progress_frame(active)
        daemon.handle_interaction_progress_frame(stale)
        daemon.handle_interaction_progress_frame(settled)

        self.assertEqual(daemon.progress_sequence_by_interaction["interaction-1"], 3)
        self.assertIsNone(daemon.active_progress_phase)

    def test_progress_frame_keeps_each_tty_phase_as_a_line(self) -> None:
        class TtyOutput(io.StringIO):
            def isatty(self) -> bool:
                return True

        output = TtyOutput()
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=output,
        )
        active = {
            "type": "interaction_progress",
            "device_id": "terminal-edge-1",
            "progress": {
                "version": 1,
                "interaction_id": "interaction-1",
                "interaction_turn_id": "interaction-turn-1",
                "sequence": 1,
                "phase": "deliberating",
                "state": "active",
                "occurred_at": "2026-07-18T10:00:00Z",
                "presentation_hint": "working",
            },
        }

        daemon.handle_interaction_progress_frame(active)
        daemon.handle_interaction_progress_frame(
            {
                **active,
                "progress": {**active["progress"], "sequence": 2, "phase": "planning"},
            }
        )
        daemon.handle_interaction_progress_frame(
            {
                **active,
                "progress": {
                    **active["progress"],
                    "sequence": 3,
                    "phase": "completed",
                    "state": "settled",
                },
            }
        )

        self.assertEqual(
            output.getvalue(),
            "[progress] 正在理解你的请求...\n"
            "[progress] 正在准备下一步...\n",
        )
        self.assertEqual(
            list(daemon.transcript),
            [
                "[progress] 正在理解你的请求...",
                "[progress] 正在准备下一步...",
            ],
        )

    def test_local_help_command_is_handled_without_runtime_event(self) -> None:
        stdout = io.StringIO()
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=stdout,
        )

        handled = daemon.handle_local_input("/help")

        self.assertTrue(handled)
        self.assertIn("/help", stdout.getvalue())
        self.assertIn("/status", stdout.getvalue())
        self.assertEqual(daemon.local_command_count, 1)
        self.assertEqual(daemon.user_request_count, 0)

    def test_local_status_command_renders_readable_session_summary(self) -> None:
        stdout = io.StringIO()
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=stdout,
        )
        daemon.connection_state = "connected"
        daemon.terminal_activity_state = "active"
        daemon.user_request_count = 2
        daemon.runtime_message_count = 1
        daemon.local_command_count = 1
        daemon.pending_runtime_reply = True

        handled = daemon.handle_local_input("/status")

        self.assertTrue(handled)
        rendered = stdout.getvalue()
        self.assertIn("Session status", rendered)
        self.assertIn("connection=connected", rendered)
        self.assertIn("activity=active", rendered)
        self.assertIn("user_requests=2", rendered)
        self.assertIn("runtime_messages=1", rendered)
        self.assertIn("pending_runtime_reply=yes", rendered)

    def test_local_history_command_renders_recent_transcript(self) -> None:
        stdout = io.StringIO()
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=stdout,
        )
        daemon.transcript.extend(
            deque(
                [
                    "[system] Session ready.",
                    "[user] hello runtime",
                    "[runtime] Runtime heard: hello runtime",
                ],
                maxlen=daemon.transcript_limit,
            )
        )

        handled = daemon.handle_local_input("/history")

        self.assertTrue(handled)
        rendered = stdout.getvalue()
        self.assertIn("Recent session history", rendered)
        self.assertIn("[user] hello runtime", rendered)
        self.assertIn("[runtime] Runtime heard: hello runtime", rendered)

    def test_local_quit_command_marks_daemon_for_clean_exit(self) -> None:
        stdout = io.StringIO()
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=stdout,
        )

        handled = daemon.handle_local_input("/quit")

        self.assertTrue(handled)
        self.assertTrue(daemon.quit_requested)
        self.assertIn("Shutting down terminal session", stdout.getvalue())

    def test_render_runtime_notification_body_uses_readable_terminal_prefix(self) -> None:
        stdout = io.StringIO()
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=stdout,
        )

        result = daemon.handle_action_request(
            {
                "type": "action_request",
                "device_id": "terminal-edge-1",
                "action": {
                    "capability": "notification.show",
                    "payload": {
                        "title": "OpenHalo",
                        "body": "runtime push",
                    },
                },
            }
        )

        self.assertEqual(result["result"]["status"], "ok")
        self.assertIn("[runtime] runtime push", stdout.getvalue())
        self.assertEqual(
            result["result"]["details"],
            {
                "delivered_via": "terminal.stdout",
                "title": "OpenHalo",
                "body": "runtime push",
            },
        )
        self.assertEqual(daemon.runtime_message_count, 1)
        self.assertFalse(daemon.pending_runtime_reply)

    def test_action_request_clears_tty_progress_before_runtime_output(self) -> None:
        class TtyOutput(io.StringIO):
            def isatty(self) -> bool:
                return True

        output = TtyOutput()
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=output,
        )
        daemon.handle_interaction_progress_frame(
            {
                "type": "interaction_progress",
                "device_id": "terminal-edge-1",
                "progress": {
                    "version": 1,
                    "interaction_id": "interaction-1",
                    "interaction_turn_id": "interaction-turn-1",
                    "sequence": 1,
                    "phase": "executing",
                    "state": "active",
                    "occurred_at": "2026-07-19T10:00:00Z",
                    "presentation_hint": "working",
                },
            }
        )

        daemon.handle_action_request(
            {
                "type": "action_request",
                "device_id": "terminal-edge-1",
                "action": {
                    "capability": "notification.show",
                    "payload": {"title": "OpenHalo", "body": "runtime push"},
                },
            }
        )

        self.assertEqual(
            output.getvalue(),
            "[progress] 正在执行操作...\n[runtime] runtime push\n",
        )

    def test_runtime_action_result_preserves_request_correlation(self) -> None:
        stdout = io.StringIO()
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=stdout,
        )

        result = daemon.handle_action_request(
            {
                "type": "action_request",
                "request_id": "action-2",
                "interaction_id": "interaction-1",
                "interaction_turn_id": "interaction-turn-1",
                "trace_id": "trace-terminal-edge-1-3",
                "session_id": "session-terminal-edge-1",
                "turn_id": "turn-terminal-edge-1-3",
                "event_id": "terminal-edge-1-evt-3",
                "device_id": "terminal-edge-1",
                "action": {
                    "capability": "notification.show",
                    "payload": {"title": "OpenHalo", "body": "runtime push"},
                },
            }
        )

        self.assertEqual(result["request_id"], "action-2")
        self.assertEqual(result["interaction_id"], "interaction-1")
        self.assertEqual(result["interaction_turn_id"], "interaction-turn-1")
        self.assertEqual(result["trace_id"], "trace-terminal-edge-1-3")
        self.assertEqual(result["session_id"], "session-terminal-edge-1")
        self.assertEqual(result["turn_id"], "turn-terminal-edge-1-3")
        self.assertEqual(result["event_id"], "terminal-edge-1-evt-3")

    def test_interaction_update_clears_waiting_without_local_action_request(self) -> None:
        stdout = io.StringIO()
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=stdout,
        )
        daemon.pending_runtime_reply = True

        daemon.handle_interaction_frame(
            {
                "type": "interaction_update",
                "device_id": "terminal-edge-1",
                "interaction": {
                    "interaction_id": "interaction-1",
                    "status": "completed",
                    "summary": "Runtime status is healthy.",
                },
            }
        )

        self.assertFalse(daemon.pending_runtime_reply)
        self.assertIn("Runtime status is healthy.", stdout.getvalue())

    def test_silent_interaction_update_clears_waiting_without_rendering_summary(self) -> None:
        stdout = io.StringIO()
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=stdout,
        )
        daemon.pending_runtime_reply = True

        daemon.handle_interaction_frame(
            {
                "type": "interaction_update",
                "device_id": "terminal-edge-1",
                "interaction": {
                    "interaction_id": "interaction-1",
                    "status": "completed",
                    "summary": "Hello! Runtime here.",
                    "visibility": "silent",
                },
            }
        )

        self.assertFalse(daemon.pending_runtime_reply)
        self.assertNotIn("Hello! Runtime here.", stdout.getvalue())

    def test_render_status_line_records_recent_transcript_entries(self) -> None:
        stdout = io.StringIO()
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=stdout,
        )

        daemon.render_status_line("Connected to runtime.")
        daemon.render_user_line("hello runtime")

        self.assertEqual(
            list(daemon.transcript),
            ["[system] Connected to runtime.", "[user] hello runtime"],
        )
        self.assertIn("[system] Connected to runtime.", stdout.getvalue())

    def test_parser_accepts_optional_live_startup_timestamp_override(self) -> None:
        parser = build_terminal_daemon_parser()

        args = parser.parse_args(
            [
                "--url",
                "ws://127.0.0.1:8765",
            ]
        )

        self.assertEqual(args.url, "ws://127.0.0.1:8765")
        self.assertIsNone(args.startup_observed_at)

    def test_parser_accepts_optional_first_stdin_timestamp_override(self) -> None:
        parser = build_terminal_daemon_parser()

        args = parser.parse_args(
            [
                "--url",
                "ws://127.0.0.1:8765",
                "--stdin-observed-at",
                "2026-06-22T10:00:00Z",
            ]
        )

        self.assertEqual(args.stdin_observed_at, "2026-06-22T10:00:00Z")

    def test_parser_accepts_optional_tui_mode_flag(self) -> None:
        parser = build_terminal_daemon_parser()

        args = parser.parse_args(
            [
                "--url",
                "ws://127.0.0.1:8765",
                "--tui",
            ]
        )

        self.assertTrue(args.tui)

    def test_parser_accepts_diagnostic_log_path(self) -> None:
        parser = build_terminal_daemon_parser()

        args = parser.parse_args(
            [
                "--url",
                "ws://127.0.0.1:8765",
                "--diagnostic-log-path",
                ".runtime/diagnostics/terminal-edge-1.jsonl",
            ]
        )

        self.assertEqual(
            args.diagnostic_log_path,
            Path(".runtime/diagnostics/terminal-edge-1.jsonl"),
        )

    def test_build_user_input_frames_use_session_client_correlation(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )

        frames = daemon.build_user_input_frames(
            text="hello runtime",
            observed_at="2026-06-30T12:00:00Z",
        )

        self.assertEqual(frames[1]["type"], "event_push")
        self.assertEqual(frames[1]["capability"], "text.input")
        self.assertRegex(frames[1]["trace_id"], r"^trace-terminal-edge-1-\d+$")
        self.assertEqual(frames[1]["payload"]["observed_at"], "2026-06-30T12:00:00Z")

    def test_parser_defaults_to_line_mode_when_tui_flag_is_omitted(self) -> None:
        parser = build_terminal_daemon_parser()

        args = parser.parse_args(
            [
                "--url",
                "ws://127.0.0.1:8765",
            ]
        )

        self.assertFalse(args.tui)

    def test_project_declares_textual_runtime_dependency_for_tui_mode(self) -> None:
        payload = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertIn("textual", payload["project"]["dependencies"])

    def test_queue_input_stream_reads_queued_lines_for_daemon(self) -> None:
        from device_edge.cli.terminal_tui import QueueLineInput

        line_queue: queue.Queue[str | None] = queue.Queue()
        stream = QueueLineInput(line_queue)

        line_queue.put("hello runtime")
        line_queue.put(None)

        self.assertEqual(stream.readline(), "hello runtime\n")
        self.assertEqual(stream.readline(), "")

    def test_queue_output_stream_emits_completed_transcript_lines(self) -> None:
        from device_edge.cli.terminal_tui import QueueLineOutput

        line_queue: queue.Queue[str] = queue.Queue()
        stream = QueueLineOutput(line_queue)

        self.assertEqual(stream.write("[system] Connected"), 18)
        self.assertTrue(line_queue.empty())
        self.assertEqual(stream.write("\n[runtime] hello"), 16)
        self.assertEqual(line_queue.get_nowait(), "[system] Connected")
        self.assertEqual(stream.write("\n"), 1)
        self.assertEqual(line_queue.get_nowait(), "[runtime] hello")

    def test_create_textual_terminal_app_uses_queue_backed_daemon_streams(self) -> None:
        from device_edge.cli.terminal_tui import QueueLineInput
        from device_edge.cli.terminal_tui import QueueLineOutput
        from device_edge.cli.terminal_tui import create_textual_terminal_app

        app = create_textual_terminal_app(
            url="ws://127.0.0.1:8765",
            token="dev-token",
            device_id="terminal-edge-1",
            startup_observed_at=None,
            idle_timeout_s=30.0,
            idle_observed_at=None,
            max_idle_cycles=None,
            max_action_requests=None,
            max_sessions=None,
            stdin_observed_at=None,
            scripted_inputs=[],
        )

        self.assertIsInstance(app.daemon.input_stream, QueueLineInput)
        self.assertIsInstance(app.daemon.output_stream, QueueLineOutput)
        self.assertIs(app.daemon.input_state_stream, app.input_state_queue)
        self.assertIsNotNone(app.start_session)

    def test_main_dispatches_to_textual_mode_when_tui_flag_is_set(self) -> None:
        def close_coroutine(coro) -> None:
            coro.close()

        with (
            mock.patch(
                "sys.argv",
                [
                    "terminal_daemon",
                    "--url",
                    "ws://127.0.0.1:8765",
                    "--tui",
                ],
            ),
            mock.patch.dict("os.environ", {"TERM": "xterm-256color"}, clear=False),
            mock.patch("asyncio.run", side_effect=close_coroutine) as asyncio_run,
            mock.patch(
                "device_edge.cli.terminal_tui.run_textual_terminal_daemon"
            ) as run_tui,
        ):
            main()

        asyncio_run.assert_not_called()
        run_tui.assert_called_once()

    def test_main_falls_back_to_line_mode_when_tui_requested_in_dumb_terminal(self) -> None:
        def close_coroutine(coro) -> None:
            coro.close()

        with (
            mock.patch(
                "sys.argv",
                [
                    "terminal_daemon",
                    "--url",
                    "ws://127.0.0.1:8765",
                    "--tui",
                ],
            ),
            mock.patch.dict("os.environ", {"TERM": "dumb"}, clear=False),
            mock.patch("asyncio.run", side_effect=close_coroutine) as asyncio_run,
            mock.patch(
                "device_edge.cli.terminal_tui.run_textual_terminal_daemon"
            ) as run_tui,
            mock.patch("builtins.print") as print_mock,
        ):
            main()

        run_tui.assert_not_called()
        asyncio_run.assert_called_once()
        printed = "\n".join(
            " ".join(str(arg) for arg in call.args)
            for call in print_mock.call_args_list
        )
        self.assertIn("TERM=dumb", printed)
        self.assertIn("falling back to line mode", printed)


class TerminalEdgeTuiTests(unittest.IsolatedAsyncioTestCase):
    async def test_textual_terminal_app_exposes_status_transcript_and_input_widgets(
        self,
    ) -> None:
        from device_edge.cli.terminal_tui import TerminalEdgeApp

        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=queue.Queue(),
            transcript_queue=queue.Queue(),
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertIsNotNone(app.query_one("#status-bar", Static))
            self.assertIsNotNone(app.query_one("#transcript-log", RichLog))
            input_widget = app.query_one("#command-input", Input)
            self.assertIn("/help", input_widget.placeholder)
            help_bar = app.query_one("#help-bar", Static)
            self.assertIn("/quit", str(help_bar.content))

    async def test_textual_terminal_app_renders_live_daemon_status_summary(
        self,
    ) -> None:
        from device_edge.cli.terminal_tui import TerminalEdgeApp

        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )
        daemon.connection_state = "connected"
        daemon.terminal_activity_state = "active"
        daemon.pending_runtime_reply = True
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=queue.Queue(),
            transcript_queue=queue.Queue(),
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            status_bar = app.query_one("#status-bar", Static)
            self.assertIn("connection=connected", str(status_bar.content))
            self.assertIn("state=waiting", str(status_bar.content))

    async def test_textual_terminal_app_drains_transcript_queue_into_log(self) -> None:
        from device_edge.cli.terminal_tui import TerminalEdgeApp

        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )
        transcript_queue: queue.Queue[str] = queue.Queue()
        transcript_queue.put("[system] Connected to runtime.")
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=queue.Queue(),
            transcript_queue=transcript_queue,
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            transcript_log = app.query_one("#transcript-log", RichLog)
            self.assertGreaterEqual(len(transcript_log.lines), 1)

    async def test_textual_terminal_app_records_draft_input_state_changes(self) -> None:
        from device_edge.cli.terminal_tui import TerminalEdgeApp

        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )
        input_state_queue: queue.Queue[dict] = queue.Queue()
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=input_state_queue,
            transcript_queue=queue.Queue(),
        )

        async with app.run_test() as pilot:
            input_widget = app.query_one("#command-input", Input)
            input_widget.value = "现在runtime运行状态如何？"
            await pilot.pause()
            input_widget.value = ""
            await pilot.pause()

        nonempty = input_state_queue.get_nowait()
        empty = input_state_queue.get_nowait()
        self.assertEqual(nonempty["state"], "draft_nonempty")
        self.assertEqual(nonempty["draft_length"], 16)
        self.assertEqual(empty["state"], "draft_empty")
        self.assertEqual(empty["draft_length"], 0)

    async def test_textual_terminal_app_exits_after_quit_once_daemon_disconnects_even_if_thread_lingers(
        self,
    ) -> None:
        from device_edge.cli.terminal_tui import TerminalEdgeApp

        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )
        daemon.quit_requested = True
        daemon.connection_state = "disconnected"
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=queue.Queue(),
            transcript_queue=queue.Queue(),
        )
        lingering_thread = mock.Mock()
        lingering_thread.is_alive.return_value = True

        async with app.run_test() as pilot:
            app.session_thread = lingering_thread
            app.exit = mock.Mock()
            await pilot.pause()
            app._refresh_status_bar()
            app.exit.assert_called_once()

    def test_builds_bootstrap_frames_for_terminal_edge(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )

        bootstrap_frames = daemon.build_bootstrap_frames()

        self.assertEqual(bootstrap_frames[0]["type"], "connect")
        self.assertEqual(bootstrap_frames[1]["type"], "capability_announce")
        self.assertEqual(
            bootstrap_frames[1]["capabilities"],
            [
                "text.input",
                "notification.show",
                "terminal.context",
                "interaction.progress",
            ],
        )

    def test_builds_terminal_activity_observation_frame(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )

        frame = daemon.build_terminal_activity_frame(
            activity_state="active",
            observed_at="2026-06-22T10:10:00Z",
        )

        self.assertEqual(frame["type"], "observation_push")
        self.assertEqual(frame["capability"], "terminal.context")
        self.assertEqual(
            frame["payload"]["observations"][0]["name"],
            "terminal.activity_state",
        )
        self.assertEqual(
            frame["payload"]["observations"][0]["value"],
            "active",
        )

    def test_builds_pull_text_event_after_marking_terminal_active(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )

        frames = daemon.build_user_input_frames(
            text="hello runtime",
            observed_at="2026-06-22T10:10:00Z",
        )

        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0]["capability"], "terminal.context")
        self.assertEqual(
            frames[0]["payload"]["observations"][0]["value"],
            "active",
        )
        self.assertEqual(frames[1]["capability"], "text.input")
        self.assertEqual(frames[1]["payload"]["text"], "hello runtime")


class TerminalEdgeAsyncSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_expected_frame_wait_rejects_excess_deferred_frames(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )

        class NonAcknowledgingWebSocket:
            def __init__(self) -> None:
                self.received_frames = 0

            async def recv(self) -> str:
                self.received_frames += 1
                if self.received_frames > 65:
                    raise AssertionError("expected-frame wait did not stop")
                return json.dumps(
                    {
                        "type": "action_request",
                        "device_id": "terminal-edge-1",
                        "action": {
                            "capability": "notification.show",
                            "payload": {"title": "OpenHalo", "body": "queued"},
                        },
                    }
                )

        with self.assertRaisesRegex(RuntimeError, "deferred frames exceeded 64"):
            await daemon._recv_expected_frame(
                NonAcknowledgingWebSocket(),
                [],
                expected_type="event_ack",
            )

    async def test_daemon_session_keeps_action_request_when_progress_arrives_first(
        self,
    ) -> None:
        class ProgressBeforeActionWebSocket:
            def __init__(self) -> None:
                self.frames: asyncio.Queue[dict] = asyncio.Queue()

            async def send(self, raw_frame: str) -> None:
                frame = json.loads(raw_frame)
                if frame["type"] == "connect":
                    await self.frames.put({"type": "connect_ok"})
                    return
                if frame["type"] not in {"event_push", "observation_push"}:
                    return
                if frame["capability"] != "text.input":
                    await self.frames.put({"type": "event_ack"})
                    return
                await self.frames.put(
                    {
                        "type": "interaction_progress",
                        "device_id": "terminal-edge-1",
                        "progress": {
                            "version": 1,
                            "interaction_id": "interaction-1",
                            "interaction_turn_id": "interaction-turn-1",
                            "sequence": 1,
                            "phase": "deliberating",
                            "state": "active",
                            "occurred_at": "2026-07-18T10:00:00Z",
                            "presentation_hint": "working",
                        },
                    }
                )
                await self.frames.put({"type": "event_ack"})
                await self.frames.put(
                    {
                        "type": "action_request",
                        "device_id": "terminal-edge-1",
                        "request_id": "action-1",
                        "interaction_id": "interaction-1",
                        "interaction_turn_id": "interaction-turn-1",
                        "action": {
                            "capability": "notification.show",
                            "payload": {"title": "OpenHalo", "body": "Action result"},
                        },
                    }
                )

            async def recv(self) -> str:
                return json.dumps(await self.frames.get())

        stdout = io.StringIO()
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=stdout,
        )

        websocket = ProgressBeforeActionWebSocket()
        try:
            results = await asyncio.wait_for(
                daemon.run_scripted_session(
                    websocket=websocket,
                    scripted_inputs=[
                        {
                            "text": "run action",
                            "observed_at": "2026-07-18T10:00:00Z",
                        }
                    ],
                    startup_observed_at="2026-07-18T10:00:00Z",
                    idle_after_inputs=True,
                    idle_timeout_s=0.001,
                    max_idle_cycles=1,
                    max_action_requests=1,
                ),
                timeout=0.1,
            )
        except TimeoutError:
            results = []

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["request_id"], "action-1")
        self.assertIn("[progress] 正在理解你的请求...", stdout.getvalue())

    async def test_run_forever_stops_reconnecting_after_quit_command(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )
        session_calls: list[int] = []

        async def fake_run_scripted_session(**kwargs) -> list[dict]:
            session_calls.append(1)
            daemon.quit_requested = True
            return []

        daemon.run_scripted_session = fake_run_scripted_session  # type: ignore[method-assign]

        class FakeConnection:
            async def __aenter__(self):
                return object()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        original_connect = websockets.connect
        websockets.connect = lambda url: FakeConnection()  # type: ignore[assignment]
        try:
            await daemon.run_forever(
                url="ws://127.0.0.1:8765",
                max_sessions=5,
                enable_live_input=True,
            )
        finally:
            websockets.connect = original_connect  # type: ignore[assignment]

        self.assertEqual(len(session_calls), 1)

    async def test_daemon_session_handles_live_help_command_without_runtime_event(
        self,
    ) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            input_stream=io.StringIO("/help\n"),
            output_stream=io.StringIO(),
            timestamp_provider=lambda: "2026-06-22T10:09:00Z",
        )
        sent_frames: list[dict] = []

        class FakeWebSocket:
            def __init__(self) -> None:
                self.recv_count = 0

            async def send(self, payload: str) -> None:
                sent_frames.append(json.loads(payload))

            async def recv(self) -> str:
                self.recv_count += 1
                if self.recv_count == 1:
                    return json.dumps({"type": "connect_ok"})
                if self.recv_count == 2:
                    return json.dumps({"type": "event_ack"})
                raise RuntimeError("StopIteration")

        results = await daemon.run_scripted_session(
            websocket=FakeWebSocket(),
            scripted_inputs=[],
            startup_observed_at=None,
            idle_after_inputs=True,
            enable_live_input=True,
            max_idle_cycles=1,
            idle_timeout_s=0.01,
        )

        self.assertEqual(results, [])
        self.assertEqual(
            [frame["type"] for frame in sent_frames],
            ["connect", "capability_announce", "observation_push"],
        )
        self.assertFalse(
            any(frame.get("capability") == "text.input" for frame in sent_frames)
        )
        self.assertIn("Available local commands", daemon.output_stream.getvalue())

    async def test_daemon_session_reads_live_terminal_input_from_stdin(
        self,
    ) -> None:
        observed_at_values = iter(
            [
                "2026-06-22T10:09:00Z",
                "2026-06-22T10:10:00Z",
                "2026-06-22T10:11:00Z",
            ]
        )
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            input_stream=io.StringIO("\nhello runtime\n"),
            timestamp_provider=lambda: next(observed_at_values),
        )
        sent_frames: list[dict] = []
        class FakeWebSocket:
            def __init__(self) -> None:
                self.recv_count = 0
                self.post_text_ack_sent = False

            async def send(self, payload: str) -> None:
                sent_frames.append(json.loads(payload))

            async def recv(self) -> str:
                self.recv_count += 1
                if self.recv_count == 1:
                    return json.dumps({"type": "connect_ok"})
                if not any(
                    frame.get("capability") == "text.input" for frame in sent_frames
                ):
                    return json.dumps({"type": "event_ack"})
                if not self.post_text_ack_sent:
                    self.post_text_ack_sent = True
                    return json.dumps({"type": "event_ack"})
                return json.dumps(
                    {
                        "type": "action_request",
                        "device_id": "terminal-edge-1",
                        "action": {
                            "capability": "notification.show",
                            "payload": {
                                "title": "OpenHalo",
                                "body": "Runtime heard: hello runtime",
                            },
                        },
                    }
                )

        results = await daemon.run_scripted_session(
            websocket=FakeWebSocket(),
            scripted_inputs=[],
            startup_observed_at=None,
            idle_after_inputs=True,
            enable_live_input=True,
            max_action_requests=1,
        )

        self.assertEqual(len(results), 1)
        activity_frames = [
            frame
            for frame in sent_frames
            if frame.get("capability") == "terminal.context"
        ]
        text_frames = [
            frame for frame in sent_frames if frame.get("capability") == "text.input"
        ]

        self.assertGreaterEqual(len(activity_frames), 2)
        self.assertEqual(
            activity_frames[0]["payload"]["observations"][0]["observed_at"],
            "2026-06-22T10:09:00Z",
        )
        self.assertEqual(
            activity_frames[-1]["payload"]["observations"][0]["observed_at"],
            "2026-06-22T10:10:00Z",
        )
        self.assertEqual(len(text_frames), 1)
        self.assertEqual(text_frames[0]["payload"]["text"], "hello runtime")
        self.assertEqual(
            text_frames[0]["payload"]["observed_at"],
            "2026-06-22T10:10:00Z",
        )

    async def test_daemon_session_sends_tui_input_state_observations(
        self,
    ) -> None:
        observed_at_values = iter(
            [
                "2026-06-22T10:09:00Z",
                "2026-06-22T10:10:00Z",
                "2026-06-22T10:11:00Z",
            ]
        )
        input_state_queue: queue.Queue[dict] = queue.Queue()
        input_state_queue.put(
            {
                "state": "draft_nonempty",
                "draft_length": 16,
            }
        )
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            input_state_stream=input_state_queue,
            timestamp_provider=lambda: next(observed_at_values),
        )
        sent_frames: list[dict] = []

        class FakeWebSocket:
            def __init__(self) -> None:
                self.recv_count = 0

            async def send(self, payload: str) -> None:
                sent_frames.append(json.loads(payload))

            async def recv(self) -> str:
                self.recv_count += 1
                if self.recv_count == 1:
                    return json.dumps({"type": "connect_ok"})
                if self.recv_count in {2, 3}:
                    return json.dumps({"type": "event_ack"})
                if self.recv_count == 4:
                    await asyncio.sleep(0.05)
                    raise RuntimeError("StopIteration")
                return json.dumps({"type": "event_ack"})

        await daemon.run_scripted_session(
            websocket=FakeWebSocket(),
            scripted_inputs=[],
            startup_observed_at=None,
            idle_after_inputs=True,
            idle_timeout_s=0.01,
            max_idle_cycles=1,
        )

        input_state_frames = [
            frame
            for frame in sent_frames
            if frame.get("capability") == "terminal.context"
            and any(
                observation["name"] == "terminal.input_state"
                for observation in frame["payload"]["observations"]
            )
        ]
        self.assertEqual(len(input_state_frames), 1)
        observations = input_state_frames[0]["payload"]["observations"]
        self.assertEqual(observations[0]["value"], "draft_nonempty")
        self.assertEqual(observations[1]["name"], "terminal.input_draft_length")
        self.assertEqual(observations[1]["value"], 16)

    async def test_daemon_session_sends_tui_input_state_before_idle_when_draft_arrives_during_wait(
        self,
    ) -> None:
        observed_at_values = iter(
            [
                "2026-06-22T10:09:00Z",
                "2026-06-22T10:10:00Z",
                "2026-06-22T10:11:00Z",
            ]
        )
        input_state_queue: queue.Queue[dict] = queue.Queue()
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            input_state_stream=input_state_queue,
            timestamp_provider=lambda: next(observed_at_values),
        )
        sent_frames: list[dict] = []

        class FakeWebSocket:
            def __init__(self) -> None:
                self.recv_count = 0

            async def send(self, payload: str) -> None:
                sent_frames.append(json.loads(payload))

            async def recv(self) -> str:
                self.recv_count += 1
                if self.recv_count == 1:
                    return json.dumps({"type": "connect_ok"})
                if self.recv_count == 2:
                    return json.dumps({"type": "event_ack"})
                if self.recv_count == 3:
                    await asyncio.sleep(0.02)
                    return json.dumps({"type": "event_ack"})
                if self.recv_count == 4:
                    await asyncio.sleep(0.02)
                    return json.dumps({"type": "event_ack"})
                await asyncio.sleep(0.05)
                raise RuntimeError("StopIteration")

        async def inject_draft_state() -> None:
            await asyncio.sleep(0.005)
            input_state_queue.put(
                {
                    "state": "draft_nonempty",
                    "draft_length": 16,
                }
            )

        await asyncio.gather(
            daemon.run_scripted_session(
                websocket=FakeWebSocket(),
                scripted_inputs=[],
                startup_observed_at=None,
                idle_after_inputs=True,
                idle_timeout_s=0.05,
                max_idle_cycles=1,
            ),
            inject_draft_state(),
        )

        terminal_context_frames = [
            frame
            for frame in sent_frames
            if frame.get("capability") == "terminal.context"
        ]
        observed_names = [
            observation["name"]
            for frame in terminal_context_frames
            for observation in frame["payload"]["observations"]
        ]
        self.assertIn("terminal.input_state", observed_names)
        later_idle_index = next(
            (
                index
                for index, name in enumerate(observed_names[1:], start=1)
                if name == "terminal.activity_state"
            ),
            None,
        )
        if later_idle_index is not None:
            self.assertLess(
                observed_names.index("terminal.input_state"),
                later_idle_index,
            )

    async def test_daemon_session_reads_multiple_live_terminal_inputs_from_stdin(
        self,
    ) -> None:
        observed_at_values = iter(
            [
                "2026-06-22T10:09:00Z",
                "2026-06-22T10:10:00Z",
                "2026-06-22T10:11:00Z",
            ]
        )
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            input_stream=io.StringIO("hello?\nstatus?\n"),
            timestamp_provider=lambda: next(observed_at_values),
        )
        sent_frames: list[dict] = []
        recv_queue: list[dict] = [
            {"type": "connect_ok"},
            {"type": "event_ack"},
        ]

        class FakeWebSocket:
            async def send(self, payload: str) -> None:
                frame = json.loads(payload)
                sent_frames.append(frame)
                if frame.get("capability") == "terminal.context":
                    recv_queue.append({"type": "event_ack"})
                if frame.get("capability") == "text.input":
                    recv_queue.append({"type": "event_ack"})
                    recv_queue.append(
                        {
                            "type": "action_request",
                            "device_id": "terminal-edge-1",
                            "action": {
                                "capability": "notification.show",
                                "payload": {
                                    "title": "OpenHalo",
                                    "body": f"Runtime heard: {frame['payload']['text']}",
                                },
                            },
                        }
                    )

            async def recv(self) -> str:
                while not recv_queue:
                    await asyncio.sleep(0)
                return json.dumps(recv_queue.pop(0))

        results = await daemon.run_scripted_session(
            websocket=FakeWebSocket(),
            scripted_inputs=[],
            startup_observed_at=None,
            idle_after_inputs=True,
            enable_live_input=True,
            max_action_requests=2,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(
            [result["result"]["details"]["body"] for result in results],
            ["Runtime heard: hello?", "Runtime heard: status?"],
        )
        text_frames = [
            frame for frame in sent_frames if frame.get("capability") == "text.input"
        ]
        self.assertEqual(
            [frame["payload"]["text"] for frame in text_frames],
            ["hello?", "status?"],
        )

    async def test_daemon_session_keeps_resident_after_stdin_eof_until_runtime_push_arrives(
        self,
    ) -> None:
        observed_at_values = iter(
            [
                "2026-06-22T10:09:00Z",
                "2026-06-22T10:10:00Z",
            ]
        )
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            input_stream=io.StringIO("hello runtime\n"),
            output_stream=io.StringIO(),
            timestamp_provider=lambda: next(observed_at_values),
        )
        sent_frames: list[dict] = []
        recv_queue: list[dict] = [
            {"type": "connect_ok"},
            {"type": "event_ack"},
        ]

        class FakeWebSocket:
            async def send(self, payload: str) -> None:
                frame = json.loads(payload)
                sent_frames.append(frame)
                if frame.get("capability") == "terminal.context":
                    recv_queue.append({"type": "event_ack"})
                if frame.get("capability") == "text.input":
                    recv_queue.append({"type": "event_ack"})
                    recv_queue.append(
                        {
                            "type": "action_request",
                            "device_id": "terminal-edge-1",
                            "action": {
                                "capability": "notification.show",
                                "payload": {
                                    "title": "OpenHalo",
                                    "body": "Runtime heard: hello runtime",
                                },
                            },
                        }
                    )

            async def recv(self) -> str:
                while not recv_queue:
                    await asyncio.sleep(0)
                return json.dumps(recv_queue.pop(0))

        results = await daemon.run_scripted_session(
            websocket=FakeWebSocket(),
            scripted_inputs=[],
            startup_observed_at=None,
            idle_after_inputs=True,
            enable_live_input=True,
            max_action_requests=1,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]["result"]["details"]["body"],
            "Runtime heard: hello runtime",
        )

    async def test_daemon_session_keeps_resident_for_runtime_push_after_first_reply(
        self,
    ) -> None:
        observed_at_values = iter(
            [
                "2026-06-22T10:09:00Z",
                "2026-06-22T10:10:00Z",
            ]
        )
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            input_stream=io.StringIO("hello runtime\n"),
            output_stream=io.StringIO(),
            timestamp_provider=lambda: next(observed_at_values),
        )
        sent_frames: list[dict] = []
        recv_queue: list[dict] = [
            {"type": "connect_ok"},
            {"type": "event_ack"},
        ]
        injected_runtime_push = False

        class FakeWebSocket:
            async def send(self, payload: str) -> None:
                nonlocal injected_runtime_push
                frame = json.loads(payload)
                sent_frames.append(frame)
                if frame.get("capability") == "terminal.context":
                    recv_queue.append({"type": "event_ack"})
                if frame.get("capability") == "text.input":
                    recv_queue.append({"type": "event_ack"})
                    recv_queue.append(
                        {
                            "type": "action_request",
                            "device_id": "terminal-edge-1",
                            "action": {
                                "capability": "notification.show",
                                "payload": {
                                    "title": "OpenHalo",
                                    "body": "Runtime heard: hello runtime",
                                },
                            },
                        }
                    )
                if (
                    frame.get("type") == "action_result"
                    and frame["result"]["details"]["body"]
                    == "Runtime heard: hello runtime"
                    and not injected_runtime_push
                ):
                    injected_runtime_push = True
                    recv_queue.append(
                        {
                            "type": "action_request",
                            "device_id": "terminal-edge-1",
                            "action": {
                                "capability": "notification.show",
                                "payload": {
                                    "title": "OpenHalo",
                                    "body": "runtime push active",
                                },
                            },
                        }
                    )

            async def recv(self) -> str:
                while not recv_queue:
                    await asyncio.sleep(0)
                return json.dumps(recv_queue.pop(0))

        results = await daemon.run_scripted_session(
            websocket=FakeWebSocket(),
            scripted_inputs=[],
            startup_observed_at=None,
            idle_after_inputs=True,
            enable_live_input=True,
            max_action_requests=2,
        )

        self.assertEqual(
            [result["result"]["details"]["body"] for result in results],
            ["Runtime heard: hello runtime", "runtime push active"],
        )

    async def test_daemon_session_waits_for_delayed_runtime_push_after_first_reply(
        self,
    ) -> None:
        observed_at_values = iter(
            [
                "2026-06-22T10:09:00Z",
                "2026-06-22T10:10:00Z",
            ]
        )
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            input_stream=io.StringIO("hello runtime\n"),
            output_stream=io.StringIO(),
            timestamp_provider=lambda: next(observed_at_values),
        )
        recv_queue: asyncio.Queue[dict] = asyncio.Queue()
        await recv_queue.put({"type": "connect_ok"})
        await recv_queue.put({"type": "event_ack"})
        first_reply_delivered = asyncio.Event()

        class FakeWebSocket:
            async def send(self, payload: str) -> None:
                frame = json.loads(payload)
                if frame.get("capability") == "terminal.context":
                    await recv_queue.put({"type": "event_ack"})
                if frame.get("capability") == "text.input":
                    await recv_queue.put({"type": "event_ack"})
                    await recv_queue.put(
                        {
                            "type": "action_request",
                            "device_id": "terminal-edge-1",
                            "action": {
                                "capability": "notification.show",
                                "payload": {
                                    "title": "OpenHalo",
                                    "body": "Runtime heard: hello runtime",
                                },
                            },
                        }
                    )
                if (
                    frame.get("type") == "action_result"
                    and frame["result"]["details"]["body"]
                    == "Runtime heard: hello runtime"
                ):
                    first_reply_delivered.set()

            async def recv(self) -> str:
                frame = await recv_queue.get()
                return json.dumps(frame)

        async def inject_delayed_push() -> None:
            await first_reply_delivered.wait()
            await asyncio.sleep(0.05)
            await recv_queue.put(
                {
                    "type": "action_request",
                    "device_id": "terminal-edge-1",
                    "action": {
                        "capability": "notification.show",
                        "payload": {
                            "title": "OpenHalo",
                            "body": "runtime push active",
                        },
                    },
                }
            )

        injector_task = asyncio.create_task(inject_delayed_push())
        try:
            results = await asyncio.wait_for(
                daemon.run_scripted_session(
                    websocket=FakeWebSocket(),
                    scripted_inputs=[],
                    startup_observed_at=None,
                    idle_after_inputs=True,
                    enable_live_input=True,
                    max_action_requests=2,
                    idle_timeout_s=0.2,
                ),
                timeout=1,
            )
        finally:
            injector_task.cancel()
            with suppress(asyncio.CancelledError):
                await injector_task

        self.assertEqual(
            [result["result"]["details"]["body"] for result in results],
            ["Runtime heard: hello runtime", "runtime push active"],
        )

    async def test_daemon_session_sends_scripted_pull_input_and_terminal_activity(
        self,
    ) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )
        sent_frames: list[dict] = []
        recv_frames = iter(
            [
                {"type": "connect_ok"},
                {"type": "event_ack"},
                {"type": "event_ack"},
                {"type": "event_ack"},
                {
                    "type": "action_request",
                    "device_id": "terminal-edge-1",
                    "action": {
                        "capability": "notification.show",
                        "payload": {
                            "title": "OpenHalo",
                            "body": "Runtime heard: hello runtime",
                        },
                    },
                },
            ]
        )

        class FakeWebSocket:
            async def send(self, payload: str) -> None:
                sent_frames.append(json.loads(payload))

            async def recv(self) -> str:
                return json.dumps(next(recv_frames))

        results = await daemon.run_scripted_session(
            websocket=FakeWebSocket(),
            scripted_inputs=[
                {
                    "text": "hello runtime",
                    "observed_at": "2026-06-22T10:10:00Z",
                }
            ],
            startup_observed_at="2026-06-22T10:09:00Z",
            idle_after_inputs=True,
            max_action_requests=1,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(sent_frames[2]["capability"], "terminal.context")
        self.assertEqual(sent_frames[3]["capability"], "terminal.context")
        self.assertEqual(sent_frames[4]["capability"], "text.input")
        self.assertEqual(sent_frames[4]["payload"]["text"], "hello runtime")

    async def test_daemon_session_handles_runtime_push_and_returns_action_result(
        self,
    ) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )
        sent_frames: list[dict] = []
        recv_frames = iter(
            [
                {"type": "connect_ok"},
                {"type": "event_ack"},
                {
                    "type": "action_request",
                    "device_id": "terminal-edge-1",
                    "action": {
                        "capability": "notification.show",
                        "payload": {"title": "OpenHalo", "body": "runtime push"},
                    },
                },
            ]
        )

        class FakeWebSocket:
            async def send(self, payload: str) -> None:
                sent_frames.append(json.loads(payload))

            async def recv(self) -> str:
                return json.dumps(next(recv_frames))

        results = await daemon.run_scripted_session(
            websocket=FakeWebSocket(),
            scripted_inputs=[],
            startup_observed_at="2026-06-22T10:10:00Z",
            idle_after_inputs=True,
            max_action_requests=1,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["result"]["status"], "ok")
        self.assertEqual(
            results[0]["result"]["details"]["delivered_via"],
            "terminal.stdout",
        )
        self.assertEqual(sent_frames[0]["type"], "connect")
        self.assertEqual(sent_frames[1]["type"], "capability_announce")
        self.assertEqual(sent_frames[2]["capability"], "terminal.context")
        self.assertEqual(sent_frames[-1]["type"], "action_result")

    async def test_daemon_session_accepts_interaction_completion_without_action_request(
        self,
    ) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )
        sent_frames: list[dict] = []
        recv_frames = iter(
            [
                {"type": "connect_ok"},
                {"type": "event_ack"},
                {"type": "event_ack"},
                {"type": "event_ack"},
                {
                    "type": "interaction_update",
                    "device_id": "terminal-edge-1",
                    "interaction": {
                        "interaction_id": "interaction-1",
                        "status": "completed",
                        "summary": "Runtime status is healthy.",
                    },
                },
            ]
        )

        class FakeWebSocket:
            async def send(self, payload: str) -> None:
                sent_frames.append(json.loads(payload))

            async def recv(self) -> str:
                return json.dumps(next(recv_frames))

        results = await daemon.run_scripted_session(
            websocket=FakeWebSocket(),
            scripted_inputs=[
                {
                    "text": "check runtime status",
                    "observed_at": "2026-06-22T10:10:00Z",
                }
            ],
            startup_observed_at="2026-06-22T10:09:00Z",
            idle_after_inputs=True,
            max_action_requests=1,
        )

        self.assertEqual(results, [])
        self.assertFalse(daemon.pending_runtime_reply)
        self.assertEqual(sent_frames[-1]["capability"], "text.input")

    async def test_daemon_session_emits_idle_activity_after_timeout(
        self,
    ) -> None:
        observed_at_values = iter(
            [
                "2026-06-22T10:10:00Z",
                "2026-06-22T10:11:00Z",
            ]
        )
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            timestamp_provider=lambda: next(observed_at_values),
        )
        sent_frames: list[dict] = []

        class FakeWebSocket:
            def __init__(self) -> None:
                self.recv_count = 0

            async def send(self, payload: str) -> None:
                sent_frames.append(json.loads(payload))

            async def recv(self) -> str:
                self.recv_count += 1
                if self.recv_count == 1:
                    return json.dumps({"type": "connect_ok"})
                if self.recv_count == 2:
                    return json.dumps({"type": "event_ack"})
                if self.recv_count == 3:
                    await asyncio.sleep(0.05)
                    raise RuntimeError("StopIteration")
                return json.dumps({"type": "event_ack"})

        results = await daemon.run_scripted_session(
            websocket=FakeWebSocket(),
            scripted_inputs=[],
            startup_observed_at=None,
            idle_after_inputs=True,
            idle_timeout_s=0.01,
            idle_observed_at=None,
            max_idle_cycles=1,
        )

        self.assertEqual(results, [])
        self.assertEqual(sent_frames[-1]["capability"], "terminal.context")
        self.assertEqual(
            sent_frames[-1]["payload"]["observations"][0]["value"],
            "idle",
        )
        self.assertEqual(
            sent_frames[-1]["payload"]["observations"][0]["observed_at"],
            "2026-06-22T10:11:00Z",
        )

    async def test_daemon_session_cancels_pending_live_input_task_on_exit(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )
        sent_frames: list[dict] = []
        read_started = asyncio.Event()
        read_cancelled = asyncio.Event()

        async def fake_read_live_input_line() -> str | None:
            read_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                read_cancelled.set()
                raise

        daemon._read_live_input_line = fake_read_live_input_line  # type: ignore[method-assign]

        class FakeWebSocket:
            def __init__(self) -> None:
                self.recv_count = 0

            async def send(self, payload: str) -> None:
                sent_frames.append(json.loads(payload))

            async def recv(self) -> str:
                self.recv_count += 1
                if self.recv_count == 1:
                    return json.dumps({"type": "connect_ok"})
                if self.recv_count == 2:
                    return json.dumps({"type": "event_ack"})
                if self.recv_count == 3:
                    return json.dumps(
                        {
                            "type": "action_request",
                            "device_id": "terminal-edge-1",
                            "action": {
                                "capability": "notification.show",
                                "payload": {
                                    "title": "OpenHalo",
                                    "body": "runtime push",
                                },
                            },
                        }
                    )
                raise RuntimeError("StopIteration")

        results = await daemon.run_scripted_session(
            websocket=FakeWebSocket(),
            scripted_inputs=[],
            startup_observed_at="2026-06-22T10:10:00Z",
            idle_after_inputs=True,
            enable_live_input=True,
            max_action_requests=1,
        )

        self.assertEqual(len(results), 1)
        self.assertTrue(read_started.is_set())
        self.assertTrue(read_cancelled.is_set())


if __name__ == "__main__":
    unittest.main()
