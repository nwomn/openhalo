"""Minimal in-memory gateway loop for the v0 runtime."""

import json
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from itertools import count
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosedError
from websockets.exceptions import ConnectionClosedOK

from edge_api.protocol import validate_frame, with_api_version
from personal_runtime.action_layer import build_interaction_update
from personal_runtime.agent_executor import ProposalFormation
from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.execution_planning import ExecutionPlanner
from personal_runtime.presence_router import PresenceRouter
from personal_runtime.runtime_orchestrator import RuntimeOrchestrator
from personal_runtime.runtime_state import RuntimeState
from personal_runtime.runtime_state import _compatibility_capability_registration
from personal_runtime.state_store import JsonStateStore
from personal_runtime.trace_recorder import TraceRecorder


class RuntimeGateway:
    _interaction_counter = count(1)

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
        diagnostic_recorder=None,
        runtime_instance_id: str = "runtime-main",
    ) -> None:
        self.shared_token = shared_token
        self.state_store = JsonStateStore(
            state_path or Path(".runtime/state.json")
        )
        if state is not None:
            self.state = state
        elif not persist_state and state_path is None:
            self.state = RuntimeState()
        else:
            self.state = self.state_store.load()
        self.online_device_ids: set[str] = set()
        self.live_connections: dict[str, object] = {}
        self.trace_recorder = trace_recorder
        self.persist_state = persist_state
        self.runtime_event_emitter = runtime_event_emitter
        self.llm_config_path = llm_config_path
        self.grounding_edge_history_fetcher = grounding_edge_history_fetcher
        self.diagnostic_recorder = diagnostic_recorder
        self.runtime_instance_id = runtime_instance_id
        self.orchestrator = RuntimeOrchestrator(self)
        self._action_request_counter = count(1)
        self.proposal_formation = ProposalFormation(
            diagnostic_recorder=diagnostic_recorder,
            runtime_instance_id=runtime_instance_id,
            trace_recorder=trace_recorder,
            config_path=llm_config_path,
        )
        self.presence_router = PresenceRouter(
            diagnostic_recorder=diagnostic_recorder,
            runtime_instance_id=runtime_instance_id,
            trace_recorder=trace_recorder,
        )
        self.execution_planner = ExecutionPlanner(
            diagnostic_recorder=diagnostic_recorder,
            runtime_instance_id=runtime_instance_id,
        )
        self._websocket_frame_lock = asyncio.Lock()

    def _persist_state(self) -> None:
        if not self.persist_state:
            return
        self.state_store.save(self.state)

    def _next_interaction_id(self) -> str:
        return f"interaction-{next(self._interaction_counter)}"

    def _next_action_request_id(self) -> str:
        return f"action-{next(self._action_request_counter)}"

    def _build_interaction_record(
        self,
        interaction_id: str,
        frame: dict,
        proposal,
        decision,
    ) -> dict:
        participant_device_ids = [frame["device_id"]]
        if (
            decision.target_device_id is not None
            and decision.target_device_id not in participant_device_ids
        ):
            participant_device_ids.append(decision.target_device_id)
        return {
            "interaction_id": interaction_id,
            "status": "planned",
            "source_device_id": frame["device_id"],
            "participant_device_ids": participant_device_ids,
            "proposal_type": proposal.proposal_type,
            "interaction_type": proposal.interaction_type,
            "visibility_intent": proposal.visibility_intent,
            "candidate_surface_hints": proposal.candidate_surface_hints or [],
            "primary_action": {
                "capability": proposal.action_capability,
                "target_device_id": decision.target_device_id,
            }
            if proposal.action_capability is not None
            else None,
        }

    def _build_interaction_turn_update(
        self,
        interaction: dict,
        proposal,
        decision,
    ) -> dict:
        participant_device_ids = list(interaction.get("participant_device_ids", []))
        for device_id in (
            interaction.get("source_device_id"),
            decision.target_device_id,
        ):
            if device_id is not None and device_id not in participant_device_ids:
                participant_device_ids.append(device_id)
        return {
            **interaction,
            "status": "planned",
            "participant_device_ids": participant_device_ids,
            "proposal_type": proposal.proposal_type,
            "interaction_type": proposal.interaction_type,
            "visibility_intent": proposal.visibility_intent,
            "candidate_surface_hints": proposal.candidate_surface_hints or [],
            "primary_action": {
                "capability": proposal.action_capability,
                "target_device_id": decision.target_device_id,
            }
            if proposal.action_capability is not None
            else None,
        }

    def _build_interaction_summary(
        self,
        proposal: dict,
        result: dict | None = None,
    ) -> str:
        if result is not None:
            delivered_message = result.get("details", {}).get("message")
            if isinstance(delivered_message, str) and delivered_message.strip():
                return delivered_message.strip()
        proposal_type = proposal.get("proposal_type")
        if proposal_type in {"reply", "clarification"}:
            return proposal.get("action_payload", {}).get("message", "")
        if proposal_type == "no_intervention":
            rationale = proposal.get("metadata", {}).get("proposal_rationale", {})
            return rationale.get("summary", "")
        if result is not None and result.get("capability") == "runtime.status":
            details = result.get("details", {})
            state = details.get("state", "unknown")
            pid = details.get("pid")
            if pid is not None:
                return f"Runtime status: {state} (pid {pid})."
            return f"Runtime status: {state}."
        if result is not None and result.get("capability"):
            return (
                f"{result['capability']} completed with "
                f"status {result.get('status', 'unknown')}."
            )
        return ""

    def _complete_interaction(
        self,
        interaction_id: str,
        summary: str,
        visibility: str,
        result_status: str | None = None,
    ) -> dict:
        return self.state.update_interaction(
            interaction_id,
            status="completed",
            summary=summary,
            completion={
                "visibility": visibility,
                "summary": summary,
                "result_status": result_status,
            },
        )

    def _completion_visibility_for_action_result(
        self,
        interaction: dict,
        proposal: dict,
        result: dict,
    ) -> str:
        proposal_type = proposal.get("proposal_type")
        target_device_id = interaction.get("primary_action", {}).get("target_device_id")
        source_device_id = interaction.get("source_device_id")
        capability = proposal.get("action_capability")
        delivered_message = result.get("details", {}).get("message")

        if proposal_type == "no_intervention":
            return proposal.get("visibility_intent", "silent")

        if (
            proposal_type in {"reply", "clarification"}
            and capability == "notification.show"
            and delivered_message
            and target_device_id is not None
            and target_device_id == source_device_id
        ):
            return "silent"
        return interaction.get("visibility_intent", "visible")

    def _build_interaction_update_replies(
        self,
        interaction: dict,
        correlation: dict | None = None,
    ) -> list[dict]:
        visibility = interaction.get("completion", {}).get("visibility", "visible")
        summary = interaction.get("completion", {}).get("summary", "")
        replies = [
            build_interaction_update(
                interaction["source_device_id"],
                {
                    "interaction_id": interaction["interaction_id"],
                    "status": interaction["status"],
                    "summary": summary,
                    "visibility": visibility,
                    "completion": interaction.get("completion", {}),
                },
                trace_recorder=self.trace_recorder,
                correlation=correlation,
            )
        ]
        return replies

    def _build_event_replies(self, frame: dict) -> list[dict]:
        correlation = {
            "trace_id": frame.get("trace_id"),
            "session_id": frame.get("session_id"),
            "turn_id": frame.get("turn_id"),
            "event_id": frame.get("event_id"),
            "request_id": None,
            "interaction_id": frame.get("interaction_id"),
        }
        self._record_diagnostic(
            module="Gateway",
            operation="receive_frame",
            phase="input",
            correlation=correlation,
            input_payload={
                "type": frame["type"],
                "device_id": frame.get("device_id"),
                "capability": frame.get("capability"),
            },
            output_payload={"ack": "event_ack"},
            summary=f"Received {frame.get('capability', '')} event frame.",
        )
        return [
            with_api_version({"type": "event_ack"}),
            *self.orchestrator.handle_event_frame(frame),
        ]

    def _build_event_replies_impl(self, frame: dict) -> list[dict]:
        return self.orchestrator.handle_event_frame(frame)

    def _turn_index_for_interaction(self, interaction_id: str) -> int:
        return (
            len(
                [
                    intervention
                    for intervention in self.state.interventions
                    if intervention.get("interaction_id") == interaction_id
                ]
            )
            + 1
        )

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
        correlation: dict | None = None,
    ):
        return self.proposal_formation.build_normal_path_proposal(
            frame,
            snapshot=snapshot,
            grounding_bundle=grounding_bundle,
            correlation=correlation,
        )

    def _build_edge_history_for_grounding(self) -> dict | None:
        if self.grounding_edge_history_fetcher is None:
            return None
        return self.grounding_edge_history_fetcher()

    def _latest_open_interaction_for_observations(
        self,
        frame: dict,
    ) -> dict | None:
        source_device_id = frame["device_id"]
        for interaction in reversed(self.state.interactions):
            if interaction.get("status") == "completed":
                continue
            participant_device_ids = interaction.get("participant_device_ids", [])
            if source_device_id in participant_device_ids:
                return interaction
        return None

    def _observations_relevant_to_open_interaction(
        self,
        interaction: dict,
        observations: list[dict],
    ) -> bool:
        del interaction
        for observation in observations:
            name = observation.get("name")
            value = str(observation.get("value", "")).lower()
            # M16 keeps this as a deliberately narrow hard-coded re-entry gate.
            # Later salience work should move this toward a configurable,
            # learned, or model-assisted gate instead of sending every
            # observation batch back through proposal formation.
            if name == "runtime.health_state" and value in {
                "degraded",
                "unhealthy",
                "down",
                "failed",
            }:
                return True
            if name == "runtime.process_present" and value == "false":
                return True
        return False

    def _observation_timestamp(self, frame: dict) -> str:
        observations = frame.get("payload", {}).get("observations", [])
        observed_at_values = [
            observation.get("observed_at")
            for observation in observations
            if observation.get("observed_at")
        ]
        if observed_at_values:
            return max(
                observed_at_values,
                key=lambda timestamp: datetime.fromisoformat(
                    timestamp.replace("Z", "+00:00")
                ),
            )
        return self._event_timestamp(frame)

    def _build_observation_reentry_replies(self, frame: dict) -> list[dict]:
        return self.orchestrator.handle_observation_reentry_frame(frame)

    def _build_action_result_replies(self, frame: dict) -> list[dict]:
        return self.orchestrator.handle_action_result_frame(frame)

    def _build_action_result_replies_impl(self, frame: dict) -> list[dict]:
        return self.orchestrator.handle_action_result_frame(frame)

    def _handle_frames_sync(self, frames: list[dict]) -> list[dict]:
        replies = []
        for raw_frame in frames:
            frame = self._normalize_public_frame(validate_frame(raw_frame))
            if frame["type"] == "connect":
                self._record_trace(
                    "GATEWAY",
                    "received connect",
                    device_id=frame["device"]["device_id"],
                )
                if frame["auth"]["token"] != self.shared_token:
                    replies.append(
                        with_api_version(
                            {"type": "error", "message": "unauthorized"}
                        )
                    )
                    continue
                self.state.register_device(
                    frame["device"]["device_id"],
                    frame["device"]["device_type"],
                    role=frame["device"].get("role"),
                    profile=frame["device"].get("profile"),
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
                replies.append(with_api_version({"type": "connect_ok"}))
            elif frame["type"] == "capability_announce":
                self._record_trace(
                    "GATEWAY",
                    "received capability_announce",
                    device_id=frame["device_id"],
                )
                for capability in frame["capabilities"]:
                    self.state.register_capability(frame["device_id"], capability)
                self._persist_state()
            elif frame["type"] == "event_push":
                self._record_trace(
                    "GATEWAY",
                    "received event_push",
                    device_id=frame["device_id"],
                    capability=frame["capability"],
                )
                validation_error = self._validate_observation_ingress(frame)
                if validation_error is not None:
                    replies.append(validation_error)
                    continue
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
                replies.extend(self._build_action_result_replies(frame))
            elif frame["type"] == "interaction_update":
                self.state.record_interaction(frame["interaction"])
                self._persist_state()
        return replies

    @staticmethod
    def _capability_name(capability: str | dict) -> str:
        if isinstance(capability, dict):
            return capability["name"]
        return capability

    @staticmethod
    def _normalize_public_frame(frame: dict) -> dict:
        if frame["type"] != "observation_push":
            return frame
        return {
            **frame,
            "type": "event_push",
            "payload": {"observations": frame.get("observations", [])},
        }

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

    def _validate_observation_ingress(self, frame: dict) -> dict | None:
        observations = frame.get("payload", {}).get("observations", [])
        if not observations:
            return None
        device_id = frame["device_id"]
        capability = frame["capability"]
        registered = (
            self.state.observation_registry.get(device_id, {})
            .get(capability, {})
        )
        if not registered and _compatibility_capability_registration(capability):
            self.state.devices.setdefault(
                device_id,
                {"device_type": "unknown", "capabilities": set()},
            )
            self.state.register_capability(device_id, capability)
            registered = (
                self.state.observation_registry.get(device_id, {})
                .get(capability, {})
            )
        for observation in observations:
            observation_name = observation.get("name")
            registration = registered.get(observation_name)
            if registration is None:
                return self._build_observation_error(
                    code="unregistered_observation",
                    message="Observation is not registered for this device capability.",
                    device_id=device_id,
                    capability=capability,
                    observation=observation_name,
                )
            schema = registration.get("schema")
            if schema is not None and not self._value_matches_schema(
                observation.get("value"),
                schema,
            ):
                return self._build_observation_error(
                    code="schema_mismatch",
                    message="Observation value does not match registered schema.",
                    device_id=device_id,
                    capability=capability,
                    observation=observation_name,
                )
        return None

    @staticmethod
    def _build_observation_error(
        code: str,
        message: str,
        device_id: str,
        capability: str,
        observation: str | None,
    ) -> dict:
        return with_api_version(
            {
                "type": "error",
                "code": code,
                "message": message,
                "device_id": device_id,
                "capability": capability,
                "observation": observation,
            }
        )

    @classmethod
    def _value_matches_schema(cls, value, schema: dict) -> bool:
        if value is None and schema.get("nullable") is True:
            return True
        schema_type = schema.get("type")
        if schema_type == "string" and not isinstance(value, str):
            return False
        if schema_type == "number" and not isinstance(value, (int, float)):
            return False
        if schema_type == "integer" and not isinstance(value, int):
            return False
        if schema_type == "boolean" and not isinstance(value, bool):
            return False
        if schema_type == "object":
            if not isinstance(value, dict):
                return False
            for required_key in schema.get("required", []):
                if required_key not in value:
                    return False
            properties = schema.get("properties", {})
            for key, property_schema in properties.items():
                if key in value and not cls._value_matches_schema(
                    value[key],
                    property_schema,
                ):
                    return False
        if "enum" in schema and value not in schema["enum"]:
            return False
        return True

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

    def _action_result_timestamp(self, frame: dict) -> str:
        result = frame.get("result", {})
        if result.get("observed_at"):
            return result["observed_at"]
        if frame.get("observed_at"):
            return frame["observed_at"]
        return self._event_timestamp(frame)

    async def handle_test_frames(self, frames: list[dict]) -> list[dict]:
        return self._handle_frames_sync(frames)

    def run_roundtrip(self, frames: list[dict]) -> list[dict]:
        return self._handle_frames_sync(frames)

    async def _handle_websocket_frame(self, frame: dict) -> list[dict]:
        async with self._websocket_frame_lock:
            return await asyncio.to_thread(self._handle_frames_sync, [frame])

    async def _send_frame(self, websocket, frame: dict) -> None:
        await websocket.send(json.dumps(frame))

    def _record_trace(self, component: str, message: str, **fields: str) -> None:
        if self.trace_recorder is not None:
            self.trace_recorder.record(component, message, **fields)

    def _record_diagnostic(
        self,
        module: str,
        operation: str,
        phase: str,
        correlation: dict | None,
        input_payload: dict | None,
        output_payload: dict | None,
        summary: str,
    ) -> None:
        if self.diagnostic_recorder is None:
            return
        self.diagnostic_recorder.record_boundary(
            side="runtime",
            runtime_instance_id=self.runtime_instance_id,
            module=module,
            operation=operation,
            phase=phase,
            correlation=correlation or {},
            input_payload=input_payload,
            output_payload=output_payload,
            summary=summary,
        )

    def _emit_runtime_event(self, message: str) -> None:
        if self.runtime_event_emitter is not None:
            self.runtime_event_emitter(message)

    async def _dispatch_websocket_replies(self, source_device_id: str, websocket, replies: list[dict]) -> None:
        for reply in replies:
            target_device_id = reply.get("device_id")
            if (
                reply["type"] in {"action_request", "interaction_update"}
                and target_device_id != source_device_id
            ):
                target_websocket = self.live_connections.get(target_device_id)
                if target_websocket is not None:
                    try:
                        await self._send_frame(target_websocket, reply)
                        self._record_dispatch_diagnostic(
                            reply=reply,
                            source_device_id=source_device_id,
                            target_connection_found=True,
                            dispatched_to=target_device_id,
                            send_status="sent",
                        )
                    except (ConnectionClosedOK, ConnectionClosedError) as exc:
                        self._record_dispatch_diagnostic(
                            reply=reply,
                            source_device_id=source_device_id,
                            target_connection_found=True,
                            dispatched_to=target_device_id,
                            send_status="connection_closed",
                            error_class=type(exc).__name__,
                        )
                        pass
                    continue
                self._record_dispatch_diagnostic(
                    reply=reply,
                    source_device_id=source_device_id,
                    target_connection_found=False,
                    dispatched_to=source_device_id,
                    send_status="target_missing",
                )
            try:
                await self._send_frame(websocket, reply)
                if not (
                    reply["type"] in {"action_request", "interaction_update"}
                    and target_device_id != source_device_id
                ):
                    self._record_dispatch_diagnostic(
                        reply=reply,
                        source_device_id=source_device_id,
                        target_connection_found=target_device_id in self.live_connections,
                        dispatched_to=source_device_id,
                        send_status="sent",
                    )
            except (ConnectionClosedOK, ConnectionClosedError) as exc:
                self._record_dispatch_diagnostic(
                    reply=reply,
                    source_device_id=source_device_id,
                    target_connection_found=target_device_id in self.live_connections,
                    dispatched_to=source_device_id,
                    send_status="connection_closed",
                    error_class=type(exc).__name__,
                )
                pass

    def _record_dispatch_diagnostic(
        self,
        reply: dict,
        source_device_id: str,
        target_connection_found: bool,
        dispatched_to: str | None,
        send_status: str,
        error_class: str | None = None,
    ) -> None:
        self._record_diagnostic(
            module="Gateway",
            operation="dispatch_reply",
            phase="output",
            correlation={
                key: reply.get(key)
                for key in (
                    "trace_id",
                    "session_id",
                    "turn_id",
                    "event_id",
                    "request_id",
                    "interaction_id",
                    "parent_event_id",
                )
                if reply.get(key) is not None
            },
            input_payload={
                "reply_type": reply.get("type"),
                "source_device_id": source_device_id,
                "target_device_id": reply.get("device_id"),
            },
            output_payload={
                "target_connection_found": target_connection_found,
                "dispatched_to": dispatched_to,
                "send_status": send_status,
                "error_class": error_class,
                "error_code": reply.get("code") if reply.get("type") == "error" else None,
                "error_message": reply.get("message")
                if reply.get("type") == "error"
                else None,
                "error_capability": reply.get("capability")
                if reply.get("type") == "error"
                else None,
                "error_observation": reply.get("observation")
                if reply.get("type") == "error"
                else None,
            },
            summary="Dispatched runtime reply over websocket.",
        )

    async def _websocket_handler(self, websocket) -> None:
        registered_device_id = None
        try:
            async for raw_frame in websocket:
                frame = json.loads(raw_frame)
                if frame["type"] == "connect" and frame["auth"]["token"] == self.shared_token:
                    registered_device_id = frame["device"]["device_id"]
                    self.online_device_ids.add(registered_device_id)
                    self.live_connections[registered_device_id] = websocket
                replies = await self._handle_websocket_frame(frame)
                await self._dispatch_websocket_replies(
                    frame.get("device_id", registered_device_id),
                    websocket,
                    replies,
                )
        except (ConnectionClosedOK, ConnectionClosedError) as exc:
            self._record_diagnostic(
                module="Gateway",
                operation="websocket_session",
                phase="output",
                correlation={},
                input_payload={"device_id": registered_device_id},
                output_payload={
                    "status": "connection_closed",
                    "error_class": type(exc).__name__,
                },
                summary="Edge websocket session closed.",
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
