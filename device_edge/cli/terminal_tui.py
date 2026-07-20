"""Full-screen Textual UI for the resident terminal edge daemon."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import queue
from queue import Empty
import threading
from typing import Callable

from rich.text import Text
from textual.app import App
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import Input
from textual.widgets import RichLog
from textual.widgets import Static


class QueueLineInput:
    """Queue-backed readline adapter for the daemon live-input path."""

    def __init__(self, line_queue: queue.Queue[str | None]) -> None:
        self.line_queue = line_queue

    def readline(self) -> str:
        line = self.line_queue.get()
        if line is None:
            return ""
        if line.endswith("\n"):
            return line
        return f"{line}\n"


class QueueLineOutput:
    """Line-buffering output adapter that forwards completed lines to the TUI."""

    def __init__(self, line_queue: queue.Queue[str]) -> None:
        self.line_queue = line_queue
        self._buffer = ""

    def write(self, value: str) -> int:
        self._buffer += value
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self.line_queue.put(line)
        return len(value)

    def flush(self) -> None:
        return None


class TerminalEdgeApp(App[None]):
    """Minimal full-screen terminal UI layered over the existing daemon."""

    CSS = """
    Screen {
        background: #10151f;
        color: #d8e0ea;
    }

    #frame {
        height: 100%;
        layout: vertical;
    }

    #title-bar {
        height: 1;
        padding: 0 1;
        background: #17324d;
        color: #f5f7fa;
        text-style: bold;
    }

    #status-bar {
        height: 1;
        padding: 0 1;
        background: #1f2633;
        color: #a8c2dd;
    }

    #transcript-log {
        height: 1fr;
        background: #0d1117;
        border: round #2e4057;
        padding: 0 1;
    }

    #command-input {
        margin: 1 0 0 0;
        border: round #406080;
    }

    #help-bar {
        height: 2;
        padding: 0 1;
        color: #8ea7c1;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(
        self,
        *,
        daemon,
        input_queue: queue.Queue[str | None],
        input_state_queue: queue.Queue[dict],
        transcript_queue: queue.Queue[str],
        start_session: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.daemon = daemon
        self.input_queue = input_queue
        self.input_state_queue = input_state_queue
        self.transcript_queue = transcript_queue
        self.start_session = start_session
        self.session_thread: threading.Thread | None = None

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(" OpenHalo  Terminal Edge", id="title-bar"),
            Static("", id="status-bar"),
            RichLog(id="transcript-log", wrap=True, markup=True, auto_scroll=True),
            Input(
                placeholder="Message runtime or use /help /status /history /quit",
                id="command-input",
            ),
            Static(
                "Enter sends to runtime. Local commands stay on-device: "
                "/help /status /history /quit",
                id="help-bar",
            ),
            id="frame",
        )

    def on_mount(self) -> None:
        self.query_one("#command-input", Input).focus()
        self._refresh_status_bar()
        self.set_interval(0.1, self._drain_transcript_queue)
        self.set_interval(0.1, self._refresh_status_bar)
        if self.start_session is not None:
            self.session_thread = threading.Thread(
                target=self.start_session,
                name="terminal-edge-tui-session",
                daemon=True,
            )
            self.session_thread.start()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            event.input.value = ""
            return
        self.input_queue.put(text)
        event.input.value = ""

    async def on_input_changed(self, event: Input.Changed) -> None:
        draft = event.value
        self.input_state_queue.put(
            {
                "state": "draft_nonempty" if draft else "draft_empty",
                "draft_length": len(draft),
            }
        )

    def action_quit(self) -> None:
        self.input_queue.put("/quit")

    def build_status_text(self) -> str:
        pending_flag = "waiting" if self.daemon.pending_runtime_reply else "ready"
        return (
            f"device={self.daemon.client.device_id} "
            f"connection={self.daemon.connection_state} "
            f"activity={self.daemon.terminal_activity_state} "
            f"state={pending_flag} "
            f"user={self.daemon.user_request_count} "
            f"runtime={self.daemon.runtime_message_count} "
            f"local={self.daemon.local_command_count}"
        )

    def _refresh_status_bar(self) -> None:
        try:
            status_bar = self.query_one("#status-bar", Static)
        except NoMatches:
            return
        status_bar.update(self.build_status_text())
        if self.daemon.quit_requested and self.daemon.connection_state == "disconnected":
            self.exit()
            return
        if (
            self.session_thread is not None
            and not self.session_thread.is_alive()
            and self.daemon.quit_requested
        ):
            self.exit()

    def _drain_transcript_queue(self) -> None:
        try:
            transcript = self.query_one("#transcript-log", RichLog)
        except NoMatches:
            return
        while True:
            try:
                line = self.transcript_queue.get_nowait()
            except Empty:
                break
            transcript.write(self._format_transcript_line(line))

    @staticmethod
    def _format_transcript_line(line: str) -> Text:
        if line.startswith("[system]"):
            return Text(line, style="bold #82cfff")
        if line.startswith("[user]"):
            return Text(line, style="bold #7be0ad")
        if line.startswith("[runtime]"):
            return Text(line, style="bold #ffd27f")
        return Text(line, style="#d8e0ea")


