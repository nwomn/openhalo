"""Minimal session client shared by multiple edge surfaces."""

import json
from itertools import count

import websockets

from device_edge.shared.capability_runtime import CapabilityRuntime
from device_edge.shared.edge_session_link import EdgeSessionLink
from device_edge.shared.local_action_executor import LocalActionExecutor
from openhalo_common.diagnostics import build_trace_id
from openhalo_common.diagnostics import build_turn_id


class SessionClient:
    _event_counter = count(1)

    def __init__(
        self,
        device_id: str,
        device_type: str,
        token: str,
        trace_recorder=None,
        diagnostic_recorder=None,
        capabilities: list[str] | None = None,
    ) -> None:
        self.device_id = device_id
        self.device_type = device_type
        self.token = token
        self.trace_recorder = trace_recorder
        self.edge_device = {
            "device_id": self.device_id,
            "device_name": self.device_id,
            "device_type": self.device_type,
        }
        self.session_link = EdgeSessionLink(
            device_id=device_id,
            device_type=device_type,
            token=token,
            diagnostic_recorder=diagnostic_recorder,
        )
        self.capability_runtime = CapabilityRuntime(
            capabilities=capabilities,
            diagnostic_recorder=diagnostic_recorder,
            device=self.edge_device,
        )
        self.action_executor = LocalActionExecutor(
            device_id=device_id,
            device_type=device_type,
            diagnostic_recorder=diagnostic_recorder,
            trace_recorder=trace_recorder,
        )
        self.session_id = self.session_link.session_id

    def build_connect_frame(self) -> dict:
        self._record_trace("EDGE", "build connect frame", device_id=self.device_id)
        return self.session_link.build_connect_frame()

    def build_capability_announce_frame(self) -> dict:
        self._record_trace(
            "EDGE",
            "build capability_announce frame",
            capabilities=",".join(self.capability_runtime.capabilities),
        )
        return self.session_link.build_capability_announce_frame(
            self.capability_runtime.capabilities
        )

    def _next_correlation(self) -> dict:
        sequence = next(self._event_counter)
        return {
            "trace_id": build_trace_id(self.device_id, sequence),
            "session_id": self.session_id,
            "turn_id": build_turn_id(self.device_id, sequence),
            "event_id": f"{self.device_id}-evt-{sequence}",
        }

    def build_text_event(self, text: str) -> dict:
        self._record_trace("EDGE", "build text.input event", text=text)
        correlation = self._next_correlation()
        normalized = self.capability_runtime.normalize_user_input(
            text,
            correlation=correlation,
        )
        return self.session_link.build_event_frame(
            capability=normalized["capability"],
            payload=normalized["payload"],
            correlation=correlation,
        )

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
        correlation = self._next_correlation()
        return self.session_link.build_event_frame(
            capability="text.input",
            payload={
                "text": "",
                "direct_action": direct_action,
            },
            correlation=correlation,
        )

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
        correlation = self._next_correlation()
        return self.session_link.build_event_frame(
            capability="agent.initiative",
            payload={
                "observed_at": observed_at,
                "agent_initiative": initiative,
            },
            correlation=correlation,
        )

    def build_observation_event(self, capability: str, observations: list[dict]) -> dict:
        correlation = self._next_correlation()
        self._record_trace(
            "EDGE",
            "build observation event",
            capability=capability,
            event_id=correlation["event_id"],
        )
        normalized = self.capability_runtime.normalize_observations(
            capability,
            observations,
            correlation=correlation,
        )
        return self.session_link.build_observation_frame(
            capability=normalized["capability"],
            observations=normalized["observations"],
            correlation=correlation,
        )

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
        return self.action_executor.handle_action_request(frame)

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
