"""Minimal session client for the v0 device edge."""

from device_edge.capability_runtime import CapabilityRuntime
from device_edge.local_actions import execute_action
from personal_runtime.protocol import build_connect_frame


class SessionClient:
    def __init__(self, device_id: str, device_type: str, token: str) -> None:
        self.device_id = device_id
        self.device_type = device_type
        self.token = token
        self.capability_runtime = CapabilityRuntime()

    def build_connect_frame(self) -> dict:
        return build_connect_frame(self.device_id, self.device_type, self.token)

    def build_capability_announce_frame(self) -> dict:
        return {
            "type": "capability_announce",
            "device_id": self.device_id,
            "capabilities": self.capability_runtime.capabilities,
        }

    def build_text_event(self, text: str) -> dict:
        return {
            "type": "event_push",
            "device_id": self.device_id,
            "capability": "text.input",
            "payload": {"text": text},
        }

    def handle_action_request(self, frame: dict) -> dict:
        result = execute_action(frame["action"])
        return {
            "type": "action_result",
            "device_id": self.device_id,
            "result": result,
        }
