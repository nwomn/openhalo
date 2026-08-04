"""Resident terminal-edge daemon for the M8 terminal interaction slice."""

from __future__ import annotations

import argparse
import asyncio
from collections import deque
import hashlib
import json
import os
import sys
import io
import sqlite3
from queue import Empty, Queue
from datetime import datetime
from datetime import timezone
from pathlib import Path
from contextlib import suppress

import websockets

from device_edge.shared.local_actions import execute_action
from device_edge.shared.identity import DeviceIdentity
from device_edge.shared.identity import create_ephemeral_identity
from device_edge.shared.identity import load_or_create_identity
from device_edge.shared.session_client import SessionClient
from device_edge.cli.coding_agent_bridge import CODING_CAPABILITY_REGISTRATIONS
from device_edge.cli.coding_agent_bridge import CodingAgentBridge
from device_edge.cli.coding_agent_bridge import validate_coding_action_payload
from device_edge.cli.coding_activity import CodingActivityJournal
from device_edge.cli.codex_app_server import CodexAppServerClient
from edge_api.endpoint import validate_runtime_endpoint
from device_edge.cli.presentation import PresentationState
from device_edge.cli.presentation import reduce_connection_state
from device_edge.cli.presentation import reduce_draft
from device_edge.cli.presentation import reduce_interaction_update
from device_edge.cli.presentation import reduce_progress_frame
from edge_api.protocol import with_api_version
from openhalo_common.diagnostics import DiagnosticBoundaryRecorder
from openhalo_common.diagnostics import JsonlDiagnosticRecorder
from openhalo_common.diagnostics import correlation_from_frame


def terminal_supports_textual_fullscreen() -> bool:
    term = os.environ.get("TERM", "").strip().lower()
    return term not in {"", "dumb"}


def build_coding_activity_path(home: str | Path | None, device_id: str) -> Path:
    root = Path(home or os.environ.get("OPENHALO_HOME", Path.home() / ".openhalo"))
    return root.expanduser().resolve() / "terminal" / device_id / "coding-activity.sqlite3"


