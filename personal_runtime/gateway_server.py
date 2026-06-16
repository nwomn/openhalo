"""Minimal in-memory gateway loop for the v0 runtime."""

import json
from contextlib import asynccontextmanager
from pathlib import Path

import websockets

from personal_runtime.action_layer import build_notification_action
from personal_runtime.agent_executor import generate_reply
from personal_runtime.presence_router import choose_response_device
from personal_runtime.runtime_state import RuntimeState
from personal_runtime.state_store import JsonStateStore


class RuntimeGateway:
    def __init__(
        self,
        shared_token: str,
        state_path: Path | None = None,
        state: RuntimeState | None = None,
    ) -> None:
        self.shared_token = shared_token
        self.state_store = JsonStateStore(
            state_path or Path(".runtime/state.json")
        )
        self.state = state or self.state_store.load()

    def _persist_state(self) -> None:
        self.state_store.save(self.state)

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
                self._persist_state()
                replies.append({"type": "connect_ok"})
            elif frame["type"] == "capability_announce":
                for name in frame["capabilities"]:
                    self.state.register_capability(frame["device_id"], name)
                self._persist_state()
            elif frame["type"] == "event_push":
                text = frame["payload"]["text"]
                self.state.events.append(frame)
                self._persist_state()
                target = choose_response_device(frame["device_id"])
                replies.append({"type": "event_ack"})
                replies.append(build_notification_action(target, generate_reply(text)))
            elif frame["type"] == "action_result":
                self.state.record_action_result(frame["result"])
                self._persist_state()
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
