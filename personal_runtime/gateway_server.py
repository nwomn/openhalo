"""Minimal in-memory gateway loop for the v0 runtime."""

import asyncio
import json
import time
import secrets
from collections.abc import Callable
from contextlib import asynccontextmanager
from contextlib import suppress
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from itertools import count
from pathlib import Path
from uuid import uuid4

import websockets
from websockets.exceptions import ConnectionClosedError
from websockets.exceptions import ConnectionClosedOK

from edge_api.auth import build_challenge_payload
from edge_api.auth import decode_base64url
from edge_api.auth import encode_base64url
from edge_api.auth import is_expired
from edge_api.auth import is_p256_public_key
from edge_api.auth import verify_challenge_signature
from edge_api.endpoint import validate_runtime_endpoint
from edge_api.protocol import validate_capability_registration
from edge_api.protocol import validate_frame, with_api_version
from personal_runtime.action_layer import build_interaction_progress
from personal_runtime.action_layer import build_interaction_update
from personal_runtime.action_result_attachments import ActionResultAttachmentService
from personal_runtime.agent_executor import ProposalFormation
from personal_runtime.agent_harness import LegacyProposalHarness
from personal_runtime.hermes_adapter import configured_harness_runner
from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.context_envelope import ContextEnvelopeCompiler
from personal_runtime.context_facts import ContextFact
from personal_runtime.context_facts import ContextFactStore
from personal_runtime.display_lifecycle import DisplayLifecycle
from personal_runtime.execution_planning import ExecutionPlanner
from personal_runtime.interaction_pool import InteractionPool
from personal_runtime.main_session import MainSessionManager
from personal_runtime.media_provider_delivery import (
    build_configured_camera_media_provider_request,
)
from personal_runtime.mobile_liveness import record_mobile_session_state
from personal_runtime.mobile_liveness import update_mobile_liveness_after_observations
from personal_runtime.model_provider import load_runtime_model_config
from personal_runtime.outcome_receipt import append_receipt_entry
from personal_runtime.outcome_receipt import project_outcome_receipt
from personal_runtime.pairing_store import PairingError
from personal_runtime.pairing_store import PairingStore
from personal_runtime.presence_router import PresenceRouter
from personal_runtime.proactive_trigger_gate import ProactiveTriggerGate
from personal_runtime.runtime_console_presenter import RuntimeConsolePresenter
from personal_runtime.runtime_orchestrator import RuntimeOrchestrator
from personal_runtime.runtime_state import RuntimeState
from personal_runtime.state_store import build_state_store
from personal_runtime.trace_recorder import TraceRecorder


StreamedReplyEmitter = Callable[[list[dict]], None]
_streamed_reply_emitter: ContextVar[StreamedReplyEmitter | None] = ContextVar(
    "streamed_reply_emitter",
    default=None,
)
_STREAMED_PROGRESS_PHASES = frozenset(
    {
        "deliberating",
        "researching",
        "planning",
        "executing",
        "completing",
        "completed",
        "failed",
        "cancelled",
    }
)


@dataclass(frozen=True)
class PendingAuthentication:
    device_id: str
    device_type: str
    device_role: str | None
    device_profile: str | None
    audience: str
    session_id: str
    challenge_id: str
    nonce: str
    expires_at: str
    public_key_der: bytes
    pairing_code: str | None = None
    display_name: str | None = None


