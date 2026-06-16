"""Minimal in-memory gateway loop for the v0 runtime."""

import json
from contextlib import asynccontextmanager
from pathlib import Path

import websockets

from personal_runtime.action_layer import build_action_request
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
        self.online_device_ids: set[str] = set()
        self.live_connections: dict[str, object] = {}

    def _persist_state(self) -> None:
        self.state_store.save(self.state)

    def _build_event_replies(self, frame: dict) -> list[dict]:
        replies = [{"type": "event_ack"}]
        direct_action = frame["payload"].get("direct_action")
        if direct_action is not None:
            replies.append(
                build_action_request(
                    direct_action.get("target_device_id", frame["device_id"]),
                    {
                        "capability": direct_action["capability"],
                        "payload": direct_action["payload"],
                    },
                )
            )
            return replies

        text = frame["payload"]["text"]
        available_devices = {
            device_id: self.state.devices[device_id]
            for device_id in self.online_device_ids
            if device_id in self.state.devices
        }
        target = choose_response_device(
            frame["device_id"],
            devices=available_devices or self.state.devices,
            required_capability="notification.show",
        )
        replies.append(build_notification_action(target, generate_reply(text)))
        return replies

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
                self.online_device_ids.add(frame["device"]["device_id"])
                self._persist_state()
                replies.append({"type": "connect_ok"})
            elif frame["type"] == "capability_announce":
                for name in frame["capabilities"]:
                    self.state.register_capability(frame["device_id"], name)
                self._persist_state()
            elif frame["type"] == "event_push":
                self.state.events.append(frame)
                self._persist_state()
                replies.extend(self._build_event_replies(frame))
            elif frame["type"] == "action_result":
                self.state.record_action_result(frame["result"])
                self._persist_state()
        return replies

    async def handle_test_frames(self, frames: list[dict]) -> list[dict]:
        return self._handle_frames_sync(frames)

    def run_roundtrip(self, frames: list[dict]) -> list[dict]:
        return self._handle_frames_sync(frames)

    async def _send_frame(self, websocket, frame: dict) -> None:
        await websocket.send(json.dumps(frame))

    async def _dispatch_websocket_replies(self, source_device_id: str, websocket, replies: list[dict]) -> None:
        for reply in replies:
            target_device_id = reply.get("device_id")
            if reply["type"] == "action_request" and target_device_id != source_device_id:
                target_websocket = self.live_connections.get(target_device_id)
                if target_websocket is not None:
                    await self._send_frame(target_websocket, reply)
                    continue
            await self._send_frame(websocket, reply)

    async def _websocket_handler(self, websocket) -> None:
        registered_device_id = None
        try:
            async for raw_frame in websocket:
                frame = json.loads(raw_frame)
                if frame["type"] == "connect" and frame["auth"]["token"] == self.shared_token:
                    registered_device_id = frame["device"]["device_id"]
                    self.online_device_ids.add(registered_device_id)
                    self.live_connections[registered_device_id] = websocket
                replies = self._handle_frames_sync([frame])
                await self._dispatch_websocket_replies(
                    frame.get("device_id", registered_device_id),
                    websocket,
                    replies,
                )
        finally:
            if registered_device_id is not None:
                current = self.live_connections.get(registered_device_id)
                if current is websocket:
                    del self.live_connections[registered_device_id]
                self.online_device_ids.discard(registered_device_id)

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
