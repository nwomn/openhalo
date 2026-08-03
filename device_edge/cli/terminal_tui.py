"""Full-screen Textual UI for the resident terminal edge daemon."""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import suppress
import queue
from queue import Empty
import sys
import threading
from typing import Callable

from rich.text import Text
from textual.app import App
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Input
from textual.widgets import Static

from device_edge.cli.presentation import OutcomeReceipt
from device_edge.cli.presentation import toggle_receipt


def restore_terminal_surface(output_stream=None) -> None:
    """Leave a clean visible terminal surface after Textual returns control."""

    stream = output_stream or sys.stdout
    if not stream.isatty():
        return
    stream.write("\x1b[0m\x1b[?25h\x1b[2J\x1b[H")
    stream.flush()


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


class OutcomeReceiptWidget(Static):
    """Focusable local-only expansion control for one safe outcome receipt."""

    can_focus = True

    def __init__(self, receipt: OutcomeReceipt, *, on_toggle: Callable[[str], None]) -> None:
        super().__init__(id=f"receipt-{receipt.interaction_id}")
        self.receipt = receipt
        self._on_toggle = on_toggle

    def set_receipt(self, receipt: OutcomeReceipt) -> None:
        self.receipt = receipt
        self.refresh()

    def toggle(self) -> None:
        self._on_toggle(self.receipt.interaction_id)

    def on_click(self) -> None:
        self.focus()
        self.toggle()

    def on_key(self, event) -> None:
        if event.key not in {"enter", "space"}:
            return
        event.stop()
        self.toggle()

    def render(self) -> Text:
        if not self.receipt.expanded:
            return Text(self.receipt.compact_line, style="bold #a8d8b9")
        lines = [self.receipt.compact_line]
        for entry in self.receipt.entries:
            timestamp = entry.occurred_at[11:16] if len(entry.occurred_at) >= 16 else entry.occurred_at
            detail = entry.device_name or _receipt_kind_label(entry.kind)
            lines.append(f"{timestamp}  {detail}")
        if self.receipt.summary:
            lines.extend(("", self.receipt.summary))
        return Text("\n".join(lines), style="#d8e0ea")


def _receipt_kind_label(kind: str) -> str:
    return {
        "request_received": "Request received",
        "started": "OpenHalo started",
        "delivery": "Delivered",
        "confirmed": "Confirmed",
        "failed": "Could not complete",
    }.get(kind, "Updated")


