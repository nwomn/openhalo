"""Runtime orchestration boundary between Gateway and runtime modules."""

from __future__ import annotations

from edge_api.protocol import with_api_version
from openhalo_common.diagnostics import correlation_from_frame
from personal_runtime.action_layer import build_action_request
from personal_runtime.context_snapshot import build_context_snapshot
from personal_runtime.context_snapshot import build_context_snapshot_contract
from personal_runtime.context_snapshot import sanitize_observation_driven_snapshot
from personal_runtime.context_snapshot import sanitize_observation_driven_snapshot_contract
from personal_runtime.runtime_memory import build_model_grounding_bundle
from personal_runtime.runtime_memory import sanitize_observation_driven_grounding_bundle


class RuntimeOrchestrator:
    def __init__(self, gateway) -> None:
        self.gateway = gateway

    def _record_planning_record(
        self,
        interaction_id: str,
        interaction_turn_id: str,
        execution_outcome: dict,
    ) -> None:
        planning_record = execution_outcome.get("planning_record")
        if planning_record is None:
            return
        self.gateway._update_intervention_for_turn(
            interaction_id,
            interaction_turn_id,
            planning_record=planning_record,
        )
        self.gateway._persist_state()

    def _build_action_request_for_turn(
        self,
        *,
        execution_outcome: dict,
        interaction_id: str,
        interaction_turn_id: str,
        correlation: dict,
    ) -> dict:
        request_id = self.gateway._next_action_request_id()
        self.gateway.interaction_pool.record_turn(
            interaction_id,
            interaction_turn_id=interaction_turn_id,
            request_id=request_id,
        )
        self.gateway._update_intervention_for_turn(
            interaction_id,
            interaction_turn_id,
            request_id=request_id,
            requested_action_capability=execution_outcome["action"]["capability"],
        )
        self.gateway._persist_state()
        action_correlation = {
            **correlation,
            "interaction_id": interaction_id,
            "interaction_turn_id": interaction_turn_id,
            "request_id": request_id,
        }
        planned_action = build_action_request(
            execution_outcome["target_device_id"],
            execution_outcome["action"],
            request_id=request_id,
            trace_recorder=self.gateway.trace_recorder,
            correlation=action_correlation,
        )
        planned_action["interaction_id"] = interaction_id
        planned_action["interaction_turn_id"] = interaction_turn_id
        return planned_action

    def _record_resolved_turn(
        self,
        interaction_id: str,
        interaction_turn_id: str,
    ) -> None:
        self.gateway.interaction_pool.record_turn(
            interaction_id,
            interaction_turn_id=interaction_turn_id,
        )

    def _complete_interaction_if_idle(
        self,
        *,
        interaction_id: str,
        summary: str,
        visibility: str,
        result_status: str | None = None,
        correlation: dict | None = None,
    ) -> list[dict]:
        if self.gateway.interaction_pool.has_pending_action(interaction_id):
            self.gateway._persist_state()
            return []
        completed = self.gateway._complete_interaction(
            interaction_id=interaction_id,
            summary=summary,
            visibility=visibility,
            result_status=result_status,
        )
        self.gateway._persist_state()
        return self.gateway._build_interaction_update_replies(
            completed,
            correlation=correlation,
        )

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
            if self._has_explicit_observation_parent(frame):
                replies.extend(self.handle_observation_reentry_frame(frame))
            else:
                replies.extend(
                    self.handle_observation_driven_frame(frame, correlation)
                )
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
                request_id=self.gateway._next_action_request_id(),
                trace_recorder=self.gateway.trace_recorder,
                correlation=correlation,
            )
        ]

    def handle_normal_turn(self, frame: dict, correlation: dict) -> list[dict]:
        registration = self.gateway._register_interaction_for_frame(frame)
        if not registration.created:
            return []
        interaction_id = registration.interaction.interaction_id
        interaction_turn_id = self.gateway._next_interaction_turn_id()
        correlation = {
            **correlation,
            "interaction_id": interaction_id,
            "interaction_turn_id": interaction_turn_id,
        }
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
        interaction_record = self.gateway._build_interaction_record(
            interaction_id=interaction_id,
            frame=frame,
            proposal=proposal,
            decision=decision,
        )
        self.gateway.state.update_interaction(
            interaction_id,
            **{
                key: value
                for key, value in interaction_record.items()
                if key != "interaction_id"
            },
        )
        self.gateway.state.record_intervention(
            {
                "interaction_id": interaction_id,
                "interaction_turn_id": interaction_turn_id,
                "request_id": None,
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
        self._record_planning_record(
            interaction_id,
            interaction_turn_id,
            execution_outcome,
        )
        if execution_outcome["kind"] == "completion":
            self._record_resolved_turn(interaction_id, interaction_turn_id)
            return self._complete_interaction_if_idle(
                interaction_id=interaction_id,
                summary=execution_outcome["summary"],
                visibility=execution_outcome["visibility"],
                correlation=correlation,
            )

        planned_action = self._build_action_request_for_turn(
            execution_outcome=execution_outcome,
            interaction_id=interaction_id,
            interaction_turn_id=interaction_turn_id,
            correlation=correlation,
        )
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

    @staticmethod
    def _has_explicit_observation_parent(frame: dict) -> bool:
        payload = frame.get("payload", {})
        return any(
            key in frame or key in payload
            for key in ("reentry_parent", "parent_event_id")
        )

    def handle_observation_driven_frame(
        self,
        frame: dict,
        correlation: dict,
    ) -> list[dict]:
        observations = self.gateway._extract_runtime_observations(frame)
        if not observations:
            return []
        decision_time = self.gateway._observation_timestamp(frame)
        snapshot_contract = sanitize_observation_driven_snapshot_contract(
            build_context_snapshot_contract(
                self.gateway.state.observations,
                snapshot_time=decision_time or None,
            )
        )
        admission = self.gateway.proactive_trigger_gate.evaluate(
            observations=observations,
            snapshot_contract=snapshot_contract,
            state=self.gateway.state,
            current_time=decision_time,
        )
        self.gateway.proactive_trigger_gate.record_decision(
            self.gateway.state,
            admission,
            recorded_at=decision_time,
            observations=observations,
        )
        self.gateway._record_diagnostic(
            module="State / Context",
            operation="evaluate_proactive_trigger_gate",
            phase="output",
            correlation=correlation,
            input_payload={"observation_count": len(observations)},
            output_payload=admission.to_dict(),
            summary="Evaluated observation-driven interaction admission.",
        )
        if admission.status != "trigger":
            self.gateway._persist_state()
            return []
        source_device_id = admission.primary_evidence_device_id
        if source_device_id is None:
            self.gateway._persist_state()
            return []
        registration = self.gateway.interaction_pool.register(
            origin="observation_driven",
            causal_scope=admission.causal_scope,
            trigger={
                "reason_code": admission.reason_code,
                "evidence_refs": admission.evidence_refs,
                "observed_at": decision_time,
            },
            participant_device_ids=[source_device_id],
            source_device_id=source_device_id,
        )
        if not registration.created:
            self.gateway._persist_state()
            return []

        interaction_id = registration.interaction.interaction_id
        interaction_turn_id = self.gateway._next_interaction_turn_id()
        correlation = {
            **correlation,
            "interaction_id": interaction_id,
            "interaction_turn_id": interaction_turn_id,
        }
        self.gateway._persist_state()
        snapshot = sanitize_observation_driven_snapshot(
            build_context_snapshot(
                self.gateway.state.observations,
                snapshot_time=decision_time or None,
            )
        )
        grounding_bundle = build_model_grounding_bundle(
            state=self.gateway.state,
            snapshot=snapshot,
            edge_history=None,
        )
        grounding_bundle = sanitize_observation_driven_grounding_bundle(
            grounding_bundle,
            snapshot=snapshot,
        )
        admitted_observations = self._admitted_observation_evidence(
            observations,
            admission.evidence_refs,
        )
        proposal = self.gateway.proposal_formation.build_observation_driven_proposal(
            interaction=registration.interaction.to_dict(),
            admission=admission.to_dict(),
            observations=admitted_observations,
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
            source_device_id=source_device_id,
            snapshot=snapshot,
            devices=self.gateway.state.devices,
            online_device_ids=set(self.gateway.online_device_ids),
            required_capability=proposal.required_capability,
            proposal=proposal.to_dict(),
            intervention_history=self.gateway.state.interventions,
            now_timestamp=decision_time,
            correlation=correlation,
        )
        interaction_record = self.gateway._build_interaction_record(
            interaction_id=interaction_id,
            frame={"device_id": source_device_id},
            proposal=proposal,
            decision=decision,
        )
        self.gateway.state.update_interaction(
            interaction_id,
            **{
                key: value
                for key, value in interaction_record.items()
                if key != "interaction_id"
            },
        )
        self.gateway.state.record_intervention(
            {
                "interaction_id": interaction_id,
                "interaction_turn_id": interaction_turn_id,
                "request_id": None,
                "source_device_id": source_device_id,
                "target_device_id": decision.target_device_id,
                "action_capability": proposal.action_capability,
                "decision": decision.decision,
                "reason": decision.reason,
                "proposal": proposal.to_dict(),
                "admission": admission.to_dict(),
                "grounding_bundle": grounding_bundle,
                "snapshot_contract": snapshot_contract,
                "correlation": correlation,
                "recorded_at": decision_time,
            }
        )
        self.gateway._persist_state()
        execution_outcome = self.gateway.execution_planner.plan_action(
            source_device_id=source_device_id,
            proposal=proposal.to_dict(),
            decision=decision.to_dict(),
            interaction_id=interaction_id,
            correlation=correlation,
            runtime_state=self.gateway.state,
            online_device_ids=set(self.gateway.online_device_ids),
        )
        self._record_planning_record(
            interaction_id,
            interaction_turn_id,
            execution_outcome,
        )
        if execution_outcome["kind"] == "completion":
            self._record_resolved_turn(interaction_id, interaction_turn_id)
            return self._complete_interaction_if_idle(
                interaction_id=interaction_id,
                summary=execution_outcome["summary"],
                visibility=execution_outcome["visibility"],
                correlation=correlation,
            )

        planned_action = self._build_action_request_for_turn(
            execution_outcome=execution_outcome,
            interaction_id=interaction_id,
            interaction_turn_id=interaction_turn_id,
            correlation=correlation,
        )
        self.gateway._record_diagnostic(
            module="Action Layer",
            operation="build_action_request",
            phase="output",
            correlation={**correlation, "request_id": planned_action.get("request_id")},
            input_payload={"planned_action": proposal.to_dict()},
            output_payload=planned_action,
            summary="Built observation-driven action_request frame.",
        )
        return [planned_action]

    @staticmethod
    def _admitted_observation_evidence(
        observations: list,
        evidence_refs: list[dict],
    ) -> list[dict]:
        evidence_keys = {
            (
                evidence_ref.get("source_device_id"),
                evidence_ref.get("source_event_id"),
                evidence_ref.get("observation_name"),
                evidence_ref.get("observed_at"),
            )
            for evidence_ref in evidence_refs
        }
        admitted = []
        for observation in observations:
            evidence_key = (
                observation.source_device_id,
                observation.source_event_id,
                observation.name,
                observation.observed_at,
            )
            if evidence_key not in evidence_keys or not isinstance(
                observation.value,
                (str, bool, int, float, type(None)),
            ):
                continue
            admitted.append(
                {
                    "name": observation.name,
                    "value": observation.value,
                    "source_device_id": observation.source_device_id,
                    "source_capability": observation.source_capability,
                    "source_event_id": observation.source_event_id,
                    "observed_at": observation.observed_at,
                    "confidence": observation.confidence,
                }
            )
        return admitted

    def handle_observation_reentry_frame(self, frame: dict) -> list[dict]:
        observations = frame.get("payload", {}).get("observations", [])
        if not observations:
            return []
        resolution = self.gateway._resolve_observation_reentry(frame)
        if resolution is None:
            return []
        interaction, intervention = resolution
        if self.gateway._observation_reentry_is_processed(interaction, frame):
            return []
        if not self.gateway._observations_relevant_to_open_interaction(
            interaction,
            observations,
        ):
            return []
        interaction_id = interaction["interaction_id"]
        interaction_turn_id = self.gateway._next_interaction_turn_id()
        self.gateway._record_observation_reentry(interaction_id, frame)

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
        correlation = {
            **correlation_from_frame(frame),
            "interaction_id": interaction_id,
            "interaction_turn_id": interaction_turn_id,
        }
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
                "interaction_turn_id": interaction_turn_id,
                "request_id": None,
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
        self._record_planning_record(
            interaction_id,
            interaction_turn_id,
            execution_outcome,
        )
        if execution_outcome["kind"] == "action":
            planned_action = self._build_action_request_for_turn(
                execution_outcome=execution_outcome,
                interaction_id=interaction_id,
                interaction_turn_id=interaction_turn_id,
                correlation=correlation,
            )
            return [planned_action]

        self._record_resolved_turn(interaction_id, interaction_turn_id)
        return self._complete_interaction_if_idle(
            interaction_id=interaction_id,
            summary=self.gateway._build_interaction_summary(proposal.to_dict()),
            visibility=proposal.visibility_intent,
            correlation=correlation,
        )

    def handle_action_result_frame(self, frame: dict) -> list[dict]:
        interaction_id = frame.get("interaction_id")
        if not interaction_id:
            return []
        result_turn_id = frame.get("interaction_turn_id")
        request_id = frame.get("request_id")
        if not result_turn_id or not request_id:
            missing_interaction = self.gateway.interaction_pool.get(interaction_id) is None
            return [
                with_api_version(
                    {
                        "type": "error",
                        "code": (
                            "lineage_missing"
                            if missing_interaction
                            else "action_result_correlation_missing"
                        ),
                        "message": (
                            "Action result cannot be applied because the active "
                            "interaction lineage is missing."
                            if missing_interaction
                            else "Action result cannot be applied because its "
                            "interaction turn correlation is missing."
                        ),
                        "device_id": frame.get("device_id"),
                        "request_id": request_id,
                        "interaction_id": interaction_id,
                    }
                )
            ]
        pool_interaction = self.gateway.interaction_pool.get_for_action_result(
            interaction_id,
            result_turn_id,
            request_id,
        )
        interaction = self.gateway._interaction_payload(interaction_id)
        if self.gateway.interaction_pool.get(interaction_id) is None:
            return [
                with_api_version(
                    {
                        "type": "error",
                        "code": "lineage_missing",
                        "message": (
                            "Action result cannot be applied because the active "
                            "interaction lineage is missing."
                        ),
                        "device_id": frame.get("device_id"),
                        "request_id": request_id,
                        "interaction_id": interaction_id,
                        "interaction_turn_id": result_turn_id,
                    }
                )
            ]
        intervention = self.gateway._intervention_for_turn(
            interaction_id,
            result_turn_id,
        )
        if (
            pool_interaction is None
            or interaction is None
            or intervention is None
        ):
            return [
                with_api_version(
                    {
                        "type": "error",
                        "code": "action_result_correlation_mismatch",
                        "message": (
                            "Action result does not match a pending interaction "
                            "turn."
                        ),
                        "device_id": frame.get("device_id"),
                        "request_id": request_id,
                        "interaction_id": interaction_id,
                        "interaction_turn_id": result_turn_id,
                    }
                )
            ]
        if intervention.get("target_device_id") != frame.get("device_id"):
            return [
                with_api_version(
                    {
                        "type": "error",
                        "code": "action_result_target_mismatch",
                        "message": (
                            "Action result did not arrive from the action target "
                            "device."
                        ),
                        "device_id": frame.get("device_id"),
                        "request_id": request_id,
                        "interaction_id": interaction_id,
                        "interaction_turn_id": result_turn_id,
                    }
                )
            ]
        if not self.gateway._action_result_capability_matches_intervention(
            frame,
            intervention,
        ):
            return [
                with_api_version(
                    {
                        "type": "error",
                        "code": "action_result_capability_mismatch",
                        "message": (
                            "Action result capability does not match the action "
                            "request."
                        ),
                        "device_id": frame.get("device_id"),
                        "request_id": request_id,
                        "interaction_id": interaction_id,
                        "interaction_turn_id": result_turn_id,
                    }
                )
            ]
        resolved_interaction = self.gateway.interaction_pool.resolve_action_result(
            interaction_id,
            result_turn_id,
            request_id,
        )
        if resolved_interaction is None:
            return [
                with_api_version(
                    {
                        "type": "error",
                        "code": "action_result_correlation_mismatch",
                        "message": (
                            "Action result does not match a pending interaction "
                            "turn."
                        ),
                        "device_id": frame.get("device_id"),
                        "request_id": request_id,
                        "interaction_id": interaction_id,
                        "interaction_turn_id": result_turn_id,
                    }
                )
            ]
        result = {
            **frame["result"],
            "device_id": frame.get("device_id"),
            "request_id": request_id,
            "interaction_id": interaction_id,
            "interaction_turn_id": result_turn_id,
        }
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
        interaction_turn_id = self.gateway._next_interaction_turn_id()
        correlation = {
            **correlation_from_frame(frame),
            "interaction_id": interaction_id,
            "interaction_turn_id": interaction_turn_id,
            "request_id": None,
        }
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
                "interaction_turn_id": interaction_turn_id,
                "parent_interaction_turn_id": result_turn_id,
                "parent_request_id": request_id,
                "request_id": None,
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
        self._record_planning_record(
            interaction_id,
            interaction_turn_id,
            execution_outcome,
        )
        if execution_outcome["kind"] == "action":
            planned_action = self._build_action_request_for_turn(
                execution_outcome=execution_outcome,
                interaction_id=interaction_id,
                interaction_turn_id=interaction_turn_id,
                correlation=correlation,
            )
            return [planned_action]

        self._record_resolved_turn(interaction_id, interaction_turn_id)
        visibility = self.gateway._completion_visibility_for_action_result(
            interaction=interaction,
            proposal=proposal.to_dict(),
            result=result,
        )
        return self._complete_interaction_if_idle(
            interaction_id=interaction_id,
            summary=self.gateway._build_interaction_summary(
                proposal.to_dict(),
                result=result,
            ),
            visibility=visibility,
            result_status=result.get("status"),
            correlation=correlation,
        )


__all__ = ["RuntimeOrchestrator"]
