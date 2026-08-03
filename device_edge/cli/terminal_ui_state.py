"""Presentation state for the full-screen terminal edge UI."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptEntry:
    role: str
    body: str


@dataclass(frozen=True)
class RuntimeSummaryView:
    summary: str
    result_status: str | None
    terminal_reason: str | None

    @property
    def is_error(self) -> bool:
        failed_values = {"error", "failed", "failure", "provider_failure"}
        return (
            (self.result_status or "").lower() in failed_values
            or (self.terminal_reason or "").lower() in failed_values
        )


@dataclass(frozen=True)
class DeviceSummaryView:
    device_id: str
    device_type: str
    role: str | None
    online: bool
    action_capabilities: tuple[str, ...]


@dataclass(frozen=True)
class InteractionRouteStepView:
    target_device_id: str
    capability: str
    presence_decision: str


@dataclass(frozen=True)
class InteractionRouteView:
    interaction_id: str
    source_device_id: str
    routes: tuple[InteractionRouteStepView, ...]


@dataclass(frozen=True)
class DaemonUiSnapshot:
    connection_state: str
    pending_runtime_reply: bool
    active_progress_phase: str | None
    runtime_summary: RuntimeSummaryView | None
    devices: tuple[DeviceSummaryView, ...]
    interaction_route: InteractionRouteView | None
    reconnect_attempt: int
    reconnect_delay_s: float
    connection_recovered: bool

    @classmethod
    def from_daemon(cls, daemon) -> "DaemonUiSnapshot":
        raw_summary = getattr(daemon, "latest_runtime_summary", None)
        runtime_summary = None
        if isinstance(raw_summary, dict):
            runtime_summary = RuntimeSummaryView(
                summary=str(raw_summary.get("summary", "")),
                result_status=raw_summary.get("result_status"),
                terminal_reason=raw_summary.get("terminal_reason"),
            )
        raw_route = getattr(daemon, "active_interaction_route", None)
        interaction_route = None
        if isinstance(raw_route, dict):
            interaction_route = InteractionRouteView(
                interaction_id=str(raw_route.get("interaction_id", "")),
                source_device_id=str(raw_route.get("source_device_id", "")),
                routes=tuple(
                    InteractionRouteStepView(
                        target_device_id=str(route.get("target_device_id", "")),
                        capability=str(route.get("capability", "")),
                        presence_decision=str(
                            route.get("presence_decision", "allow")
                        ),
                    )
                    for route in raw_route.get("routes", ())
                    if isinstance(route, dict)
                ),
            )
        return cls(
            connection_state=daemon.connection_state,
            pending_runtime_reply=daemon.pending_runtime_reply,
            active_progress_phase=daemon.active_progress_phase,
            runtime_summary=runtime_summary,
            devices=tuple(
                DeviceSummaryView(
                    device_id=str(device.get("device_id", "")),
                    device_type=str(device.get("device_type", "unknown")),
                    role=device.get("role")
                    if isinstance(device.get("role"), str)
                    else None,
                    online=bool(device.get("online")),
                    action_capabilities=tuple(
                        str(capability)
                        for capability in device.get("action_capabilities", ())
                    ),
                )
                for device in getattr(daemon, "device_roster", ())
                if isinstance(device, dict)
            ),
            interaction_route=interaction_route,
            reconnect_attempt=getattr(daemon, "reconnect_attempt", 0),
            reconnect_delay_s=getattr(daemon, "reconnect_delay_s", 0.0),
            connection_recovered=getattr(daemon, "connection_recovered", False),
        )


@dataclass(frozen=True)
class ActiveInteractionView:
    state: str
    title: str
    detail: str


PROGRESS_PRESENTATION = {
    "deliberating": (
        "正在理解你的请求...",
        "正在理解你的请求",
        "正在整理上下文并判断下一步",
    ),
    "researching": (
        "正在查询相关信息...",
        "正在查询相关信息",
        "只会展示适合公开的进度",
    ),
    "planning": (
        "正在准备下一步...",
        "正在准备下一步",
        "正在选择合适的设备和能力",
    ),
    "executing": (
        "正在执行操作...",
        "正在执行操作",
        "已将操作交给目标设备",
    ),
    "awaiting_action_result": (
        "正在等待设备确认...",
        "正在等待设备确认",
        "操作完成后会在这里更新结果",
    ),
    "completing": (
        "正在确认处理结果...",
        "正在确认处理结果",
        "正在完成本次交互",
    ),
    "failed": ("暂时无法继续处理", "本次请求未能完成", "暂时无法继续处理"),
    "cancelled": ("处理已停止", "处理已停止", "本次交互已取消"),
}


class TerminalUiReducer:
    """Convert daemon output and state into a presentation model."""

    @staticmethod
    def consume_line(
        line: str,
        snapshot: DaemonUiSnapshot | None = None,
    ) -> TranscriptEntry | None:
        parsed = parse_terminal_line(line)
        if parsed.role == "progress":
            return None
        is_error = bool(
            parsed.role == "runtime"
            and snapshot is not None
            and snapshot.runtime_summary is not None
            and snapshot.runtime_summary.is_error
            and parsed.body == snapshot.runtime_summary.summary
        )
        return TranscriptEntry(
            role="error" if is_error else parsed.role,
            body=parsed.body,
        )

    @staticmethod
    def device_summary(snapshot: DaemonUiSnapshot) -> str:
        if not snapshot.devices:
            return "Global thread"
        online = sum(device.online for device in snapshot.devices)
        return f"Global thread · {online}/{len(snapshot.devices)} edges"

    @staticmethod
    def device_overview(snapshot: DaemonUiSnapshot, current_device_id: str) -> str:
        if not snapshot.devices:
            return "No device roster received yet."
        rows = []
        for device in snapshot.devices:
            marker = "●" if device.online else "○"
            current = " · you are here" if device.device_id == current_device_id else ""
            role = f" · {device.role}" if device.role else ""
            capabilities = ", ".join(device.action_capabilities) or "no actions"
            rows.append(
                f"{marker} {device.device_id} · {device.device_type}{role} "
                f"· {capabilities}{current}"
            )
        return "\n".join(rows)

    @staticmethod
    def _route_interaction(
        snapshot: DaemonUiSnapshot,
    ) -> ActiveInteractionView | None:
        route = snapshot.interaction_route
        if route is None or not route.routes:
            return None
        step = route.routes[0]
        title = (
            f"{route.source_device_id} → Personal Runtime "
            f"[Presence {step.presence_decision}] → {step.target_device_id}"
        )
        detail = step.capability
        if len(route.routes) > 1:
            detail = f"{detail} · +{len(route.routes) - 1} more actions"
        return ActiveInteractionView(state="route", title=title, detail=detail)

    @staticmethod
    def active_interaction(snapshot: DaemonUiSnapshot) -> ActiveInteractionView:
        connection_state = snapshot.connection_state
        if connection_state == "connecting":
            return ActiveInteractionView(
                state="connecting",
                title="正在连接 Personal Runtime",
                detail="连接成功后即可发送消息",
            )
        if connection_state == "reconnecting":
            retry_detail = "未提交的草稿会保留；在途请求不会自动重放"
            if snapshot.reconnect_attempt:
                retry_detail = (
                    f"第 {snapshot.reconnect_attempt} 次重试 · "
                    f"{snapshot.reconnect_delay_s:g} 秒后继续 · 草稿已保留"
                )
            return ActiveInteractionView(
                state="reconnecting",
                title="连接已中断，正在重试",
                detail=retry_detail,
            )
        if connection_state == "disconnected":
            return ActiveInteractionView(
                state="offline",
                title="Personal Runtime 当前离线",
                detail="可使用 /reconnect 立即重试",
            )
        route_view = TerminalUiReducer._route_interaction(snapshot)
        if route_view is not None:
            return route_view
        if snapshot.connection_recovered:
            return ActiveInteractionView(
                state="recovered",
                title="Runtime 连接已恢复",
                detail="在途请求未自动重放",
            )
        if snapshot.active_progress_phase in PROGRESS_PRESENTATION:
            _, title, detail = PROGRESS_PRESENTATION[snapshot.active_progress_phase]
            return ActiveInteractionView(
                state="active",
                title=title,
                detail=detail,
            )
        if snapshot.pending_runtime_reply:
            return ActiveInteractionView(
                state="waiting",
                title="正在等待 OpenHalo 回复",
                detail="请求已发送到 Personal Runtime",
            )
        if snapshot.runtime_summary is not None and snapshot.runtime_summary.is_error:
            return ActiveInteractionView(
                state="error",
                title="本次请求未能完成",
                detail=snapshot.runtime_summary.summary,
            )
        return ActiveInteractionView(state="idle", title="", detail="")


@dataclass(frozen=True)
class ParsedTerminalLine:
    role: str
    body: str


def parse_terminal_line(line: str) -> ParsedTerminalLine:
    for role in ("system", "user", "runtime", "progress"):
        prefix = f"[{role}]"
        if line.startswith(prefix):
            return ParsedTerminalLine(role=role, body=line[len(prefix) :].lstrip())
    return ParsedTerminalLine(role="system", body=line)


class InputHistory:
    def __init__(self, limit: int = 100) -> None:
        self._items: deque[str] = deque(maxlen=limit)
        self._index: int | None = None
        self._draft = ""

    @property
    def items(self) -> tuple[str, ...]:
        return tuple(self._items)

    def record(self, value: str) -> None:
        normalized = value.strip()
        if normalized and (not self._items or self._items[-1] != normalized):
            self._items.append(normalized)
        self.reset_navigation()

    def previous(self, current_draft: str) -> str:
        if not self._items:
            return current_draft
        if self._index is None:
            self._draft = current_draft
            self._index = len(self._items) - 1
        else:
            self._index = max(0, self._index - 1)
        return self._items[self._index]

    def next(self, current_value: str) -> str:
        if self._index is None:
            return current_value
        if self._index < len(self._items) - 1:
            self._index += 1
            return self._items[self._index]
        self._index = None
        return self._draft

    def reset_navigation(self) -> None:
        self._index = None
        self._draft = ""


@dataclass(frozen=True)
class LocalCommand:
    name: str
    description: str


class SlashCommandCatalog:
    commands = (
        LocalCommand("/help", "显示本地命令"),
        LocalCommand("/status", "显示连接和会话状态"),
        LocalCommand("/history", "重放最近的会话记录"),
        LocalCommand("/clear", "清空当前可见对话"),
        LocalCommand("/reconnect", "重新连接 Personal Runtime"),
        LocalCommand("/quit", "退出 Terminal Edge"),
    )
    names = tuple(command.name for command in commands)

    @classmethod
    def help_text(cls) -> str:
        return " ".join(cls.names)

    @classmethod
    def matches(cls, value: str) -> tuple[LocalCommand, ...]:
        normalized = value.strip().lower()
        if not normalized.startswith("/"):
            return ()
        return tuple(
            command for command in cls.commands if command.name.startswith(normalized)
        )

    @classmethod
    def complete(cls, value: str, direction: int = 1) -> str:
        normalized = value.strip().lower()
        names = cls.names
        if normalized in names:
            index = names.index(normalized)
            return names[(index + direction) % len(names)]
        matches = [command.name for command in cls.matches(normalized)]
        if not matches:
            return value
        return matches[0] if direction >= 0 else matches[-1]