def create_textual_terminal_app(
    *,
    url: str,
    token: str,
    auth_kind: str | None = None,
    device_id: str,
    startup_observed_at: str | None,
    idle_timeout_s: float,
    idle_observed_at: str | None,
    max_idle_cycles: int | None,
    max_action_requests: int | None,
    max_sessions: int | None,
    stdin_observed_at: str | None,
    scripted_inputs: list[dict],
    diagnostic_recorder=None,
) -> TerminalEdgeApp:
    from device_edge.cli.terminal_daemon import TerminalEdgeDaemon

    input_queue: queue.Queue[str | None] = queue.Queue()
    input_state_queue: queue.Queue[dict] = queue.Queue()
    transcript_queue: queue.Queue[str] = queue.Queue()
    daemon = TerminalEdgeDaemon(
        device_id=device_id,
        token=token,
        auth_kind=auth_kind,
        output_stream=QueueLineOutput(transcript_queue),
        input_stream=QueueLineInput(input_queue),
        input_state_stream=input_state_queue,
        stdin_observed_at=stdin_observed_at,
        diagnostic_recorder=diagnostic_recorder,
    )

    def start_session() -> None:
        asyncio.run(
            daemon.run_forever(
                url=url,
                scripted_inputs=scripted_inputs,
                startup_observed_at=startup_observed_at,
                idle_timeout_s=idle_timeout_s,
                idle_observed_at=idle_observed_at,
                max_idle_cycles=max_idle_cycles,
                max_action_requests=max_action_requests,
                max_sessions=max_sessions,
                enable_live_input=True,
            )
        )

    return TerminalEdgeApp(
        daemon=daemon,
        input_queue=input_queue,
        input_state_queue=input_state_queue,
        transcript_queue=transcript_queue,
        start_session=start_session,
    )


def run_textual_terminal_daemon(
    *,
    url: str,
    token: str,
    auth_kind: str | None = None,
    device_id: str,
    startup_observed_at: str | None,
    idle_timeout_s: float,
    idle_observed_at: str | None,
    max_idle_cycles: int | None,
    max_action_requests: int | None,
    max_sessions: int | None,
    stdin_observed_at: str | None,
    scripted_inputs: list[dict],
    diagnostic_recorder=None,
) -> None:
    app = create_textual_terminal_app(
        url=url,
        token=token,
        auth_kind=auth_kind,
        device_id=device_id,
        startup_observed_at=startup_observed_at,
        idle_timeout_s=idle_timeout_s,
        idle_observed_at=idle_observed_at,
        max_idle_cycles=max_idle_cycles,
        max_action_requests=max_action_requests,
        max_sessions=max_sessions,
        stdin_observed_at=stdin_observed_at,
        scripted_inputs=scripted_inputs,
        diagnostic_recorder=diagnostic_recorder,
    )
    app.run()


__all__ = [
    "QueueLineInput",
    "QueueLineOutput",
    "TerminalEdgeApp",
    "create_textual_terminal_app",
    "run_textual_terminal_daemon",
]
