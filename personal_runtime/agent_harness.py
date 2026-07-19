"""Runtime-owned contracts for the M20 Agent Harness seam."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import TYPE_CHECKING
from typing import Callable
from typing import Protocol

from personal_runtime.harness_provenance import build_trusted_user_intent_ref

if TYPE_CHECKING:
    from personal_runtime.agent_executor import InterventionProposal


class HarnessOperation(str, Enum):
    """The runtime entry point that requested harness deliberation."""

    NORMAL = "normal"
    POST_ACTION = "post_action"
    POST_OBSERVATION = "post_observation"
    OBSERVATION_DRIVEN = "observation_driven"


class ActionExecutorKind(str, Enum):
    """The OpenHalo executor selected only after action validation."""

    DEVICE_EDGE = "device_edge"
    RUNTIME_LOCAL = "runtime_local"
    MCP = "mcp"
    SKILL_PROCEDURE = "skill_procedure"


class ActionSideEffect(str, Enum):
    """The durable or external effect class of an action intent."""

    NONE = "none"
    DURABLE = "durable"
    EXTERNAL = "external"


class ActionVisibility(str, Enum):
    """Whether an action has a user-perceptible surface."""

    INTERNAL = "internal"
    USER_VISIBLE = "user_visible"


class ActionGovernance(str, Enum):
    """Whether an intent stays in the harness or enters runtime governance."""

    AGENT_PRIVATE = "agent_private"
    RUNTIME_GOVERNED = "runtime_governed"


@dataclass(frozen=True, slots=True)
class RuntimeActionIntent:
    """A runtime-owned action envelope before any executor is invoked."""

    action_id: str | None
    executor_kind: ActionExecutorKind
    capability: str
    payload: dict
    side_effect_class: ActionSideEffect
    visibility: ActionVisibility
    governance: ActionGovernance
    provenance: dict


@dataclass(frozen=True, slots=True)
class ActionBatch:
    """A deduplicated set of governed action intents from one harness turn."""

    batch_id: str
    action_intents: tuple[RuntimeActionIntent, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.batch_id, str) or not self.batch_id:
            raise ValueError("action batch requires a non-empty batch_id")
        unique_intents = []
        seen = set()
        for intent in self.action_intents:
            if not isinstance(intent, RuntimeActionIntent):
                raise TypeError("action batch entries must be RuntimeActionIntent")
            key = self._deduplication_key(intent)
            if key in seen:
                continue
            seen.add(key)
            unique_intents.append(intent)
        if not unique_intents:
            raise ValueError("action batch requires at least one action intent")
        object.__setattr__(self, "action_intents", tuple(unique_intents))

    @staticmethod
    def _deduplication_key(intent: RuntimeActionIntent) -> str:
        provenance = intent.provenance if isinstance(intent.provenance, dict) else {}
        return json.dumps(
            {
                "executor_kind": intent.executor_kind.value,
                "capability": intent.capability,
                "payload": intent.payload,
                "side_effect_class": intent.side_effect_class.value,
                "visibility": intent.visibility.value,
                "governance": intent.governance.value,
                "target_device_hint": provenance.get("target_device_hint"),
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    def action_refs(self) -> list[dict]:
        return [
            {
                "action_id": intent.action_id,
                "executor_kind": intent.executor_kind.value,
                "capability": intent.capability,
            }
            for intent in self.action_intents
        ]


@dataclass(frozen=True, slots=True)
class HarnessInput:
    """Grounded runtime input supplied to one harness deliberation."""

    operation: HarnessOperation
    interaction_id: str
    interaction_turn_id: str
    frame: dict | None = None
    interaction: dict | None = None
    prior_proposal: dict | None = None
    action_result: dict | None = None
    action_results: list[dict] | None = None
    observations: list[dict] | None = None
    admission: dict | None = None
    turn_index: int | None = None
    snapshot: dict | None = None
    grounding_bundle: dict | None = None
    working_memory: dict | None = None
    procedural_memory: list[dict] | None = None
    semantic_memory: list[dict] | None = None
    episodic_memory: list[dict] | None = None
    correlation: dict | None = None


@dataclass(frozen=True, slots=True)
class HarnessOutcome:
    """An inspectable harness decision before runtime governance executes it."""

    operation: HarnessOperation
    intent: str
    proposal: InterventionProposal | None
    metadata: dict
    executed: bool = False
    action_intent: RuntimeActionIntent | None = None
    action_batch: ActionBatch | None = None

    @classmethod
    def from_proposal(
        cls,
        *,
        operation: HarnessOperation,
        proposal: InterventionProposal,
        metadata: dict | None = None,
        action_intent: RuntimeActionIntent | None = None,
        action_batch: ActionBatch | None = None,
    ) -> HarnessOutcome:
        if action_batch is not None and len(action_batch.action_intents) == 1:
            action_intent = action_batch.action_intents[0]
        elif action_batch is not None and action_intent is None:
            action_intent = action_batch.action_intents[0]
        return cls(
            operation=operation,
            intent=proposal.proposal_type,
            proposal=proposal,
            metadata=metadata or {},
            action_intent=action_intent,
            action_batch=action_batch,
        )


class HarnessRunner(Protocol):
    """Adapter boundary for one internal agent-loop deliberation."""

    def run(self, harness_input: HarnessInput) -> HarnessOutcome:
        """Return an intent for the runtime-owned governance path."""


class LegacyProposalHarness:
    """Temporary adapter from the M20 contract to accepted proposal formation."""

    durable_memory_engine = "openhalo_legacy"

    def __init__(self, proposal_formation_getter: Callable[[], object]) -> None:
        self._proposal_formation_getter = proposal_formation_getter

    @staticmethod
    def _action_intent_from_proposal(
        proposal: InterventionProposal,
        harness_input: HarnessInput,
    ) -> RuntimeActionIntent | None:
        if proposal.proposal_type != "action":
            return None
        if (
            not isinstance(proposal.action_capability, str)
            or not proposal.action_capability
            or not isinstance(proposal.action_payload, dict)
        ):
            return None

        provenance = {
            "origin": "legacy_proposal_formation",
            "operation": harness_input.operation.value,
            "interaction_id": harness_input.interaction_id,
            "interaction_turn_id": harness_input.interaction_turn_id,
            "proposal_source": proposal.source,
            "target_device_hint": proposal.target_device_hint,
        }
        trusted_user_intent = build_trusted_user_intent_ref(harness_input)
        if trusted_user_intent is not None:
            provenance["trusted_user_intent"] = trusted_user_intent

        return RuntimeActionIntent(
            action_id=f"legacy:{harness_input.interaction_turn_id}",
            executor_kind=ActionExecutorKind.DEVICE_EDGE,
            capability=proposal.action_capability,
            payload=dict(proposal.action_payload),
            side_effect_class=ActionSideEffect.EXTERNAL,
            visibility=ActionVisibility.USER_VISIBLE,
            governance=ActionGovernance.RUNTIME_GOVERNED,
            provenance=provenance,
        )

    def run(self, harness_input: HarnessInput) -> HarnessOutcome:
        proposal_formation = self._proposal_formation_getter()
        snapshot = harness_input.snapshot if harness_input.snapshot is not None else {}
        correlation = (
            harness_input.correlation if harness_input.correlation is not None else {}
        )
        if harness_input.operation == HarnessOperation.NORMAL:
            proposal = proposal_formation.build_normal_path_proposal(
                harness_input.frame,
                snapshot=snapshot,
                grounding_bundle=harness_input.grounding_bundle,
                correlation=correlation,
            )
        elif harness_input.operation == HarnessOperation.POST_ACTION:
            proposal = proposal_formation.build_post_action_proposal(
                interaction=harness_input.interaction,
                prior_proposal=harness_input.prior_proposal,
                result=harness_input.action_result,
                turn_index=harness_input.turn_index,
                snapshot=snapshot,
                grounding_bundle=harness_input.grounding_bundle,
                correlation=correlation,
            )
        elif harness_input.operation == HarnessOperation.POST_OBSERVATION:
            proposal = proposal_formation.build_post_observation_proposal(
                interaction=harness_input.interaction,
                prior_proposal=harness_input.prior_proposal,
                observations=harness_input.observations,
                turn_index=harness_input.turn_index,
                snapshot=snapshot,
                grounding_bundle=harness_input.grounding_bundle,
                correlation=correlation,
            )
        elif harness_input.operation == HarnessOperation.OBSERVATION_DRIVEN:
            proposal = proposal_formation.build_observation_driven_proposal(
                interaction=harness_input.interaction,
                admission=harness_input.admission,
                observations=harness_input.observations,
                turn_index=harness_input.turn_index,
                snapshot=snapshot,
                grounding_bundle=harness_input.grounding_bundle,
                correlation=correlation,
            )
        else:
            raise ValueError(f"unknown harness operation: {harness_input.operation}")
        return HarnessOutcome.from_proposal(
            operation=harness_input.operation,
            proposal=proposal,
            metadata={
                "runner": "legacy_proposal_formation",
                "operation": harness_input.operation.value,
                "durable_memory_engine": self.durable_memory_engine,
            },
            action_intent=self._action_intent_from_proposal(
                proposal,
                harness_input,
            ),
        )
