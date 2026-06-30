"""Minimal session client shared by multiple edge surfaces."""

import json
from itertools import count

import websockets

from device_edge.shared.capability_runtime import CapabilityRuntime
from device_edge.shared.local_actions import execute_action
from edge_api.protocol import build_capability_announce_frame
from edge_api.protocol import build_connect_frame
from edge_api.protocol import build_event_push_frame
from edge_api.protocol import build_observation_push_frame
from edge_api.protocol import with_api_version
from openhalo_common.diagnostics import build_session_id
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
        self.diagnostic_recorder = diagnostic_recorder
        self.edge_device = {
            "device_id": self.device_id,
            "device_name": self.device_id,
            "device_type": self.device_type,
        }
        self.capability_runtime = CapabilityRuntime(
            capabilities=capabilities,
            diagnostic_recorder=diagnostic_recorder,
            device=self.edge_device,
        )
        self.session_id = build_session_id(device_id)

    def build_connect_frame(self) -> dict:
        self._record_trace("EDGE", "build connect frame", device_id=self.device_id)
        return build_connect_frame(
            self.device_id,
            self.device_type,
            self.token,
            session_id=self.session_id,
        )

    def build_capability_announce_frame(self) -> dict:
        self._record_trace(
            "EDGE",
            "build capability_announce frame",
            capabilities=",".join(self.capability_runtime.capabilities),
        )
        return build_capability_announce_frame(
            self.device_id,
            self.capability_runtime.capabilities,
            session_id=self.session_id,
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
        frame = build_event_push_frame(
            device_id=self.device_id,
            capability=normalized["capability"],
            payload=normalized["payload"],
            **correlation,
        )
        self._record_diagnostic(
            module="Edge Session Link",
            operation="send_frame",
            phase="output",
            correlation=correlation,
            input_payload={},
            output_payload=frame,
            summary="Prepared event_push frame for runtime.",
        )
        return frame

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
        return build_event_push_frame(
            device_id=self.device_id,
            capability="text.input",
            payload={
                "text": "",
                "direct_action": direct_action,
            },
            **correlation,
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
        return build_event_push_frame(
            device_id=self.device_id,
            capability="agent.initiative",
            payload={
                "observed_at": observed_at,
                "agent_initiative": initiative,
            },
            **correlation,
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
        frame = build_observation_push_frame(
            device_id=self.device_id,
            capability=normalized["capability"],
            observations=normalized["observations"],
            **correlation,
        )
        self._record_diagnostic(
            module="Edge Session Link",
            operation="send_frame",
            phase="output",
            correlation=correlation,
            input_payload={},
            output_payload=frame,
            summary="Prepared observation_push frame for runtime.",
        )
        return frame

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
        action_result = with_api_version(
            {
                "type": "action_result",
                "device_id": self.device_id,
                "result": result,
            }
        )
        if frame.get("request_id"):
            action_result["request_id"] = frame["request_id"]
        if frame.get("interaction_id"):
            action_result["interaction_id"] = frame["interaction_id"]
        for key in ("trace_id", "session_id", "turn_id", "event_id", "parent_event_id"):
            if frame.get(key) is not None:
                action_result[key] = frame[key]
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

    def _record_diagnostic(
        self,
        module: str,
        operation: str,
        phase: str,
        correlation: dict,
        input_payload: dict | None,
        output_payload: dict | None,
        summary: str,
    ) -> None:
        if self.diagnostic_recorder is None:
            return
        self.diagnostic_recorder.record_boundary(
            side="edge",
            device=self.edge_device,
            module=module,
            operation=operation,
            phase=phase,
            correlation=correlation,
            input_payload=input_payload,
            output_payload=output_payload,
            summary=summary,
        )
