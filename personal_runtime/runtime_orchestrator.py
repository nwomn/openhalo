"""Runtime orchestration boundary between Gateway and runtime modules."""

from __future__ import annotations

from openhalo_common.diagnostics import correlation_from_frame
from personal_runtime.action_layer import build_action_request
from personal_runtime.context_snapshot import build_context_snapshot
from personal_runtime.context_snapshot import build_context_snapshot_contract
from personal_runtime.runtime_memory import build_model_grounding_bundle


class RuntimeOrchestrator:
    def __init__(self, gateway) -> None:
        self.gateway = gateway

    def handle_event_frame(self, frame: dict) -> list[dict]:
        replies = []
        payload = frame["payload"]
        direct_action = payload.get("direct_action")
        correlation = correlation_from_frame(frame)
        if direct_action is not None:
            replies.extend(self.handle_direct_action(frame, direct_action, correlation))
            return replies

        if payload.get("observations"):
            self.gateway._record_diagnostic(
                module="State / Context",
                operation="ingest_observations",
                phase="input",
                correlation=correlation,
                input_payload={"observation_count": len(payload.get("observations", []))},
                output_payload={},
                summary="Received observation event for state/context ingest.",
            )
            replies.extend(self.handle_observation_reentry_frame(frame))
            return replies

        replies.extend(self.handle_normal_turn(frame, correlation))
        return replies

    def handle_direct_action(
        self,
        frame: dict,
        direct_action: dict,
        correlation: dict,
    ) -> list[dict]:
        execution_outcome = self.gateway.execution_planner.plan_direct_action(
            source_device_id=frame["device_id"],
            direct_action=direct_action,
            correlation=correlation,
        )
        return [
            build_action_request(
                execution_outcome["target_device_id"],
                execution_outcome["action"],
                trace_recorder=self.gateway.trace_recorder,
                correlation=correlation,
            )
        ]

    def handle_normal_turn(self, frame: dict, correlation: dict) -> list[dict]:
        decision_time = self.gateway._event_timestamp(frame)
        snapshot = build_context_snapshot(
            self.gateway.state.observations,
            snapshot_time=decision_time or None,
        )
        self.gateway._record_diagnostic(
            module="State / Context",
            operation="build_compact_snapshot",
            phase="output",
            correlation=correlation,
            input_payload={"stored_observation_count": len(self.gateway.state.observations)},
            output_payload=snapshot,
            summary="Built compact context snapshot.",
        )
        edge_history = self.gateway._build_edge_history_for_grounding()
        grounding_bundle = build_model_grounding_bundle(
            state=self.gateway.state,
            snapshot=snapshot,
            edge_history=edge_history,
        )
        self.gateway._record_diagnostic(
            module="Grounding / Runtime Memory",
            operation="build_grounding_bundle",
            phase="output",
            correlation=correlation,
            input_payload={"snapshot": snapshot},
            output_payload=grounding_bundle,
            summary="Built grounding bundle for proposal formation.",
        )
        snapshot_contract = build_context_snapshot_contract(
            self.gateway.state.observations,
            snapshot_time=decision_time or None,
        )
        proposal = self.gateway.proposal_formation.build_normal_path_proposal(
            frame,
            snapshot=snapshot,
            grounding_bundle=grounding_bundle,
            correlation=correlation,
        )
        self.gateway.state.record_model_health(
            proposal.metadata,
            observed_at=decision_time,
        )
        decision = self.gateway.presence_router.choose(
            source_device_id=frame["device_id"],
            snapshot=snapshot,
            devices=self.gateway.state.devices,
            online_device_ids=set(self.gateway.online_device_ids),
            required_capability=proposal.required_capability,
            proposal=proposal.to_dict(),
            intervention_history=self.gateway.state.interventions,
            now_timestamp=decision_time,
            correlation=correlation,
        )
        interaction_id = self.gateway._next_interaction_id()
        correlation["interaction_id"] = interaction_id
        self.gateway.state.record_interaction(
            self.gateway._build_interaction_record(
                interaction_id=interaction_id,
                frame=frame,
                proposal=proposal,
                decision=decision,
            )
        )
        self.gateway.state.record_intervention(
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
        self.gateway._record_diagnostic(
            module="State / Context",
            operation="record_intervention",
            phase="output",
            correlation=correlation,
            input_payload={"interaction_id": interaction_id},
            output_payload={"decision": decision.decision},
            summary="Recorded interaction and intervention.",
        )
        self.gateway._persist_state()
        execution_outcome = self.gateway.execution_planner.plan_action(
            source_device_id=frame["device_id"],
            proposal=proposal.to_dict(),
            decision=decision.to_dict(),
            interaction_id=interaction_id,
            correlation=correlation,
            runtime_state=self.gateway.state,
            online_device_ids=set(self.gateway.online_device_ids),
        )
        if self.gateway.state.interventions and execution_outcome.get("planning_record"):
            self.gateway.state.interventions[-1]["planning_record"] = execution_outcome[
                "planning_record"
            ]
            self.gateway._persist_state()
        if execution_outcome["kind"] == "completion":
            completed = self.gateway._complete_interaction(
                interaction_id=interaction_id,
                summary=execution_outcome["summary"],
                visibility=execution_outcome["visibility"],
            )
            return self.gateway._build_interaction_update_replies(
                completed,
                correlation=correlation,
            )

        planned_action = build_action_request(
            execution_outcome["target_device_id"],
            execution_outcome["action"],
            trace_recorder=self.gateway.trace_recorder,
            correlation=correlation,
        )
        planned_action["interaction_id"] = interaction_id
        self.gateway._record_diagnostic(
            module="Action Layer",
            operation="build_action_request",
            phase="output",
            correlation={**correlation, "request_id": planned_action.get("request_id")},
            input_payload={"planned_action": proposal.to_dict()},
            output_payload=planned_action,
            summary="Built action_request frame.",
        )
        return [planned_action]

    def handle_observation_reentry_frame(self, frame: dict) -> list[dict]:
        observations = frame.get("payload", {}).get("observations", [])
        if not observations:
            return []
        interaction = self.gateway._latest_open_interaction_for_observations(frame)
        if interaction is None:
            return []
        if not self.gateway._observations_relevant_to_open_interaction(
            interaction,
            observations,
        ):
            return []
        interaction_id = interaction["interaction_id"]
        intervention = next(
            (
                item
                for item in reversed(self.gateway.state.interventions)
                if item.get("interaction_id") == interaction_id
            ),
            None,
        )
        if intervention is None:
            return []

        decision_time = self.gateway._observation_timestamp(frame)
        snapshot = build_context_snapshot(
            self.gateway.state.observations,
            snapshot_time=decision_time or None,
        )
        edge_history = self.gateway._build_edge_history_for_grounding()
        grounding_bundle = build_model_grounding_bundle(
            state=self.gateway.state,
            snapshot=snapshot,
            edge_history=edge_history,
        )
        snapshot_contract = build_context_snapshot_contract(
            self.gateway.state.observations,
            snapshot_time=decision_time or None,
        )
        correlation = correlation_from_frame(frame)
        correlation["interaction_id"] = interaction_id
        proposal = self.gateway.proposal_formation.build_post_observation_proposal(
            interaction=interaction,
            prior_proposal=intervention["proposal"],
            observations=observations,
            turn_index=self.gateway._turn_index_for_interaction(interaction_id),
            snapshot=snapshot,
            grounding_bundle=grounding_bundle,
            correlation=correlation,
        )
        self.gateway.state.record_model_health(
            proposal.metadata,
            observed_at=decision_time,
        )
        decision = self.gateway.presence_router.choose(
            source_device_id=interaction["source_device_id"],
            snapshot=snapshot,
            devices=self.gateway.state.devices,
            online_device_ids=set(self.gateway.online_device_ids),
            required_capability=proposal.required_capability,
            proposal=proposal.to_dict(),
            intervention_history=self.gateway.state.interventions,
            now_timestamp=decision_time,
            correlation=correlation,
        )
        self.gateway.state.update_interaction(
            interaction_id,
            **{
                key: value
                for key, value in self.gateway._build_interaction_turn_update(
                    interaction=interaction,
                    proposal=proposal,
                    decision=decision,
                ).items()
                if key != "interaction_id"
            },
        )
        self.gateway.state.record_intervention(
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
        self.gateway._persist_state()

        execution_outcome = self.gateway.execution_planner.plan_action(
            source_device_id=interaction["source_device_id"],
            proposal=proposal.to_dict(),
            decision=decision.to_dict(),
            interaction_id=interaction_id,
            correlation=correlation,
            runtime_state=self.gateway.state,
            online_device_ids=set(self.gateway.online_device_ids),
        )
        if self.gateway.state.interventions and execution_outcome.get("planning_record"):
            self.gateway.state.interventions[-1]["planning_record"] = execution_outcome[
                "planning_record"
            ]
            self.gateway._persist_state()
        if execution_outcome["kind"] == "action":
            planned_action = build_action_request(
                execution_outcome["target_device_id"],
                execution_outcome["action"],
                trace_recorder=self.gateway.trace_recorder,
                correlation=correlation,
            )
            planned_action["interaction_id"] = interaction_id
            return [planned_action]

        completed = self.gateway._complete_interaction(
            interaction_id=interaction_id,
            summary=self.gateway._build_interaction_summary(proposal.to_dict()),
            visibility=proposal.visibility_intent,
        )
        self.gateway._persist_state()
        return self.gateway._build_interaction_update_replies(completed)

    def handle_action_result_frame(self, frame: dict) -> list[dict]:
        interaction_id = frame.get("interaction_id")
        if not interaction_id:
            return []
        interaction = next(
            (
                item
                for item in reversed(self.gateway.state.interactions)
                if item.get("interaction_id") == interaction_id
            ),
            None,
        )
        intervention = next(
            (
                item
                for item in reversed(self.gateway.state.interventions)
                if item.get("interaction_id") == interaction_id
            ),
            None,
        )
        if interaction is None or intervention is None:
            return []
        result = frame["result"]
        decision_time = self.gateway._action_result_timestamp(frame)
        snapshot = build_context_snapshot(
            self.gateway.state.observations,
            snapshot_time=decision_time or None,
        )
        edge_history = self.gateway._build_edge_history_for_grounding()
        grounding_bundle = build_model_grounding_bundle(
            state=self.gateway.state,
            snapshot=snapshot,
            edge_history=edge_history,
        )
        snapshot_contract = build_context_snapshot_contract(
            self.gateway.state.observations,
            snapshot_time=decision_time or None,
        )
        correlation = correlation_from_frame(frame)
        correlation["interaction_id"] = interaction_id
        proposal = self.gateway.proposal_formation.build_post_action_proposal(
            interaction=interaction,
            prior_proposal=intervention["proposal"],
            result=result,
            turn_index=self.gateway._turn_index_for_interaction(interaction_id),
            snapshot=snapshot,
            grounding_bundle=grounding_bundle,
            correlation=correlation,
        )
        self.gateway.state.record_model_health(
            proposal.metadata,
            observed_at=decision_time,
        )
        decision = self.gateway.presence_router.choose(
            source_device_id=interaction["source_device_id"],
            snapshot=snapshot,
            devices=self.gateway.state.devices,
            online_device_ids=set(self.gateway.online_device_ids),
            required_capability=proposal.required_capability,
            proposal=proposal.to_dict(),
            intervention_history=self.gateway.state.interventions,
            now_timestamp=decision_time,
            correlation=correlation,
        )
        self.gateway.state.update_interaction(
            interaction_id,
            **{
                key: value
                for key, value in self.gateway._build_interaction_turn_update(
                    interaction=interaction,
                    proposal=proposal,
                    decision=decision,
                ).items()
                if key != "interaction_id"
            },
        )
        self.gateway.state.record_intervention(
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
        self.gateway._persist_state()

        execution_outcome = self.gateway.execution_planner.plan_action(
            source_device_id=interaction["source_device_id"],
            proposal=proposal.to_dict(),
            decision=decision.to_dict(),
            interaction_id=interaction_id,
            correlation=correlation,
            runtime_state=self.gateway.state,
            online_device_ids=set(self.gateway.online_device_ids),
        )
        if self.gateway.state.interventions and execution_outcome.get("planning_record"):
            self.gateway.state.interventions[-1]["planning_record"] = execution_outcome[
                "planning_record"
            ]
            self.gateway._persist_state()
        if execution_outcome["kind"] == "action":
            planned_action = build_action_request(
                execution_outcome["target_device_id"],
                execution_outcome["action"],
                trace_recorder=self.gateway.trace_recorder,
                correlation=correlation,
            )
            planned_action["interaction_id"] = interaction_id
            return [planned_action]

        visibility = self.gateway._completion_visibility_for_action_result(
            interaction=interaction,
            proposal=proposal.to_dict(),
            result=result,
        )
        completed = self.gateway._complete_interaction(
            interaction_id=interaction_id,
            summary=self.gateway._build_interaction_summary(
                proposal.to_dict(),
                result=result,
            ),
            visibility=visibility,
            result_status=result.get("status"),
        )
        self.gateway._persist_state()
        return self.gateway._build_interaction_update_replies(completed)


__all__ = ["RuntimeOrchestrator"]
