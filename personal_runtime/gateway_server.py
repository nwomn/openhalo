"""Minimal in-memory gateway loop for the v0 runtime."""

from personal_runtime.action_layer import build_notification_action
from personal_runtime.agent_executor import generate_reply
from personal_runtime.presence_router import choose_response_device
from personal_runtime.runtime_state import RuntimeState


class RuntimeGateway:
    def __init__(self, shared_token: str) -> None:
        self.shared_token = shared_token
        self.state = RuntimeState()

    def _handle_frames_sync(self, frames: list[dict]) -> list[dict]:
        replies = []
        for frame in frames:
            if frame["type"] == "connect":
                if frame["auth"]["token"] != self.shared_token:
                    replies.append({"type": "error", "message": "unauthorized"})
                    continue
                self.state.register_device(
                    frame["device"]["device_id"],
                    frame["device"]["device_type"],
                )
                replies.append({"type": "connect_ok"})
            elif frame["type"] == "capability_announce":
                for name in frame["capabilities"]:
                    self.state.register_capability(frame["device_id"], name)
            elif frame["type"] == "event_push":
                text = frame["payload"]["text"]
                target = choose_response_device(frame["device_id"])
                replies.append({"type": "event_ack"})
                replies.append(build_notification_action(target, generate_reply(text)))
        return replies

    async def handle_test_frames(self, frames: list[dict]) -> list[dict]:
        return self._handle_frames_sync(frames)

    def run_roundtrip(self, frames: list[dict]) -> list[dict]:
        return self._handle_frames_sync(frames)
