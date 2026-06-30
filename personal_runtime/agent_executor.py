"""Minimal agent proposal and reply generation for the early runtime path."""

import json
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path

from openhalo_common.diagnostics import DiagnosticBoundaryRecorder
from personal_runtime.model_provider import generate_text_reply_plan
from personal_runtime.model_provider import generate_text_proposal_plan
from personal_runtime.model_provider import generate_post_action_proposal_plan
from personal_runtime.model_provider import generate_post_observation_proposal_plan
from personal_runtime.prompt_context import build_behavior_contract
from personal_runtime.prompt_context import build_prompt_context_package
from personal_runtime.prompt_context import prompt_context_metadata_from_package
from personal_runtime.runtime_memory import grounding_metadata_from_bundle
from personal_runtime.action_layer import required_device_capability_for_action


@dataclass(slots=True)
class InterventionProposal:
    kind: str
    proposal_type: str
    source: str
    action_capability: str | None
    required_capability: str | None
    action_payload: dict
    message: str
    metadata: dict
    target_device_hint: str | None = None
    interaction_type: str = "pull"
    visibility_intent: str = "visible"
    candidate_surface_hints: list[str] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ProposalFormation:
    def __init__(
        self,
        diagnostic_recorder=None,
        runtime_instance_id: str = "runtime-main",
        trace_recorder=None,
        config_path: Path | None = None,
    ) -> None:
        self.diagnostics = DiagnosticBoundaryRecorder(
            recorder=diagnostic_recorder,
            side="runtime",
            runtime_instance_id=runtime_instance_id,
        )
        self.trace_recorder = trace_recorder
        self.config_path = config_path

    def build_normal_path_proposal(
        self,
        frame: dict,
        snapshot: dict,
        grounding_bundle: dict | None = None,
        correlation: dict | None = None,
    ) -> InterventionProposal:
        payload = frame["payload"]
        operation_input = {
            "capability": frame.get("capability"),
            "text": payload.get("text", ""),
            "has_agent_initiative": payload.get("agent_initiative") is not None,
        }
        with self.diagnostics.boundary(
            module="Proposal Formation",
            operation="build_proposal",
            correlation=correlation or {},
            input_payload=operation_input,
            summary="Built intervention proposal.",
        ) as boundary:
            if payload.get("agent_initiative") is not None:
                proposal = build_agent_initiative_proposal(
                    payload["agent_initiative"],
                    snapshot=snapshot,
                    grounding_bundle=grounding_bundle,
                    trace_recorder=self.trace_recorder,
                )
            else:
                proposal = build_intervention_proposal(
                    payload["text"],
                    snapshot=snapshot,
                    grounding_bundle=grounding_bundle,
                    trace_recorder=self.trace_recorder,
                    config_path=self.config_path,
                )
            boundary.output(proposal.to_dict())
            return proposal

    def build_post_action_proposal(
        self,
        interaction: dict,
        prior_proposal: dict,
        result: dict,
        turn_index: int,
        snapshot: dict,
        grounding_bundle: dict | None = None,
        correlation: dict | None = None,
    ) -> InterventionProposal:
        with self.diagnostics.boundary(
            module="Proposal Formation",
            operation="build_post_action_proposal",
            correlation=correlation or {},
            input_payload={
                "interaction_id": interaction.get("interaction_id"),
                "result": result,
                "turn_index": turn_index,
            },
            summary="Built post-action proposal.",
        ) as boundary:
            proposal = build_post_action_proposal(
                interaction=interaction,
                prior_proposal=prior_proposal,
                result=result,
                turn_index=turn_index,
                snapshot=snapshot,
                grounding_bundle=grounding_bundle,
                trace_recorder=self.trace_recorder,
                config_path=self.config_path,
            )
            boundary.output(proposal.to_dict())
            return proposal

    def build_post_observation_proposal(
        self,
        interaction: dict,
        prior_proposal: dict,
        observations: list[dict],
        turn_index: int,
        snapshot: dict,
        grounding_bundle: dict | None = None,
        correlation: dict | None = None,
    ) -> InterventionProposal:
        with self.diagnostics.boundary(
            module="Proposal Formation",
            operation="build_post_observation_proposal",
            correlation=correlation or {},
            input_payload={
                "interaction_id": interaction.get("interaction_id"),
                "observation_count": len(observations),
                "turn_index": turn_index,
            },
            summary="Built post-observation proposal.",
        ) as boundary:
            proposal = build_post_observation_proposal(
                interaction=interaction,
                prior_proposal=prior_proposal,
                observations=observations,
                turn_index=turn_index,
                snapshot=snapshot,
                grounding_bundle=grounding_bundle,
                trace_recorder=self.trace_recorder,
                config_path=self.config_path,
            )
            boundary.output(proposal.to_dict())
            return proposal


