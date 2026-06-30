"""Runtime orchestration boundary between Gateway and runtime modules."""

from __future__ import annotations


class RuntimeOrchestrator:
    def __init__(self, gateway) -> None:
        self.gateway = gateway

    def handle_event_frame(self, frame: dict) -> list[dict]:
        return self.gateway._build_event_replies_impl(frame)

    def handle_action_result_frame(self, frame: dict) -> list[dict]:
        return self.gateway._build_action_result_replies_impl(frame)


__all__ = ["RuntimeOrchestrator"]
