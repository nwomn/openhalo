"""Minimal session client shared by multiple edge surfaces."""

import json
from itertools import count

import websockets

from device_edge.shared.capability_runtime import CapabilityRuntime
from device_edge.shared.local_actions import execute_action
from personal_runtime.protocol import build_connect_frame
from personal_runtime.trace_recorder import TraceRecorder


class SessionClient:
    _event_counter = count(1)

    def __init__(
        self,
        device_id: str,
        device_type: str,
        token: str,
        trace_recorder: TraceRecorder | None = None,
        capabilities: list[str] | None = None,
    ) -> None:
        self.device_id = device_id
        self.device_type = device_type
        self.token = token
        self.capability_runtime = CapabilityRuntime(capabilities=capabilities)
        self.trace_recorder = trace_recorder

    def build_connect_frame(self) -> dict:
        self._record_trace("EDGE", "build connect frame", device_id=self.device_id)
        return build_connect_frame(self.device_id, self.device_type, self.token)

    def build_capability_announce_frame(self) -> dict:
        self._record_trace(
            "EDGE",
            "build capability_announce frame",
            capabilities=",".join(self.capability_runtime.capabilities),
        )
        return {
            "type": "capability_announce",
            "device_id": self.device_id,
            "capabilities": self.capability_runtime.capabilities,
        }

    def build_text_event(self, text: str) -> dict:
        self._record_trace("EDGE", "build text.input event", text=text)
        return {
            "type": "event_push",
            "device_id": self.device_id,
            "capability": "text.input",
            "payload": {"text": text},
        }

    def build_direct_action_event(
        self,
        capability: str,
        payload: dict,
        target_device_id: str | None = None,
    ) -> dict:
        self._record_trace(
            "EDGE",
            "build direct action event",
            capability=capability,
        )
        direct_action = {
            "capability": capability,
            "payload": payload,
        }
        if target_device_id is not None:
            direct_action["target_device_id"] = target_device_id
        return {
            "type": "event_push",
            "device_id": self.device_id,
            "capability": "text.input",
            "payload": {
                "text": "",
                "direct_action": direct_action,
            },
        }

    def build_agent_initiative_event(
        self,
        action_capability: str,
        action_payload: dict,
        reason: str,
        observed_at: str,
        target_device_hint: str | None = None,
        message: str | None = None,
    ) -> dict:
        self._record_trace(
            "EDGE",
            "build agent.initiative event",
            capability=action_capability,
        )
        initiative = {
            "action_capability": action_capability,
            "action_payload": action_payload,
            "reason": reason,
        }
        if target_device_hint is not None:
            initiative["target_device_hint"] = target_device_hint
        if message is not None:
            initiative["message"] = message
        return {
            "type": "event_push",
            "device_id": self.device_id,
            "capability": "agent.initiative",
            "payload": {
                "observed_at": observed_at,
                "agent_initiative": initiative,
            },
        }

    def build_observation_event(self, capability: str, observations: list[dict]) -> dict:
        event_id = f"{self.device_id}-evt-{next(self._event_counter)}"
        self._record_trace(
            "EDGE",
            "build observation event",
            capability=capability,
            event_id=event_id,
        )
        return {
            "type": "event_push",
            "device_id": self.device_id,
            "capability": capability,
            "event_id": event_id,
            "payload": {"observations": observations},
        }

    def build_terminal_activity_event(
        self,
        activity_state: str,
        observed_at: str,
    ) -> dict:
        return self.build_observation_event(
            capability="terminal.context",
            observations=[
                {
                    "name": "terminal.activity_state",
                    "value": activity_state,
                    "observed_at": observed_at,
                    "confidence": 1.0,
                }
            ],
        )

    def handle_action_request(self, frame: dict) -> dict:
        result = execute_action(frame["action"])
        self._record_trace(
            "EDGE",
            "executed notification.show",
            status=result["status"],
        )
        action_result = {
            "type": "action_result",
            "device_id": self.device_id,
            "result": result,
        }
        if frame.get("interaction_id"):
            action_result["interaction_id"] = frame["interaction_id"]
        return action_result

    async def run_websocket_roundtrip(self, server_factory, text: str) -> dict:
        async with server_factory() as server_info:
            return await self.run_websocket_client(url=server_info["url"], text=text)

    async def run_websocket_client(self, url: str, text: str) -> dict:
        async with websockets.connect(url) as websocket:
            await websocket.send(json.dumps(self.build_connect_frame()))
            await websocket.send(json.dumps(self.build_capability_announce_frame()))
            await websocket.send(json.dumps(self.build_text_event(text)))

            await websocket.recv()
            await websocket.recv()
            action_request = json.loads(await websocket.recv())
            action_result = self.handle_action_request(action_request)
            await websocket.send(json.dumps(action_result))
            return action_result

    def _record_trace(self, component: str, message: str, **fields: str) -> None:
        if self.trace_recorder is not None:
            self.trace_recorder.record(component, message, **fields)