def build_intervention_proposal(
    user_text: str,
    snapshot: dict | None = None,
    grounding_bundle: dict | None = None,
    trace_recorder=None,
    config_path: Path | None = None,
) -> InterventionProposal:
    _snapshot = snapshot or {}
    prompt_context_package = build_prompt_context_package(
        user_text=user_text,
        snapshot=_snapshot,
        grounding_bundle=grounding_bundle,
    )
    behavior_contract = build_behavior_contract(
        prompt_context_package=prompt_context_package,
        grounding_bundle=grounding_bundle,
    )
    proposal_plan = generate_text_proposal_plan(
        user_text=user_text,
        snapshot=_snapshot,
        grounding=grounding_bundle,
        profile_name="proposal_formation",
        config_path=config_path,
    )
    action_capability = proposal_plan.action_capability
    if proposal_plan.proposal_type == "no_intervention":
        kind = "no_intervention"
    elif action_capability and action_capability.startswith("runtime."):
        kind = "runtime_control"
    else:
        kind = "notify"
    action_payload = dict(proposal_plan.action_payload)
    if action_capability == "notification.show":
        action_payload.setdefault("message", proposal_plan.response_text)
    proposal = InterventionProposal(
        kind=kind,
        proposal_type=proposal_plan.proposal_type,
        source="sense_first",
        action_capability=action_capability,
        required_capability=required_device_capability_for_action(
            action_capability
        )
        if action_capability is not None
        else None,
        action_payload=action_payload,
        message=user_text,
        metadata={
            "trigger": "text.input",
            "snapshot_fields": sorted(_snapshot.keys()),
            **grounding_metadata_from_bundle(grounding_bundle),
            **prompt_context_metadata_from_package(
                prompt_context_package,
                behavior_contract,
            ),
            **proposal_plan.metadata,
        },
        interaction_type="pull",
        visibility_intent="visible"
        if proposal_plan.proposal_type != "no_intervention"
        else "silent",
        candidate_surface_hints=["source_device", "terminal"]
        if proposal_plan.proposal_type != "no_intervention"
        else ["background"],
    )
    if trace_recorder is not None:
        trace_recorder.record(
            "AGENT",
            "built intervention proposal",
            source=proposal.source,
            kind=proposal.kind,
            proposal_type=proposal.proposal_type,
            action_capability=proposal.action_capability or "none",
        )
    return proposal