class RuntimeGateway:
    def __init__(
        self,
        shared_token: str | None = None,
        state_path: Path | None = None,
        state: RuntimeState | None = None,
        trace_recorder: TraceRecorder | None = None,
        persist_state: bool = True,
        runtime_event_emitter=None,
        llm_config_path: Path | None = None,
        grounding_edge_history_fetcher=None,
        diagnostic_recorder=None,
        runtime_instance_id: str = "runtime-main",
        agent_harness=None,
        pairing_store: PairingStore | None = None,
        audience: str = "wss://runtime.invalid/openhalo/edge",
        proxy_screen_vision_evaluator=None,
    ) -> None:
        del shared_token
        self.audience = audience
        default_state_path = (
            Path(".runtime/state.sqlite3")
            if persist_state
            else Path(".runtime/state.json")
        )
        self.state_store = build_state_store(state_path or default_state_path)
        if state is not None:
            self.state = state
        elif not persist_state and state_path is None:
            self.state = RuntimeState()
        else:
            self.state = self.state_store.load()
        self.context_fact_store = ContextFactStore(
            ContextFact.from_dict(fact)
            for fact in self.state.context_facts.values()
        )
        self.context_envelope_compiler = ContextEnvelopeCompiler()
        self.interaction_pool = InteractionPool(self.state)
        self.display_lifecycle = DisplayLifecycle()
        self.runtime_event_emitter = runtime_event_emitter
        self.runtime_console_presenter = RuntimeConsolePresenter(
            runtime_event_emitter
        )
        self.proactive_trigger_gate = ProactiveTriggerGate()
        self.online_device_ids: set[str] = set()
        self.live_connections: dict[str, object] = {}
        self.trace_recorder = trace_recorder
        self.persist_state = persist_state
        self.llm_config_path = llm_config_path
        self.grounding_edge_history_fetcher = grounding_edge_history_fetcher
        self.diagnostic_recorder = diagnostic_recorder
        self.runtime_instance_id = runtime_instance_id
        self.pairing_store = pairing_store
        self.pending_authentications: dict[str, PendingAuthentication] = {}
        self._last_storage_maintenance_at = 0.0
        self._deferred_storage_flush_handle = None
        self._websocket_send_locks: dict[int, asyncio.Lock] = {}
        self._interaction_processing_locks: dict[str, tuple[asyncio.Lock, int]] = {}
        self.orchestrator = RuntimeOrchestrator(self)
        self._action_request_counter = count(1)
        self.proposal_formation = ProposalFormation(
            diagnostic_recorder=diagnostic_recorder,
            runtime_instance_id=runtime_instance_id,
            trace_recorder=trace_recorder,
            config_path=llm_config_path,
        )
        legacy_harness = LegacyProposalHarness(lambda: self.proposal_formation)
        self.agent_harness = agent_harness or configured_harness_runner(
            config_path=llm_config_path,
            legacy_runner=legacy_harness,
        )
        self.main_session_manager = MainSessionManager(
            state=self.state.main_session,
            restore=self._restore_main_session,
            create=self._create_main_session,
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
        self.action_result_attachments = ActionResultAttachmentService(
            vision_evaluator=proxy_screen_vision_evaluator,
        )

    def _persist_state(self, *, deferred: bool = False) -> None:
        if not self.persist_state:
            return
        self.state_store.save(self.state, deferred=deferred)
        if deferred:
            self._schedule_deferred_storage_flush()
        self._maybe_maintain_storage()

    def build_context_envelope(
        self,
        *,
        processed_version: int = 0,
        now: str | None = None,
        interaction_projection: list[dict] | None = None,
    ):
        return self.context_envelope_compiler.compile(
            facts=self.context_fact_store.query(now=now or _utc_now()),
            processed_version=processed_version,
            now=now or _utc_now(),
            interaction_projection=interaction_projection,
        )

    def ensure_main_hermes_session(self):
        if getattr(self.agent_harness, "durable_memory_engine", None) != "hermes_native":
            return None
        session = self.main_session_manager.ensure_session()
        self.state.mark_state_value("main_session")
        self._persist_state()
        return session

    def _restore_main_session(self, session_id: str) -> bool:
        restore = getattr(self.agent_harness, "restore_main_session", None)
        if not callable(restore):
            return False
        try:
            return bool(restore(session_id))
        except Exception:
            return False

    def _create_main_session(self, generation: int) -> str:
        session_id = f"openhalo-main-g{generation}-{uuid4().hex}"
        create = getattr(self.agent_harness, "create_main_session", None)
        if callable(create):
            create(session_id)
        return session_id

    def _persist_state_deferred(self) -> None:
        try:
            self._persist_state(deferred=True)
        except TypeError as exc:
            if "deferred" not in str(exc):
                raise
            self._persist_state()

    def _schedule_deferred_storage_flush(self) -> None:
        flush = getattr(self.state_store, "flush", None)
        if flush is None or self._deferred_storage_flush_handle is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._deferred_storage_flush_handle = loop.call_later(
            0.25,
            self._flush_deferred_storage,
        )

    def _flush_deferred_storage(self) -> None:
        self._deferred_storage_flush_handle = None
        flush = getattr(self.state_store, "flush", None)
        if flush is not None:
            flush()

    def _close_state_store(self) -> None:
        handle = self._deferred_storage_flush_handle
        if handle is not None:
            handle.cancel()
            self._deferred_storage_flush_handle = None
        close = getattr(self.state_store, "close", None)
        if close is not None:
            close()

    def _maybe_maintain_storage(self) -> None:
        maintain = getattr(self.state_store, "enforce_retention", None)
        if maintain is None:
            return
        now = time.monotonic()
        if now - self._last_storage_maintenance_at < 6 * 60 * 60:
            return
        maintain(now=_utc_now())
        self._last_storage_maintenance_at = now

    def reconcile_interaction_health(self, *, current_time: str | None = None) -> list[dict]:
        """Reconcile persistent interaction health without provider polling."""

        observed_at = current_time or _utc_now()
        changed = self.interaction_pool.reconcile_health(
            current_time=observed_at,
            online_device_ids=set(self.online_device_ids),
        )
        if not changed:
            return []
        updates = []
        for interaction in changed:
            health = dict(interaction.health)
            update = {
                "interaction_id": interaction.interaction_id,
                "process_health": health,
                "observed_at": observed_at,
            }
            self.state.record_event(
                {
                    "type": "process_health_changed",
                    **update,
                }
            )
            updates.append(update)
        self._persist_state()
        return updates

    def _next_interaction_id(self) -> str:
        return self.state.allocate_interaction_id()

    def _next_action_request_id(self) -> str:
        return f"action-{next(self._action_request_counter)}"

    def _build_camera_media_provider_configure_reply(
        self,
        *,
        device_id: str,
    ) -> dict | None:
        """Return the fixed direct-media profile for a newly ready Camera Edge.

        This is deliberately a connection-time control action rather than
        Runtime memory: the Edge keeps the projected provider profile only in
        process memory and must be configured again after it restarts.
        """

        device = self.state.devices.get(device_id, {})
        media_capability = next(
            (
                capability
                for capability in self.state.capability_registry.get(device_id, {}).values()
                if isinstance(capability, dict) and capability.get("model_requirements")
            ),
            None,
        )
        if media_capability is None:
            return None
        # An absent Runtime model configuration is normal for deployments that
        # have no direct-media Edge. Do not turn capability registration into a
        # failure in that case.
        if self.llm_config_path is None:
            return None
        try:
            config = load_runtime_model_config(self.llm_config_path)
            reply = build_configured_camera_media_provider_request(
                target_device_id=device_id,
                request_id=self._next_action_request_id(),
                config=config,
            )
        except (OSError, ValueError, KeyError):
            return None
        self._record_trace(
            "GATEWAY",
            "built direct media provider configure action",
            device_id=device_id,
        )
        return {
            "api_version": "edge.runtime.v2",
            "type": "device_configuration",
            "device_id": device_id,
            "request_id": reply.get("request_id"),
            "configuration": {
                "kind": "media_provider",
                **reply["action"]["payload"],
            },
        }

    def _next_interaction_turn_id(self) -> str:
        return self.state.allocate_interaction_turn_id()

    def _configure_interaction_continuation_for_action(
        self,
        *,
        interaction_id: str,
        target_device_id: str,
        action_capability: str,
    ) -> None:
        metadata = self.state.capability_registry.get(target_device_id, {}).get(
            action_capability,
            {},
        )
        contract = metadata.get("process_contract")
        if isinstance(contract, dict):
            self.interaction_pool.configure_continuation(
                interaction_id,
                contract,
                target_device_id=target_device_id,
            )

    def _configure_interaction_continuation_from_proposal(
        self,
        *,
        interaction_id: str,
        proposal: dict,
        target_device_id: str | None,
    ) -> None:
        metadata = proposal.get("metadata", {}) if isinstance(proposal, dict) else {}
        intent = metadata.get("continuation_intent")
        if not isinstance(intent, dict) or not intent:
            return
        self.interaction_pool.configure_continuation(
            interaction_id,
            intent,
            target_device_id=target_device_id,
        )

    def _register_interaction_for_frame(self, frame: dict):
        payload = frame.get("payload", {})
        origin = (
            "agent_initiative"
            if payload.get("agent_initiative") is not None
            else "user_event"
        )
        is_explicit_user_intent = origin == "user_event"
        source_event_id = frame.get("event_id")
        provenance_token = source_event_id or f"ingress-{uuid4().hex}"
        causal_scope = {
            "key": (
                f"{origin}:{frame['device_id']}:"
                f"{frame['capability']}:{provenance_token}"
            ),
            "source_device_id": frame["device_id"],
            "source_capability": frame["capability"],
            "source_event_id": source_event_id,
        }
        trigger = {
            "frame_type": frame["type"],
            "source_event_id": source_event_id,
            "observed_at": payload.get("observed_at")
            or frame.get("observed_at"),
        }
        if origin == "agent_initiative":
            trigger["initiative_reason"] = payload["agent_initiative"].get("reason")
        registration = self.interaction_pool.register(
            origin=origin,
            causal_scope=causal_scope,
            trigger=trigger,
            participant_device_ids=[frame["device_id"]],
            source_device_id=frame["device_id"],
            initiator_kind=(
                "explicit_user_intent"
                if is_explicit_user_intent
                else "agent_initiative"
            ),
            requesting_device_id=(
                frame["device_id"] if is_explicit_user_intent else None
            ),
            outcome_delivery_required=is_explicit_user_intent,
        )
        if registration.created:
            self.state.update_interaction(
                registration.interaction.interaction_id,
                outcome_receipt_entries=append_receipt_entry(
                    [],
                    kind="request_received",
                    occurred_at=_utc_now(),
                ),
            )
        return registration

    def _interaction_payload(self, interaction_id: str) -> dict | None:
        return next(
            (
                interaction
                for interaction in self.state.interactions
                if interaction.get("interaction_id") == interaction_id
            ),
            None,
        )

    def _intervention_for_turn(
        self,
        interaction_id: str,
        interaction_turn_id: str,
        request_id: str | None = None,
    ) -> dict | None:
        return next(
            (
                intervention
                for intervention in reversed(self.state.interventions)
                if intervention.get("interaction_id") == interaction_id
                and intervention.get("interaction_turn_id") == interaction_turn_id
                and (
                    request_id is None
                    or intervention.get("request_id") == request_id
                )
            ),
            None,
        )

    def _latest_intervention_for_interaction(self, interaction_id: str) -> dict | None:
        return next(
            (
                intervention
                for intervention in reversed(self.state.interventions)
                if intervention.get("interaction_id") == interaction_id
            ),
            None,
        )

    def _update_intervention_for_turn(
        self,
        interaction_id: str,
        interaction_turn_id: str,
        lookup_request_id: str | None = None,
        **changes,
    ) -> dict | None:
        intervention = self._intervention_for_turn(
            interaction_id,
            interaction_turn_id,
            request_id=lookup_request_id,
        )
        if intervention is not None:
            intervention.update(changes)
        return intervention

    def _update_intervention_for_action(
        self,
        interaction_id: str,
        interaction_turn_id: str,
        action_id: str,
        **changes,
    ) -> dict | None:
        intervention = next(
            (
                intervention
                for intervention in reversed(self.state.interventions)
                if intervention.get("interaction_id") == interaction_id
                and intervention.get("interaction_turn_id") == interaction_turn_id
                and intervention.get("action_id") == action_id
            ),
            None,
        )
        if intervention is not None:
            intervention.update(changes)
        return intervention

    def _normalize_action_result_correlation(self, frame: dict) -> dict:
        return frame

    @staticmethod
    def _action_result_capability_matches_intervention(
        frame: dict,
        intervention: dict,
    ) -> bool:
        expected_capability = intervention.get(
            "requested_action_capability",
            intervention.get("action_capability"),
        )
        return frame.get("result", {}).get("capability") == expected_capability

    def _can_record_action_result(self, frame: dict) -> bool:
        interaction_id = frame.get("interaction_id")
        if interaction_id is None:
            return True
        interaction_turn_id = frame.get("interaction_turn_id")
        request_id = frame.get("request_id")
        if not interaction_turn_id or not request_id:
            return False
        if (
            self.interaction_pool.get_for_action_result(
                interaction_id,
                interaction_turn_id,
                request_id,
            )
            is None
        ):
            return False
        intervention = self._intervention_for_turn(
            interaction_id,
            interaction_turn_id,
            request_id=request_id,
        )
        return (
            intervention is not None
            and intervention.get("target_device_id") == frame.get("device_id")
            and self._action_result_capability_matches_intervention(
                frame,
                intervention,
            )
        )

    def _record_action_result_frame(self, frame: dict) -> dict:
        result = {
            **frame["result"],
            "device_id": frame.get("device_id"),
            "request_id": frame.get("request_id"),
            "interaction_id": frame.get("interaction_id"),
            "interaction_turn_id": frame.get("interaction_turn_id"),
        }
        intervention = self._intervention_for_turn(
            frame.get("interaction_id"),
            frame.get("interaction_turn_id"),
            request_id=frame.get("request_id"),
        )
        action_intent = (
            (intervention or {})
            .get("proposal", {})
            .get("metadata", {})
            .get("harness_validation", {})
            .get("action_intent")
        )
        if action_intent is not None:
            result["action_envelope"] = {
                "action_id": action_intent.get("action_id"),
                "executor_kind": action_intent.get("executor_kind"),
                "capability": action_intent.get("capability"),
                "status": result.get("status"),
                "details": result.get("details", {}),
                "governance": action_intent.get("governance"),
                "provenance": action_intent.get("provenance", {}),
            }
        self.state.record_action_result(result)
        if (
            result.get("capability") == "proxy.screen.profile.configure"
            and result.get("status") == "ok"
            and isinstance(result.get("details"), dict)
        ):
            details = result["details"]
            required = {
                "target_id",
                "surface_id",
                "profile_id",
                "revision",
                "features",
                "expires_at",
                "visual_action_policy",
            }
            if required.issubset(details):
                self.state.record_proxy_screen_profile(
                    frame["device_id"],
                    {key: details[key] for key in required},
                )
        interaction_id = frame.get("interaction_id")
        if isinstance(interaction_id, str) and interaction_id:
            self._append_outcome_receipt_entry(
                interaction_id,
                kind="confirmed"
                if result.get("status") == "ok"
                else "failed",
                device_id=frame.get("device_id"),
            )
        return frame

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
            delivered_body = result.get("details", {}).get("body")
            if isinstance(delivered_body, str) and delivered_body.strip():
                return delivered_body.strip()
        proposal_type = proposal.get("proposal_type")
        if proposal_type == "action":
            return proposal.get("action_payload", {}).get("body", "")
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
        terminal_reason: str | None = None,
    ) -> dict:
        return self.state.update_interaction(
            interaction_id,
            status="completed",
            summary=summary,
            completion={
                "visibility": visibility,
                "summary": summary,
                "result_status": result_status,
                "terminal_reason": terminal_reason,
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
        delivered_body = result.get("details", {}).get("body")

        if proposal_type == "no_intervention":
            return proposal.get("visibility_intent", "silent")

        if (
            proposal_type == "action"
            and capability == "notification.show"
            and delivered_body
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
        requesting_device_id = interaction.get("requesting_device_id")
        if not interaction.get("outcome_delivery_required") or not requesting_device_id:
            return []
        visibility = interaction.get("completion", {}).get("visibility", "visible")
        summary = interaction.get("completion", {}).get("summary", "")
        interaction_payload = {
            "interaction_id": interaction["interaction_id"],
            "status": interaction["status"],
            "summary": summary,
            "visibility": visibility,
            "completion": interaction.get("completion", {}),
        }
        receipt = self._project_outcome_receipt(interaction)
        if receipt is not None:
            interaction_payload["outcome_receipt"] = receipt
        replies = [
            build_interaction_update(
                requesting_device_id,
                interaction_payload,
                trace_recorder=self.trace_recorder,
                correlation=correlation,
            )
        ]
        return replies

    def _project_outcome_receipt(self, interaction: dict) -> dict | None:
        names = {
            device_id: record.get("display_name", device_id)
            for device_id, record in self.state.device_registry.items()
        }
        return project_outcome_receipt(
            entries=interaction.get("outcome_receipt_entries"),
            state=interaction.get("status"),
            participant_device_ids=interaction.get("participant_device_ids", []),
            device_names=names,
        )

    def _append_outcome_receipt_entry(
        self,
        interaction_id: str,
        *,
        kind: str,
        device_id: str | None = None,
    ) -> None:
        interaction = self._interaction_payload(interaction_id)
        if interaction is None:
            return
        entries = list(interaction.get("outcome_receipt_entries", []))
        if any(
            entry.get("kind") == kind and entry.get("device_id") == device_id
            for entry in entries
            if isinstance(entry, dict)
        ):
            return
        self.state.update_interaction(
            interaction_id,
            outcome_receipt_entries=append_receipt_entry(
                entries,
                kind=kind,
                occurred_at=_utc_now(),
                device_id=device_id,
            ),
        )

    def _progress_recipients_for_interaction(self, interaction: dict) -> list[str]:
        """Return authorized, progress-capable Edge participants only."""

        if not interaction.get("outcome_delivery_required"):
            return []
        candidates = [interaction.get("requesting_device_id")]
        candidates.extend(interaction.get("display_participant_device_ids", []))
        recipients = []
        for device_id in dict.fromkeys(candidates):
            if not isinstance(device_id, str) or not device_id:
                continue
            capabilities = self.state.devices.get(device_id, {}).get(
                "capabilities", set()
            )
            if (
                device_id in self.online_device_ids
                and "interaction.progress" in capabilities
            ):
                recipients.append(device_id)
        return recipients

    def emit_interaction_progress(
        self,
        *,
        interaction_id: str,
        interaction_turn_id: str | None,
        phase: str,
        state: str,
        presentation_hint: str,
        correlation: dict | None = None,
        occurred_at: str | None = None,
    ) -> list[dict]:
        """Project one safe lifecycle state without affecting work execution."""

        interaction = self._interaction_payload(interaction_id)
        if interaction is None:
            return []
        self.display_lifecycle.restore_sequence(
            interaction_id,
            interaction.get("display_progress_sequence"),
        )
        progress = self.display_lifecycle.advance(
            interaction_id=interaction_id,
            interaction_turn_id=interaction_turn_id,
            phase=phase,
            state=state,
            occurred_at=occurred_at or _utc_now(),
            presentation_hint=presentation_hint,
        )
        if phase in {"deliberating", "researching", "planning"}:
            self._append_outcome_receipt_entry(
                interaction_id,
                kind="started",
            )
        self.state.update_interaction(
            interaction_id,
            display_progress_sequence=progress["sequence"],
        )
        if phase in {"deliberating", "researching", "planning"}:
            self._persist_state_deferred()
        else:
            self._persist_state()
        self.runtime_console_presenter.present(progress)
        recipients = self._progress_recipients_for_interaction(interaction)
        self._record_diagnostic(
            module="Display Lifecycle",
            operation="project_interaction_progress",
            phase="output",
            correlation={
                **(correlation or {}),
                "interaction_id": interaction_id,
                "interaction_turn_id": interaction_turn_id,
            },
            input_payload={
                "phase": phase,
                "state": state,
                "recipient_count": len(recipients),
            },
            output_payload={
                "progress": progress,
                "recipients": recipients,
            },
            summary="Projected safe interaction progress for authorized Edges.",
        )
        replies = [
            build_interaction_progress(
                target_device_id=device_id,
                progress=progress,
                correlation=correlation,
            )
            for device_id in recipients
        ]
        if phase in _STREAMED_PROGRESS_PHASES:
            self.stream_outbound_replies(replies)
        return replies

    def stream_outbound_replies(self, replies: list[dict]) -> None:
        """Queue ordered runtime output for immediate websocket dispatch when active."""

        emitter = _streamed_reply_emitter.get()
        if emitter is not None and replies:
            emitter(replies)

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
        initiative_id: str | None = None,
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
            "event_id": (
                initiative_id
                or initiative_request.get("initiative_id")
                or f"initiative-{uuid4().hex}"
            ),
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
        initiative_id: str | None = None,
    ) -> list[dict]:
        replies = self.trigger_agent_initiative(
            source_device_id=source_device_id,
            initiative_request=initiative_request,
            observed_at=observed_at,
            initiative_id=initiative_id,
        )
        for reply in replies:
            if reply["type"] != "action_request":
                continue
            target_device_id = reply["device_id"]
            target_websocket = self.live_connections.get(target_device_id)
            if target_websocket is not None:
                await self._send_frame(target_websocket, reply)
        return replies

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

    def _resolve_observation_reentry(self, frame: dict) -> tuple[dict, dict] | None:
        payload = frame.get("payload", {})
        reentry_parent = frame.get("reentry_parent") or payload.get(
            "reentry_parent"
        )
        if isinstance(reentry_parent, dict):
            interaction_id = reentry_parent.get("interaction_id")
            interaction_turn_id = reentry_parent.get("interaction_turn_id")
            request_id = reentry_parent.get("request_id")
            if not interaction_id or not interaction_turn_id or not request_id:
                return None
            if (
                self.interaction_pool.get_for_action_result(
                    interaction_id,
                    interaction_turn_id,
                    request_id,
                )
                is None
            ):
                return None
            interaction = self._interaction_payload(interaction_id)
            intervention = self._intervention_for_turn(
                interaction_id,
                interaction_turn_id,
                request_id=request_id,
            )
            if (
                interaction is None
                or intervention is None
                or intervention.get("target_device_id") != frame.get("device_id")
            ):
                return None
            return interaction, intervention

        parent_event_id = frame.get("parent_event_id") or payload.get(
            "parent_event_id"
        )
        if not parent_event_id:
            return None
        interactions = [
            interaction
            for interaction in self.state.interactions
            if interaction.get("status") != "completed"
            and interaction.get("causal_scope", {}).get("source_event_id")
            == parent_event_id
        ]
        if len(interactions) != 1:
            return None
        interaction = interactions[0]
        pool_interaction = self.interaction_pool.get(interaction["interaction_id"])
        if pool_interaction is None:
            return None
        pending_turn_ids = {
            turn.interaction_turn_id
            for turn in pool_interaction.turns
            if turn.action_status == "pending"
        }
        interventions = [
            intervention
            for intervention in self.state.interventions
            if intervention.get("interaction_id") == interaction["interaction_id"]
            and intervention.get("interaction_turn_id") in pending_turn_ids
            and intervention.get("target_device_id") == frame.get("device_id")
        ]
        if len(interventions) != 1:
            return None
        return interaction, interventions[0]

    def _observation_reentry_is_processed(
        self,
        interaction: dict,
        frame: dict,
    ) -> bool:
        event_id = frame.get("event_id")
        if not event_id:
            return True
        return event_id in interaction.get("observation_reentry_event_ids", [])

    def _record_observation_reentry(self, interaction_id: str, frame: dict) -> None:
        event_id = frame.get("event_id")
        if not event_id:
            return
        interaction = self._interaction_payload(interaction_id)
        if interaction is None:
            return
        event_ids = list(interaction.get("observation_reentry_event_ids", []))
        if event_id not in event_ids:
            event_ids.append(event_id)
        self.state.update_interaction(
            interaction_id,
            observation_reentry_event_ids=event_ids[-20:],
        )

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

    def _handle_frames_sync(
        self,
        frames: list[dict],
    ) -> list[dict]:
        replies = []
        for raw_frame in frames:
            frame = self._normalize_public_frame(validate_frame(raw_frame))
            if frame["type"] == "connect":
                self._record_trace(
                    "GATEWAY",
                    "received connect",
                    device_id=frame["device"]["device_id"],
                )
                replies.append(self._begin_authentication(frame))
            elif frame["type"] == "auth_proof":
                reply, _ = self._complete_authentication(frame)
                replies.append(reply)
            elif frame["type"] == "capability_announce":
                self._record_trace(
                    "GATEWAY",
                    "received capability_announce",
                    device_id=frame["device_id"],
                )
                if frame["device_id"] not in self.state.devices:
                    replies.append(
                        self._build_public_error(
                            code="unknown_device",
                            message=(
                                "Device must connect successfully before "
                                "announcing capabilities."
                            ),
                            device_id=frame["device_id"],
                        )
                    )
                    continue
                try:
                    for capability in frame["capabilities"]:
                        validate_capability_registration(capability)
                except ValueError as exc:
                    replies.append(
                        self._build_public_error(
                            code="invalid_capability_contract",
                            message=str(exc),
                            device_id=frame["device_id"],
                        )
                    )
                    continue
                self.state.replace_capabilities(
                    frame["device_id"],
                    frame["capabilities"],
                )
                self._persist_state()
                provider_configure_reply = (
                    self._build_camera_media_provider_configure_reply(
                        device_id=frame["device_id"],
                    )
                )
                if provider_configure_reply is not None:
                    replies.append(provider_configure_reply)
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
                self.state.record_event(frame)
                self.state.record_observations(
                    self._extract_runtime_observations(frame)
                )
                self._materialize_context_facts(frame)
                update_mobile_liveness_after_observations(
                    self.state,
                    device_id=frame["device_id"],
                    online_device_ids=set(self.online_device_ids),
                    current_time=self._observation_timestamp(frame),
                )
                self._record_trace(
                    "STATE",
                    "recorded event_push",
                    capability=frame["capability"],
                )
                self._persist_state_deferred()
                replies.extend(self._build_event_replies(frame))
            elif frame["type"] == "action_result":
                frame = self.action_result_attachments.sanitize(frame)
                recordable = self._can_record_action_result(frame)
                if recordable:
                    frame = self._record_action_result_frame(frame)
                self._record_trace(
                    "GATEWAY",
                    "received action_result",
                    device_id=frame["device_id"],
                )
                if recordable:
                    self._record_trace(
                        "STATE",
                        "recorded action_result",
                        status=frame["result"]["status"],
                    )
                    self._persist_state()
                replies.extend(self._build_action_result_replies(frame))
            elif frame["type"] == "device_configuration_result":
                self._record_trace(
                    "GATEWAY",
                    "received device configuration result",
                    device_id=frame["device_id"],
                    kind=frame["kind"],
                    status=frame["status"],
                )
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
        parent_event_id = frame.get("parent_event_id") or frame["payload"].get(
            "parent_event_id"
        )
        reentry_parent = frame.get("reentry_parent") or frame["payload"].get(
            "reentry_parent"
        )
        return [
            RuntimeObservation(
                name=observation_payload["name"],
                value=observation_payload["value"],
                source_device_id=frame["device_id"],
                source_capability=frame["capability"],
                source_event_id=event_id,
                observed_at=observation_payload["observed_at"],
                confidence=observation_payload["confidence"],
                parent_event_id=parent_event_id,
                reentry_parent=dict(reentry_parent)
                if isinstance(reentry_parent, dict)
                else None,
                process_id=observation_payload.get("process_id"),
                evidence_ref=observation_payload.get("evidence_ref"),
                coverage=dict(observation_payload["coverage"])
                if isinstance(observation_payload.get("coverage"), dict)
                else None,
                context_disposition=observation_payload.get(
                    "context_disposition", "full"
                ),
            )
            for observation_payload in observations
        ]

    def _materialize_context_facts(self, frame: dict) -> None:
        device_id = frame["device_id"]
        capability = frame["capability"]
        registrations = self.state.observation_registry.get(device_id, {}).get(
            capability,
            {},
        )
        changed = []
        for observation in self._extract_runtime_observations(frame):
            registration = registrations.get(observation.name, {})
            if self.context_fact_store.materialize(
                observation,
                freshness_seconds=int(registration.get("freshness_seconds", 120)),
                schema_version=registration.get("schema_version"),
                semantic_contract=registration.get("semantic_contract"),
            ):
                fact = next(
                    item for item in self.context_fact_store.all_facts()
                    if item.fact_id == f"{observation.source_device_id}/{observation.name}"
                )
                payload = fact.to_dict()
                self.state.context_facts[fact.fact_id] = payload
                changed.append(payload)
        upsert = getattr(self.state_store, "upsert_context_fact", None)
        if upsert is not None:
            for fact in changed:
                upsert(fact)

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
        for observation in observations:
            observation_name = observation.get("name")
            disposition = observation.get("context_disposition", "full")
            if disposition not in {"full", "structural", "unavailable", "withheld"}:
                return self._build_observation_error(
                    code="invalid_context_disposition",
                    message="Observation context_disposition is unsupported.",
                    device_id=device_id,
                    capability=capability,
                    observation=observation_name,
                )
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
    def _build_public_error(
        code: str,
        message: str,
        device_id: str | None = None,
        capability: str | None = None,
        observation: str | None = None,
    ) -> dict:
        payload = {
            "type": "error",
            "code": code,
            "message": message,
        }
        if device_id is not None:
            payload["device_id"] = device_id
        if capability is not None:
            payload["capability"] = capability
        if observation is not None:
            payload["observation"] = observation
        return with_api_version(payload)

    @staticmethod
    def _build_observation_error(
        code: str,
        message: str,
        device_id: str,
        capability: str,
        observation: str | None,
    ) -> dict:
        return RuntimeGateway._build_public_error(
            code=code,
            message=message,
            device_id=device_id,
            capability=capability,
            observation=observation,
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

    @staticmethod
    def _interaction_id_for_frame(frame: dict) -> str | None:
        interaction_id = frame.get("interaction_id")
        if isinstance(interaction_id, str) and interaction_id:
            return interaction_id
        payload = frame.get("payload")
        if not isinstance(payload, dict):
            return None
        reentry_parent = frame.get("reentry_parent") or payload.get(
            "reentry_parent"
        )
        if isinstance(reentry_parent, dict):
            interaction_id = reentry_parent.get("interaction_id")
            if isinstance(interaction_id, str) and interaction_id:
                return interaction_id
        interaction_ids = {
            observation.get("value", {}).get("interaction_id")
            for observation in payload.get("observations", [])
            if isinstance(observation, dict)
            and isinstance(observation.get("value"), dict)
            and isinstance(observation["value"].get("interaction_id"), str)
            and observation["value"]["interaction_id"]
        }
        if len(interaction_ids) == 1:
            return interaction_ids.pop()
        return None

    @asynccontextmanager
    async def _interaction_processing_slot(self, frame: dict):
        interaction_id = self._interaction_id_for_frame(frame)
        if interaction_id is None:
            yield
            return
        lock, references = self._interaction_processing_locks.get(
            interaction_id,
            (asyncio.Lock(), 0),
        )
        self._interaction_processing_locks[interaction_id] = (lock, references + 1)
        try:
            async with lock:
                yield
        finally:
            _, references = self._interaction_processing_locks[interaction_id]
            if references == 1:
                del self._interaction_processing_locks[interaction_id]
            else:
                self._interaction_processing_locks[interaction_id] = (
                    lock,
                    references - 1,
                )

    async def _handle_websocket_frame(
        self,
        frame: dict,
        progress_sink=None,
    ) -> list[dict]:
        async with self._interaction_processing_slot(frame):
            return await self._handle_websocket_frame_unlocked(
                frame,
                progress_sink=progress_sink,
            )

    async def _handle_websocket_frame_unlocked(
        self,
        frame: dict,
        progress_sink=None,
    ) -> list[dict]:
        if progress_sink is None:
            return await asyncio.to_thread(
                self._handle_frames_sync,
                [frame],
            )

        loop = asyncio.get_running_loop()
        streamed_reply_queue: asyncio.Queue[list[dict]] = asyncio.Queue()
        streamed_reply_ids: set[int] = set()
        streamed_reply_batches: list[list[dict]] = []
        dispatched_reply_ids: set[int] = set()

        def enqueue_streamed_replies(replies: list[dict]) -> None:
            streamed_reply_ids.update(id(reply) for reply in replies)
            streamed_reply_batches.append(replies)
            loop.call_soon_threadsafe(streamed_reply_queue.put_nowait, replies)

        async def dispatch_streamed_replies(replies: list[dict]) -> None:
            unsent_replies = [
                reply for reply in replies if id(reply) not in dispatched_reply_ids
            ]
            if not unsent_replies:
                return
            dispatched_reply_ids.update(id(reply) for reply in unsent_replies)
            await progress_sink(unsent_replies)

        emitter_token = _streamed_reply_emitter.set(enqueue_streamed_replies)
        worker_task = asyncio.create_task(
            asyncio.to_thread(
                self._handle_frames_sync,
                [frame],
            )
        )
        progress_task = asyncio.create_task(streamed_reply_queue.get())
        try:
            while True:
                completed, _ = await asyncio.wait(
                    {worker_task, progress_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if progress_task in completed:
                    await dispatch_streamed_replies(progress_task.result())
                    progress_task = asyncio.create_task(streamed_reply_queue.get())
                if worker_task not in completed:
                    continue

                if progress_task.done():
                    await dispatch_streamed_replies(progress_task.result())
                for streamed_replies in streamed_reply_batches:
                    await dispatch_streamed_replies(streamed_replies)
                replies = await worker_task
                return [
                    reply
                    for reply in replies
                    if id(reply) not in streamed_reply_ids
                ]
        finally:
            _streamed_reply_emitter.reset(emitter_token)
            if not progress_task.done():
                progress_task.cancel()
                with suppress(asyncio.CancelledError):
                    await progress_task

    async def _send_frame(self, websocket, frame: dict) -> None:
        websocket_key = id(websocket)
        send_lock = self._websocket_send_locks.setdefault(
            websocket_key,
            asyncio.Lock(),
        )
        async with send_lock:
            await websocket.send(json.dumps(frame))

    @staticmethod
    def _build_target_missing_action_result(reply: dict) -> dict:
        action = reply.get("action", {})
        target_device_id = reply.get("device_id")
        result = {
            "status": "failed",
            "reason": "target_missing",
            "capability": action.get("capability"),
            "details": {
                "target_device_id": target_device_id,
                "message": "Target device is not connected.",
            },
        }
        failure = {
            "type": "action_result",
            "device_id": target_device_id,
            "request_id": reply.get("request_id"),
            "interaction_id": reply.get("interaction_id"),
            "interaction_turn_id": reply.get("interaction_turn_id"),
            "result": result,
        }
        for key in (
            "trace_id",
            "session_id",
            "turn_id",
            "event_id",
            "parent_event_id",
        ):
            if reply.get(key) is not None:
                failure[key] = reply[key]
        return with_api_version(failure)

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

    def _current_source_websocket(self, source_device_id: str, websocket):
        if source_device_id is None:
            return websocket
        return self.live_connections.get(source_device_id) or websocket

    async def _dispatch_websocket_replies(self, source_device_id: str, websocket, replies: list[dict]) -> None:
        source_websocket = self._current_source_websocket(source_device_id, websocket)
        for reply in replies:
            target_device_id = reply.get("device_id")
            if (
                reply["type"]
                in {
                    "action_request",
                    "interaction_progress",
                    "interaction_update",
                    "understanding_update",
                }
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
                        self._release_closed_websocket_session(
                            target_device_id,
                            target_websocket,
                        )
                    continue
                self._record_dispatch_diagnostic(
                    reply=reply,
                    source_device_id=source_device_id,
                    target_connection_found=False,
                    dispatched_to=source_device_id,
                    send_status="target_missing",
                )
                if reply["type"] == "action_request":
                    failed_result = self._build_target_missing_action_result(reply)
                    await self._send_frame(
                        source_websocket,
                        failed_result,
                    )
                    if self._can_record_action_result(failed_result):
                        failed_result = self._record_action_result_frame(failed_result)
                    self._persist_state()
                    await self._dispatch_websocket_replies(
                        source_device_id,
                        source_websocket,
                        self._build_action_result_replies(failed_result),
                    )
                    continue
            try:
                await self._send_frame(source_websocket, reply)
                if not (
                    reply["type"]
                    in {
                        "action_request",
                        "interaction_progress",
                        "interaction_update",
                        "understanding_update",
                    }
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
                self._release_closed_websocket_session(
                    source_device_id,
                    source_websocket,
                )

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
                    "interaction_turn_id",
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

    def _begin_authentication(self, frame: dict) -> dict:
        """Validate a pre-auth connect and issue one P-256 challenge."""

        device = frame.get("device")
        if not isinstance(device, dict):
            return self._build_public_error(
                code="invalid_connect",
                message="connect requires a device object.",
            )
        device_id = device.get("device_id")
        device_type = device.get("device_type")
        session_id = frame.get("session_id")
        audience = frame.get("audience")
        if not all(
            isinstance(value, str) and value
            for value in (device_id, device_type, session_id, audience)
        ):
            return self._build_public_error(
                code="invalid_connect",
                message="connect requires device_id, device_type, session_id, and audience.",
            )
        try:
            validate_runtime_endpoint(audience)
        except ValueError:
            return self._build_public_error(
                code="invalid_connect",
                message="connect requires a complete ws:// or wss:// audience.",
                device_id=device_id,
            )
        if session_id in self.pending_authentications:
            return self._build_public_error(
                code="session_in_use",
                message="A pre-authentication session is already active.",
                device_id=device_id,
            )

        auth = frame.get("auth")
        pairing_code = None
        display_name = None
        if auth is None:
            if self.pairing_store is None:
                return self._build_public_error(
                    code="pairing_required",
                    message="This device must be paired before reconnecting.",
                    device_id=device_id,
                )
            record = self.pairing_store.get_active_device(device_id)
            if record is None:
                return self._build_public_error(
                    code="pairing_required",
                    message="This device must be paired before reconnecting.",
                    device_id=device_id,
                )
            if record.get("audience") != audience:
                return self._build_public_error(
                    code="audience_mismatch",
                    message="Device is paired for a different Runtime audience.",
                    device_id=device_id,
                )
            display_name = record.get("display_name")
            try:
                public_key_der = decode_base64url(record["public_key"])
            except (KeyError, ValueError):
                return self._build_public_error(
                    code="invalid_device_identity",
                    message="Stored device identity is invalid.",
                    device_id=device_id,
                )
        elif not isinstance(auth, dict) or auth.get("kind") != "pairing":
            return self._build_public_error(
                code="unsupported_auth_kind",
                message="Bearer and shared-token authentication are not supported.",
                device_id=device_id,
            )
        else:
            if self.pairing_store is None:
                return self._build_public_error(
                    code="pairing_unavailable",
                    message="Runtime device pairing is not configured.",
                    device_id=device_id,
                )
            pairing_code = auth.get("pairing_code")
            public_key = auth.get("public_key")
            display_name = auth.get("display_name")
            if not all(
                isinstance(value, str) and value
                for value in (pairing_code, public_key, display_name)
            ):
                return self._build_public_error(
                    code="invalid_pairing_request",
                    message="Pairing requires a code, public key, and device name.",
                    device_id=device_id,
                )
            try:
                public_key_der = decode_base64url(public_key)
            except ValueError:
                return self._build_public_error(
                    code="invalid_device_identity",
                    message="Device public key is not valid base64url.",
                    device_id=device_id,
                )

        if not is_p256_public_key(public_key_der):
            return self._build_public_error(
                code="invalid_device_identity",
                message="Device public key must be a P-256 DER SPKI value.",
                device_id=device_id,
            )
        expires_at = (datetime.now(UTC) + timedelta(seconds=60)).isoformat().replace(
            "+00:00", "Z"
        )
        pending = PendingAuthentication(
            device_id=device_id,
            device_type=device_type,
            device_role=device.get("role"),
            device_profile=device.get("profile"),
            audience=audience,
            session_id=session_id,
            challenge_id=str(uuid4()),
            nonce=encode_base64url(secrets.token_bytes(32)),
            expires_at=expires_at,
            public_key_der=public_key_der,
            pairing_code=pairing_code,
            display_name=display_name,
        )
        self.pending_authentications[session_id] = pending
        return with_api_version(
            {
                "type": "auth_challenge",
                "device_id": device_id,
                "session_id": session_id,
                "audience": audience,
                "challenge": {
                    "version": 1,
                    "challenge_id": pending.challenge_id,
                    "nonce": pending.nonce,
                    "expires_at": pending.expires_at,
                },
            }
        )

    def _complete_authentication(self, frame: dict) -> tuple[dict, str | None]:
        """Verify a one-time proof, then register the authenticated device."""

        session_id = frame.get("session_id")
        if not isinstance(session_id, str):
            return (
                self._build_public_error(
                    code="invalid_auth_proof",
                    message="auth_proof requires session_id.",
                    device_id=frame.get("device_id"),
                ),
                None,
            )
        pending = self.pending_authentications.pop(session_id, None)
        if pending is None:
            return (
                self._build_public_error(
                    code="unknown_challenge",
                    message="Authentication challenge is unknown or already used.",
                    device_id=frame.get("device_id"),
                ),
                None,
            )
        if (
            frame.get("device_id") != pending.device_id
            or frame.get("audience") != pending.audience
            or frame.get("challenge_id") != pending.challenge_id
        ):
            return (
                self._build_public_error(
                    code="invalid_auth_proof",
                    message="Authentication proof does not match its challenge.",
                    device_id=pending.device_id,
                ),
                None,
            )
        try:
            signature = decode_base64url(frame.get("signature"))
        except ValueError:
            return (
                self._build_public_error(
                    code="invalid_auth_proof",
                    message="Authentication proof signature is invalid.",
                    device_id=pending.device_id,
                ),
                None,
            )
        if is_expired(pending.expires_at, now=datetime.now(UTC)) or not verify_challenge_signature(
            pending.public_key_der,
            build_challenge_payload(
                audience=pending.audience,
                device_id=pending.device_id,
                session_id=pending.session_id,
                challenge_id=pending.challenge_id,
                nonce=pending.nonce,
                expires_at=pending.expires_at,
            ),
            signature,
        ):
            return (
                self._build_public_error(
                    code="invalid_auth_proof",
                    message="Authentication proof was not accepted.",
                    device_id=pending.device_id,
                ),
                None,
            )
        if pending.pairing_code is not None:
            assert self.pairing_store is not None
            try:
                self.pairing_store.claim_pairing_code(
                    pending.pairing_code,
                    device_id=pending.device_id,
                    device_type=pending.device_type,
                    display_name=pending.display_name or pending.device_id,
                    audience=pending.audience,
                    public_key=encode_base64url(pending.public_key_der),
                )
            except PairingError as error:
                return (
                    self._build_public_error(
                        code=error.code,
                        message="Pairing code was not accepted.",
                        device_id=pending.device_id,
                    ),
                    None,
                )
        elif self.pairing_store is None or not self.pairing_store.record_authenticated(
            pending.device_id
        ):
            return (
                self._build_public_error(
                    code="unauthorized",
                    message="Device is no longer authorized.",
                    device_id=pending.device_id,
                ),
                None,
            )

        self._activate_authenticated_device(pending)
        return with_api_version({"type": "connect_ok"}), pending.device_id

    def _activate_authenticated_device(self, pending: PendingAuthentication) -> None:
        self.state.register_device(
            pending.device_id,
            pending.device_type,
            role=pending.device_role,
            profile=pending.device_profile,
            display_name=pending.display_name,
        )
        self._record_trace("STATE", "registered device", device_id=pending.device_id)
        self.online_device_ids.add(pending.device_id)
        record_mobile_session_state(
            self.state,
            pending.device_id,
            status="connected",
            observed_at=_utc_now(),
        )
        self._persist_state()
        self._emit_runtime_event(
            f"Edge connected: {pending.device_id} ({pending.device_type})"
        )

    def _websocket_session_error(
        self,
        frame: dict,
        registered_device_id: str | None,
    ) -> dict | None:
        frame_type = frame.get("type")
        if registered_device_id is None:
            if frame_type != "connect":
                return self._build_public_error(
                    code="not_connected",
                    message=(
                        "A successful connect frame is required before sending "
                        "post-connect frames."
                    ),
                    device_id=frame.get("device_id"),
                )
            return None

        if frame_type == "connect":
            return self._build_public_error(
                code="already_connected",
                message="This WebSocket already has an authenticated device session.",
                device_id=registered_device_id,
            )

        if frame.get("device_id") != registered_device_id:
            return self._build_public_error(
                code="device_mismatch",
                message="Frame device_id does not match the authenticated session.",
                device_id=frame.get("device_id"),
            )
        return None

    def _bind_websocket_connect(self, frame: dict, websocket) -> tuple[str | None, dict | None]:
        if frame.get("type") != "connect":
            return None, None
        device = frame.get("device")
        if not isinstance(device, dict):
            return None, None
        device_id = device.get("device_id")
        if not isinstance(device_id, str):
            return None, None
        availability_error = self._websocket_connect_availability_error(
            device_id,
            websocket,
        )
        if availability_error is not None:
            return None, availability_error
        self.live_connections[device_id] = websocket
        return device_id, None

    def _websocket_connect_availability_error(
        self,
        device_id: str,
        websocket,
    ) -> dict | None:
        existing_websocket = self.live_connections.get(device_id)
        if existing_websocket is not None and existing_websocket is not websocket:
            return self._build_public_error(
                code="device_already_connected",
                message="A live WebSocket session already owns this device_id.",
                device_id=device_id,
            )
        return None

    def _release_closed_websocket_session(self, device_id: str | None, websocket) -> None:
        if device_id is None or not self._release_websocket_session(device_id, websocket):
            return
        record_mobile_session_state(
            self.state,
            device_id,
            status="disconnected",
            observed_at=_utc_now(),
        )
        self._persist_state()

    def _release_websocket_session(self, device_id: str, websocket) -> bool:
        if self.live_connections.get(device_id) is websocket:
            del self.live_connections[device_id]
            self.online_device_ids.discard(device_id)
            return True
        return False

    async def _websocket_handler(self, websocket) -> None:
        registered_device_id = None
        pending_session_id = None
        processing_tasks: set[asyncio.Task] = set()

        def track_processing_task(task: asyncio.Task) -> None:
            processing_tasks.add(task)

            def finish(completed_task: asyncio.Task) -> None:
                processing_tasks.discard(completed_task)
                if not completed_task.cancelled():
                    exc = completed_task.exception()
                    if exc is not None:
                        self._record_diagnostic(
                            module="Gateway",
                            operation="background_frame",
                            phase="output",
                            correlation={},
                            input_payload={"device_id": registered_device_id},
                            output_payload={"error_class": type(exc).__name__},
                            summary="Background WebSocket frame processing failed.",
                        )

            task.add_done_callback(finish)

        async def process_authenticated_frame(
            frame: dict,
            source_device_id: str,
        ) -> None:
            try:
                async def dispatch_streamed_progress(replies: list[dict]) -> None:
                    await self._dispatch_websocket_replies(
                        source_device_id,
                        websocket,
                        replies,
                    )

                replies = await self._handle_websocket_frame(
                    frame,
                    progress_sink=dispatch_streamed_progress,
                )
                await self._dispatch_websocket_replies(
                    source_device_id,
                    websocket,
                    replies,
                )
            except Exception as exc:
                self._record_diagnostic(
                    module="Gateway",
                    operation="background_frame",
                    phase="output",
                    correlation={
                        key: frame[key]
                        for key in (
                            "trace_id",
                            "session_id",
                            "turn_id",
                            "interaction_id",
                            "interaction_turn_id",
                            "request_id",
                        )
                        if frame.get(key) is not None
                    },
                    input_payload={
                        "device_id": source_device_id,
                        "frame_type": frame.get("type"),
                    },
                    output_payload={"error_class": type(exc).__name__},
                    summary="Background WebSocket frame processing failed.",
                )
                await self._dispatch_websocket_replies(
                    source_device_id,
                    websocket,
                    [
                        self._build_public_error(
                            code="frame_processing_failed",
                            message="Runtime could not process this frame.",
                            device_id=source_device_id,
                        )
                    ],
                )

        try:
            async for raw_frame in websocket:
                frame = self._normalize_public_frame(validate_frame(json.loads(raw_frame)))
                if registered_device_id is None:
                    if frame.get("type") == "connect":
                        if pending_session_id is not None:
                            await self._send_frame(
                                websocket,
                                self._build_public_error(
                                    code="authentication_pending",
                                    message="Complete the outstanding authentication challenge first.",
                                ),
                            )
                            continue
                        device = frame.get("device")
                        device_id = device.get("device_id") if isinstance(device, dict) else None
                        if isinstance(device_id, str):
                            availability_error = self._websocket_connect_availability_error(
                                device_id, websocket
                            )
                            if availability_error is not None:
                                await self._send_frame(websocket, availability_error)
                                continue
                        reply = self._begin_authentication(frame)
                        if reply.get("type") == "auth_challenge":
                            pending_session_id = reply["session_id"]
                        await self._send_frame(websocket, reply)
                        continue
                    if frame.get("type") == "auth_proof":
                        if frame.get("session_id") != pending_session_id:
                            await self._send_frame(
                                websocket,
                                self._build_public_error(
                                    code="unknown_challenge",
                                    message="Authentication challenge is unknown or already used.",
                                    device_id=frame.get("device_id"),
                                ),
                            )
                            continue
                        reply, authenticated_device_id = self._complete_authentication(frame)
                        pending_session_id = None
                        if authenticated_device_id is not None:
                            availability_error = self._websocket_connect_availability_error(
                                authenticated_device_id, websocket
                            )
                            if availability_error is not None:
                                self.online_device_ids.discard(authenticated_device_id)
                                await self._send_frame(websocket, availability_error)
                                continue
                            self.live_connections[authenticated_device_id] = websocket
                            registered_device_id = authenticated_device_id
                        await self._send_frame(websocket, reply)
                        continue
                    await self._send_frame(
                        websocket,
                        self._build_public_error(
                            code="not_connected",
                            message="A successful authentication proof is required before sending post-connect frames.",
                            device_id=frame.get("device_id"),
                        ),
                    )
                    continue
                session_error = self._websocket_session_error(
                    frame,
                    registered_device_id,
                )
                if session_error is not None:
                    await self._send_frame(websocket, session_error)
                    continue

                if frame["type"] == "capability_announce":
                    # Capability registration is a short ingress prerequisite.
                    # Complete it before accepting later frames from this Edge;
                    # long-running user/observation processing remains queued
                    # below and is not held by a global frame lock.
                    replies = self._handle_frames_sync([frame])
                    await self._dispatch_websocket_replies(
                        registered_device_id,
                        websocket,
                        replies,
                    )
                    continue

                track_processing_task(
                    asyncio.create_task(
                        process_authenticated_frame(
                            frame,
                            registered_device_id,
                        )
                    )
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
                if self.live_connections.get(registered_device_id) is websocket:
                    self._release_websocket_session(registered_device_id, websocket)
                    record_mobile_session_state(
                        self.state,
                        registered_device_id,
                        status="disconnected",
                        observed_at=_utc_now(),
                    )
                    self._persist_state()
            # Release the device session before waiting for in-flight work.
            # A slow Hermes/Edge interaction must not prevent this device from
            # reconnecting while its already-admitted work finishes.
            if processing_tasks:
                await asyncio.gather(*processing_tasks, return_exceptions=True)
            self._websocket_send_locks.pop(id(websocket), None)

    @asynccontextmanager
    async def run_test_server(self):
        server = await websockets.serve(self._websocket_handler, "127.0.0.1", 0)
        try:
            host, port = server.sockets[0].getsockname()[:2]
            url = f"ws://{host}:{port}"
            if self.audience == "wss://runtime.invalid/openhalo/edge":
                self.audience = url
            yield {"url": url}
        finally:
            server.close()
            await server.wait_closed()
            self._close_state_store()

    @asynccontextmanager
    async def run_server(self, host: str = "127.0.0.1", port: int = 8765):
        server = await websockets.serve(self._websocket_handler, host, port)
        maintenance_task = asyncio.create_task(self._maintenance_loop())
        try:
            bound_host, bound_port = server.sockets[0].getsockname()[:2]
            url = f"ws://{bound_host}:{bound_port}"
            if self.audience == "wss://runtime.invalid/openhalo/edge":
                self.audience = url
            yield {"url": url}
        finally:
            maintenance_task.cancel()
            with suppress(asyncio.CancelledError):
                await maintenance_task
            server.close()
            await server.wait_closed()
            self._close_state_store()

    async def _maintenance_loop(self) -> None:
        while True:
            updates = self.reconcile_interaction_health()
            for update in updates:
                replies = self.orchestrator.handle_process_health_update(update)
                if not replies:
                    continue
                interaction = self.interaction_pool.get(update["interaction_id"])
                source_device_id = interaction.source_device_id if interaction else None
                source_websocket = self.live_connections.get(source_device_id)
                if source_device_id and source_websocket is not None:
                    await self._dispatch_websocket_replies(
                        source_device_id,
                        source_websocket,
                        replies,
                    )
            await asyncio.sleep(30)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
