"""Minimal in-memory gateway loop for the v0 runtime."""

import json
from contextlib import asynccontextmanager

import websockets

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
            elif frame["type"] == "action_result":
                self.state.record_action_result(frame["result"])
        return replies

    async def handle_test_frames(self, frames: list[dict]) -> list[dict]:
        return self._handle_frames_sync(frames)

    def run_roundtrip(self, frames: list[dict]) -> list[dict]:
        return self._handle_frames_sync(frames)

    async def _websocket_handler(self, websocket) -> None:
        async for raw_frame in websocket:
            frame = json.loads(raw_frame)
            replies = self._handle_frames_sync([frame])
            for reply in replies:
                await websocket.send(json.dumps(reply))

    @asynccontextmanager
    async def run_test_server(self):
        server = await websockets.serve(self._websocket_handler, "127.0.0.1", 0)
        try:
            host, port = server.sockets[0].getsockname()[:2]
            yield {"url": f"ws://{host}:{port}"}
        finally:
            server.close()
            await server.wait_closed()

    @asynccontextmanager
    async def run_server(self, host: str = "127.0.0.1", port: int = 8765):
        server = await websockets.serve(self._websocket_handler, host, port)
        try:
            yield {"url": f"ws://{host}:{port}"}
        finally:
            server.close()
            await server.wait_closed()