class TerminalEdgeDaemon:
    transcript_limit = 200
    max_deferred_frames = 64
    reconnect_initial_delay_s = 0.25
    reconnect_max_delay_s = 5.0
    progress_messages = {
        "deliberating": "正在理解你的请求...",
        "researching": "正在查询相关信息...",
        "planning": "正在准备下一步...",
        "executing": "正在执行操作...",
        "awaiting_action_result": "正在等待设备确认...",
        "completing": "正在确认处理结果...",
        "failed": "暂时无法继续处理",
        "cancelled": "处理已停止",
    }

    def __init__(
        self,
        device_id: str,
        audience: str = "ws://127.0.0.1:8765",
        identity: DeviceIdentity | None = None,
        display_name: str | None = None,
        output_stream=None,
        input_stream=None,
        input_state_stream=None,
        timestamp_provider=None,
        stdin_observed_at: str | None = None,
        diagnostic_recorder=None,
        coding_enabled: bool = False,
        coding_workspace: str | Path | None = None,
        coding_activity_path: str | Path | None = None,
        coding_bridge: CodingAgentBridge | None = None,
    ) -> None:
        validate_runtime_endpoint(audience)
        self.output_stream = output_stream or sys.stdout
        self.input_stream = input_stream or sys.stdin
        self.input_state_stream = input_state_stream
        self.timestamp_provider = timestamp_provider or self._default_timestamp_provider
        self.stdin_observed_at = stdin_observed_at
        self.connection_state = "disconnected"
        self.terminal_activity_state = "unknown"
        self.pending_runtime_reply = False
        self.pending_interaction_id: str | None = None
        self.active_progress_phase: str | None = None
        self.active_progress_interaction_id: str | None = None
        self.progress_sequence_by_interaction: dict[str, int] = {}
        self.user_request_count = 0
        self.runtime_message_count = 0
        self.local_command_count = 0
        self.quit_requested = False
        self.coding_enabled = coding_enabled
        self.coding_workspace = str(
            Path(coding_workspace or Path.cwd()).expanduser().resolve()
        )
        self.coding_activity_journal = (
            CodingActivityJournal(coding_activity_path)
            if coding_activity_path is not None
            else None
        )
        self.coding_activity_storage_error: str | None = None
        self.coding_observations: deque[dict] = deque(maxlen=256)
        self.coding_observation_event: asyncio.Event | None = None
        self.coding_control_queue: Queue[dict] = Queue()
        self.pending_coding_prompts: dict[str, dict] = {}
        self.pending_coding_action_frames: dict[str, dict] = {}
        self.local_action_results: deque[dict] = deque(maxlen=64)
        self.coding_action_results: dict[str, dict] = {}
        self.coding_request_prompts: dict[str, str] = {}
        self.transcript = deque(maxlen=self.transcript_limit)
        self.presentation = PresentationState(transcript_limit=self.transcript_limit)
        self.device = {
            "device_id": device_id,
            "device_name": device_id,
            "device_type": "desktop-cli",
        }
        self.action_diagnostics = DiagnosticBoundaryRecorder(
            recorder=diagnostic_recorder,
            side="edge",
            device=self.device,
        )
        capabilities: list[str | dict] = [
            "text.input",
            "notification.show",
            "terminal.context",
            "interaction.progress",
        ]
        self.coding_bridge = coding_bridge
        if coding_enabled and self.coding_bridge is None:
            workspace_ref = self._build_workspace_ref(self.coding_workspace)
            self.coding_bridge = CodingAgentBridge(
                client=CodexAppServerClient(),
                workspace_path=self.coding_workspace,
                workspace_ref=workspace_ref,
                observation_sink=self._receive_coding_observation,
                approval_sink=self._receive_coding_prompt,
                timestamp_provider=self._default_timestamp_provider,
            )
        elif self.coding_bridge is not None:
            self.coding_bridge.observation_sink = self._receive_coding_observation
            self.coding_bridge.approval_sink = self._receive_coding_prompt
        if coding_enabled:
            capabilities.extend(self._coding_capability_registrations())
        self.client = SessionClient(
            device_id=device_id,
            device_type="desktop-cli",
            audience=audience,
            identity=identity or create_ephemeral_identity(),
            display_name=display_name,
            capabilities=capabilities,
            diagnostic_recorder=diagnostic_recorder,
        )

    def set_connection_state(self, connection_state: str) -> None:
        self.connection_state = connection_state
        self.presentation = reduce_connection_state(
            self.presentation,
            connection_state,
        )

    def set_draft(self, draft: str) -> None:
        self.presentation = reduce_draft(self.presentation, draft)

    @staticmethod
    def _build_workspace_ref(workspace_path: str) -> str:
        digest = hashlib.sha256(workspace_path.encode()).hexdigest()[:10]
        name = Path(workspace_path).name or "workspace"
        return f"{name}-{digest}"

    def _coding_capability_registrations(self) -> list[dict]:
        workspace_ref = self._build_workspace_ref(self.coding_workspace)
        registrations = []
        for registration in CODING_CAPABILITY_REGISTRATIONS:
            copy = json.loads(json.dumps(registration))
            if copy["name"] == "coding.turn.start":
                copy["workspace_ref"] = workspace_ref
            registrations.append(copy)
        return registrations

    def _receive_coding_observation(self, observation: dict) -> None:
        if self.coding_activity_journal is not None:
            try:
                self.coding_activity_journal.append(observation)
                if observation.get("value", {}).get("event_kind") in {
                    "turn_completed",
                    "turn_failed",
                    "turn_interrupted",
                }:
                    self.coding_activity_journal.prune_completed()
            except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
                self.coding_activity_storage_error = str(exc)
        self.coding_observations.append(observation)
        if self.coding_observation_event is not None:
            self.coding_observation_event.set()

    def queue_coding_control(
        self,
        kind: str,
        *,
        interaction_id: str,
        text: str = "",
    ) -> None:
        if kind not in {"steer", "interrupt"}:
            raise ValueError("Unsupported foreground Coding control.")
        if not interaction_id:
            raise ValueError("Foreground Coding control requires a selected task.")
        self.coding_control_queue.put(
            {"kind": kind, "interaction_id": interaction_id, "text": text}
        )

    def _receive_coding_prompt(self, prompt: dict) -> None:
        prompt_id = prompt.get("prompt_id")
        if not isinstance(prompt_id, str):
            return
        self.pending_coding_prompts[prompt_id] = prompt
        kind = prompt.get("kind", "coding")
        summary = prompt.get("summary", "Codex requested a local decision.")
        detail = prompt.get("detail")
        suffix = f" · {detail}" if isinstance(detail, str) and detail else ""
        if kind == "suggestion":
            choices = "accept | ignore | suppress_task"
        else:
            choices = "allow | allow-session | deny | cancel"
        self.render_status_line(
            f"Coding {kind} [{prompt_id}]: {summary}{suffix} ({choices})"
        )

    def _resolve_coding_prompt(self, text: str) -> bool:
        parts = text.strip().split(maxsplit=1)
        if len(parts) != 2:
            return False
        command, prompt_id = parts
        prompt = self.pending_coding_prompts.get(prompt_id)
        if prompt is None or self.coding_bridge is None:
            return False
        kind = prompt.get("kind")
        if kind == "suggestion":
            if command not in {"/accept", "/ignore", "/suppress_task"}:
                return False
            choice = command.removeprefix("/")
            try:
                result = self.coding_bridge.resolve_suggestion(prompt_id, choice)
            except ValueError as exc:
                self.render_status_line(str(exc))
                return True
            frame = self.pending_coding_action_frames.pop(prompt_id, None)
            self.pending_coding_prompts.pop(prompt_id, None)
            if frame is not None:
                action_result = self._build_action_result(frame, result)
                request_id = frame.get("request_id")
                if request_id is not None:
                    self.coding_action_results[request_id] = action_result
                    self.coding_request_prompts.pop(request_id, None)
                self.local_action_results.append(action_result)
            return True
        if command not in {"/allow", "/allow-session", "/deny", "/cancel"}:
            return False
        decision = {
            "/allow": "accept",
            "/allow-session": "acceptForSession",
            "/deny": "decline",
            "/cancel": "cancel",
        }[command]
        try:
            self.coding_bridge.resolve_approval(prompt_id, decision)
        except ValueError as exc:
            self.render_status_line(str(exc))
        else:
            self.pending_coding_prompts.pop(prompt_id, None)
        return True

    @staticmethod
    def _default_timestamp_provider() -> str:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def build_bootstrap_frames(self) -> list[dict]:
        return [
            self.client.build_connect_frame(),
            self.client.build_capability_announce_frame(),
        ]

    def build_terminal_activity_frame(
        self,
        activity_state: str,
        observed_at: str,
    ) -> dict:
        return self.client.build_terminal_activity_event(
            activity_state=activity_state,
            observed_at=observed_at,
        )

    def _drain_input_state_frames(self) -> list[dict]:
        if self.input_state_stream is None:
            return []
        latest_state_payload: dict | None = None
        while True:
            try:
                state_payload = self.input_state_stream.get_nowait()
            except Empty:
                break
            if not isinstance(state_payload, dict):
                continue
            latest_state_payload = state_payload
        if latest_state_payload is None:
            return []

        observed_at = latest_state_payload.get("observed_at") or self._next_observed_at()
        observations = [
            {
                "name": "terminal.input_state",
                "value": latest_state_payload.get("state", "draft_empty"),
                "observed_at": observed_at,
                "confidence": 1.0,
            }
        ]
        if "draft_length" in latest_state_payload:
            observations.append(
                {
                    "name": "terminal.input_draft_length",
                    "value": latest_state_payload["draft_length"],
                    "observed_at": observed_at,
                    "confidence": 1.0,
                }
            )
        return [
            {
                "type": "event_push",
                "device_id": self.client.device_id,
                "capability": "terminal.context",
                "payload": {"observations": observations},
            }
        ]

    async def _wait_for_input_state_frames(self) -> list[dict]:
        while True:
            frames = self._drain_input_state_frames()
            if frames:
                return frames
            await asyncio.sleep(0.01)

    async def _wait_for_coding_observation(self) -> None:
        if self.coding_observation_event is None:
            return
        while not self.coding_observations:
            await self.coding_observation_event.wait()
            self.coding_observation_event.clear()

    async def _wait_for_coding_control(self) -> None:
        while self.coding_control_queue.empty():
            await asyncio.sleep(0.05)

    async def _flush_coding_controls(self) -> None:
        if self.coding_bridge is None:
            while True:
                try:
                    self.coding_control_queue.get_nowait()
                except Empty:
                    return
        while True:
            try:
                control = self.coding_control_queue.get_nowait()
            except Empty:
                return
            try:
                if control["kind"] == "steer":
                    await self.coding_bridge.foreground_steer(
                        interaction_id=control["interaction_id"],
                        instruction=control["text"],
                    )
                    self.render_status_line(
                        f"Coding correction sent to {control['interaction_id']}."
                    )
                else:
                    await self.coding_bridge.interrupt(
                        interaction_id=control["interaction_id"]
                    )
                    self.render_status_line(
                        f"Coding turn interrupted: {control['interaction_id']}."
                    )
            except (ConnectionError, RuntimeError, ValueError) as exc:
                self.render_status_line(f"Coding control failed: {exc}")

    def _drain_coding_observation_frames(self) -> list[dict]:
        frames = []
        while self.coding_observations:
            observation = self.coding_observations.popleft()
            frames.append(
                self.client.build_observation_event(
                    capability="coding.activity",
                    observations=[observation],
                )
            )
        return frames

    async def _flush_coding_observations(
        self,
        websocket,
        pending_frames: list[dict],
    ) -> None:
        for frame in self._drain_coding_observation_frames():
            await self._send_frame(websocket, frame)
            pending_frames.append(await self._recv_frame(websocket))

    async def _flush_local_action_results(
        self,
        websocket,
        results: list[dict],
    ) -> None:
        while self.local_action_results:
            result = self.local_action_results.popleft()
            results.append(result)
            await self._send_frame(websocket, result)

    async def _start_coding_bridge(self) -> None:
        if not self.coding_enabled or self.coding_bridge is None:
            return
        try:
            await self.coding_bridge.start()
        except Exception as exc:
            self.render_status_line(f"Coding Bridge unavailable: {exc}")
        else:
            self.render_status_line("Coding Bridge ready.")

    async def _run_coding_bridge_supervisor(self) -> None:
        if not self.coding_enabled or self.coding_bridge is None:
            return
        retry_delay = 0.5
        while not self.quit_requested:
            bridge = self.coding_bridge
            if bridge.state != "ready" or bridge.client.state != "ready":
                if bridge.state == "ready" or bridge.client.state != "disconnected":
                    with suppress(Exception):
                        await bridge.close()
                try:
                    await bridge.start()
                except Exception as exc:
                    bridge.state = "degraded"
                    self.render_status_line(f"Coding Bridge retrying: {exc}")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 10.0)
                    continue
                retry_delay = 0.5
                self.render_status_line("Coding Bridge ready.")
            await asyncio.sleep(0.5)

    async def _stop_coding_bridge(self) -> None:
        if self.coding_bridge is None:
            return
        with suppress(Exception):
            await self.coding_bridge.close()

    @staticmethod
    def _input_state_frames_include_nonempty_draft(frames: list[dict]) -> bool:
        for frame in frames:
            for observation in frame.get("payload", {}).get("observations", []):
                if (
                    observation.get("name") == "terminal.input_state"
                    and observation.get("value") == "draft_nonempty"
                ):
                    return True
        return False

    def build_user_input_frames(
        self,
        text: str,
        observed_at: str,
    ) -> list[dict]:
        return [
            self.build_terminal_activity_frame(
                activity_state="active",
                observed_at=observed_at,
            ),
            self._build_text_input_frame(text=text, observed_at=observed_at),
        ]

    def _build_text_input_frame(self, text: str, observed_at: str) -> dict:
        frame = self.client.build_text_event(text)
        frame["payload"]["observed_at"] = observed_at
        return frame

    def _next_observed_at(self, explicit_observed_at: str | None = None) -> str:
        if explicit_observed_at is not None:
            return explicit_observed_at
        return self.timestamp_provider()

    def _append_transcript(self, prefix: str, message: str) -> None:
        self.transcript.append(f"[{prefix}] {message}")

    def _write_line(self, prefix: str, message: str) -> None:
        line = f"[{prefix}] {message}"
        print(line, file=self.output_stream)
        self.transcript.append(line)

    def render_status_line(self, message: str) -> None:
        self.clear_progress()
        self._write_line("system", message)

    def render_user_line(self, text: str) -> None:
        self.clear_progress()
        self._write_line("user", text)

    def render_runtime_line(self, message: str) -> None:
        self.clear_progress()
        self._write_line("runtime", message)

    def render_receipt_line(self, message: str) -> None:
        self.clear_progress()
        self._write_line("receipt", message)

    def render_progress_phase(self, interaction_id: str, phase: str) -> None:
        message = self.progress_messages.get(phase)
        if message is None:
            return
        self.active_progress_interaction_id = interaction_id
        self.active_progress_phase = phase
        self._write_line("progress", message)

    def clear_progress(self) -> None:
        self.active_progress_interaction_id = None
        self.active_progress_phase = None

    def _output_is_tty(self) -> bool:
        try:
            return bool(self.output_stream.isatty())
        except (AttributeError, OSError):
            return False

    def render_help(self) -> None:
        self.render_status_line(
            "Available local commands: /help /status /history /quit; "
            "coding: /coding tasks | /coding send <task> <text> | "
            "/coding interrupt <task>; prompts: /accept /ignore /suppress_task "
            "/allow /allow-session /deny /cancel"
        )

    def _handle_coding_local_command(self, text: str) -> bool:
        parts = text.split(maxsplit=2)
        if not parts or parts[0] != "/coding":
            return False
        if len(parts) == 2 and parts[1] == "tasks":
            rows = (
                self.coding_activity_journal.tasks(limit=200)
                if self.coding_activity_journal is not None
                else []
            )
            if not rows and self.coding_bridge is not None:
                rows = [
                    {
                        "interaction_id": task.interaction_id,
                        "turn_id": task.turn_id,
                        "status": task.status,
                    }
                    for task in self.coding_bridge.tasks.values()
                ]
            self.render_status_line(
                "Coding tasks: "
                + ("; ".join(
                    f"{row.get('interaction_id')} ({row.get('status')})"
                    for row in rows
                ) or "(none)")
            )
            return True
        if len(parts) < 3 or parts[1] not in {"send", "interrupt"}:
            self.render_status_line(
                "Usage: /coding tasks | /coding send <task> <text> | "
                "/coding interrupt <task>"
            )
            return True
        task_id, text_payload = parts[2].split(maxsplit=1) if " " in parts[2] else (parts[2], "")
        if parts[1] == "interrupt":
            task_id = parts[2].strip()
            text_payload = ""
        if self.coding_bridge is None or task_id not in self.coding_bridge.tasks:
            self.render_status_line("Coding input requires a selected active task.")
            return True
        task = self.coding_bridge.tasks[task_id]
        if task.status != "active":
            self.render_status_line("Coding input requires a selected active task.")
            return True
        if parts[1] == "send" and not text_payload.strip():
            self.render_status_line("Coding correction must not be empty.")
            return True
        self.queue_coding_control(
            "steer" if parts[1] == "send" else "interrupt",
            interaction_id=task_id,
            text=text_payload,
        )
        return True

    def render_status_summary(self) -> None:
        pending_flag = "yes" if self.pending_runtime_reply else "no"
        self.render_status_line(
            "Session status: "
            f"connection={self.connection_state} "
            f"activity={self.terminal_activity_state} "
            f"user_requests={self.user_request_count} "
            f"runtime_messages={self.runtime_message_count} "
            f"local_commands={self.local_command_count} "
            f"pending_runtime_reply={pending_flag}"
        )

    def render_history(self) -> None:
        self.render_status_line("Recent session history:")
        if not self.transcript:
            self.render_status_line("(empty)")
            return
        for line in self.transcript:
            print(line, file=self.output_stream)

    def handle_local_input(self, text: str) -> bool:
        normalized_text = text.strip()
        if not normalized_text.startswith("/"):
            return False

        self.local_command_count += 1
        if self._resolve_coding_prompt(normalized_text):
            return True
        if self._handle_coding_local_command(normalized_text):
            return True
        if normalized_text == "/help":
            self.render_help()
            return True
        if normalized_text == "/status":
            self.render_status_summary()
            return True
        if normalized_text == "/history":
            self.render_history()
            return True
        if normalized_text == "/quit":
            self.quit_requested = True
            self.render_status_line("Shutting down terminal session.")
            return True

        self.render_status_line(f"Unknown local command: {normalized_text}")
        self.render_help()
        return True

    async def _read_live_input_line(self) -> str | None:
        loop = asyncio.get_running_loop()
        fileno = None
        try:
            fileno = self.input_stream.fileno()
        except (AttributeError, io.UnsupportedOperation, OSError):
            fileno = None

        if fileno is None:
            if isinstance(self.input_stream, io.StringIO):
                line = self.input_stream.readline()
            else:
                line = await loop.run_in_executor(None, self.input_stream.readline)
            if line == "":
                return None
            return line

        line_future = loop.create_future()

        def on_readable() -> None:
            if line_future.done():
                return
            try:
                line = self.input_stream.readline()
            except Exception as exc:  # pragma: no cover - defensive passthrough
                line_future.set_exception(exc)
            else:
                line_future.set_result(None if line == "" else line)
            finally:
                with suppress(Exception):
                    loop.remove_reader(fileno)

        loop.add_reader(fileno, on_readable)
        try:
            return await line_future
        finally:
            with suppress(Exception):
                loop.remove_reader(fileno)

    async def _send_user_input(
        self,
        websocket,
        text: str,
        observed_at: str | None = None,
        pending_frames: list[dict] | None = None,
    ) -> bool:
        normalized_text = text.strip()
        if not normalized_text:
            return False
        if self.handle_local_input(normalized_text):
            return False
        event_timestamp = self._next_observed_at(observed_at)
        self.user_request_count += 1
        self.pending_runtime_reply = True
        self.pending_interaction_id = None
        self.render_user_line(normalized_text)
        for frame in self.build_user_input_frames(
            text=normalized_text,
            observed_at=event_timestamp,
        ):
            await self._send_frame(websocket, frame)
            if pending_frames is None:
                await self._recv_frame(websocket)
            else:
                await self._recv_expected_frame(
                    websocket,
                    pending_frames,
                    expected_type="event_ack",
                )
        self.terminal_activity_state = "active"
        return True

    async def _drain_live_input(self, websocket) -> bool:
        line = await self._read_live_input_line()
        if line is None:
            return False
        return await self._send_user_input(
            websocket,
            text=line,
        )

    async def _recv_expected_frame(
        self,
        websocket,
        pending_frames: list[dict],
        expected_type: str,
    ) -> dict:
        for index, frame in enumerate(pending_frames):
            if frame.get("type") == expected_type:
                return pending_frames.pop(index)
        while True:
            frame = await self._recv_frame(websocket)
            if frame.get("type") == expected_type:
                return frame
            if frame.get("type") == "interaction_progress":
                self.handle_interaction_progress_frame(frame)
                continue
            if len(pending_frames) >= self.max_deferred_frames:
                raise RuntimeError(
                    "deferred frames exceeded "
                    f"{self.max_deferred_frames} while waiting for {expected_type}"
                )
            pending_frames.append(frame)

    def handle_action_request(self, frame: dict) -> dict:
        correlation = correlation_from_frame(frame)
        with self.action_diagnostics.boundary(
            module="Local Action Executor",
            operation="execute_action",
            correlation=correlation,
            input_payload={"action": frame["action"]},
            summary="Executed terminal-edge action request.",
        ) as boundary:
            self.runtime_message_count += 1
            self.pending_runtime_reply = False
            self.pending_interaction_id = None
            self.clear_progress()
            result = execute_action(
                frame["action"],
                output_stream=self.output_stream,
                delivered_via="terminal.stdout",
                message_prefix="[runtime] ",
            )
            if result["status"] == "ok":
                self._append_transcript(
                    "runtime",
                    result["details"]["body"],
                )
            action_result = self._build_action_result(frame, result)
            boundary.output({"result": result, "frame": action_result})
            return action_result

    def _build_action_result(self, frame: dict, result: dict) -> dict:
        action_result = with_api_version(
            {
                "type": "action_result",
                "device_id": self.client.device_id,
                "result": result,
            }
        )
        for key in (
            "request_id",
            "interaction_id",
            "interaction_turn_id",
            "trace_id",
            "session_id",
            "turn_id",
            "event_id",
            "parent_event_id",
        ):
            if frame.get(key) is not None:
                action_result[key] = frame[key]
        return action_result

    async def handle_action_request_async(self, frame: dict) -> dict | None:
        action = frame.get("action", {})
        capability = action.get("capability")
        if capability not in {
            "coding.turn.start",
            "coding.suggestion.offer",
            "coding.turn.steer",
        }:
            return self.handle_action_request(frame)
        if self.coding_bridge is None:
            return self._build_action_result(
                frame,
                {
                    "status": "error",
                    "capability": capability,
                    "reason": "coding_bridge_unavailable",
                },
            )
        request_id = frame.get("request_id")
        if request_id is not None:
            cached = getattr(self, "coding_action_results", {}).get(request_id)
            if cached is not None:
                return cached
        self.runtime_message_count += 1
        self.pending_runtime_reply = False
        self.pending_interaction_id = None
        self.clear_progress()
        payload = action.get("payload")
        if not isinstance(payload, dict):
            result = {
                "status": "error",
                "capability": capability,
                "reason": "invalid_payload",
            }
            return self._build_action_result(frame, result)
        try:
            validate_coding_action_payload(capability, payload)
            if capability == "coding.turn.start":
                details = await self.coding_bridge.start_turn(
                    interaction_id=payload.get("interaction_id") or frame.get("interaction_id", ""),
                    task=payload.get("task", ""),
                    workspace_ref=payload.get("workspace_ref", ""),
                )
                self.render_status_line(
                    f"Codex task started: {details['agent_session_id']}/{details['agent_turn_id']}"
                )
                result = details
            elif capability == "coding.suggestion.offer":
                prompt = self.coding_bridge.offer_suggestion(**payload)
                prompt_id = prompt["prompt_id"]
                self.pending_coding_action_frames[prompt_id] = frame
                if request_id is not None:
                    self.coding_request_prompts[request_id] = prompt_id
                return None
            else:
                result = await self.coding_bridge.steer(**payload)
        except (ConnectionError, TypeError, ValueError, RuntimeError) as exc:
            result = {
                "status": "error",
                "capability": capability,
                "reason": str(exc),
            }
        action_result = self._build_action_result(frame, result)
        if request_id is not None:
            self.coding_action_results[request_id] = action_result
        return action_result

    def handle_interaction_frame(self, frame: dict) -> None:
        interaction = frame["interaction"]
        previous_receipts = self.presentation.receipts
        self.presentation = reduce_interaction_update(self.presentation, frame)
        self.pending_interaction_id = interaction.get("interaction_id")
        if interaction.get("status") == "completed":
            self.pending_runtime_reply = False
            self.pending_interaction_id = None
            self.clear_progress()
        visibility = interaction.get("visibility", "visible")
        summary = interaction.get("summary", "").strip()
        interaction_id = interaction.get("interaction_id")
        receipt = (
            self.presentation.receipts.get(interaction_id)
            if isinstance(interaction_id, str)
            else None
        )
        if receipt is not None and previous_receipts.get(interaction_id) != receipt:
            self.render_receipt_line(receipt.compact_line)
            return
        if summary and visibility != "silent":
            self.render_runtime_line(summary)

    def handle_interaction_progress_frame(self, frame: dict) -> None:
        previous_presentation = self.presentation
        self.presentation = reduce_progress_frame(self.presentation, frame)
        if self.presentation == previous_presentation:
            return
        progress = frame.get("progress", {})
        interaction_id = progress.get("interaction_id")
        sequence = progress.get("sequence")
        if not isinstance(interaction_id, str) or not interaction_id:
            return
        if not isinstance(sequence, int) or sequence < 1:
            return
        if sequence <= self.progress_sequence_by_interaction.get(interaction_id, 0):
            return
        self.progress_sequence_by_interaction[interaction_id] = sequence
        phase = progress.get("phase")
        state = progress.get("state")
        if state == "settled" or phase in {"completed", "failed", "cancelled"}:
            if self.active_progress_interaction_id == interaction_id:
                self.clear_progress()
            return
        if isinstance(phase, str):
            self.render_progress_phase(interaction_id, phase)

    async def _send_frame(self, websocket, frame: dict) -> None:
        await websocket.send(json.dumps(frame))

    async def _recv_frame(self, websocket) -> dict:
        return json.loads(await websocket.recv())

    async def run_scripted_session(
        self,
        websocket,
        scripted_inputs: list[dict],
        startup_observed_at: str | None,
        idle_after_inputs: bool = False,
        idle_timeout_s: float = 30.0,
        idle_observed_at: str | None = None,
        max_idle_cycles: int | None = None,
        max_action_requests: int | None = None,
        enable_live_input: bool = False,
    ) -> list[dict]:
        results: list[dict] = []
        idle_cycles = 0
        pending_frames: list[dict] = []
        terminal_activity_state = "unknown"
        live_input_open = enable_live_input
        live_input_task = None
        self.coding_observation_event = asyncio.Event()

        try:
            connect_frame, capability_frame = self.build_bootstrap_frames()
            await self._send_frame(websocket, connect_frame)
            challenge_frame = await self._recv_frame(websocket)
            await self._send_frame(
                websocket,
                self.client.build_auth_proof_frame(challenge_frame),
            )
            connect_ok = await self._recv_frame(websocket)
            if connect_ok.get("type") != "connect_ok":
                raise RuntimeError("Runtime rejected terminal device authentication.")
            await self._send_frame(websocket, capability_frame)
            self.set_connection_state("connected")
            self.render_status_line(
                f"Connected to runtime as {self.client.device_id}."
            )

            startup_timestamp = self._next_observed_at(startup_observed_at)
            await self._send_frame(
                websocket,
                self.build_terminal_activity_frame(
                    activity_state="active",
                    observed_at=startup_timestamp,
                ),
            )
            await self._recv_frame(websocket)
            terminal_activity_state = "active"
            self.terminal_activity_state = "active"
            self.render_status_line("Session ready. Terminal marked active.")

            for scripted_input in scripted_inputs:
                input_sent = await self._send_user_input(
                    websocket,
                    text=scripted_input["text"],
                    observed_at=scripted_input["observed_at"],
                    pending_frames=pending_frames,
                )
                if input_sent:
                    terminal_activity_state = "active"
                    self.terminal_activity_state = "active"

            if idle_after_inputs:
                while max_action_requests is None or len(results) < max_action_requests:
                    for frame in self._drain_input_state_frames():
                        await self._send_frame(websocket, frame)
                        pending_frames.append(await self._recv_frame(websocket))
                    if self.quit_requested:
                        break
                    if pending_frames:
                        pending_frame = pending_frames.pop(0)
                        frame_type = pending_frame.get("type")
                        if frame_type == "interaction_progress":
                            self.handle_interaction_progress_frame(pending_frame)
                            continue
                        if frame_type == "interaction_update":
                            self.handle_interaction_frame(pending_frame)
                            if (
                                self.pending_runtime_reply is False
                                and max_action_requests is not None
                                and len(results) >= max_action_requests
                            ):
                                return results
                            continue
                        if frame_type == "action_request":
                            idle_cycles = 0
                            result = await self.handle_action_request_async(pending_frame)
                            if result is not None:
                                results.append(result)
                                await self._send_frame(websocket, result)
                            continue
                    await self._flush_coding_observations(websocket, pending_frames)
                    await self._flush_coding_controls()
                    await self._flush_local_action_results(websocket, results)
                    recv_task = asyncio.create_task(self._recv_frame(websocket))
                    if live_input_open and live_input_task is None:
                        live_input_task = asyncio.create_task(
                            self._read_live_input_line()
                        )
                    idle_task = asyncio.create_task(asyncio.sleep(idle_timeout_s))
                    input_state_task = None
                    if self.input_state_stream is not None:
                        input_state_task = asyncio.create_task(
                            self._wait_for_input_state_frames()
                        )
                    coding_observation_task = None
                    coding_control_task = None
                    if self.coding_enabled:
                        coding_observation_task = asyncio.create_task(
                            self._wait_for_coding_observation()
                        )
                        coding_control_task = asyncio.create_task(
                            self._wait_for_coding_control()
                        )
                    wait_set = {recv_task, idle_task}
                    if live_input_task is not None:
                        wait_set.add(live_input_task)
                    if input_state_task is not None:
                        wait_set.add(input_state_task)
                    if coding_observation_task is not None:
                        wait_set.add(coding_observation_task)
                    if coding_control_task is not None:
                        wait_set.add(coding_control_task)
                    done, pending = await asyncio.wait(
                        wait_set,
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    if recv_task in pending:
                        recv_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await recv_task
                    if idle_task in pending:
                        idle_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await idle_task
                    if input_state_task is not None and input_state_task in pending:
                        input_state_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await input_state_task
                    if coding_observation_task is not None and coding_observation_task in pending:
                        coding_observation_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await coding_observation_task
                    if coding_control_task is not None and coding_control_task in pending:
                        coding_control_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await coding_control_task

                    activity_observed = False
                    recv_closed = False
                    if recv_task in done:
                        try:
                            frame = recv_task.result()
                        except RuntimeError as exc:
                            if "StopIteration" not in str(exc):
                                raise
                            recv_closed = True
                        else:
                            pending_frames.append(frame)

                    if recv_closed:
                        if live_input_task is not None and live_input_task.done():
                            line = live_input_task.result()
                            live_input_task = None
                            if line is None:
                                live_input_open = False
                            elif self.handle_local_input(line):
                                live_input_open = True
                                if self.quit_requested:
                                    break
                                continue
                        break

                    if live_input_task is not None and live_input_task in done:
                        line = live_input_task.result()
                        live_input_task = None
                        if line is None:
                            live_input_open = False
                        else:
                            observed_at_override = self.stdin_observed_at
                            self.stdin_observed_at = None
                            input_sent = await self._send_user_input(
                                websocket,
                                text=line,
                                observed_at=observed_at_override,
                                pending_frames=pending_frames,
                            )
                            if input_sent:
                                terminal_activity_state = "active"
                                self.terminal_activity_state = "active"
                                idle_cycles = 0
                                activity_observed = True
                            if self.quit_requested:
                                break

                    await self._flush_local_action_results(websocket, results)

                    if input_state_task is not None and input_state_task in done:
                        input_state_frames = input_state_task.result()
                        for frame in input_state_frames:
                            await self._send_frame(websocket, frame)
                            pending_frames.append(await self._recv_frame(websocket))
                        if self._input_state_frames_include_nonempty_draft(
                            input_state_frames
                        ):
                            terminal_activity_state = "active"
                            self.terminal_activity_state = "active"
                            idle_cycles = 0
                            activity_observed = True
                        continue

                    if coding_observation_task is not None and coding_observation_task in done:
                        await self._flush_coding_observations(websocket, pending_frames)
                        continue

                    if coding_control_task is not None and coding_control_task in done:
                        await self._flush_coding_controls()
                        continue

                    if idle_task in done and not activity_observed:
                        if terminal_activity_state == "idle":
                            if max_idle_cycles is not None:
                                idle_cycles += 1
                                if idle_cycles >= max_idle_cycles:
                                    return results
                            continue
                        idle_timestamp = self._next_observed_at(idle_observed_at)
                        await self._send_frame(
                            websocket,
                            self.build_terminal_activity_frame(
                                activity_state="idle",
                                observed_at=idle_timestamp,
                            ),
                        )
                        try:
                            await self._recv_expected_frame(
                                websocket,
                                pending_frames,
                                expected_type="event_ack",
                            )
                        except RuntimeError as exc:
                            if "StopIteration" not in str(exc):
                                raise
                            return results
                        terminal_activity_state = "idle"
                        self.terminal_activity_state = "idle"
                        self.render_status_line("Terminal idle.")
                        idle_cycles += 1
                        if max_idle_cycles is not None and idle_cycles >= max_idle_cycles:
                            return results
                        continue

                    progress_frame = next(
                        (
                            pending_frames.pop(index)
                            for index, candidate in enumerate(pending_frames)
                            if candidate.get("type") == "interaction_progress"
                        ),
                        None,
                    )
                    if progress_frame is not None:
                        self.handle_interaction_progress_frame(progress_frame)
                        continue
                    interaction_frame = next(
                        (
                            pending_frames.pop(index)
                            for index, candidate in enumerate(pending_frames)
                            if candidate.get("type") == "interaction_update"
                        ),
                        None,
                    )
                    if interaction_frame is not None:
                        self.handle_interaction_frame(interaction_frame)
                        if (
                            self.pending_runtime_reply is False
                            and max_action_requests is not None
                            and len(results) >= max_action_requests
                        ):
                            return results
                        continue
                    action_frame = next(
                        (
                            pending_frames.pop(index)
                            for index, candidate in enumerate(pending_frames)
                            if candidate.get("type") == "action_request"
                        ),
                        None,
                    )
                    if action_frame is None:
                        continue
                    idle_cycles = 0
                    result = await self.handle_action_request_async(action_frame)
                    if result is not None:
                        results.append(result)
                        await self._send_frame(websocket, result)
        finally:
            self.set_connection_state("disconnected")
            self.clear_progress()
            self.coding_observation_event = None
            if live_input_task is not None and not live_input_task.done():
                live_input_task.cancel()
                with suppress(asyncio.CancelledError):
                    await live_input_task
            if self.quit_requested:
                self.render_status_line("Terminal session closed.")

        return results

    async def run_forever(
        self,
        url: str,
        scripted_inputs: list[dict] | None = None,
        startup_observed_at: str | None = None,
        idle_timeout_s: float = 30.0,
        idle_observed_at: str | None = None,
        max_idle_cycles: int | None = None,
        max_action_requests: int | None = None,
        max_sessions: int | None = None,
        enable_live_input: bool = False,
    ) -> None:
        session_count = 0
        reconnect_delay_s = self.reconnect_initial_delay_s
        coding_supervisor_task = None
        if self.coding_enabled:
            coding_supervisor_task = asyncio.create_task(
                self._run_coding_bridge_supervisor()
            )
        try:
            while max_sessions is None or session_count < max_sessions:
                if self.quit_requested:
                    break
                self.set_connection_state("connecting")
                try:
                    async with websockets.connect(url) as websocket:
                        await self.run_scripted_session(
                            websocket=websocket,
                            scripted_inputs=scripted_inputs or [],
                            startup_observed_at=startup_observed_at,
                            idle_after_inputs=True,
                            idle_timeout_s=idle_timeout_s,
                            idle_observed_at=idle_observed_at,
                            max_idle_cycles=max_idle_cycles,
                            max_action_requests=max_action_requests,
                            enable_live_input=enable_live_input,
                        )
                except (OSError, websockets.WebSocketException):
                    if self.quit_requested:
                        break
                    self.set_connection_state("retrying")
                    self.render_status_line("Runtime connection unavailable. Retrying.")
                    await asyncio.sleep(reconnect_delay_s)
                    reconnect_delay_s = min(
                        reconnect_delay_s * 2,
                        self.reconnect_max_delay_s,
                    )
                    continue
                session_count += 1
                reconnect_delay_s = self.reconnect_initial_delay_s
                if self.quit_requested:
                    break
        finally:
            if coding_supervisor_task is not None:
                coding_supervisor_task.cancel()
                with suppress(asyncio.CancelledError):
                    await coding_supervisor_task
            await self._stop_coding_bridge()


def build_terminal_daemon_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the M8 terminal edge daemon.")
    parser.add_argument("--url", required=True, help="Runtime WebSocket URL.")
    parser.add_argument("--home", type=Path, help="OPENHALO_HOME identity directory.")
    parser.add_argument(
        "--device-id",
        default="terminal-edge-1",
        help="Terminal edge device id.",
    )
    parser.add_argument("--display-name", help="Visible terminal device name.")
    parser.add_argument(
        "--startup-observed-at",
        help="Initial active terminal observation timestamp.",
    )
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=30.0,
        help="Seconds to wait before emitting idle terminal activity.",
    )
    parser.add_argument(
        "--idle-observed-at",
        help="Timestamp to use for scripted idle terminal activity.",
    )
    parser.add_argument(
        "--max-idle-cycles",
        type=int,
        help="Optional number of idle cycles before exiting.",
    )
    parser.add_argument(
        "--max-action-requests",
        type=int,
        help="Optional number of action requests to handle before exiting.",
    )
    parser.add_argument(
        "--max-sessions",
        type=int,
        help="Optional number of daemon sessions to run before exiting.",
    )
    parser.add_argument(
        "--stdin-observed-at",
        help="Optional fixed timestamp for the first live stdin input event.",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Run the resident terminal edge in full-screen Textual UI mode.",
    )
    parser.add_argument(
        "--coding-workspace",
        type=Path,
        help="Workspace used by the hosted Codex coding agent (defaults to cwd).",
    )
    parser.add_argument(
        "--disable-coding-bridge",
        action="store_true",
        help="Keep the Terminal Edge available without starting hosted Codex.",
    )
    parser.add_argument(
        "--diagnostic-log-path",
        type=Path,
        help="Optional local JSONL path for terminal-edge diagnostic.v1 events.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_terminal_daemon_parser()
    args = parser.parse_args(argv)
    scripted_inputs = []
    scripted_text = os.environ.get("TERMINAL_EDGE_SCRIPTED_TEXT")
    scripted_observed_at = os.environ.get("TERMINAL_EDGE_SCRIPTED_OBSERVED_AT")
    if scripted_text and scripted_observed_at:
        scripted_inputs.append(
            {
                "text": scripted_text,
                "observed_at": scripted_observed_at,
            }
        )
    if args.tui and not terminal_supports_textual_fullscreen():
        print(
            "TERM="
            f"{os.environ.get('TERM', '') or '(unset)'} does not support reliable "
            "Textual full-screen mode; falling back to line mode."
        )
    elif args.tui:
        from device_edge.cli.terminal_tui import run_textual_terminal_daemon

        run_textual_terminal_daemon(
            url=args.url,
            device_id=args.device_id,
            identity_home=args.home,
            display_name=args.display_name,
            startup_observed_at=args.startup_observed_at,
            idle_timeout_s=args.idle_timeout,
            idle_observed_at=args.idle_observed_at,
            max_idle_cycles=args.max_idle_cycles,
            max_action_requests=args.max_action_requests,
            max_sessions=args.max_sessions,
            stdin_observed_at=args.stdin_observed_at,
            scripted_inputs=scripted_inputs,
            coding_enabled=not args.disable_coding_bridge,
            coding_workspace=args.coding_workspace,
            coding_activity_path=(
                build_coding_activity_path(args.home, args.device_id)
                if not args.disable_coding_bridge
                else None
            ),
            diagnostic_recorder=JsonlDiagnosticRecorder(args.diagnostic_log_path)
            if args.diagnostic_log_path is not None
            else None,
        )
        return
    daemon = TerminalEdgeDaemon(
        device_id=args.device_id,
        audience=args.url,
        identity=load_or_create_identity(
            args.home or Path(os.environ.get("OPENHALO_HOME", Path.home() / ".openhalo")),
            args.device_id,
        ),
        display_name=args.display_name,
        stdin_observed_at=args.stdin_observed_at,
        coding_enabled=not args.disable_coding_bridge,
        coding_workspace=args.coding_workspace,
        coding_activity_path=(
            build_coding_activity_path(args.home, args.device_id)
            if not args.disable_coding_bridge
            else None
        ),
        diagnostic_recorder=JsonlDiagnosticRecorder(args.diagnostic_log_path)
        if args.diagnostic_log_path is not None
        else None,
    )
    asyncio.run(
        daemon.run_forever(
            url=args.url,
            scripted_inputs=scripted_inputs,
            startup_observed_at=args.startup_observed_at,
            idle_timeout_s=args.idle_timeout,
            idle_observed_at=args.idle_observed_at,
            max_idle_cycles=args.max_idle_cycles,
            max_action_requests=args.max_action_requests,
            max_sessions=args.max_sessions,
            enable_live_input=True,
        )
    )


__all__ = [
    "TerminalEdgeDaemon",
    "build_coding_activity_path",
    "build_terminal_daemon_parser",
    "main",
]


if __name__ == "__main__":
    main()
