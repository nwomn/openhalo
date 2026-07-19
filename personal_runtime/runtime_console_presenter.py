"""Human-readable local Runtime presentation for safe lifecycle progress."""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Mapping


_PHASE_MESSAGES = {
    "deliberating": "正在理解请求",
    "researching": "正在查询相关信息",
    "planning": "正在准备下一步",
    "executing": "正在执行操作",
    "awaiting_action_result": "正在等待设备确认",
    "completing": "正在确认处理结果",
    "completed": "本次处理已完成",
    "failed": "本次处理未完成",
    "cancelled": "本次处理已停止",
}


class RuntimeConsolePresenter:
    """Render only fixed OpenHalo status text from safe progress phases."""

    def __init__(self, emit: Callable[[str], None] | None = None) -> None:
        self._emit = emit

    def present(self, progress: Mapping[str, object]) -> str | None:
        phase = progress.get("phase")
        if not isinstance(phase, str):
            return None
        message = _PHASE_MESSAGES.get(phase)
        if message is None:
            return None

        rendered = f"OpenHalo Runtime · {message}"
        if self._emit is not None:
            try:
                self._emit(rendered)
            except Exception:
                pass
        return rendered
