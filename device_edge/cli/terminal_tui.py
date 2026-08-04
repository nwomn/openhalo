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
from textual.widgets import Button
from textual.widgets import Input
from textual.widgets import Select
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

    _local_commands = ("/help", "/status", "/history", "/coding", "/quit")
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

    #coding-panel {
        height: 3;
        padding: 0 2;
        background: #151b15;
        border-top: solid #2d372c;
    }

    #coding-panel.expanded {
        height: 12;
    }

    #coding-toolbar {
        height: 2;
    }

    #coding-toggle {
        width: 18;
        min-width: 18;
    }

    #coding-task-select {
        width: 1fr;
        height: 2;
        margin-left: 1;
    }

    #coding-activity-log {
        height: 10;
        padding: 0 1;
        overflow-y: scroll;
        color: #c8d6c7;
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
        self._coding_history: deque[str] = deque(maxlen=self._history_limit)
        self._history_index: int | None = None
        self._history_draft = ""
        self._coding_history_index: int | None = None
        self._coding_history_draft = ""
        self.coding_expanded = False
        self.selected_coding_task: str | None = None
        self._coding_activity_entries: list[dict] = []
        self._coding_activity_before: int | None = None
        self._coding_task_options: tuple[tuple[str, str], ...] = ()

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
                Horizontal(
                    Button("Coding +", id="coding-toggle"),
                    Select(
                        [],
                        prompt="Select an active Coding task",
                        allow_blank=True,
                        id="coding-task-select",
                    ),
                    id="coding-toolbar",
                ),
                Static("", id="coding-activity-log"),
                id="coding-panel",
            ),
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
        self._refresh_coding_panel()
        self._drain_transcript_queue()
        self.set_interval(0.1, self._drain_transcript_queue)
        self.set_interval(0.1, self._refresh_status_bar)
        self.set_interval(0.1, self._refresh_help_bar)
        self.set_interval(0.1, self._refresh_active_progress)
        self.set_interval(0.2, self._refresh_coding_panel)
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
        if self.coding_expanded:
            if not self.selected_coding_task:
                self.daemon.render_status_line(
                    "Select an active Coding task before sending correction."
                )
                return
            if not self._coding_history or self._coding_history[-1] != text:
                self._coding_history.append(text)
            self._coding_history_index = None
            self._coding_history_draft = ""
            self.daemon.queue_coding_control(
                "steer",
                interaction_id=self.selected_coding_task,
                text=text,
            )
        else:
            if not self._command_history or self._command_history[-1] != text:
                self._command_history.append(text)
            self._history_index = None
            self._history_draft = ""
            self.input_queue.put(text)
        event.input.value = ""

    async def on_input_changed(self, event: Input.Changed) -> None:
        draft = event.value
        if self.coding_expanded:
            self._coding_draft = draft
            return
        else:
            self.daemon.set_draft(draft)
        self.input_state_queue.put(
            {
                "state": "draft_nonempty" if draft else "draft_empty",
                "draft_length": len(draft),
            }
        )

    def on_key(self, event) -> None:
        if self.coding_expanded and event.key == "pageup":
            self._load_older_coding_activity_page()
            event.prevent_default()
            event.stop()
            return
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
            if self.coding_expanded:
                if self.selected_coding_task:
                    self.daemon.queue_coding_control(
                        "interrupt", interaction_id=self.selected_coding_task
                    )
                else:
                    self.daemon.render_status_line(
                        "Select an active Coding task before interrupting."
                    )
            else:
                composer.value = ""
                self._history_index = None
                self._history_draft = ""
            event.prevent_default()
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "coding-toggle":
            return
        self.coding_expanded = not self.coding_expanded
        panel = self.query_one("#coding-panel", Vertical)
        panel.set_class(self.coding_expanded, "expanded")
        panel.styles.height = 12 if self.coding_expanded else 3
        event.button.label = "Coding −" if self.coding_expanded else "Coding +"
        composer = self.query_one("#command-input", Input)
        if self.coding_expanded:
            composer.value = getattr(self, "_coding_draft", "")
            composer.placeholder = "Correction for selected Codex task · Enter sends · Esc interrupts"
        else:
            self._coding_draft = composer.value
            composer.value = self.daemon.presentation.draft
            composer.placeholder = "Write a message or use /help"
        composer.focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "coding-task-select":
            return
        value = event.value
        self.selected_coding_task = value if isinstance(value, str) else None
        self._coding_activity_entries = []
        self._coding_activity_before = None
        self._refresh_coding_activity_log()

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
        history = self._coding_history if self.coding_expanded else self._command_history
        index = self._coding_history_index if self.coding_expanded else self._history_index
        draft = self._coding_history_draft if self.coding_expanded else self._history_draft
        if not history:
            return False
        history = list(history)
        if direction < 0:
            if index is None:
                draft = composer.value
                index = len(history) - 1
            else:
                index = max(index - 1, 0)
            composer.value = history[index]
            if self.coding_expanded:
                self._coding_history_draft, self._coding_history_index = draft, index
            else:
                self._history_draft, self._history_index = draft, index
            return True
        if index is None:
            return False
        if index >= len(history) - 1:
            composer.value = draft
            index = None
            draft = ""
            if self.coding_expanded:
                self._coding_history_draft, self._coding_history_index = draft, index
            else:
                self._history_draft, self._history_index = draft, index
            return True
        index += 1
        composer.value = history[index]
        if self.coding_expanded:
            self._coding_history_draft, self._coding_history_index = draft, index
        else:
            self._history_draft, self._history_index = draft, index
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
            "Enter to send · ↑↓ history · Coding panel: Enter correction / Esc interrupt · "
            "Tab commands/receipt",
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

    def _coding_task_rows(self) -> list[dict]:
        journal = getattr(self.daemon, "coding_activity_journal", None)
        if journal is not None:
            return journal.tasks(limit=200)
        bridge = getattr(self.daemon, "coding_bridge", None)
        if bridge is None:
            return []
        return [
            {
                "interaction_id": task.interaction_id,
                "thread_id": task.thread_id,
                "turn_id": task.turn_id,
                "status": task.status,
                "updated_at": "",
            }
            for task in bridge.tasks.values()
        ]

    def _refresh_coding_panel(self) -> None:
        try:
            select = self.query_one("#coding-task-select", Select)
        except NoMatches:
            return
        rows = self._coding_task_rows()
        options = [
            (
                f"{row['interaction_id']} · {row['status']} · {row['turn_id']}",
                row["interaction_id"],
            )
            for row in rows
            if isinstance(row.get("interaction_id"), str)
        ]
        active_values = {
            row.get("interaction_id")
            for row in rows
            if row.get("status") == "active"
            and isinstance(row.get("interaction_id"), str)
        }
        current = self.selected_coding_task
        option_tuple = tuple(options)
        if option_tuple != self._coding_task_options:
            try:
                select.set_options(options)
            except NoMatches:
                return
            self._coding_task_options = option_tuple
        identifiers = {value for _, value in options}
        if current not in identifiers:
            if len(active_values) == 1:
                current = next(iter(active_values))
            else:
                current = None
            self.selected_coding_task = current
        if current is None:
            select.value = Select.NULL
        else:
            select.value = current
        self._refresh_coding_activity_log()

    def _refresh_coding_activity_log(self) -> None:
        try:
            log = self.query_one("#coding-activity-log", Static)
        except NoMatches:
            return
        if not self.selected_coding_task:
            log.update("Select a Coding task to inspect its activity.\nPageUp loads older local history.")
            return
        journal = getattr(self.daemon, "coding_activity_journal", None)
        if journal is None:
            log.update("Local Coding journal is unavailable in this session.")
            return
        latest_page = journal.page(self.selected_coding_task, limit=200)
        if not self._coding_activity_entries:
            self._coding_activity_entries = latest_page
        elif latest_page:
            latest_sequence = self._coding_activity_entries[-1].get("local_sequence", 0)
            new_entries = [
                entry
                for entry in latest_page
                if entry.get("local_sequence", 0) > latest_sequence
            ]
            if new_entries:
                self._coding_activity_entries = (
                    self._coding_activity_entries + new_entries
                )[-600:]
        lines = []
        if self.daemon.coding_activity_storage_error:
            lines.append(f"⚠ local journal degraded: {self.daemon.coding_activity_storage_error}")
        for entry in self._coding_activity_entries:
            value = entry.get("value", {})
            observed_at = str(value.get("observed_at", ""))
            timestamp = observed_at[11:19] if len(observed_at) >= 19 else observed_at
            event_kind = str(value.get("event_kind", "activity"))
            summary = str(value.get("summary", "")).replace("\n", " · ")
            lines.append(f"{timestamp}  {event_kind}  {summary}")
        if self._coding_activity_before is not None:
            lines.insert(0, "↑ older local history loaded · PageUp for more")
        else:
            lines.append("PageUp loads older local history.")
        log.update("\n".join(lines))

    def _load_older_coding_activity_page(self) -> None:
        if not self.selected_coding_task or not self._coding_activity_entries:
            return
        journal = getattr(self.daemon, "coding_activity_journal", None)
        if journal is None:
            return
        first_sequence = self._coding_activity_entries[0].get("local_sequence")
        if not isinstance(first_sequence, int):
            return
        older = journal.page(
            self.selected_coding_task,
            before_sequence=first_sequence,
            limit=200,
        )
        if not older:
            self._coding_activity_before = first_sequence
            self._refresh_coding_activity_log()
            return
        self._coding_activity_entries = (older + self._coding_activity_entries)[-600:]
        self._coding_activity_before = older[0].get("local_sequence")
        self._refresh_coding_activity_log()

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
    coding_activity_path=None,
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
        coding_activity_path=coding_activity_path,
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
    coding_activity_path=None,
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
        coding_activity_path=coding_activity_path,
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