def build_agent_initiative_proposal(
    initiative_request: dict,
    snapshot: dict | None = None,
    grounding_bundle: dict | None = None,
    trace_recorder=None,
) -> InterventionProposal:
    _snapshot = snapshot or {}
    action_capability = initiative_request["action_capability"]
    action_payload = dict(initiative_request.get("action_payload", {}))
    metadata = {
        key: value
        for key, value in initiative_request.items()
        if key
        not in {"action_capability", "action_payload", "target_device_hint"}
    }
    prompt_context_package = build_prompt_context_package(
        user_text=initiative_request.get("message", ""),
        snapshot=_snapshot,
        grounding_bundle=grounding_bundle,
    )
    behavior_contract = build_behavior_contract(
        prompt_context_package=prompt_context_package,
        grounding_bundle=grounding_bundle,
    )
    proposal = InterventionProposal(
        kind="runtime_control"
        if action_capability.startswith("runtime.")
        else "notify",
        proposal_type="action"
        if action_capability.startswith("runtime.")
        else "reply",
        source="agent_initiative",
        action_capability=action_capability,
        required_capability=required_device_capability_for_action(
            action_capability
        ),
        action_payload=action_payload,
        message=initiative_request.get("message", ""),
        metadata={
            **metadata,
            "snapshot_fields": sorted(_snapshot.keys()),
            **grounding_metadata_from_bundle(grounding_bundle),
            **prompt_context_metadata_from_package(
                prompt_context_package,
                behavior_contract,
            ),
        },
        target_device_hint=initiative_request.get("target_device_hint"),
        interaction_type="push",
        visibility_intent="visible",
        candidate_surface_hints=[
            initiative_request.get("target_device_hint", "preferred_target")
        ],
    )
    if trace_recorder is not None:
        trace_recorder.record(
            "AGENT",
            "built intervention proposal",
            source=proposal.source,
            kind=proposal.kind,
            proposal_type=proposal.proposal_type,
            action_capability=proposal.action_capability,
        )
    return proposal


def build_post_action_proposal(
    interaction: dict,
    prior_proposal: dict,
    result: dict,
    turn_index: int,
    snapshot: dict | None = None,
    grounding_bundle: dict | None = None,
    trace_recorder=None,
    config_path: Path | None = None,
) -> InterventionProposal:
    _snapshot = snapshot or {}
    interaction_id = interaction["interaction_id"]
    post_action_text = json.dumps(
        {
            "trigger": "action_result",
            "interaction_id": interaction_id,
            "prior_proposal_type": prior_proposal.get("proposal_type"),
            "prior_action_capability": prior_proposal.get("action_capability"),
            "result": result,
        },
        sort_keys=True,
    )
    prompt_context_package = build_prompt_context_package(
        user_text=post_action_text,
        snapshot=_snapshot,
        grounding_bundle=grounding_bundle,
    )
    behavior_contract = build_behavior_contract(
        prompt_context_package=prompt_context_package,
        grounding_bundle=grounding_bundle,
    )
    proposal_plan = generate_post_action_proposal_plan(
        interaction_id=interaction_id,
        prior_proposal=prior_proposal,
        result=result,
        snapshot=_snapshot,
        grounding=grounding_bundle,
        profile_name="proposal_formation",
        config_path=config_path,
    )
    action_capability = proposal_plan.action_capability
    if proposal_plan.proposal_type == "no_intervention":
        kind = "no_intervention"
    elif action_capability and action_capability.startswith("runtime."):
        kind = "runtime_control"
    else:
        kind = "notify"
    action_payload = dict(proposal_plan.action_payload)
    if action_capability == "notification.show":
        action_payload.setdefault("message", proposal_plan.response_text)
    metadata = {
        "trigger": "action_result",
        "interaction_id": interaction_id,
        "turn_index": turn_index,
        "parent_proposal_type": prior_proposal.get("proposal_type"),
        "parent_action_capability": prior_proposal.get("action_capability")
        or result.get("capability"),
        "result_status": result.get("status"),
        "snapshot_fields": sorted(_snapshot.keys()),
        **grounding_metadata_from_bundle(grounding_bundle),
        **prompt_context_metadata_from_package(
            prompt_context_package,
            behavior_contract,
        ),
        **proposal_plan.metadata,
    }
    proposal = InterventionProposal(
        kind=kind,
        proposal_type=proposal_plan.proposal_type,
        source="post_action",
        action_capability=action_capability,
        required_capability=required_device_capability_for_action(
            action_capability
        )
        if action_capability is not None
        else None,
        action_payload=action_payload,
        message=proposal_plan.response_text,
        metadata=metadata,
        target_device_hint=interaction.get("source_device_id")
        if action_capability == "notification.show"
        else None,
        interaction_type=interaction.get("interaction_type", "pull"),
        visibility_intent="silent"
        if proposal_plan.proposal_type == "no_intervention"
        else "visible",
        candidate_surface_hints=["source_device"]
        if proposal_plan.proposal_type != "no_intervention"
        else ["background"],
    )
    if trace_recorder is not None:
        trace_recorder.record(
            "AGENT",
            "built post-action proposal",
            source=proposal.source,
            kind=proposal.kind,
            proposal_type=proposal.proposal_type,
            action_capability=proposal.action_capability or "none",
            interaction_id=interaction_id,
        )
    return proposal


