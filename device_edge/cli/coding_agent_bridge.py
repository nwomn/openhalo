"""Codex-first coding capability hosted by the Terminal Edge."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import secrets
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from device_edge.cli.codex_app_server import CodexAppServerClient


CODING_ACTIVITY_SCHEMA = {
    "type": "object",
    "required": [
        "agent",
        "interaction_id",
        "agent_session_id",
        "agent_turn_id",
        "event_kind",
        "phase",
        "observed_at",
        "confidence",
        "causal_parent",
        "workspace_ref",
        "summary",
        "evidence_ref",
    ],
    "additionalProperties": False,
    "properties": {
        "agent": {"type": "string", "enum": ["codex"]},
        "interaction_id": {"type": "string", "minLength": 1},
        "agent_session_id": {"type": "string", "minLength": 1},
        "agent_turn_id": {"type": "string", "minLength": 1},
        "event_kind": {
            "type": "string",
            "enum": [
                "session_started",
                "prompt_submitted",
                "reasoning_summary",
                "plan_update",
                "agent_message",
                "command_execution",
                "tool_activity",
                "file_change",
                "test_result",
                "user_correction",
                "turn_completed",
                "turn_failed",
                "approval_waiting",
                "approval_resolved",
                "turn_interrupted",
            ],
        },
        "phase": {"type": "string", "minLength": 1},
        "observed_at": {"type": "string", "minLength": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "causal_parent": {"type": "string", "minLength": 1},
        "workspace_ref": {"type": "string", "minLength": 1},
        "summary": {"type": "string", "maxLength": 4096},
        "evidence_ref": {"type": "string", "maxLength": 256},
    },
}

CODING_ATTENTION_SCHEMA = CODING_ACTIVITY_SCHEMA


def _action_registration(
    name: str,
    *,
    input_schema: dict,
    side_effect: str,
    affordances: list[str],
) -> dict:
    return {
        "name": name,
        "direction": "runtime_to_edge",
        "kind": "action",
        "affordances": affordances,
        "modality": "terminal_text",
        "content_capacity": "bounded_text",
        "privacy": "personal",
        "interruptiveness": "medium",
        "side_effect": side_effect,
        "input_schema": input_schema,
    }


CODING_CAPABILITY_REGISTRATIONS = (
    {
        "name": "coding.activity",
        "direction": "edge_to_runtime",
        "kind": "observation_provider",
        "observations": [
            {
                "name": "coding.activity.v1",
                "schema": CODING_ACTIVITY_SCHEMA,
                "semantics": ["coding_agent_activity", "ordinary_observation"],
                "privacy": "local_coding_metadata",
                "freshness_seconds": 30,
                "confidence": {"type": "bridge_normalized"},
            }
        ],
    },
    _action_registration(
        "coding.turn.start",
        input_schema={
            "type": "object",
            "required": ["task", "workspace_ref", "interaction_id"],
            "additionalProperties": False,
            "properties": {
                "task": {"type": "string", "minLength": 1, "maxLength": 12000},
                "workspace_ref": {"type": "string", "minLength": 1},
                "interaction_id": {"type": "string", "minLength": 1},
            },
        },
        side_effect="agent_execution",
        affordances=["start_coding_turn"],
    ),
    _action_registration(
        "coding.suggestion.offer",
        input_schema={
            "type": "object",
            "required": ["suggestion_id", "agent_session_id", "agent_turn_id", "summary"],
            "additionalProperties": False,
            "properties": {
                "suggestion_id": {"type": "string", "minLength": 1},
                "agent_session_id": {"type": "string", "minLength": 1},
                "agent_turn_id": {"type": "string", "minLength": 1},
                "summary": {"type": "string", "minLength": 1, "maxLength": 512},
            },
        },
        side_effect="user_confirmation",
        affordances=["offer_coding_guidance"],
    ),
    _action_registration(
        "coding.turn.steer",
        input_schema={
            "type": "object",
            "required": [
                "suggestion_id",
                "confirmation_ref",
                "agent_session_id",
                "agent_turn_id",
                "instruction",
            ],
            "additionalProperties": False,
            "properties": {
                "suggestion_id": {"type": "string", "minLength": 1},
                "confirmation_ref": {"type": "string", "minLength": 1},
                "agent_session_id": {"type": "string", "minLength": 1},
                "agent_turn_id": {"type": "string", "minLength": 1},
                "instruction": {"type": "string", "minLength": 1, "maxLength": 12000},
            },
        },
        side_effect="agent_execution",
        affordances=["steer_coding_turn"],
    ),
)


_CODING_ACTION_SCHEMAS = {
    registration["name"]: registration["input_schema"]
    for registration in CODING_CAPABILITY_REGISTRATIONS
    if registration.get("kind") == "action"
}


def validate_coding_action_payload(capability: str, payload: object) -> dict:
    schema = _CODING_ACTION_SCHEMAS.get(capability)
    if schema is None:
        raise ValueError("Unsupported coding action capability.")
    if not isinstance(payload, dict):
        raise ValueError("Coding action payload must be an object.")
    required = schema.get("required", [])
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"Coding action payload is missing: {', '.join(missing)}.")
    properties = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        unexpected = sorted(set(payload) - set(properties))
        if unexpected:
            raise ValueError(
                f"Coding action payload has unsupported fields: {', '.join(unexpected)}."
            )
    for key, value in payload.items():
        property_schema = properties.get(key)
        if not isinstance(property_schema, dict):
            continue
        if property_schema.get("type") == "string" and not isinstance(value, str):
            raise ValueError(f"Coding action field {key!r} must be a string.")
        if isinstance(value, str):
            minimum = property_schema.get("minLength")
            maximum = property_schema.get("maxLength")
            if isinstance(minimum, int) and len(value) < minimum:
                raise ValueError(f"Coding action field {key!r} must not be empty.")
            if isinstance(maximum, int) and len(value) > maximum:
                raise ValueError(f"Coding action field {key!r} is too long.")
    return payload


def _truncate_utf8(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


@dataclass
class _TaskState:
    interaction_id: str
    thread_id: str
    turn_id: str
    status: str = "active"
    terminal_event_kind: str | None = None
    evidence_sequence: int = 0


@dataclass
class _SuggestionState:
    prompt_id: str
    suggestion_id: str
    agent_session_id: str
    agent_turn_id: str
    summary: str


@dataclass
class _ApprovalState:
    prompt_id: str
    request_id: int | str
    method: str
    params: dict
    future: asyncio.Future


@dataclass
class _CoalescedDelta:
    thread_id: str
    turn_id: str
    event_kind: str
    count: int = 0
    byte_count: int = 0
    item_type: str = "unknown"
    preview: str = ""
    flush_task: asyncio.Task | None = None


class CodingAgentBridge:
    coalesce_window_s = 0.5
    evidence_task_limit = 32
    # Evidence metadata is independently byte-bounded; it is not an activity
    # history window and must not silently impose a 64-event task limit.
    evidence_entry_limit: int | None = None
    evidence_entry_bytes = 4096
    evidence_task_bytes = 256 * 1024
    active_task_limit = 32

    def __init__(
        self,
        *,
        client: CodexAppServerClient,
        workspace_path: str | Path,
        workspace_ref: str,
        observation_sink: Callable[[dict], Any] | None = None,
        approval_sink: Callable[[dict], Any] | None = None,
        timestamp_provider: Callable[[], str] | None = None,
    ) -> None:
        self.client = client
        self.workspace_path = str(Path(workspace_path).expanduser().resolve())
        self.workspace_ref = workspace_ref
        self.observation_sink = observation_sink
        self.approval_sink = approval_sink
        self.timestamp_provider = timestamp_provider or self._default_timestamp
        self.state = "disconnected"
        self.tasks: dict[str, _TaskState] = {}
        self._task_by_thread: dict[str, _TaskState] = {}
        self._suggestions: dict[str, _SuggestionState] = {}
        self._confirmations: dict[str, dict] = {}
        self._approvals: dict[str, _ApprovalState] = {}
        self._evidence: OrderedDict[str, deque[dict]] = OrderedDict()
        self._evidence_bytes: dict[str, int] = {}
        self._deltas: dict[tuple[str, str, str], _CoalescedDelta] = {}
        self._started_turn_events: set[tuple[str, str]] = set()
        self._prompt_sequence = 0

    async def start(self) -> None:
        self.client.notification_handler = self.handle_notification
        self.client.server_request_handler = self.handle_server_request
        try:
            await self.client.start()
        except Exception:
            self.state = "degraded"
            raise
        self.state = "ready"

    async def close(self) -> None:
        cancelled_tasks = []
        for delta in self._deltas.values():
            if delta.flush_task is not None:
                delta.flush_task.cancel()
                cancelled_tasks.append(delta.flush_task)
        self._deltas.clear()
        if cancelled_tasks:
            await asyncio.gather(*cancelled_tasks, return_exceptions=True)
        for approval in tuple(self._approvals.values()):
            if not approval.future.done():
                approval.future.set_result(self._approval_result(approval, "decline"))
        self._approvals.clear()
        await self.client.close()
        self.state = "disconnected"

    async def start_turn(
        self,
        *,
        interaction_id: str,
        task: str,
        workspace_ref: str,
    ) -> dict:
        if self.state != "ready":
            raise ConnectionError("Coding Bridge is not ready.")
        if not interaction_id or not task.strip():
            raise ValueError("Coding turn requires interaction_id and task.")
        if workspace_ref != self.workspace_ref:
            raise ValueError("Coding turn workspace does not match this Terminal Edge.")
        existing = self.tasks.get(interaction_id)
        if existing is not None and existing.status == "active":
            raise ValueError("Coding interaction already has an active turn.")
        if sum(task.status == "active" for task in self.tasks.values()) >= self.active_task_limit:
            raise RuntimeError("The active Coding task limit has been reached.")
        thread = await self.client.start_thread(cwd=self.workspace_path)
        thread_id = thread["id"]
        turn = await self.client.start_turn(
            thread_id=thread_id,
            text=task.strip(),
            cwd=self.workspace_path,
        )
        task_state = _TaskState(
            interaction_id=interaction_id,
            thread_id=thread_id,
            turn_id=turn["id"],
        )
        self.tasks[interaction_id] = task_state
        self._task_by_thread[thread_id] = task_state
        self._started_turn_events.add((thread_id, turn["id"]))
        self._emit_observation(
            self._build_observation(
                task_state,
                event_kind="session_started",
                phase="active",
                summary="Codex session started.",
                evidence_metadata={},
            )
        )
        self._emit_observation(
            self._build_observation(
                task_state,
                event_kind="prompt_submitted",
                phase="in_progress",
                summary="Codex turn started.",
                evidence_metadata={"task_length": len(task.strip())},
            )
        )
        return {
            "status": "ok",
            "capability": "coding.turn.start",
            "agent": "codex",
            "agent_session_id": thread_id,
            "agent_turn_id": turn["id"],
            "workspace_ref": self.workspace_ref,
        }

    def offer_suggestion(
        self,
        *,
        suggestion_id: str,
        agent_session_id: str,
        agent_turn_id: str,
        summary: str,
    ) -> dict:
        if not suggestion_id or not agent_session_id or not agent_turn_id or not summary.strip():
            raise ValueError("Coding suggestion is incomplete.")
        self._prompt_sequence += 1
        prompt_id = f"suggestion-{self._prompt_sequence}"
        state = _SuggestionState(
            prompt_id=prompt_id,
            suggestion_id=suggestion_id,
            agent_session_id=agent_session_id,
            agent_turn_id=agent_turn_id,
            summary=summary.strip()[:512],
        )
        self._suggestions[prompt_id] = state
        self._emit_prompt(
            {
                "kind": "suggestion",
                "prompt_id": prompt_id,
                "suggestion_id": suggestion_id,
                "summary": state.summary,
                "choices": ["accept", "ignore", "suppress_task"],
            }
        )
        return {
            "prompt_id": prompt_id,
            "suggestion_id": suggestion_id,
            "summary": state.summary,
        }

    def resolve_suggestion(self, prompt_id: str, choice: str) -> dict:
        state = self._suggestions.pop(prompt_id, None)
        if state is None:
            raise ValueError("Coding suggestion is no longer pending.")
        if choice not in {"accept", "ignore", "suppress_task"}:
            raise ValueError("Unsupported coding suggestion choice.")
        details = {"choice": choice, "suggestion_id": state.suggestion_id}
        if choice == "accept":
            confirmation_ref = f"confirmation-{secrets.token_urlsafe(12)}"
            self._confirmations[confirmation_ref] = {
                "suggestion_id": state.suggestion_id,
                "agent_session_id": state.agent_session_id,
                "agent_turn_id": state.agent_turn_id,
            }
            details["confirmation_ref"] = confirmation_ref
        return {
            "status": "ok",
            "capability": "coding.suggestion.offer",
            "details": details,
        }

    async def steer(
        self,
        *,
        suggestion_id: str,
        confirmation_ref: str,
        agent_session_id: str,
        agent_turn_id: str,
        instruction: str,
    ) -> dict:
        confirmation = self._confirmations.get(confirmation_ref)
        if confirmation is None or confirmation.get("used"):
            raise ValueError("Coding steer requires an unused confirmation.")
        expected = {
            "suggestion_id": suggestion_id,
            "agent_session_id": agent_session_id,
            "agent_turn_id": agent_turn_id,
        }
        if any(confirmation.get(key) != value for key, value in expected.items()):
            raise ValueError("Coding steer lineage does not match its confirmation.")
        task_state = self._task_by_thread.get(agent_session_id)
        if task_state is None or task_state.turn_id != agent_turn_id:
            raise ValueError("Coding steer targets a stale turn.")
        if not instruction.strip():
            raise ValueError("Coding steer instruction must not be empty.")
        await self.client.steer(
            thread_id=agent_session_id,
            expected_turn_id=agent_turn_id,
            text=instruction.strip(),
        )
        confirmation["used"] = True
        self._emit_observation(
            self._build_observation(
                task_state,
                event_kind="user_correction",
                phase="in_progress",
                summary="User confirmed a Codex turn steer.",
                evidence_metadata={"suggestion_id": suggestion_id},
            )
        )
        return {
            "status": "ok",
            "capability": "coding.turn.steer",
            "agent": "codex",
            "agent_session_id": agent_session_id,
            "agent_turn_id": agent_turn_id,
        }

    async def foreground_steer(
        self,
        *,
        interaction_id: str,
        instruction: str,
    ) -> dict:
        """Send explicit foreground composer input to one selected active task."""

        task_state = self.tasks.get(interaction_id)
        if task_state is None or task_state.status != "active":
            raise ValueError("Coding input requires an explicitly selected active task.")
        instruction = instruction.strip()
        if not instruction:
            raise ValueError("Coding correction must not be empty.")
        if len(instruction) > 12000:
            raise ValueError("Coding correction is limited to 12000 characters.")
        self._emit_observation(
            self._build_observation(
                task_state,
                event_kind="user_correction",
                phase="in_progress",
                summary=instruction,
                evidence_metadata={"correction_length": len(instruction)},
            )
        )
        await self.client.steer(
            thread_id=task_state.thread_id,
            expected_turn_id=task_state.turn_id,
            text=instruction,
        )
        return {
            "status": "ok",
            "agent": "codex",
            "agent_session_id": task_state.thread_id,
            "agent_turn_id": task_state.turn_id,
        }

    async def interrupt(self, *, interaction_id: str) -> dict:
        task_state = self.tasks.get(interaction_id)
        if task_state is None or task_state.status != "active":
            raise ValueError("Coding interrupt requires an explicitly selected active task.")
        await self.client.interrupt(
            thread_id=task_state.thread_id,
            turn_id=task_state.turn_id,
        )
        task_state.status = "completed"
        task_state.terminal_event_kind = "turn_interrupted"
        self._emit_observation(
            self._build_observation(
                task_state,
                event_kind="turn_interrupted",
                phase="interrupted",
                summary="User interrupted the Codex turn.",
                evidence_metadata={},
            )
        )
        return {
            "status": "ok",
            "agent": "codex",
            "agent_session_id": task_state.thread_id,
            "agent_turn_id": task_state.turn_id,
        }

    def handle_notification(self, message: dict) -> None:
        method = message.get("method")
        params = message.get("params")
        if not isinstance(method, str) or not isinstance(params, dict):
            return
        thread_id = params.get("threadId")
        if not isinstance(thread_id, str):
            thread = params.get("thread")
            if isinstance(thread, dict):
                thread_id = thread.get("id")
        if not isinstance(thread_id, str):
            return
        task_state = self._task_by_thread.get(thread_id)
        if task_state is None:
            return
        turn_id = params.get("turnId") or params.get("turn", {}).get("id")
        if not isinstance(turn_id, str):
            turn_id = task_state.turn_id
        if method == "thread/started":
            self._emit_observation(
                self._build_observation(
                    task_state,
                    event_kind="session_started",
                    phase="active",
                    summary="Codex session started.",
                    evidence_metadata={},
                )
            )
            return
        if method == "turn/started":
            task_state.turn_id = turn_id
            if (thread_id, turn_id) in self._started_turn_events:
                return
            self._emit_observation(
                self._build_observation(
                    task_state,
                    event_kind="prompt_submitted",
                    phase="in_progress",
                    summary="Codex turn is running.",
                    evidence_metadata={},
                )
            )
            return
        if method == "turn/completed":
            turn = params.get("turn")
            status = turn.get("status") if isinstance(turn, dict) else params.get("status")
            if status == "completed":
                event_kind, phase = "turn_completed", "completed"
            elif status == "interrupted":
                event_kind, phase = "turn_interrupted", "interrupted"
            else:
                event_kind, phase = "turn_failed", "failed"
            if task_state.terminal_event_kind == event_kind:
                return
            task_state.status = "completed"
            task_state.terminal_event_kind = event_kind
            self._emit_observation(
                self._build_observation(
                    task_state,
                    event_kind=event_kind,
                    phase=phase,
                    summary=(
                        "Codex turn completed."
                        if event_kind == "turn_completed"
                        else "User interrupted the Codex turn."
                        if event_kind == "turn_interrupted"
                        else "Codex turn failed."
                    ),
                    evidence_metadata={"status": status or "unknown"},
                )
            )
            return
        if method == "turn/plan/updated":
            plan = params.get("plan")
            steps = plan if isinstance(plan, list) else []
            lines = []
            for step in steps[:32]:
                if not isinstance(step, dict):
                    continue
                text = step.get("step") or step.get("text")
                if isinstance(text, str) and text.strip():
                    lines.append(f"[{step.get('status', 'pending')}] {text.strip()}")
            if len(steps) > 32:
                lines.append("[… plan truncated after 32 items]")
            self._emit_observation(
                self._build_observation(
                    task_state,
                    event_kind="plan_update",
                    phase="in_progress",
                    summary="\n".join(lines)[:4096] or "Codex plan updated.",
                    evidence_metadata={"step_count": len(steps), "truncated": len(steps) > 32},
                )
            )
            return
        event_kind = self._event_kind_for_notification(method, params)
        if event_kind is None:
            return
        if (
            method.endswith("/delta")
            or method.endswith("Delta")
            or method == "turn/diff/updated"
        ):
            self._coalesce_delta(task_state, turn_id, event_kind, params)
            return
        summary = self._bounded_summary(method, params, event_kind)
        self._emit_observation(
            self._build_observation(
                task_state,
                event_kind=event_kind,
                phase="awaiting_approval" if event_kind == "approval_waiting" else "in_progress",
                summary=summary,
                evidence_metadata={"method": method},
            )
        )

    async def handle_server_request(self, message: dict) -> dict:
        method = message.get("method")
        params = message.get("params")
        request_id = message.get("id")
        if not isinstance(method, str) or not isinstance(params, dict):
            raise ValueError("Invalid Codex approval request.")
        if method not in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
        }:
            raise ValueError("Unsupported Codex App Server request.")
        self._prompt_sequence += 1
        prompt_id = f"approval-{self._prompt_sequence}"
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        state = _ApprovalState(
            prompt_id=prompt_id,
            request_id=request_id,
            method=method,
            params=params,
            future=future,
        )
        self._approvals[prompt_id] = state
        kind = {
            "item/commandExecution/requestApproval": "command",
            "item/fileChange/requestApproval": "file_change",
            "item/permissions/requestApproval": "permissions",
        }[method]
        task_state = self._task_by_thread.get(str(params.get("threadId")))
        if task_state is not None:
            self._emit_observation(
                self._build_observation(
                    task_state,
                    event_kind="approval_waiting",
                    phase="awaiting_approval",
                    summary=f"Codex requests {kind} approval.",
                    evidence_metadata={"kind": kind},
                )
            )
        self._emit_prompt(
            {
                "kind": kind,
                "prompt_id": prompt_id,
                "thread_id": params.get("threadId"),
                "turn_id": params.get("turnId"),
                "summary": f"Codex requests {kind} approval.",
                "detail": self._local_approval_detail(method, params),
                "choices": ["accept", "acceptForSession", "decline", "cancel"],
            }
        )
        decision = await future
        self._approvals.pop(prompt_id, None)
        task_state = self._task_by_thread.get(str(params.get("threadId")))
        if task_state is not None:
            self._emit_observation(
                self._build_observation(
                    task_state,
                    event_kind="approval_resolved",
                    phase="in_progress",
                    summary=f"Codex {kind} approval {decision}.",
                    evidence_metadata={"decision": decision, "kind": kind},
                )
            )
        return self._approval_result(state, decision)

    def resolve_approval(self, prompt_id: str, decision: str) -> None:
        state = self._approvals.get(prompt_id)
        if state is None:
            raise ValueError("Codex approval is no longer pending.")
        if decision not in {"accept", "acceptForSession", "decline", "cancel"}:
            raise ValueError("Unsupported Codex approval decision.")
        if not state.future.done():
            state.future.set_result(decision)

    def read_evidence(self, evidence_ref: str, *, limit: int = 16) -> list[dict]:
        for entries in self._evidence.values():
            matches = [entry for entry in entries if entry["evidence_ref"] == evidence_ref]
            if matches:
                return [dict(entry) for entry in matches[: max(0, min(limit, 16))]]
        return []

    def _build_observation(
        self,
        task_state: _TaskState,
        *,
        event_kind: str,
        phase: str,
        summary: str,
        evidence_metadata: dict,
    ) -> dict:
        task_state.evidence_sequence += 1
        evidence_ref = (
            f"coding-evidence://{task_state.interaction_id}/{task_state.evidence_sequence}"
        )
        self._record_evidence(task_state, evidence_ref, event_kind, evidence_metadata)
        value = {
            "agent": "codex",
            "interaction_id": task_state.interaction_id,
            "agent_session_id": task_state.thread_id,
            "agent_turn_id": task_state.turn_id,
            "event_kind": event_kind,
            "phase": phase,
            "observed_at": self.timestamp_provider(),
            "confidence": 1.0,
            "causal_parent": f"{task_state.thread_id}:{task_state.turn_id}",
            "workspace_ref": self.workspace_ref,
            "summary": _truncate_utf8(summary, 4096),
            "evidence_ref": evidence_ref,
        }
        return {
            "name": "coding.activity.v1",
            "value": value,
            "observed_at": value["observed_at"],
            "confidence": 1.0,
        }

    def _record_evidence(
        self,
        task_state: _TaskState,
        evidence_ref: str,
        event_kind: str,
        metadata: dict,
    ) -> None:
        entries = self._evidence.setdefault(task_state.interaction_id, deque())
        self._evidence.move_to_end(task_state.interaction_id)
        serialized = str(metadata).encode(errors="replace")[: self.evidence_entry_bytes]
        entry = {
            "evidence_ref": evidence_ref,
            "event_kind": event_kind,
            "sha256": hashlib.sha256(serialized).hexdigest(),
            "byte_count": len(serialized),
            "metadata": {key: value for key, value in metadata.items() if key != "raw"},
        }
        entries.append(entry)
        self._evidence_bytes[task_state.interaction_id] = (
            self._evidence_bytes.get(task_state.interaction_id, 0) + len(serialized)
        )
        while (
            (
                self.evidence_entry_limit is not None
                and len(entries) > self.evidence_entry_limit
            )
            or self._evidence_bytes[task_state.interaction_id] > self.evidence_task_bytes
        ):
            removed = entries.popleft()
            self._evidence_bytes[task_state.interaction_id] = max(
                0,
                self._evidence_bytes[task_state.interaction_id] - removed["byte_count"],
            )
        while len(self._evidence) > self.evidence_task_limit:
            old_interaction_id, _ = self._evidence.popitem(last=False)
            self._evidence_bytes.pop(old_interaction_id, None)

    def _emit_observation(self, observation: dict) -> None:
        if self.observation_sink is None:
            return
        result = self.observation_sink(observation)
        if inspect.isawaitable(result):
            asyncio.create_task(result)

    def _emit_prompt(self, prompt: dict) -> None:
        if self.approval_sink is None:
            if prompt["kind"] == "approval":
                return
            return
        result = self.approval_sink(prompt)
        if inspect.isawaitable(result):
            asyncio.create_task(result)

    def _coalesce_delta(
        self,
        task_state: _TaskState,
        turn_id: str,
        event_kind: str,
        params: dict,
    ) -> None:
        key = (task_state.thread_id, turn_id, event_kind)
        delta = self._deltas.get(key)
        if delta is None:
            delta = _CoalescedDelta(
                thread_id=task_state.thread_id,
                turn_id=turn_id,
                event_kind=event_kind,
            )
            self._deltas[key] = delta
            delta.flush_task = asyncio.create_task(self._flush_delta(key))
        delta.count += 1
        raw = params.get("delta")
        if isinstance(raw, str):
            delta.byte_count += len(raw.encode(errors="replace"))
            if event_kind in {"reasoning_summary", "agent_message"} and not delta.preview:
                delta.preview = raw[:4096]
        item = params.get("item")
        if isinstance(item, dict) and isinstance(item.get("type"), str):
            delta.item_type = item["type"]

    async def _flush_delta(self, key: tuple[str, str, str]) -> None:
        await asyncio.sleep(self.coalesce_window_s)
        delta = self._deltas.pop(key, None)
        if delta is None:
            return
        task_state = self._task_by_thread.get(delta.thread_id)
        if task_state is None:
            return
        self._emit_observation(
            self._build_observation(
                task_state,
                event_kind=delta.event_kind,
                phase="in_progress",
                summary=(
                    delta.preview
                    if delta.preview
                    else f"Codex {delta.item_type} activity coalesced "
                    f"({delta.count} updates, {delta.byte_count} bytes)."
                ),
                evidence_metadata={
                    "update_count": delta.count,
                    "byte_count": delta.byte_count,
                    "item_type": delta.item_type,
                },
            )
        )

    @staticmethod
    def _event_kind_for_notification(method: str, params: dict) -> str | None:
        if method.startswith("item/reasoning/summary"):
            return "reasoning_summary"
        if method.startswith("item/agentMessage/"):
            return "agent_message"
        item = params.get("item")
        item_type = item.get("type") if isinstance(item, dict) else None
        if method.startswith("item/") and item_type in {
            "commandExecution",
            "command_execution",
        }:
            command = params.get("command")
            if not isinstance(command, str) and isinstance(item, dict):
                command = item.get("command")
            return "test_result" if "test" in str(command or "").lower() else "command_execution"
        if method.startswith("item/") and item_type in {"fileChange", "file_change"}:
            return "file_change"
        if method.startswith("item/") and item_type in {"agentMessage", "agent_message"}:
            return "agent_message"
        if method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
        }:
            return "approval_waiting"
        if method.startswith("item/fileChange/") or method == "turn/diff/updated":
            return "file_change"
        if method.startswith("item/commandExecution/"):
            return (
                "test_result"
                if "test" in str(params.get("command", "")).lower()
                else "command_execution"
            )
        if method.startswith("item/") and "test" in str(params.get("item", "")).lower():
            return "test_result"
        if method.startswith("item/"):
            return "tool_activity"
        return None

    @staticmethod
    def _bounded_summary(method: str, params: dict, event_kind: str) -> str:
        item = params.get("item")
        item_type = item.get("type") if isinstance(item, dict) else None
        if event_kind in {"reasoning_summary", "agent_message"}:
            text = params.get("delta") or params.get("summary") or params.get("summaryText")
            if not isinstance(text, str) and isinstance(item, dict):
                text = item.get("text") or item.get("summary")
            if isinstance(text, str) and text.strip():
                return text.strip()[:4096]
        if event_kind in {"command_execution", "test_result"}:
            command = params.get("command")
            if not isinstance(command, str) and isinstance(item, dict):
                command = item.get("command")
            status = item.get("status") if isinstance(item, dict) else params.get("status")
            if isinstance(command, str) and command:
                return f"{command[:3584]} · {status or 'updated'}"[:4096]
        if event_kind == "file_change" and isinstance(item, dict):
            paths = item.get("paths") or item.get("files") or item.get("changes")
            if isinstance(paths, list):
                rendered = [
                    str(path.get("path", path))[:256]
                    if isinstance(path, dict)
                    else str(path)[:256]
                    for path in paths[:32]
                ]
                if len(paths) > 32:
                    rendered.append("[… file list truncated after 32 items]")
                if rendered:
                    return "Files: " + ", ".join(rendered)
            path = item.get("path")
            if isinstance(path, str) and path:
                return f"File changed: {path[:4090]}"
        if item_type:
            return f"Codex {event_kind.replace('_', ' ')}: {item_type}."[:4096]
        return f"Codex {event_kind.replace('_', ' ')} ({method})."[:4096]

    @staticmethod
    def _local_approval_detail(method: str, params: dict) -> str:
        if method == "item/commandExecution/requestApproval":
            command = params.get("command")
            if isinstance(command, str) and command:
                return command[:512]
        if method == "item/fileChange/requestApproval":
            grant_root = params.get("grantRoot")
            if isinstance(grant_root, str) and grant_root:
                return grant_root[:512]
        if method == "item/permissions/requestApproval":
            permissions = params.get("permissions")
            if isinstance(permissions, dict):
                return ", ".join(sorted(permissions.keys()))[:512]
        return "Codex requested a local decision."

    @staticmethod
    def _approval_result(state: _ApprovalState, decision: str) -> dict:
        if state.method == "item/permissions/requestApproval":
            if decision in {"accept", "acceptForSession"}:
                return {
                    "permissions": state.params.get("permissions", {}),
                    "scope": "session" if decision == "acceptForSession" else "turn",
                }
            return {"permissions": {}, "scope": "turn"}
        return {"decision": decision}

    @staticmethod
    def _default_timestamp() -> str:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )


__all__ = [
    "CODING_CAPABILITY_REGISTRATIONS",
    "CodingAgentBridge",
    "validate_coding_action_payload",
]