class TerminalEdgeApp(App[None]):
    """Minimal full-screen terminal UI layered over the existing daemon."""

    _local_commands = ("/help", "/status", "/history", "/quit")
    _history_limit = 100

    CSS = """
    Screen {
        background: #10130f;
        color: #e8ebe4;
    }

    #frame {
        height: 100%;
        layout: vertical;
    }

    #app-header {
        height: 4;
        padding: 0 2;
        background: #1a2019;
        border-bottom: solid #323c30;
    }

    #header-copy {
        width: 1fr;
        height: 4;
        padding: 1 0;
    }

    #edge-title {
        height: 1;
        color: #f1f5ed;
        text-style: bold;
    }

    #edge-context {
        height: 1;
        color: #9da99a;
    }

    #connection-status {
        width: auto;
        min-width: 15;
        height: 4;
        color: #8ed5a0;
        content-align: center middle;
        text-style: bold;
    }

    #transcript-log {
        height: 1fr;
        background: #10130f;
        border: none;
        padding: 1 2;
        scrollbar-color: #3a4638;
        scrollbar-color-hover: #5d7258;
    }

    #active-progress {
        height: 1;
        padding: 0 2;
        background: #151b15;
        color: #abc8b1;
    }

    OutcomeReceiptWidget {
        width: 100%;
        margin: 1 0 0 0;
        padding: 0 1;
        border-left: tall #618a6a;
        background: #151b15;
        color: #d4e1d0;
    }

    OutcomeReceiptWidget:focus {
        border-left: tall #a6d9a9;
        background: #202a20;
    }

    .transcript-line {
        width: 100%;
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1;
    }

    #composer-shell {
        height: 5;
        padding: 0 2;
        background: #151a14;
        border-top: solid #2d372c;
    }

    #composer-label {
        height: 1;
        color: #9da99a;
    }

    #command-input {
        height: 3;
        border: tall #52694f;
        background: #1b211a;
        color: #edf2e9;
    }

    #command-input:focus {
        border: tall #91c497;
    }

    #help-bar {
        height: 1;
        padding: 0 2;
        background: #151a14;
        color: #899687;
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
        self._receipt_widgets: dict[str, OutcomeReceiptWidget] = {}
        self._transcript_widgets: deque[Static] = deque()
        self._command_history: deque[str] = deque(maxlen=self._history_limit)
        self._history_index: int | None = None
        self._history_draft = ""

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                Vertical(
                    Static("OpenHalo", id="edge-title"),
                    Static(self._edge_context_text(), id="edge-context"),
                    id="header-copy",
                ),
                Static("", id="connection-status"),
                id="app-header",
            ),
            VerticalScroll(id="transcript-log"),
            Static("", id="active-progress"),
            Vertical(
                Static("Message OpenHalo", id="composer-label"),
                Input(
                    placeholder="Write a message or use /help",
                    id="command-input",
                ),
                id="composer-shell",
            ),
            Static(self.build_help_text(), id="help-bar"),
            id="frame",
        )

    def _edge_context_text(self) -> str:
        display_name = self.daemon.client.session_link.display_name
        return f"Terminal Edge · {display_name}"

    def on_mount(self) -> None:
        composer = self.query_one("#command-input", Input)
        composer.value = self.daemon.presentation.draft
        composer.focus()
        self._refresh_status_bar()
        self._refresh_help_bar()
        self._refresh_active_progress()
        self._drain_transcript_queue()
        self.set_interval(0.1, self._drain_transcript_queue)
        self.set_interval(0.1, self._refresh_status_bar)
        self.set_interval(0.1, self._refresh_help_bar)
        self.set_interval(0.1, self._refresh_active_progress)
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
        if not self._command_history or self._command_history[-1] != text:
            self._command_history.append(text)
        self._history_index = None
        self._history_draft = ""
        self.input_queue.put(text)
        event.input.value = ""

    async def on_input_changed(self, event: Input.Changed) -> None:
        draft = event.value
        self.daemon.set_draft(draft)
        self.input_state_queue.put(
            {
                "state": "draft_nonempty" if draft else "draft_empty",
                "draft_length": len(draft),
            }
        )

    def on_key(self, event) -> None:
        try:
            composer = self.query_one("#command-input", Input)
        except NoMatches:
            return
        if not composer.has_focus:
            return
        if event.key == "tab" and self._complete_local_command(composer):
            event.prevent_default()
            event.stop()
            return
        if event.key == "tab" and not composer.value and self._focus_latest_receipt():
            event.prevent_default()
            event.stop()
            return
        if event.key == "up" and self._navigate_history(composer, direction=-1):
            event.prevent_default()
            event.stop()
            return
        if event.key == "down" and self._navigate_history(composer, direction=1):
            event.prevent_default()
            event.stop()
            return
        if event.key == "escape":
            composer.value = ""
            self._history_index = None
            self._history_draft = ""
            event.prevent_default()
            event.stop()

    def _complete_local_command(self, composer: Input) -> bool:
        value = composer.value
        if not value.startswith("/") or any(character.isspace() for character in value):
            return False
        matches = [command for command in self._local_commands if command.startswith(value)]
        if len(matches) != 1:
            return False
        composer.value = matches[0]
        return True

    def _focus_latest_receipt(self) -> bool:
        if not self._receipt_widgets:
            return False
        next(reversed(self._receipt_widgets.values())).focus()
        return True

    def _navigate_history(self, composer: Input, *, direction: int) -> bool:
        if not self._command_history:
            return False
        history = list(self._command_history)
        if direction < 0:
            if self._history_index is None:
                self._history_draft = composer.value
                self._history_index = len(history) - 1
            else:
                self._history_index = max(self._history_index - 1, 0)
            composer.value = history[self._history_index]
            return True
        if self._history_index is None:
            return False
        if self._history_index >= len(history) - 1:
            composer.value = self._history_draft
            self._history_index = None
            self._history_draft = ""
            return True
        self._history_index += 1
        composer.value = history[self._history_index]
        return True

    def action_quit(self) -> None:
        self.input_queue.put("/quit")

    def build_status_text(self, max_width: int | None = None) -> str:
        labels = {
            "connected": "Connected",
            "connecting": "Connecting",
            "retrying": "Reconnecting",
            "disconnected": "Offline",
            "failed": "Needs attention",
        }
        text = f"● {labels.get(self.daemon.connection_state, 'Connecting')}"
        if max_width is None or max_width <= 0 or len(text) <= max_width:
            return text
        return text[:max_width]

    @staticmethod
    def build_help_text(max_width: int | None = None) -> str:
        options = (
            "Enter to send · ↑↓ history · Tab commands/receipt · "
            "coding prompts use /accept or /allow",
            "Enter to send · ↑↓ history · Tab commands · /help · /quit",
            "Enter to send · /quit",
        )
        if max_width is None or max_width <= 0:
            return options[0]
        return next(
            (option for option in options if len(option) <= max_width),
            options[-1][:max_width],
        )

    def _refresh_status_bar(self) -> None:
        try:
            status_bar = self.query_one("#connection-status", Static)
        except NoMatches:
            return
        status_bar.update(
            self.build_status_text(max_width=status_bar.size.width or None)
        )
        if self.daemon.quit_requested and self.daemon.connection_state == "disconnected":
            self.exit()
            return
        if (
            self.session_thread is not None
            and not self.session_thread.is_alive()
            and self.daemon.quit_requested
        ):
            self.exit()

    def _refresh_help_bar(self) -> None:
        try:
            help_bar = self.query_one("#help-bar", Static)
        except NoMatches:
            return
        help_bar.update(self.build_help_text(max_width=help_bar.size.width or None))

    def _drain_transcript_queue(self) -> None:
        try:
            transcript = self.query_one("#transcript-log", VerticalScroll)
        except NoMatches:
            return
        while True:
            try:
                line = self.transcript_queue.get_nowait()
            except Empty:
                break
            if line.startswith("[progress]"):
                continue
            if self._mount_receipt_for_line(line):
                continue
            self._mount_transcript_line(transcript, line)

    def _refresh_active_progress(self) -> None:
        try:
            active_progress = self.query_one("#active-progress", Static)
        except NoMatches:
            return
        phase = next(reversed(self.daemon.presentation.active_progress.values()), None)
        message = self.daemon.progress_messages.get(phase, "")
        active_progress.update(f"◇ {message}" if message else "")

    def _mount_transcript_line(self, transcript: VerticalScroll, line: str) -> None:
        widget = Static(
            self._format_transcript_line(line),
            classes="transcript-line",
        )
        self._mount_transcript_widget(transcript, widget)

    def _mount_transcript_widget(
        self, transcript: VerticalScroll, widget: Static
    ) -> None:
        transcript.mount(widget)
        self._transcript_widgets.append(widget)
        while len(self._transcript_widgets) > self.daemon.transcript_limit:
            self._transcript_widgets.popleft().remove()
        transcript.scroll_end(animate=False)

    def _mount_receipt_for_line(self, line: str) -> bool:
        if not line.startswith("[receipt] "):
            return False
        compact_line = line.removeprefix("[receipt] ")
        receipt = next(
            (
                candidate
                for candidate in reversed(list(self.daemon.presentation.receipts.values()))
                if candidate.compact_line == compact_line
            ),
            None,
        )
        if receipt is None:
            return False
        widget = self._receipt_widgets.get(receipt.interaction_id)
        if widget is None:
            widget = OutcomeReceiptWidget(receipt, on_toggle=self._toggle_receipt)
            self._receipt_widgets[receipt.interaction_id] = widget
            transcript = self.query_one("#transcript-log", VerticalScroll)
            self._mount_transcript_widget(transcript, widget)
        else:
            widget.set_receipt(receipt)
        return True

    def _toggle_receipt(self, interaction_id: str) -> None:
        self.daemon.presentation = toggle_receipt(
            self.daemon.presentation,
            interaction_id,
        )
        receipt = self.daemon.presentation.receipts.get(interaction_id)
        widget = self._receipt_widgets.get(interaction_id)
        if receipt is not None and widget is not None:
            widget.set_receipt(receipt)

    @staticmethod
    def _format_transcript_line(line: str) -> Text:
        if line.startswith("[system]"):
            return Text.assemble(
                ("System  ", "bold #8da9c5"),
                (line.removeprefix("[system]").strip(), "#aeb9c4"),
            )
        if line.startswith("[user]"):
            return Text.assemble(
                ("You  ", "bold #9fddb0"),
                (line.removeprefix("[user]").strip(), "#e2eee1"),
            )
        if line.startswith("[runtime]"):
            return Text.assemble(
                ("OpenHalo  ", "bold #d7c18e"),
                (line.removeprefix("[runtime]").strip(), "#edf0e8"),
            )
        return Text(line, style="#d8e0ea")


def create_textual_terminal_app(
    *,
    url: str,
    device_id: str,
    identity_home,
    display_name: str | None,
    startup_observed_at: str | None,
    idle_timeout_s: float,
    idle_observed_at: str | None,
    max_idle_cycles: int | None,
    max_action_requests: int | None,
    max_sessions: int | None,
    stdin_observed_at: str | None,
    scripted_inputs: list[dict],
    diagnostic_recorder=None,
    coding_enabled: bool = False,
    coding_workspace=None,
) -> TerminalEdgeApp:
    from device_edge.cli.terminal_daemon import TerminalEdgeDaemon
    from device_edge.shared.identity import load_or_create_identity

    input_queue: queue.Queue[str | None] = queue.Queue()
    input_state_queue: queue.Queue[dict] = queue.Queue()
    transcript_queue: queue.Queue[str] = queue.Queue()
    daemon = TerminalEdgeDaemon(
        device_id=device_id,
        audience=url,
        identity=load_or_create_identity(identity_home, device_id)
        if identity_home is not None
        else None,
        display_name=display_name,
        output_stream=QueueLineOutput(transcript_queue),
        input_stream=QueueLineInput(input_queue),
        input_state_stream=input_state_queue,
        stdin_observed_at=stdin_observed_at,
        coding_enabled=coding_enabled,
        coding_workspace=coding_workspace,
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
    device_id: str,
    identity_home,
    display_name: str | None,
    startup_observed_at: str | None,
    idle_timeout_s: float,
    idle_observed_at: str | None,
    max_idle_cycles: int | None,
    max_action_requests: int | None,
    max_sessions: int | None,
    stdin_observed_at: str | None,
    scripted_inputs: list[dict],
    diagnostic_recorder=None,
    coding_enabled: bool = False,
    coding_workspace=None,
) -> None:
    app = create_textual_terminal_app(
        url=url,
        device_id=device_id,
        identity_home=identity_home,
        display_name=display_name,
        startup_observed_at=startup_observed_at,
        idle_timeout_s=idle_timeout_s,
        idle_observed_at=idle_observed_at,
        max_idle_cycles=max_idle_cycles,
        max_action_requests=max_action_requests,
        max_sessions=max_sessions,
        stdin_observed_at=stdin_observed_at,
        scripted_inputs=scripted_inputs,
        diagnostic_recorder=diagnostic_recorder,
        coding_enabled=coding_enabled,
        coding_workspace=coding_workspace,
    )
    try:
        app.run()
    finally:
        restore_terminal_surface()


__all__ = [
    "QueueLineInput",
    "QueueLineOutput",
    "TerminalEdgeApp",
    "create_textual_terminal_app",
    "restore_terminal_surface",
    "run_textual_terminal_daemon",
]
