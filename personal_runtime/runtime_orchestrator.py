"""Runtime orchestration boundary between Gateway and runtime modules."""

from __future__ import annotations

from dataclasses import replace

from edge_api.protocol import with_api_version
from openhalo_common.diagnostics import correlation_from_frame
from personal_runtime.action_layer import build_action_request
from personal_runtime.action_layer import required_device_capability_for_action
from personal_runtime.agent_harness import ActionExecutorKind
from personal_runtime.agent_harness import ActionGovernance
from personal_runtime.agent_harness import ActionSideEffect
from personal_runtime.agent_harness import ActionVisibility
from personal_runtime.agent_harness import HarnessInput
from personal_runtime.agent_harness import HarnessOperation
from personal_runtime.agent_executor import InterventionProposal
from personal_runtime.context_snapshot import build_context_snapshot
from personal_runtime.context_snapshot import build_context_snapshot_contract
from personal_runtime.context_snapshot import sanitize_observation_driven_snapshot
from personal_runtime.context_snapshot import sanitize_observation_driven_snapshot_contract
from personal_runtime.harness_memory import build_harness_memory_context
from personal_runtime.harness_memory import build_memory_consolidation_candidate
from personal_runtime.harness_evaluation import build_harness_trace
from personal_runtime.harness_provenance import build_trusted_user_intent_ref
from personal_runtime.harness_provenance import internal_tool_audit_issue
from personal_runtime.harness_provenance import sanitize_hermes_memory_events
from personal_runtime.harness_provenance import sanitize_internal_tool_events
from personal_runtime.harness_provenance import trusted_user_intent_ref_matches
from personal_runtime.interaction_pool import build_action_result_outcome_contract
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

    @staticmethod
    def _outcome_fallback_proposal(
        proposal: InterventionProposal,
        outcome_contract: dict,
    ) -> InterventionProposal:
        body = (
            "已发送到目标设备。"
            if outcome_contract.get("result_status") == "ok"
            else "目标设备未能完成操作。"
        )
        return InterventionProposal(
            kind="action",
            proposal_type="action",
            source="runtime_outcome_fallback",
            action_capability="notification.show",
            required_capability=required_device_capability_for_action(
                "notification.show"
            ),
            action_payload={"title": "OpenHalo", "body": body},
            message=body,
            metadata={
                **proposal.metadata,
                "runtime_generated_action": "outcome_delivery_fallback",
                "outcome_delivery": {
                    **outcome_contract,
                    "required": True,
                    "fallback_reason": proposal.proposal_type,
                },
            },
            target_device_hint=outcome_contract["requesting_device_id"],
            interaction_type="pull",
            visibility_intent="visible",
            candidate_surface_hints=["requesting_device"],
        )

    def _proposal_from_harness(self, harness_input: HarnessInput):
        if self._uses_legacy_harness_memory():
            memory_context = build_harness_memory_context(
                state=self.gateway.state,
                interaction_id=harness_input.interaction_id,
                interaction_turn_id=harness_input.interaction_turn_id,
                working_memory={
                    "operation": harness_input.operation.value,
                    "interaction_id": harness_input.interaction_id,
                    "interaction_turn_id": harness_input.interaction_turn_id,
                },
            )
            harness_input = replace(
                harness_input,
                working_memory=memory_context["working"],
                procedural_memory=memory_context["procedural"],
                semantic_memory=memory_context["semantic"],
                episodic_memory=memory_context["episodic"],
            )
        outcome = self.gateway.agent_harness.run(harness_input)
        internal_tool_events = sanitize_internal_tool_events(
            outcome.metadata.get("internal_tool_events")
        )
        hermes_memory_events = sanitize_hermes_memory_events(
            outcome.metadata.get("hermes_memory_events")
        )
        self.gateway.state.record_internal_tool_events(
            internal_tool_events,
            interaction_id=harness_input.interaction_id,
            interaction_turn_id=harness_input.interaction_turn_id,
        )
        self.gateway.state.record_hermes_memory_events(
            hermes_memory_events,
            interaction_id=harness_input.interaction_id,
            interaction_turn_id=harness_input.interaction_turn_id,
        )
        if self._uses_legacy_harness_memory():
            self.gateway.state.record_memory_consolidation_candidate(
                build_memory_consolidation_candidate(
                    harness_input=harness_input,
                    outcome=outcome,
                    terminal_reason=self._terminal_reason_for_harness_outcome(outcome),
                )
            )
        if outcome.proposal is None:
            raise ValueError(
                "harness returned no proposal for "
                f"{harness_input.operation.value} deliberation"
            )
        proposal = outcome.proposal
        validation = self._validate_harness_outcome(outcome, harness_input)
        self.gateway.state.record_harness_trace(
            build_harness_trace(
                harness_input=harness_input,
                outcome=outcome,
                validation=validation,
                terminal_reason=self._terminal_reason_for_harness_outcome(
                    outcome,
                    validation=validation,
                ),
            )
        )
        if validation["reason"] is not None:
            proposal = InterventionProposal(
                kind=(
                    "action_batch_rejected"
                    if validation["reason"] == "action_batch_rejected"
                    else "no_intervention"
                ),
                proposal_type=(
                    "action_batch_rejected"
                    if validation["reason"] == "action_batch_rejected"
                    else "no_intervention"
                ),
                source=proposal.source,
                action_capability=None,
                required_capability=None,
                action_payload={},
                message="",
                metadata={
                    **proposal.metadata,
                    "harness_validation": {
                        "decision": "rejected",
                        "reason": validation["reason"],
                        "action_intent": validation["action_intent"],
                        "authorization": validation["authorization"],
                        "phase": "pre_presence",
                    },
                },
                interaction_type=proposal.interaction_type,
                visibility_intent="silent",
                candidate_surface_hints=proposal.candidate_surface_hints,
            )
        elif validation["action_intent"] is not None:
            proposal.metadata = {
                **proposal.metadata,
                "harness_validation": {
                    "decision": "allowed",
                    "reason": None,
                    "action_intent": validation["action_intent"],
                    "authorization": validation["authorization"],
                    "phase": "pre_presence",
                    **(
                        {"action_batch": validation["action_batch"]}
                        if validation.get("action_batch") is not None
                        else {}
                    ),
                },
            }
        proposal_metadata = dict(proposal.metadata)
        if "internal_tool_events" in proposal_metadata:
            proposal_metadata["internal_tool_events"] = sanitize_internal_tool_events(
                proposal_metadata["internal_tool_events"]
            )
        if "hermes_memory_events" in proposal_metadata:
            proposal_metadata["hermes_memory_events"] = sanitize_hermes_memory_events(
                proposal_metadata["hermes_memory_events"]
            )
        proposal.metadata = {
            **proposal_metadata,
            "harness": {
                **outcome.metadata,
                "internal_tool_events": internal_tool_events,
                "hermes_memory_events": hermes_memory_events,
                "operation": outcome.operation.value,
                "intent": outcome.intent,
            },
        }
        return proposal

    @staticmethod
    def _action_batch_proposals(
        proposal: InterventionProposal,
    ) -> list[InterventionProposal]:
        """Project a validated batch into per-action governance proposals."""

        validation = proposal.metadata.get("harness_validation", {})
        batch = validation.get("action_batch")
        if not isinstance(batch, dict):
            return [proposal]
        batch_id = batch.get("batch_id")
        validations = batch.get("validations")
        if not isinstance(batch_id, str) or not isinstance(validations, list):
            return [proposal]
        projected = []
        for index, item in enumerate(validations):
            intent = item.get("action_intent") if isinstance(item, dict) else None
            if not isinstance(intent, dict):
                continue
            payload = intent.get("payload")
            if not isinstance(payload, dict):
                continue
            provenance = intent.get("provenance")
            target_device_hint = (
                provenance.get("target_device_hint")
                if isinstance(provenance, dict)
                else None
            )
            projected.append(
                replace(
                    proposal,
                    action_capability=intent.get("capability"),
                    required_capability=required_device_capability_for_action(
                        intent.get("capability")
                    ),
                    action_payload=dict(payload),
                    message=str(payload.get("body") or ""),
                    target_device_hint=target_device_hint,
                    metadata={
                        **proposal.metadata,
                        "harness_validation": {
                            "decision": "allowed",
                            "reason": None,
                            "action_intent": intent,
                            "authorization": item.get("authorization"),
                            "phase": "pre_presence",
                            "action_batch": {
                                "batch_id": batch_id,
                                "index": index,
                                "size": len(validations),
                            },
                        },
                    },
                )
            )
        return projected or [proposal]

    @staticmethod
    def _has_action_batch(proposal: InterventionProposal) -> bool:
        validation = proposal.metadata.get("harness_validation", {})
        return isinstance(validation.get("action_batch"), dict)

    def _uses_legacy_harness_memory(self) -> bool:
        return (
            getattr(
                self.gateway.agent_harness,
                "durable_memory_engine",
                None,
            )
            == "openhalo_legacy"
        )

    @staticmethod
    def _terminal_reason_for_harness_outcome(
        outcome,
        *,
        validation: dict | None = None,
    ) -> str:
        if validation is not None and validation["reason"] is not None:
            return (
                "action_batch_rejected"
                if validation["reason"] == "action_batch_rejected"
                else "no_intervention"
            )
        if outcome.intent == "provider_failure":
            return "failed"
        if outcome.intent == "no_intervention":
            return "no_intervention"
        if outcome.intent == "action":
            return "action_pending"
        return "unsupported_outcome"

    @staticmethod
    def _terminal_reason_for_execution(proposal, execution_outcome: dict) -> str:
        if proposal.proposal_type == "no_intervention":
            return "no_intervention"
        if proposal.proposal_type == "provider_failure":
            return "failed"
        if proposal.proposal_type == "action_batch_rejected":
            return "action_batch_rejected"
        if execution_outcome.get("reason") == "presence_suppressed":
            return "suppressed"
        return execution_outcome.get("reason", "complete")

    def _validate_harness_outcome(
        self,
        outcome,
        harness_input: HarnessInput,
    ) -> dict:
        if outcome.action_batch is not None:
            validations = []
            for intent in outcome.action_batch.action_intents:
                provenance = (
                    intent.provenance if isinstance(intent.provenance, dict) else {}
                )
                intent_proposal = replace(
                    outcome.proposal,
                    action_capability=intent.capability,
                    required_capability=required_device_capability_for_action(
                        intent.capability
                    ),
                    action_payload=dict(intent.payload),
                    message=str(intent.payload.get("body") or ""),
                    target_device_hint=provenance.get("target_device_hint"),
                )
                validations.append(
                    self._validate_harness_outcome(
                        replace(
                            outcome,
                            proposal=intent_proposal,
                            action_intent=intent,
                            action_batch=None,
                        ),
                        harness_input,
                    )
                )
            invalid = next(
                (validation for validation in validations if validation["reason"]),
                None,
            )
            return {
                "reason": "action_batch_rejected" if invalid is not None else None,
                "action_intent": validations[0]["action_intent"],
                "authorization": (
                    invalid["authorization"] if invalid is not None else None
                ),
                "action_batch": {
                    "batch_id": outcome.action_batch.batch_id,
                    "validations": validations,
                },
            }
        intent = outcome.action_intent
        if intent is None:
            if outcome.proposal.proposal_type == "action":
                return {
                    "reason": "action_missing_runtime_intent",
                    "action_intent": None,
                    "authorization": None,
                }
            return {
                "reason": None,
                "action_intent": None,
                "authorization": None,
            }
        intent_metadata = {
            "action_id": intent.action_id,
            "executor_kind": intent.executor_kind.value,
            "capability": intent.capability,
            "side_effect_class": intent.side_effect_class.value,
            "visibility": intent.visibility.value,
            "governance": intent.governance.value,
            "payload": intent.payload,
            "provenance": intent.provenance,
        }
        if (
            intent.governance != ActionGovernance.RUNTIME_GOVERNED
            or intent.side_effect_class == ActionSideEffect.NONE
            or intent.visibility != ActionVisibility.USER_VISIBLE
        ):
            return {
                "reason": "private_intent_cannot_be_user_visible",
                "action_intent": intent_metadata,
                "authorization": None,
            }
        proposal = outcome.proposal
        if (
            proposal.proposal_type != "action"
            or proposal.action_capability != intent.capability
            or proposal.action_payload != intent.payload
        ):
            return {
                "reason": "action_intent_proposal_mismatch",
                "action_intent": intent_metadata,
                "authorization": None,
            }
        research_authorization = self._validate_research_assisted_action(
            outcome=outcome,
            harness_input=harness_input,
            intent=intent,
        )
        if research_authorization["reason"] is not None:
            return {
                "reason": research_authorization["reason"],
                "action_intent": intent_metadata,
                "authorization": research_authorization["authorization"],
            }
        if (
            intent.executor_kind == ActionExecutorKind.DEVICE_EDGE
            and not self._has_registered_device_action(intent.capability)
        ):
            return {
                "reason": "unregistered_action_capability",
                "action_intent": intent_metadata,
                "authorization": research_authorization["authorization"],
            }
        if (
            intent.executor_kind != ActionExecutorKind.DEVICE_EDGE
            and not self._has_registered_runtime_action(intent)
        ):
            return {
                "reason": "unregistered_action_target",
                "action_intent": intent_metadata,
                "authorization": research_authorization["authorization"],
            }
        return {
            "reason": None,
            "action_intent": intent_metadata,
            "authorization": research_authorization["authorization"],
        }

    def _validate_research_assisted_action(
        self,
        *,
        outcome,
        harness_input: HarnessInput,
        intent,
    ) -> dict:
        """Require trusted user scope before untrusted research influences action."""

        provenance = intent.provenance if isinstance(intent.provenance, dict) else {}
        actual_events = sanitize_internal_tool_events(
            outcome.metadata.get("internal_tool_events")
        )
        for event in actual_events:
            audit_issue = internal_tool_audit_issue(event)
            if audit_issue is not None:
                return {
                    "reason": audit_issue,
                    "authorization": {
                        "decision": "rejected",
                        "source": "untrusted_research",
                        "risk": "elevated",
                        "confirmation": "not_required",
                    },
                }
        actual_refs = [
            self._research_ref_key(event)
            for event in actual_events
            if self._is_untrusted_research_event(event)
        ]
        claimed_refs = provenance.get("research_input_refs")
        claimed_taint = (
            provenance.get("untrusted_input_present") is True
            or (isinstance(claimed_refs, list) and bool(claimed_refs))
        )
        if not actual_refs and not claimed_taint:
            return {"reason": None, "authorization": None}

        authorization = {
            "decision": "rejected",
            "source": "untrusted_research",
            "risk": "elevated",
            "confirmation": "not_required",
        }
        if (
            not actual_refs
            or provenance.get("untrusted_input_present") is not True
            or not isinstance(claimed_refs, list)
            or any(self._research_ref_key(reference) is None for reference in claimed_refs)
            or sorted(actual_refs) != sorted(
                self._research_ref_key(reference)
                for reference in claimed_refs
            )
        ):
            return {
                "reason": "untrusted_research_missing_provenance",
                "authorization": authorization,
            }

        trusted_intent = provenance.get("trusted_user_intent")
        expected_intent = build_trusted_user_intent_ref(harness_input)
        if not isinstance(trusted_intent, dict) or expected_intent is None:
            return {
                "reason": "untrusted_research_missing_trusted_user_intent",
                "authorization": authorization,
            }
        if not trusted_user_intent_ref_matches(trusted_intent, harness_input):
            return {
                "reason": "untrusted_research_trusted_user_intent_mismatch",
                "authorization": authorization,
            }
        if not self._is_low_risk_research_reply(intent, expected_intent):
            return {
                "reason": "untrusted_research_confirmation_required",
                "authorization": {
                    **authorization,
                    "decision": "confirmation_required",
                    "confirmation": "required",
                },
            }
        return {
            "reason": None,
            "authorization": {
                "decision": "allowed",
                "source": "trusted_user_intent",
                "risk": "low",
                "confirmation": "not_required",
            },
        }

    @staticmethod
    def _is_untrusted_research_event(event: object) -> bool:
        return (
            isinstance(event, dict)
            and event.get("untrusted") is True
            and isinstance(event.get("tool_name"), str)
            and event["tool_name"].startswith("openhalo_web_")
        )

    @staticmethod
    def _research_ref_key(reference: object) -> tuple[str, str, str, bool] | None:
        if not isinstance(reference, dict):
            return None
        tool_call_id = reference.get("tool_call_id")
        tool_name = reference.get("tool_name")
        content_sha256 = reference.get("content_sha256")
        if (
            not isinstance(tool_call_id, str)
            or not tool_call_id
            or not isinstance(tool_name, str)
            or not tool_name.startswith("openhalo_web_")
            or not isinstance(content_sha256, str)
            or len(content_sha256) != 64
            or reference.get("untrusted") is not True
        ):
            return None
        return (tool_call_id, tool_name, content_sha256, True)

    @staticmethod
    def _is_low_risk_research_reply(intent, trusted_intent: dict) -> bool:
        target_device_hint = intent.provenance.get("target_device_hint")
        payload = intent.payload
        return (
            intent.executor_kind == ActionExecutorKind.DEVICE_EDGE
            and intent.capability == "notification.show"
            and isinstance(payload, dict)
            and set(payload) == {"title", "body"}
            and isinstance(payload.get("title"), str)
            and isinstance(payload.get("body"), str)
            and bool(payload["body"].strip())
            and target_device_hint
            in {None, trusted_intent["source_device_id"]}
        )

    def _has_registered_device_action(self, capability: str) -> bool:
        expected_capabilities = {
            capability,
            required_device_capability_for_action(capability),
        }
        for registered_capabilities in self.gateway.state.capability_registry.values():
            for name, metadata in registered_capabilities.items():
                if (
                    name in expected_capabilities
                    and metadata.get("direction")
                    in {"runtime_to_edge", "bidirectional"}
                    and metadata.get("kind") in {None, "action"}
                ):
                    return True
        return False

    def _has_registered_runtime_action(self, intent) -> bool:
        route = self.gateway.state.action_registry.get(intent.capability)
        return (
            route is not None
            and route.get("executor_kind") == intent.executor_kind.value
        )

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
        terminal_reason: str | None = None,
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
            terminal_reason=terminal_reason,
        )
        self.gateway._persist_state()
        return self.gateway._build_interaction_update_replies(
            completed,
            correlation=correlation,
        )

    def _handle_action_batch(
        self,
        *,
        frame: dict,
        interaction_id: str,
        interaction_turn_id: str,
        proposals: list[InterventionProposal],
        snapshot: dict,
        grounding_bundle: dict,
        snapshot_contract: dict,
        decision_time: str | None,
        correlation: dict,
    ) -> list[dict]:
        """Validate, plan, and atomically dispatch a multi-action harness turn."""

        batch_metadata = proposals[0].metadata["harness_validation"]["action_batch"]
        batch_id = batch_metadata["batch_id"]
        planned = []
        for proposal in proposals:
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
            execution_outcome = self.gateway.execution_planner.plan_action(
                source_device_id=frame["device_id"],
                proposal=proposal.to_dict(),
                decision=decision.to_dict(),
                interaction_id=interaction_id,
                correlation=correlation,
                runtime_state=self.gateway.state,
                online_device_ids=set(self.gateway.online_device_ids),
            )
            if execution_outcome["kind"] != "action":
                self.gateway.state.update_interaction(
                    interaction_id,
                    action_batch={
                        "batch_id": batch_id,
                        "status": "rejected",
                        "reason": execution_outcome.get("reason", "not_dispatchable"),
                    },
                )
                self._record_resolved_turn(interaction_id, interaction_turn_id)
                return self._complete_interaction_if_idle(
                    interaction_id=interaction_id,
                    summary="",
                    visibility="silent",
                    terminal_reason="action_batch_rejected",
                    correlation=correlation,
                )
            planned.append((proposal, decision, execution_outcome))

        interaction_record = self.gateway._build_interaction_record(
            interaction_id=interaction_id,
            frame=frame,
            proposal=proposals[0],
            decision=planned[0][1],
        )
        participant_device_ids = list(interaction_record["participant_device_ids"])
        for _, decision, _ in planned[1:]:
            if (
                decision.target_device_id is not None
                and decision.target_device_id not in participant_device_ids
            ):
                participant_device_ids.append(decision.target_device_id)
        self.gateway.state.update_interaction(
            interaction_id,
            **{
                **{
                    key: value
                    for key, value in interaction_record.items()
                    if key != "interaction_id"
                },
                "participant_device_ids": participant_device_ids,
                "action_batch": {
                    "batch_id": batch_id,
                    "status": "planning",
                    "action_ids": [
                        proposal.metadata["harness_validation"]["action_intent"][
                            "action_id"
                        ]
                        for proposal, _, _ in planned
                    ],
                },
            },
        )

        action_ids = []
        for proposal, decision, execution_outcome in planned:
            action_intent = proposal.metadata["harness_validation"]["action_intent"]
            action_id = action_intent.get("action_id")
            if not isinstance(action_id, str) or not action_id:
                action_id = f"{batch_id}:action-{len(action_ids) + 1}"
            action_ids.append(action_id)
            self.gateway.state.record_intervention(
                {
                    "interaction_id": interaction_id,
                    "interaction_turn_id": interaction_turn_id,
                    "request_id": None,
                    "action_batch_id": batch_id,
                    "action_id": action_id,
                    "source_device_id": frame["device_id"],
                    "target_device_id": decision.target_device_id,
                    "action_capability": proposal.action_capability,
                    "decision": decision.decision,
                    "reason": decision.reason,
                    "proposal": proposal.to_dict(),
                    "grounding_bundle": grounding_bundle,
                    "snapshot_contract": snapshot_contract,
                    "planning_record": execution_outcome.get("planning_record"),
                    "correlation": correlation,
                    "recorded_at": decision_time,
                }
            )

        request_ids = [self.gateway._next_action_request_id() for _ in planned]
        self.gateway.interaction_pool.record_action_batch(
            interaction_id,
            interaction_turn_id=interaction_turn_id,
            action_batch_id=batch_id,
            action_requests=list(zip(request_ids, action_ids, strict=True)),
        )
        action_requests = []
        for (proposal, _, execution_outcome), request_id, action_id in zip(
            planned,
            request_ids,
            action_ids,
            strict=True,
        ):
            self.gateway._update_intervention_for_action(
                interaction_id,
                interaction_turn_id,
                action_id,
                request_id=request_id,
                requested_action_capability=execution_outcome["action"]["capability"],
            )
            action_correlation = {
                **correlation,
                "interaction_id": interaction_id,
                "interaction_turn_id": interaction_turn_id,
                "request_id": request_id,
            }
            action_request = build_action_request(
                execution_outcome["target_device_id"],
                execution_outcome["action"],
                request_id=request_id,
                trace_recorder=self.gateway.trace_recorder,
                correlation=action_correlation,
            )
            action_request["interaction_id"] = interaction_id
            action_request["interaction_turn_id"] = interaction_turn_id
            action_request["action_batch_id"] = batch_id
            action_request["action_id"] = action_id
            action_requests.append(action_request)
        self.gateway.state.update_interaction(
            interaction_id,
            action_batch={
                "batch_id": batch_id,
                "status": "awaiting_action_results",
                "action_ids": action_ids,
                "request_ids": request_ids,
            },
        )
        self.gateway._persist_state()
        return action_requests

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
            runtime_state=self.gateway.state,
            online_device_ids=self.gateway.online_device_ids,
        )
        if execution_outcome["kind"] != "action":
            return [
                self.gateway._build_public_error(
                    code="direct_action_rejected",
                    message=(
                        "Direct action does not satisfy the registered "
                        "capability and payload contract."
                    ),
                    device_id=frame["device_id"],
                    capability=(
                        direct_action.get("capability")
                        if isinstance(direct_action, dict)
                        and isinstance(direct_action.get("capability"), str)
                        else None
                    ),
                )
            ]
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
            online_device_ids=set(self.gateway.online_device_ids),
            request_source_device_id=frame["device_id"],
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
        proposal = self._proposal_from_harness(
            HarnessInput(
                operation=HarnessOperation.NORMAL,
                interaction_id=interaction_id,
                interaction_turn_id=interaction_turn_id,
                frame=frame,
                interaction=registration.interaction.to_dict(),
                snapshot=snapshot,
                grounding_bundle=grounding_bundle,
                correlation=correlation,
            )
        )
        self.gateway.state.record_model_health(
            proposal.metadata,
            observed_at=decision_time,
        )
        action_batch_proposals = self._action_batch_proposals(proposal)
        if self._has_action_batch(proposal):
            return self._handle_action_batch(
                frame=frame,
                interaction_id=interaction_id,
                interaction_turn_id=interaction_turn_id,
                proposals=action_batch_proposals,
                snapshot=snapshot,
                grounding_bundle=grounding_bundle,
                snapshot_contract=snapshot_contract,
                decision_time=decision_time,
                correlation=correlation,
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
                terminal_reason=self._terminal_reason_for_execution(
                    proposal,
                    execution_outcome,
                ),
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
            initiator_kind="passive_observation",
            requesting_device_id=None,
            outcome_delivery_required=False,
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
            online_device_ids=set(self.gateway.online_device_ids),
            request_source_device_id=source_device_id,
        )
        grounding_bundle = sanitize_observation_driven_grounding_bundle(
            grounding_bundle,
            snapshot=snapshot,
        )
        admitted_observations = self._admitted_observation_evidence(
            observations,
            admission.evidence_refs,
        )
        proposal = self._proposal_from_harness(
            HarnessInput(
                operation=HarnessOperation.OBSERVATION_DRIVEN,
                interaction_id=interaction_id,
                interaction_turn_id=interaction_turn_id,
                interaction=registration.interaction.to_dict(),
                admission=admission.to_dict(),
                observations=admitted_observations,
                turn_index=self.gateway._turn_index_for_interaction(interaction_id),
                snapshot=snapshot,
                grounding_bundle=grounding_bundle,
                correlation=correlation,
            )
        )
        self.gateway.state.record_model_health(
            proposal.metadata,
            observed_at=decision_time,
        )
        action_batch_proposals = self._action_batch_proposals(proposal)
        if self._has_action_batch(proposal):
            return self._handle_action_batch(
                frame={"device_id": source_device_id},
                interaction_id=interaction_id,
                interaction_turn_id=interaction_turn_id,
                proposals=action_batch_proposals,
                snapshot=snapshot,
                grounding_bundle=grounding_bundle,
                snapshot_contract=snapshot_contract,
                decision_time=decision_time,
                correlation=correlation,
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
                terminal_reason=self._terminal_reason_for_execution(
                    proposal,
                    execution_outcome,
                ),
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
        if self.gateway.interaction_pool.has_pending_action(interaction_id):
            self.gateway._record_observation_reentry(interaction_id, frame)
            self.gateway._persist_state()
            return []
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
            online_device_ids=set(self.gateway.online_device_ids),
            request_source_device_id=interaction["source_device_id"],
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
        proposal = self._proposal_from_harness(
            HarnessInput(
                operation=HarnessOperation.POST_OBSERVATION,
                interaction_id=interaction_id,
                interaction_turn_id=interaction_turn_id,
                interaction=interaction,
                prior_proposal=intervention["proposal"],
                observations=observations,
                turn_index=self.gateway._turn_index_for_interaction(interaction_id),
                snapshot=snapshot,
                grounding_bundle=grounding_bundle,
                correlation=correlation,
            )
        )
        self.gateway.state.record_model_health(
            proposal.metadata,
            observed_at=decision_time,
        )
        action_batch_proposals = self._action_batch_proposals(proposal)
        if self._has_action_batch(proposal):
            return self._handle_action_batch(
                frame={"device_id": interaction["source_device_id"]},
                interaction_id=interaction_id,
                interaction_turn_id=interaction_turn_id,
                proposals=action_batch_proposals,
                snapshot=snapshot,
                grounding_bundle=grounding_bundle,
                snapshot_contract=snapshot_contract,
                decision_time=decision_time,
                correlation=correlation,
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
            terminal_reason=self._terminal_reason_for_execution(
                proposal,
                execution_outcome,
            ),
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
            request_id=request_id,
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
        action_batch_id = self.gateway.interaction_pool.action_batch_id_for_request(
            interaction_id,
            result_turn_id,
            request_id,
        )
        if self.gateway.interaction_pool.has_pending_action(interaction_id):
            self.gateway._persist_state()
            return []
        batch_turns = (
            self.gateway.interaction_pool.action_requests_for_batch(
                interaction_id,
                action_batch_id,
            )
            if action_batch_id is not None
            else []
        )
        result_by_request_id = {
            action_result.get("request_id"): action_result
            for action_result in self.gateway.state.action_results
            if action_result.get("interaction_id") == interaction_id
            and action_result.get("interaction_turn_id") == result_turn_id
        }
        action_results = [
            dict(result_by_request_id[turn.request_id])
            for turn in batch_turns
            if turn.request_id in result_by_request_id
        ]
        if not action_results:
            action_results = [result]
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
            online_device_ids=set(self.gateway.online_device_ids),
            request_source_device_id=interaction["source_device_id"],
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
        proposal = self._proposal_from_harness(
            HarnessInput(
                operation=HarnessOperation.POST_ACTION,
                interaction_id=interaction_id,
                interaction_turn_id=interaction_turn_id,
                interaction=interaction,
                prior_proposal=intervention["proposal"],
                action_result=result,
                action_results=action_results,
                turn_index=self.gateway._turn_index_for_interaction(interaction_id),
                snapshot=snapshot,
                grounding_bundle=grounding_bundle,
                correlation=correlation,
            )
        )
        outcome_contract = build_action_result_outcome_contract(interaction, result)
        if (
            outcome_contract["source_outcome_required"]
            and proposal.proposal_type in {"no_intervention", "provider_failure"}
        ):
            proposal = self._outcome_fallback_proposal(proposal, outcome_contract)
        self.gateway.state.record_model_health(
            proposal.metadata,
            observed_at=decision_time,
        )
        action_batch_proposals = self._action_batch_proposals(proposal)
        if self._has_action_batch(proposal):
            return self._handle_action_batch(
                frame={"device_id": interaction["source_device_id"]},
                interaction_id=interaction_id,
                interaction_turn_id=interaction_turn_id,
                proposals=action_batch_proposals,
                snapshot=snapshot,
                grounding_bundle=grounding_bundle,
                snapshot_contract=snapshot_contract,
                decision_time=decision_time,
                correlation=correlation,
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
            terminal_reason=self._terminal_reason_for_execution(
                proposal,
                execution_outcome,
            ),
            correlation=correlation,
        )


__all__ = ["RuntimeOrchestrator"]
