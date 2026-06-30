"""Minimal in-memory gateway loop for the v0 runtime."""

import json
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from itertools import count
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosedOK

from edge_api.protocol import validate_frame
from edge_api.protocol import with_api_version
from openhalo_common.diagnostics import correlation_from_frame
from personal_runtime.action_layer import build_action_request
from personal_runtime.action_layer import build_interaction_update
from personal_runtime.action_layer import build_planned_action
from personal_runtime.agent_executor import build_intervention_proposal
from personal_runtime.agent_executor import build_agent_initiative_proposal
from personal_runtime.agent_executor import build_post_action_proposal
from personal_runtime.agent_executor import build_post_observation_proposal
from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.context_snapshot import build_context_snapshot
from personal_runtime.context_snapshot import build_context_snapshot_contract
from personal_runtime.execution_planning import build_execution_outcome
from personal_runtime.presence_router import choose_presence_decision
from personal_runtime.runtime_memory import build_model_grounding_bundle
from personal_runtime.runtime_orchestrator import RuntimeOrchestrator
from personal_runtime.runtime_state import RuntimeState
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
        self._websocket_frame_lock = asyncio.Lock()

    def _persist_state(self) -> None:
        if not self.persist_state:
            return
        self.state_store.save(self.state)

    def _next_interaction_id(self) -> str:
        return f"interaction-{next(self._interaction_counter)}"

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
        return self.orchestrator.handle_event_frame(frame)

    def _build_event_replies_impl(self, frame: dict) -> list[dict]:
        replies = [with_api_version({"type": "event_ack"})]
        payload = frame["payload"]
        direct_action = payload.get("direct_action")
        correlation = correlation_from_frame(frame)
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
        if direct_action is not None:
            self._record_diagnostic(
                module="Execution Planning",
                operation="plan_direct_action",
                phase="output",
                correlation=correlation,
                input_payload={"direct_action": direct_action},
                output_payload={"target_device_id": direct_action.get("target_device_id", frame["device_id"])},
                summary="Planned direct action fast path.",
            )
            replies.append(
                build_action_request(
                    direct_action.get("target_device_id", frame["device_id"]),
                    {
                        "capability": direct_action["capability"],
                        "payload": direct_action["payload"],
                    },
                    trace_recorder=self.trace_recorder,
                    correlation=correlation,
                )
            )
            return replies

        if payload.get("observations"):
            self._record_diagnostic(
                module="State / Context",
                operation="ingest_observations",
                phase="input",
                correlation=correlation,
                input_payload={"observation_count": len(payload.get("observations", []))},
                output_payload={},
                summary="Received observation event for state/context ingest.",
            )
            replies.extend(self._build_observation_reentry_replies(frame))
            return replies

        decision_time = self._event_timestamp(frame)
        snapshot = build_context_snapshot(
            self.state.observations,
            snapshot_time=decision_time or None,
        )
        self._record_diagnostic(
            module="State / Context",
            operation="build_compact_snapshot",
            phase="output",
            correlation=correlation,
            input_payload={"stored_observation_count": len(self.state.observations)},
            output_payload=snapshot,
            summary="Built compact context snapshot.",
        )
        edge_history = self._build_edge_history_for_grounding()
        grounding_bundle = build_model_grounding_bundle(
            state=self.state,
            snapshot=snapshot,
            edge_history=edge_history,
        )
        self._record_diagnostic(
            module="Grounding / Runtime Memory",
            operation="build_grounding_bundle",
            phase="output",
            correlation=correlation,
            input_payload={"snapshot": snapshot},
            output_payload=grounding_bundle,
            summary="Built grounding bundle for proposal formation.",
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
        self._record_diagnostic(
            module="Proposal Formation",
            operation="build_proposal",
            phase="output",
            correlation=correlation,
            input_payload={"text": payload.get("text", "")},
            output_payload=proposal.to_dict(),
            summary="Built intervention proposal.",
        )
        self.state.record_model_health(
            proposal.metadata,
            observed_at=decision_time,
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
        self._record_diagnostic(
            module="Presence Router",
            operation="choose_presence_decision",
            phase="output",
            correlation=correlation,
            input_payload={
                "source_device_id": frame["device_id"],
                "required_capability": proposal.required_capability,
                "proposal_type": proposal.proposal_type,
            },
            output_payload=decision.to_dict(),
            summary="Evaluated presence decision.",
        )
        interaction_id = self._next_interaction_id()
        correlation["interaction_id"] = interaction_id
        self.state.record_interaction(
            self._build_interaction_record(
                interaction_id=interaction_id,
                frame=frame,
                proposal=proposal,
                decision=decision,
            )
        )
        self.state.record_intervention(
            {
                "interaction_id": interaction_id,
                "source_device_id": frame["device_id"],
                "target_device_id": decision.target_device_id,
                "action_capability": proposal.action_capability,
                "decision": decision.decision,
                "reason": decision.reason,
                "proposal": proposal.to_dict(),
                "grounding_bundle": grounding_bundle,
                "snapshot_contract": snapshot_contract,
                "correlation": correlation,
                "recorded_at": decision_time,
            }
        )
        self._record_diagnostic(
            module="State / Context",
            operation="record_intervention",
            phase="output",
            correlation=correlation,
            input_payload={"interaction_id": interaction_id},
            output_payload={"decision": decision.decision},
            summary="Recorded interaction and intervention.",
        )
        self._persist_state()
        execution_outcome = build_execution_outcome(
            source_device_id=frame["device_id"],
            proposal=proposal.to_dict(),
            decision=decision.to_dict(),
            interaction_id=interaction_id,
            correlation=correlation,
        )
        self._record_diagnostic(
            module="Execution Planning",
            operation="plan_action"
            if execution_outcome["kind"] == "action"
            else "complete_interaction",
            phase="output",
            correlation=correlation,
            input_payload={"proposal": proposal.to_dict(), "decision": decision.to_dict()},
            output_payload=execution_outcome,
            summary="Planned runtime execution outcome.",
        )
        if execution_outcome["kind"] == "completion":
            completed = self._complete_interaction(
                interaction_id=interaction_id,
                summary=execution_outcome["summary"],
                visibility=execution_outcome["visibility"],
            )
            replies.extend(
                self._build_interaction_update_replies(
                    completed,
                    correlation=correlation,
                )
            )
            return replies

        planned_action = build_planned_action(
            execution_outcome["target_device_id"],
            proposal.to_dict(),
            trace_recorder=self.trace_recorder,
            correlation=correlation,
        )
        planned_action["interaction_id"] = interaction_id
        self._record_diagnostic(
            module="Action Layer",
            operation="build_action_request",
            phase="output",
            correlation={**correlation, "request_id": planned_action.get("request_id")},
            input_payload={"planned_action": proposal.to_dict()},
            output_payload=planned_action,
            summary="Built action_request frame.",
        )
        replies.append(planned_action)
        return replies

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
        observations = frame.get("payload", {}).get("observations", [])
        if not observations:
            return []
        interaction = self._latest_open_interaction_for_observations(frame)
        if interaction is None:
            return []
        if not self._observations_relevant_to_open_interaction(
            interaction,
            observations,
        ):
            return []
        interaction_id = interaction["interaction_id"]
        intervention = next(
            (
                item
                for item in reversed(self.state.interventions)
                if item.get("interaction_id") == interaction_id
            ),
            None,
        )
        if intervention is None:
            return []

        decision_time = self._observation_timestamp(frame)
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
        proposal = build_post_observation_proposal(
            interaction=interaction,
            prior_proposal=intervention["proposal"],
            observations=observations,
            turn_index=self._turn_index_for_interaction(interaction_id),
            snapshot=snapshot,
            grounding_bundle=grounding_bundle,
            trace_recorder=self.trace_recorder,
            config_path=self.llm_config_path,
        )
        self.state.record_model_health(
            proposal.metadata,
            observed_at=decision_time,
        )
        decision = choose_presence_decision(
            source_device_id=interaction["source_device_id"],
            snapshot=snapshot,
            devices=self.state.devices,
            online_device_ids=set(self.online_device_ids),
            required_capability=proposal.required_capability,
            proposal=proposal.to_dict(),
            intervention_history=self.state.interventions,
            now_timestamp=decision_time,
            trace_recorder=self.trace_recorder,
        )
        self.state.update_interaction(
            interaction_id,
            **{
                key: value
                for key, value in self._build_interaction_turn_update(
                    interaction=interaction,
                    proposal=proposal,
                    decision=decision,
                ).items()
                if key != "interaction_id"
            },
        )
        self.state.record_intervention(
            {
                "interaction_id": interaction_id,
                "source_device_id": interaction["source_device_id"],
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

        if decision.decision == "allow" and proposal.action_capability is not None:
            planned_action = build_planned_action(
                decision.target_device_id or interaction["source_device_id"],
                proposal.to_dict(),
                trace_recorder=self.trace_recorder,
            )
            planned_action["interaction_id"] = interaction_id
            return [planned_action]

        completed = self._complete_interaction(
            interaction_id=interaction_id,
            summary=self._build_interaction_summary(proposal.to_dict()),
            visibility=proposal.visibility_intent,
        )
        self._persist_state()
        return self._build_interaction_update_replies(completed)

    def _build_action_result_replies(self, frame: dict) -> list[dict]:
        return self.orchestrator.handle_action_result_frame(frame)

    def _build_action_result_replies_impl(self, frame: dict) -> list[dict]:
        interaction_id = frame.get("interaction_id")
        if not interaction_id:
            return []
        interaction = next(
            (
                item
                for item in reversed(self.state.interactions)
                if item.get("interaction_id") == interaction_id
            ),
            None,
        )
        intervention = next(
            (
                item
                for item in reversed(self.state.interventions)
                if item.get("interaction_id") == interaction_id
            ),
            None,
        )
        if interaction is None or intervention is None:
            return []
        result = frame["result"]
        decision_time = self._action_result_timestamp(frame)
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
        proposal = build_post_action_proposal(
            interaction=interaction,
            prior_proposal=intervention["proposal"],
            result=result,
            turn_index=self._turn_index_for_interaction(interaction_id),
            snapshot=snapshot,
            grounding_bundle=grounding_bundle,
            trace_recorder=self.trace_recorder,
            config_path=self.llm_config_path,
        )
        self.state.record_model_health(
            proposal.metadata,
            observed_at=decision_time,
        )
        decision = choose_presence_decision(
            source_device_id=interaction["source_device_id"],
            snapshot=snapshot,
            devices=self.state.devices,
            online_device_ids=set(self.online_device_ids),
            required_capability=proposal.required_capability,
            proposal=proposal.to_dict(),
            intervention_history=self.state.interventions,
            now_timestamp=decision_time,
            trace_recorder=self.trace_recorder,
        )
        self.state.update_interaction(
            interaction_id,
            **{
                key: value
                for key, value in self._build_interaction_turn_update(
                    interaction=interaction,
                    proposal=proposal,
                    decision=decision,
                ).items()
                if key != "interaction_id"
            },
        )
        self.state.record_intervention(
            {
                "interaction_id": interaction_id,
                "source_device_id": interaction["source_device_id"],
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

        if decision.decision == "allow" and proposal.action_capability is not None:
            planned_action = build_planned_action(
                decision.target_device_id or interaction["source_device_id"],
                proposal.to_dict(),
                trace_recorder=self.trace_recorder,
            )
            planned_action["interaction_id"] = interaction_id
            return [planned_action]

        visibility = self._completion_visibility_for_action_result(
            interaction=interaction,
            proposal=proposal.to_dict(),
            result=result,
        )
        completed = self._complete_interaction(
            interaction_id=interaction_id,
            summary=self._build_interaction_summary(
                proposal.to_dict(),
                result=result,
            ),
            visibility=visibility,
            result_status=result.get("status"),
        )
        self._persist_state()
        return self._build_interaction_update_replies(completed)

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
                    name = self._capability_name(capability)
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
                    except ConnectionClosedOK:
                        pass
                    continue
            try:
                await self._send_frame(websocket, reply)
            except ConnectionClosedOK:
                pass

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