def build_post_observation_proposal(
    interaction: dict,
    prior_proposal: dict,
    observations: list[dict],
    turn_index: int,
    snapshot: dict | None = None,
    grounding_bundle: dict | None = None,
    trace_recorder=None,
    config_path: Path | None = None,
) -> InterventionProposal:
    _snapshot = snapshot or {}
    interaction_id = interaction["interaction_id"]
    observation_names = sorted(
        {
            observation.get("name", "")
            for observation in observations
            if observation.get("name")
        }
    )
    post_observation_text = json.dumps(
        {
            "trigger": "observation",
            "interaction_id": interaction_id,
            "prior_proposal_type": prior_proposal.get("proposal_type"),
            "prior_action_capability": prior_proposal.get("action_capability"),
            "observations": observations,
        },
        sort_keys=True,
    )
    prompt_context_package = build_prompt_context_package(
        user_text=post_observation_text,
        snapshot=_snapshot,
        grounding_bundle=grounding_bundle,
    )
    behavior_contract = build_behavior_contract(
        prompt_context_package=prompt_context_package,
        grounding_bundle=grounding_bundle,
    )
    proposal_plan = generate_post_observation_proposal_plan(
        interaction_id=interaction_id,
        prior_proposal=prior_proposal,
        observations=observations,
        snapshot=_snapshot,
        grounding=grounding_bundle,
        profile_name="proposal_formation",
        config_path=config_path,
    )
    action_capability = proposal_plan.action_capability
    if proposal_plan.proposal_type == "no_intervention":
        kind = "no_intervention"
    elif action_capability and action_capability.startswith("runtime."):
        kind = "runtime_control"
    else:
        kind = "notify"
    action_payload = dict(proposal_plan.action_payload)
    if action_capability == "notification.show":
        action_payload.setdefault("message", proposal_plan.response_text)
    metadata = {
        "trigger": "observation",
        "interaction_id": interaction_id,
        "turn_index": turn_index,
        "parent_proposal_type": prior_proposal.get("proposal_type"),
        "parent_action_capability": prior_proposal.get("action_capability"),
        "observation_names": observation_names,
        "snapshot_fields": sorted(_snapshot.keys()),
        **grounding_metadata_from_bundle(grounding_bundle),
        **prompt_context_metadata_from_package(
            prompt_context_package,
            behavior_contract,
        ),
        **proposal_plan.metadata,
    }
    proposal = InterventionProposal(
        kind=kind,
        proposal_type=proposal_plan.proposal_type,
        source="post_observation",
        action_capability=action_capability,
        required_capability=required_device_capability_for_action(
            action_capability
        )
        if action_capability is not None
        else None,
        action_payload=action_payload,
        message=proposal_plan.response_text,
        metadata=metadata,
        target_device_hint=interaction.get("source_device_id")
        if action_capability == "notification.show"
        else None,
        interaction_type=interaction.get("interaction_type", "pull"),
        visibility_intent="silent"
        if proposal_plan.proposal_type == "no_intervention"
        else "visible",
        candidate_surface_hints=["source_device"]
        if proposal_plan.proposal_type != "no_intervention"
        else ["background"],
    )
    if trace_recorder is not None:
        trace_recorder.record(
            "AGENT",
            "built post-observation proposal",
            source=proposal.source,
            kind=proposal.kind,
            proposal_type=proposal.proposal_type,
            action_capability=proposal.action_capability or "none",
            interaction_id=interaction_id,
        )
    return proposal


def generate_reply(user_text: str, trace_recorder=None) -> str:
    reply = f"Runtime heard: {user_text}"
    if trace_recorder is not None:
        trace_recorder.record("AGENT", "generated reply", reply=reply)
    return reply
