"""Minimal in-memory gateway loop for the v0 runtime."""

import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import websockets

from personal_runtime.action_layer import build_action_request
from personal_runtime.action_layer import build_planned_action
from personal_runtime.agent_executor import build_intervention_proposal
from personal_runtime.agent_executor import build_agent_initiative_proposal
from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.context_snapshot import build_context_snapshot
from personal_runtime.context_snapshot import build_context_snapshot_contract
from personal_runtime.presence_router import choose_presence_decision
from personal_runtime.runtime_memory import build_model_grounding_bundle
from personal_runtime.runtime_state import RuntimeState
from personal_runtime.state_store import JsonStateStore
from personal_runtime.trace_recorder import TraceRecorder


class RuntimeGateway:
    def __init__(
        self,
        shared_token: str,
        state_path: Path | None = None,
        state: RuntimeState | None = None,
        trace_recorder: TraceRecorder | None = None,
        persist_state: bool = True,
        runtime_event_emitter=None,
        llm_config_path: Path | None = None,
        grounding_edge_history_fetcher=None,
    ) -> None:
        self.shared_token = shared_token
        self.state_store = JsonStateStore(
            state_path or Path(".runtime/state.json")
        )
        self.state = state or self.state_store.load()
        self.online_device_ids: set[str] = set()
        self.live_connections: dict[str, object] = {}
        self.trace_recorder = trace_recorder
        self.persist_state = persist_state
        self.runtime_event_emitter = runtime_event_emitter
        self.llm_config_path = llm_config_path
        self.grounding_edge_history_fetcher = grounding_edge_history_fetcher

    def _persist_state(self) -> None:
        if not self.persist_state:
            return
        self.state_store.save(self.state)

    def _build_event_replies(self, frame: dict) -> list[dict]:
        replies = [{"type": "event_ack"}]
        payload = frame["payload"]
        direct_action = payload.get("direct_action")
        if direct_action is not None:
            replies.append(
                build_action_request(
                    direct_action.get("target_device_id", frame["device_id"]),
                    {
                        "capability": direct_action["capability"],
                        "payload": direct_action["payload"],
                    },
                    trace_recorder=self.trace_recorder,
                )
            )
            return replies

        if payload.get("observations"):
            return replies

        decision_time = self._event_timestamp(frame)
        snapshot = build_context_snapshot(
            self.state.observations,
            snapshot_time=decision_time or None,
        )
        edge_history = self._build_edge_history_for_grounding()
        grounding_bundle = build_model_grounding_bundle(
            state=self.state,
            snapshot=snapshot,
            edge_history=edge_history,
        )
        snapshot_contract = build_context_snapshot_contract(
            self.state.observations,
            snapshot_time=decision_time or None,
        )
        proposal = self._build_normal_path_proposal(
            frame,
            snapshot=snapshot,
            grounding_bundle=grounding_bundle,
        )
        decision = choose_presence_decision(
            source_device_id=frame["device_id"],
            snapshot=snapshot,
            devices=self.state.devices,
            online_device_ids=set(self.online_device_ids),
            required_capability=proposal.required_capability,
            proposal=proposal.to_dict(),
            intervention_history=self.state.interventions,
            now_timestamp=decision_time,
            trace_recorder=self.trace_recorder,
        )
        self.state.record_intervention(
            {
                "target_device_id": decision.target_device_id,
                "action_capability": proposal.action_capability,
                "decision": decision.decision,
                "reason": decision.reason,
                "proposal": proposal.to_dict(),
                "grounding_bundle": grounding_bundle,
                "snapshot_contract": snapshot_contract,
                "recorded_at": decision_time,
            }
        )
        self._persist_state()
        if decision.decision != "allow":
            return replies

        replies.append(
            build_planned_action(
                decision.target_device_id or frame["device_id"],
                proposal.to_dict(),
                trace_recorder=self.trace_recorder,
            )
        )
        return replies

    def trigger_agent_initiative(
        self,
        source_device_id: str,
        initiative_request: dict,
        observed_at: str,
    ) -> list[dict]:
        self._record_trace(
            "GATEWAY",
            "triggered agent initiative",
            source_device_id=source_device_id,
            action_capability=initiative_request["action_capability"],
        )
        frame = {
            "type": "event_push",
            "device_id": source_device_id,
            "capability": "agent.initiative",
            "payload": {
                "observed_at": observed_at,
                "agent_initiative": initiative_request,
            },
        }
        return self._build_event_replies(frame)

    async def dispatch_agent_initiative(
        self,
        source_device_id: str,
        initiative_request: dict,
        observed_at: str,
    ) -> list[dict]:
        replies = self.trigger_agent_initiative(
            source_device_id=source_device_id,
            initiative_request=initiative_request,
            observed_at=observed_at,
        )
        for reply in replies:
            if reply["type"] != "action_request":
                continue
            target_device_id = reply["device_id"]
            target_websocket = self.live_connections.get(target_device_id)
            if target_websocket is not None:
                await self._send_frame(target_websocket, reply)
        return replies

    def _build_normal_path_proposal(
        self,
        frame: dict,
        snapshot: dict,
        grounding_bundle: dict | None = None,
    ):
        payload = frame["payload"]
        if payload.get("agent_initiative") is not None:
            return build_agent_initiative_proposal(
                payload["agent_initiative"],
                snapshot=snapshot,
                grounding_bundle=grounding_bundle,
                trace_recorder=self.trace_recorder,
            )
        return build_intervention_proposal(
            payload["text"],
            snapshot=snapshot,
            grounding_bundle=grounding_bundle,
            trace_recorder=self.trace_recorder,
            config_path=self.llm_config_path,
        )

    def _build_edge_history_for_grounding(self) -> dict | None:
        if self.grounding_edge_history_fetcher is None:
            return None
        return self.grounding_edge_history_fetcher()

    def _handle_frames_sync(self, frames: list[dict]) -> list[dict]:
        replies = []
        for frame in frames:
            if frame["type"] == "connect":
                self._record_trace(
                    "GATEWAY",
                    "received connect",
                    device_id=frame["device"]["device_id"],
                )
                if frame["auth"]["token"] != self.shared_token:
                    replies.append({"type": "error", "message": "unauthorized"})
                    continue
                self.state.register_device(
                    frame["device"]["device_id"],
                    frame["device"]["device_type"],
                )
                self._record_trace(
                    "STATE",
                    "registered device",
                    device_id=frame["device"]["device_id"],
                )
                self.online_device_ids.add(frame["device"]["device_id"])
                self._persist_state()
                self._emit_runtime_event(
                    "Edge connected: "
                    f"{frame['device']['device_id']} "
                    f"({frame['device']['device_type']})"
                )
                replies.append({"type": "connect_ok"})
            elif frame["type"] == "capability_announce":
                self._record_trace(
                    "GATEWAY",
                    "received capability_announce",
                    device_id=frame["device_id"],
                )
                for name in frame["capabilities"]:
                    self.state.register_capability(frame["device_id"], name)
                self._persist_state()
            elif frame["type"] == "event_push":
                self._record_trace(
                    "GATEWAY",
                    "received event_push",
                    device_id=frame["device_id"],
                    capability=frame["capability"],
                )
                self.state.events.append(frame)
                self.state.record_observations(self._extract_runtime_observations(frame))
                self._record_trace(
                    "STATE",
                    "recorded event_push",
                    capability=frame["capability"],
                )
                self._persist_state()
                replies.extend(self._build_event_replies(frame))
            elif frame["type"] == "action_result":
                self._record_trace(
                    "GATEWAY",
                    "received action_result",
                    device_id=frame["device_id"],
                )
                self.state.record_action_result(frame["result"])
                self._record_trace(
                    "STATE",
                    "recorded action_result",
                    status=frame["result"]["status"],
                )
                self._persist_state()
        return replies

    def _extract_runtime_observations(self, frame: dict) -> list[RuntimeObservation]:
        observations = frame["payload"].get("observations", [])
        event_id = frame.get("event_id", "")
        return [
            RuntimeObservation(
                name=observation_payload["name"],
                value=observation_payload["value"],
                source_device_id=frame["device_id"],
                source_capability=frame["capability"],
                source_event_id=event_id,
                observed_at=observation_payload["observed_at"],
                confidence=observation_payload["confidence"],
            )
            for observation_payload in observations
        ]

    def _event_timestamp(self, frame: dict) -> str:
        payload = frame.get("payload", {})
        if payload.get("observed_at"):
            return payload["observed_at"]
        if frame.get("observed_at"):
            return frame["observed_at"]
        if self.state.observations:
            known_timestamps = [
                observation.observed_at
                for observation in self.state.observations
                if observation.observed_at
            ]
            if known_timestamps:
                return max(
                    known_timestamps,
                    key=lambda timestamp: datetime.fromisoformat(
                        timestamp.replace("Z", "+00:00")
                    ),
                )
        return ""

    async def handle_test_frames(self, frames: list[dict]) -> list[dict]:
        return self._handle_frames_sync(frames)

    def run_roundtrip(self, frames: list[dict]) -> list[dict]:
        return self._handle_frames_sync(frames)

    async def _send_frame(self, websocket, frame: dict) -> None:
        await websocket.send(json.dumps(frame))

    def _record_trace(self, component: str, message: str, **fields: str) -> None:
        if self.trace_recorder is not None:
            self.trace_recorder.record(component, message, **fields)

    def _emit_runtime_event(self, message: str) -> None:
        if self.runtime_event_emitter is not None:
            self.runtime_event_emitter(message)

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
