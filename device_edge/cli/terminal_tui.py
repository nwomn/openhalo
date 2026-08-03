"""Full-screen Textual UI for the resident terminal edge daemon."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import queue
from queue import Empty
import threading
from typing import Callable

from rich.text import Text
from textual import events
from textual.app import App
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import Button
from textual.widgets import Input
from textual.widgets import LoadingIndicator
from textual.widgets import RichLog
from textual.widgets import Static

from device_edge.cli.terminal_ui_state import DaemonUiSnapshot
from device_edge.cli.terminal_ui_state import InputHistory
from device_edge.cli.terminal_ui_state import SlashCommandCatalog
from device_edge.cli.terminal_ui_state import TerminalUiReducer
from device_edge.cli.terminal_ui_state import TranscriptEntry


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

    async def readline_async(self) -> str:
        while True:
            try:
                line = self.line_queue.get_nowait()
            except Empty:
                await asyncio.sleep(0.05)
                continue
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
        self._lock = threading.Lock()

    def write(self, value: str) -> int:
        with self._lock:
            self._buffer += value
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                self.line_queue.put(line)
        return len(value)

    def flush(self) -> None:
        return None


class TerminalEdgeApp(App[None]):
    """Conversation-first terminal UI layered over the resident edge daemon."""

    CSS = """
    Screen {
        background: #0d1117;
        color: #cdd6f4;
    }

    #frame {
        height: 100%;
        layout: vertical;
        background: #0d1117;
    }

    #app-header {
        height: 2;
        padding: 0 3 0 3;
        align: left middle;
        background: transparent;
        border-bottom: tall #1f2430;
    }

    #title-bar {
        width: 1fr;
        color: #f2f7fb;
        text-style: bold;
    }

    #device-summary {
        width: auto;
        min-width: 14;
        height: 1;
        padding: 0 1;
        border: none;
        color: #8f9dad;
        background: transparent;
        text-style: none;
    }

    #device-summary:hover, #device-summary.open {
        color: #c4d1de;
        background: #161d27;
    }

    #device-overview {
        display: none;
        height: auto;
        max-height: 9;
        margin: 0 3;
        padding: 1 2;
        color: #94a3b5;
        background: #111720;
        border-left: tall #39516b;
    }

    #device-overview.visible {
        display: block;
    }

    #connection-chip {
        width: auto;
        padding: 0 0 0 1;
        color: #95d2a8;
        text-style: bold;
    }

    #connection-chip.connecting, #connection-chip.reconnecting {
        color: #f0c170;
    }

    #connection-chip.offline {
        color: #6e7681;
    }

    #status-bar {
        height: 1;
        padding: 0 3 0 3;
        color: #6e7681;
        background: transparent;
    }

    #transcript-log {
        height: 1fr;
        min-height: 6;
        padding: 0 3 0 4;
        background: #0d1117;
        border: none;
        scrollbar-color: #2a3140;
        scrollbar-background: transparent;
        scrollbar-size-vertical: 1;
    }

    #active-interaction {
        height: 1;
        padding: 0 3;
        align: left middle;
        border-left: tall #39516b;
        background: transparent;
    }

    #active-interaction.idle {
        display: none;
    }

    #active-interaction.active, #active-interaction.route {
        border-left: tall #73b7ff;
    }

    #active-interaction.waiting {
        border-left: tall #d9b97d;
    }

    #active-interaction.connecting, #active-interaction.reconnecting {
        border-left: tall #f0c170;
    }

    #active-interaction.offline {
        border-left: tall #6e7681;
    }

    #active-interaction.recovered {
        border-left: tall #7dca9b;
        background: #0f1714;
    }

    #active-interaction.error {
        border-left: tall #f08080;
        background: #1a1014;
    }

    #activity-spinner {
        width: 2;
        height: 1;
        color: #73b7ff;
    }

    #active-interaction.waiting #activity-spinner,
    #active-interaction.connecting #activity-spinner,
    #active-interaction.reconnecting #activity-spinner {
        color: #f0c170;
    }

    #active-interaction.error #activity-spinner {
        color: #f08080;
    }

    #active-copy {
        width: 1fr;
        height: 1;
        align: left middle;
    }

    #active-title {
        width: auto;
        height: 1;
        color: #dde6f2;
        text-style: bold;
    }

    #active-detail {
        width: 1fr;
        height: 1;
        padding: 0 0 0 2;
        color: #8aa0b8;
    }

    #active-interaction.error #active-detail {
        color: #c0a4a4;
    }

    #command-suggestions {
        display: none;
        height: auto;
        max-height: 7;
        margin: 0 3 0 3;
        padding: 0 1 0 2;
        color: #a8c4da;
        background: transparent;
        border-left: tall #39516b;
    }

    #command-suggestions.visible {
        display: block;
    }

    #composer-shell {
        height: auto;
        margin: 1 3 0 3;
        padding: 0 1 0 1;
        align: left middle;
        background: #121821;
        border-bottom: tall #39516b;
    }

    #composer-shell:focus-within {
        border-bottom: tall #73b7ff;
    }

    #composer-prompt {
        width: 1;
        color: #73b7ff;
        text-style: bold;
    }

    #command-input {
        width: 1fr;
        height: 1;
        border: none;
        background: transparent;
        padding: 0 1;
        color: #dce6f1;
    }

    #command-input:focus {
        border: none;
    }

    #composer-note {
        display: none;
        height: 1;
        margin: 0 3;
        padding: 0 1;
        color: #d9b97d;
    }

    #composer-note.visible {
        display: block;
    }

    #help-bar {
        height: 1;
        padding: 1 3 0 3;
        color: #4b5663;
        background: transparent;
    }

    Screen.narrow #status-bar {
        display: none;
    }

    Screen.narrow #app-header {
        padding: 0 1 0 2;
    }

    Screen.narrow #transcript-log {
        padding: 0 1 0 2;
    }

    Screen.narrow #active-interaction {
        padding: 0 1 0 2;
    }

    Screen.narrow #device-summary {
        display: none;
    }

    Screen.narrow #device-overview {
        margin: 0 1;
    }

    Screen.narrow #composer-shell {
        margin: 1 1 0 1;
    }

    Screen.narrow #composer-note {
        margin: 0 1;
    }

    Screen.short #help-bar {
        height: 1;
    }

    Screen.short #active-detail {
        display: none;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear_transcript", "Clear"),
        ("ctrl+d", "toggle_devices", "Devices"),
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
        self.reducer = TerminalUiReducer()
        self.input_history = InputHistory()
        self.command_catalog = SlashCommandCatalog()
        self._history_value_pending: str | None = None
        self._last_snapshot: DaemonUiSnapshot | None = None
        self._last_status_text = ""
        self._recovery_hide_timer = None

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                Static(
                    f"◯  OpenHalo  ·  {self.daemon.client.device_id}",
                    id="title-bar",
                ),
                Button("Global thread", id="device-summary", variant="default"),
                Static("○ Offline", id="connection-chip", classes="offline"),
                id="app-header",
            ),
            Static("", id="status-bar"),
            Static("", id="device-overview"),
            RichLog(
                id="transcript-log",
                max_lines=1200,
                min_width=1,
                wrap=True,
                markup=False,
                auto_scroll=True,
            ),
            Horizontal(
                LoadingIndicator(id="activity-spinner"),
                Horizontal(
                    Static("", id="active-title"),
                    Static("", id="active-detail"),
                    id="active-copy",
                ),
                id="active-interaction",
                classes="idle",
            ),
            Static("", id="command-suggestions"),
            Horizontal(
                Static("›", id="composer-prompt"),
                Input(
                    placeholder="Message OpenHalo, or use /help for local commands",
                    id="command-input",
                    compact=True,
                ),
                id="composer-shell",
            ),
            Static("", id="composer-note"),
            Static(
                "Enter send  ·  ↑↓ history  ·  Tab commands  ·  "
                f"Ctrl+D devices  ·  Ctrl+L clear  ·  {SlashCommandCatalog.help_text()}",
                id="help-bar",
            ),
            id="frame",
        )

    def on_mount(self) -> None:
        self.query_one("#command-input", Input).focus()
        self._apply_responsive_classes(self.size.width, self.size.height)
        self._refresh_ui()
        self.set_interval(0.08, self._refresh_ui)
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
        if text == "/clear":
            self.input_history.record(text)
            self.daemon.local_command_count += 1
            self.action_clear_transcript()
            event.input.value = ""
            return
        if text.startswith("/"):
            self.input_history.record(text)
            self.daemon.handle_local_input(text)
            self.input_queue.put("")
            event.input.value = ""
            return
        if self.daemon.connection_state != "connected":
            return
        self.input_history.record(text)
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
        if self._history_value_pending == draft:
            self._history_value_pending = None
        else:
            self.input_history.reset_navigation()
        self._refresh_command_suggestions(draft)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "device-summary":
            self.action_toggle_devices()

    def on_key(self, event: events.Key) -> None:
        try:
            input_widget = self.query_one("#command-input", Input)
            transcript = self.query_one("#transcript-log", RichLog)
        except NoMatches:
            return
        if event.key == "escape":
            self.query_one("#command-suggestions", Static).remove_class("visible")
            self.query_one("#device-overview", Static).remove_class("visible")
            self.query_one("#device-summary", Button).remove_class("open")
            input_widget.focus()
            event.prevent_default().stop()
            return
        if self.focused is input_widget:
            if event.key == "up":
                value = self.input_history.previous(input_widget.value)
                self._history_value_pending = value
                input_widget.value = value
                input_widget.cursor_position = len(input_widget.value)
                event.prevent_default().stop()
                return
            if event.key == "down":
                value = self.input_history.next(input_widget.value)
                self._history_value_pending = value
                input_widget.value = value
                input_widget.cursor_position = len(input_widget.value)
                event.prevent_default().stop()
                return
            if event.key in {"tab", "shift+tab"} and input_widget.value.startswith("/"):
                direction = -1 if event.key == "shift+tab" else 1
                input_widget.value = self.command_catalog.complete(
                    input_widget.value,
                    direction,
                )
                input_widget.cursor_position = len(input_widget.value)
                event.prevent_default().stop()
                return
        if event.key == "pageup":
            transcript.scroll_page_up()
            event.prevent_default().stop()
        elif event.key == "pagedown":
            transcript.scroll_page_down()
            event.prevent_default().stop()
        elif event.key == "end":
            transcript.scroll_end(animate=False)
            event.prevent_default().stop()

    def on_resize(self, event: events.Resize) -> None:
        self._apply_responsive_classes(event.size.width, event.size.height)

    def action_quit(self) -> None:
        if not self.daemon.quit_requested:
            self.daemon.handle_local_input("/quit")
            self.input_queue.put("")
        if self.daemon.connection_state == "disconnected":
            self.exit()

    def action_clear_transcript(self) -> None:
        try:
            self.query_one("#transcript-log", RichLog).clear()
        except NoMatches:
            return

    def action_toggle_devices(self) -> None:
        try:
            overview = self.query_one("#device-overview", Static)
            summary = self.query_one("#device-summary", Button)
        except NoMatches:
            return
        visible = overview.has_class("visible")
        overview.set_class(not visible, "visible")
        summary.set_class(not visible, "open")

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

    def _refresh_ui(self) -> None:
        try:
            snapshot = DaemonUiSnapshot.from_daemon(self.daemon)
            transcript = self.query_one("#transcript-log", RichLog)
        except NoMatches:
            return
        follow_output = transcript.is_vertical_scroll_end
        while True:
            try:
                line = self.transcript_queue.get_nowait()
            except Empty:
                break
            entry = self.reducer.consume_line(line, snapshot)
            if entry is not None:
                transcript.write(
                    self._format_transcript_entry(entry),
                    scroll_end=follow_output,
                )
        state_changed = snapshot != self._last_snapshot
        status_text = self.build_status_text()
        try:
            if state_changed:
                self._refresh_header(snapshot)
                self._refresh_device_overview(snapshot)
                self._refresh_active_interaction(snapshot)
                self._refresh_composer_note(snapshot)
                self._last_snapshot = snapshot
            if status_text != self._last_status_text:
                self.query_one("#status-bar", Static).update(status_text)
                self._last_status_text = status_text
        except NoMatches:
            return
        if self.daemon.quit_requested and self.daemon.connection_state == "disconnected":
            self.exit()
            return
        if (
            self.session_thread is not None
            and not self.session_thread.is_alive()
            and self.daemon.quit_requested
        ):
            self.exit()

    def _refresh_header(self, snapshot: DaemonUiSnapshot) -> None:
        chip = self.query_one("#connection-chip", Static)
        chip.remove_class("connected", "connecting", "reconnecting", "offline")
        labels = {
            "connected": "● Connected",
            "connecting": "◌ Connecting",
            "reconnecting": "↻ Reconnecting",
            "disconnected": "○ Offline",
        }
        css_class = snapshot.connection_state
        if css_class == "disconnected":
            css_class = "offline"
        chip.add_class(css_class)
        chip.update(labels.get(snapshot.connection_state, "○ Offline"))

    def _refresh_device_overview(self, snapshot: DaemonUiSnapshot) -> None:
        self.query_one("#device-summary", Button).label = (
            self.reducer.device_summary(snapshot)
        )
        self.query_one("#device-overview", Static).update(
            self.reducer.device_overview(snapshot, self.daemon.client.device_id)
        )

    def _refresh_composer_note(self, snapshot: DaemonUiSnapshot) -> None:
        note = self.query_one("#composer-note", Static)
        disconnected = snapshot.connection_state != "connected"
        note.set_class(disconnected, "visible")
        if disconnected:
            note.update(
                "Runtime offline · draft preserved · Enter will not send · "
                "/reconnect retries now"
            )
        else:
            note.update("")

    def _refresh_active_interaction(self, snapshot: DaemonUiSnapshot) -> None:
        view = self.reducer.active_interaction(snapshot)
        panel = self.query_one("#active-interaction", Horizontal)
        panel.remove_class(
            "idle",
            "active",
            "waiting",
            "connecting",
            "reconnecting",
            "recovered",
            "route",
            "offline",
            "error",
        )
        panel.add_class(view.state)
        if view.state == "recovered" and self._recovery_hide_timer is None:
            self._recovery_hide_timer = self.set_timer(
                3.0,
                self._dismiss_recovery_status,
            )
        elif view.state != "recovered" and self._recovery_hide_timer is not None:
            self._recovery_hide_timer.stop()
            self._recovery_hide_timer = None
        spinner = self.query_one("#activity-spinner", LoadingIndicator)
        spinner.display = view.state in {
            "active",
            "waiting",
            "connecting",
            "reconnecting",
            "route",
        }
        title_widget = self.query_one("#active-title", Static)
        detail_widget = self.query_one("#active-detail", Static)
        title_widget.update(view.title)
        detail_widget.update(view.detail)
        title_widget.display = bool(view.title)
        detail_widget.display = bool(view.detail)

    def _dismiss_recovery_status(self) -> None:
        self.daemon.connection_recovered = False
        self._recovery_hide_timer = None
        self._last_snapshot = None
        self._refresh_ui()

    def _refresh_command_suggestions(self, value: str) -> None:
        try:
            suggestions = self.query_one("#command-suggestions", Static)
        except NoMatches:
            return
        matches = self.command_catalog.matches(value)
        if not matches:
            suggestions.remove_class("visible")
            suggestions.update("")
            return
        suggestions.update(
            "\n".join(
                f"{command.name:<12} {command.description}" for command in matches
            )
        )
        suggestions.add_class("visible")

    def _show_local_notice(self, message: str) -> None:
        entry = self.reducer.consume_line(f"[system] {message}")
        if entry is None:
            return
        try:
            self.query_one("#transcript-log", RichLog).write(
                self._format_transcript_entry(entry),
                scroll_end=True,
            )
        except NoMatches:
            return

    def _apply_responsive_classes(self, width: int, height: int) -> None:
        self.screen.set_class(width < 72, "narrow")
        self.screen.set_class(height < 18, "short")

    @staticmethod
    def _format_transcript_entry(entry: TranscriptEntry) -> Text:
        accents = {
            "user": "#7dca9b",
            "runtime": "#79b8ff",
            "system": "#6e7681",
            "error": "#f08887",
        }
        body_styles = {
            "user": "#e6f1ff",
            "runtime": "#dde6f2",
            "system": "#9aa6b4",
            "error": "#f5c2c0",
        }
        labels = {"user": "USER", "runtime": "OPENHALO", "system": "SYSTEM", "error": "ERROR"}
        accent = accents.get(entry.role, accents["system"])
        body_style = body_styles.get(entry.role, body_styles["system"])
        label = labels.get(entry.role, "SYSTEM")
        rendered = Text()
        rendered.append("▌ ", style=f"bold {accent}")
        rendered.append(f"{label:<8} ", style=f"bold {accent}")
        rendered.append(entry.body, style=body_style)
        return rendered


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
        full_screen=True,
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
