"""In-memory runtime state for the v0 single-edge loop."""

from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.harness_provenance import RUNTIME_PROVENANCE_HISTORY_LIMIT
from personal_runtime.harness_provenance import sanitize_hermes_memory_events
from personal_runtime.harness_provenance import sanitize_internal_tool_events


HARNESS_PROVENANCE_HISTORY_LIMIT = RUNTIME_PROVENANCE_HISTORY_LIMIT
EVENT_HISTORY_LIMIT = 2_000
OBSERVATION_HISTORY_LIMIT = 10_000
ACTION_RESULT_HISTORY_LIMIT = 2_000
INTERACTION_HISTORY_LIMIT = 500
INTERVENTION_HISTORY_LIMIT = 2_000
MEMORY_CONSOLIDATION_HISTORY_LIMIT = 2_000
HARNESS_TRACE_HISTORY_LIMIT = 2_000
HARNESS_MEMORY_LIMIT = 5_000


class RuntimeState:
    def __init__(self) -> None:
        self.devices = {}
        self.device_registry = {}
        self.capability_registry = {}
        self.observation_registry = {}
        self.proxy_screen_profiles = {}
        self.context_facts = {}
        self.main_session = {}
        self.interaction_work = []
        self.events = []
        self.tasks = []
        self.action_results = []
        self.interactions = []
        self.interaction_sequence = 0
        self.interaction_turn_sequence = 0
        self.proactive_trigger_state = {}
        self.observations = []
        self.interventions = []
        self.model_health = {}
        self.mobile_liveness = {}
        self.managed_host_edge = {}
        self.action_registry = {
            "mcp.invoke": {
                "executor_kind": "mcp",
                "status": "placeholder",
            },
            "skill.invoke": {
                "executor_kind": "skill_procedure",
                "status": "placeholder",
            },
        }
        self.harness_memory = {
            "procedural": [],
            "semantic": [],
            "episodic": [],
        }
        self.memory_consolidation_candidates = []
        self.harness_traces = []
        self.internal_tool_events = []
        self.hermes_memory_events = []
        self._storage_operations = []

    def replace_context_facts(self, facts: list[dict]) -> None:
        self.context_facts = {
            fact["fact_id"]: dict(fact)
            for fact in facts
            if isinstance(fact, dict) and isinstance(fact.get("fact_id"), str)
        }

    def _queue_record(
        self,
        collection: str,
        payload: dict,
        *,
        record_key: str | None = None,
    ) -> None:
        self._storage_operations.append(
            {
                "kind": "record",
                "collection": collection,
                "payload": dict(payload),
                "record_key": record_key,
            }
        )

    def _queue_state_value(self, key: str, payload) -> None:
        self._storage_operations.append(
            {"kind": "state_value", "key": key, "payload": payload}
        )

    def mark_state_value(self, key: str, payload=None) -> None:
        if payload is None:
            payload = getattr(self, key)
        self._queue_state_value(key, payload)

    def drain_storage_operations(self) -> list[dict]:
        operations = self._storage_operations
        self._storage_operations = []
        return operations

    def register_device(
        self,
        device_id: str,
        device_type: str,
        role: str | None = None,
        profile: dict | None = None,
        display_name: str | None = None,
    ) -> None:
        self.devices.setdefault(
            device_id,
            {"device_type": device_type, "capabilities": set()},
        )
        self.device_registry.setdefault(
            device_id,
            {
                "device_id": device_id,
                "device_type": device_type,
            },
        )
        if role is not None:
            self.device_registry[device_id]["role"] = role
        if profile is not None:
            self.device_registry[device_id]["profile"] = profile
        if isinstance(display_name, str) and display_name.strip():
            self.device_registry[device_id]["display_name"] = display_name.strip()
        self._queue_state_value("devices", self._devices_payload())
        self._queue_state_value("device_registry", self.device_registry)

    def register_capability(self, device_id: str, capability_name: str | dict) -> None:
        if isinstance(capability_name, dict):
            capability = dict(capability_name)
            name = capability["name"]
            self.capability_registry.setdefault(device_id, {})[name] = capability
            for observation in capability.get("observations", []) or []:
                observation_name = observation["name"]
                self.observation_registry.setdefault(device_id, {}).setdefault(
                    name,
                    {},
                )[observation_name] = dict(observation)
            capability_name = name
        else:
            defaults = _compatibility_capability_registration(capability_name)
            if defaults is not None:
                self.capability_registry.setdefault(device_id, {})[
                    capability_name
                ] = defaults
                for observation in defaults.get("observations", []):
                    self.observation_registry.setdefault(device_id, {}).setdefault(
                        capability_name,
                        {},
                    )[observation["name"]] = dict(observation)
        self.devices[device_id]["capabilities"].add(capability_name)
        self._queue_state_value("devices", self._devices_payload())
        self._queue_state_value("capability_registry", self.capability_registry)
        self._queue_state_value("observation_registry", self.observation_registry)

    def record_proxy_screen_profile(self, device_id: str, profile: dict) -> None:
        """Persist configuration metadata only; never raw screen evidence."""

        self.proxy_screen_profiles[device_id] = dict(profile)
        self._queue_state_value("proxy_screen_profiles", self.proxy_screen_profiles)

    def record_event(self, event: dict) -> None:
        payload = dict(event)
        self.events.append(payload)
        self._trim_history("events", EVENT_HISTORY_LIMIT)
        self._queue_record("events", sanitize_event_for_storage(payload))

    def record_action_result(self, result: dict) -> None:
        payload = dict(result)
        self.action_results.append(payload)
        self._trim_history(
            "action_results",
            ACTION_RESULT_HISTORY_LIMIT,
            preserve_active_links=True,
        )
        self._queue_record("action_results", payload)

    def record_harness_memory(
        self,
        kind,
        *,
        memory_id: str,
        content: dict,
        source_refs: list[str],
        recorded_at: str,
    ) -> None:
        key = getattr(kind, "value", kind)
        if key not in self.harness_memory:
            raise ValueError(f"unsupported harness memory kind: {key}")
        self.harness_memory[key].append(
            {
                "memory_id": memory_id,
                "content": dict(content),
                "source_refs": list(source_refs),
                "recorded_at": recorded_at,
            }
        )
        self.harness_memory[key] = self.harness_memory[key][-HARNESS_MEMORY_LIMIT:]
        self._queue_state_value("harness_memory", self.harness_memory)

    def record_memory_consolidation_candidate(self, candidate: dict) -> None:
        payload = dict(candidate)
        self.memory_consolidation_candidates.append(payload)
        self._trim_history(
            "memory_consolidation_candidates",
            MEMORY_CONSOLIDATION_HISTORY_LIMIT,
            preserve_active_links=True,
        )
        self._queue_record("memory_consolidation_candidates", payload)

    def record_harness_trace(self, trace: dict) -> None:
        payload = dict(trace)
        self.harness_traces.append(payload)
        self._trim_history(
            "harness_traces",
            HARNESS_TRACE_HISTORY_LIMIT,
            preserve_active_links=True,
        )
        self._queue_record("harness_traces", payload)

    def record_internal_tool_events(
        self,
        events: object,
        *,
        interaction_id: str,
        interaction_turn_id: str,
    ) -> None:
        for event in sanitize_internal_tool_events(
            events,
            limit=HARNESS_PROVENANCE_HISTORY_LIMIT,
        ):
            self.internal_tool_events.append(
                {
                    "interaction_id": interaction_id,
                    "interaction_turn_id": interaction_turn_id,
                    **event,
                }
            )
            self._queue_record("internal_tool_events", self.internal_tool_events[-1])
        self.internal_tool_events = self.internal_tool_events[
            -HARNESS_PROVENANCE_HISTORY_LIMIT:
        ]

    def record_hermes_memory_events(
        self,
        events: object,
        *,
        interaction_id: str,
        interaction_turn_id: str,
    ) -> None:
        for event in sanitize_hermes_memory_events(
            events,
            limit=HARNESS_PROVENANCE_HISTORY_LIMIT,
        ):
            self.hermes_memory_events.append(
                {
                    "interaction_id": interaction_id,
                    "interaction_turn_id": interaction_turn_id,
                    **event,
                }
            )
            self._queue_record("hermes_memory_events", self.hermes_memory_events[-1])
        self.hermes_memory_events = self.hermes_memory_events[
            -HARNESS_PROVENANCE_HISTORY_LIMIT:
        ]

    def record_interaction(self, interaction: dict) -> None:
        payload = dict(interaction)
        self.interactions.append(payload)
        self._trim_history(
            "interactions",
            INTERACTION_HISTORY_LIMIT,
            preserve_active=True,
        )
        self._queue_record(
            "interactions",
            payload,
            record_key=payload.get("interaction_id"),
        )

    def mark_interaction_changed(self, interaction: dict) -> None:
        self._queue_record(
            "interactions",
            interaction,
            record_key=interaction.get("interaction_id"),
        )

    def allocate_interaction_id(self) -> str:
        existing_ids = {
            interaction.get("interaction_id") for interaction in self.interactions
        }
        next_index = self.interaction_sequence + 1
        while f"interaction-{next_index}" in existing_ids:
            next_index += 1
        self.interaction_sequence = next_index
        self._queue_state_value("interaction_sequence", next_index)
        return f"interaction-{next_index}"

    def allocate_interaction_turn_id(self) -> str:
        existing_ids = {
            turn.get("interaction_turn_id")
            for interaction in self.interactions
            for turn in interaction.get("turns", [])
            if isinstance(turn, dict)
            and isinstance(turn.get("interaction_turn_id"), str)
        }
        next_index = self.interaction_turn_sequence + 1
        while f"interaction-turn-{next_index}" in existing_ids:
            next_index += 1
        self.interaction_turn_sequence = next_index
        self._queue_state_value("interaction_turn_sequence", next_index)
        return f"interaction-turn-{next_index}"

    def update_interaction(
        self,
        interaction_id: str,
        **changes,
    ) -> dict:
        for index, existing in enumerate(self.interactions):
            if existing.get("interaction_id") == interaction_id:
                updated = {**existing, **changes}
                self.interactions[index] = updated
                self._trim_history(
                    "interactions",
                    INTERACTION_HISTORY_LIMIT,
                    preserve_active=True,
                )
                self.mark_interaction_changed(updated)
                return updated
        created = {"interaction_id": interaction_id, **changes}
        self.interactions.append(created)
        self._trim_history(
            "interactions",
            INTERACTION_HISTORY_LIMIT,
            preserve_active=True,
        )
        self.mark_interaction_changed(created)
        return created

    def record_observation(self, observation: RuntimeObservation) -> None:
        self.observations.append(observation)
        self._trim_history("observations", OBSERVATION_HISTORY_LIMIT)
        self._queue_record("observations", observation.to_dict())

    def record_observations(self, observations: list[RuntimeObservation]) -> None:
        for observation in observations:
            self.record_observation(observation)

    def record_intervention(self, intervention: dict) -> None:
        payload = dict(intervention)
        self.interventions.append(payload)
        self._trim_history(
            "interventions",
            INTERVENTION_HISTORY_LIMIT,
            preserve_active_links=True,
        )
        self._queue_record("interventions", payload)

    def record_model_health(
        self,
        metadata: dict,
        observed_at: str = "",
    ) -> None:
        profile = metadata.get("llm_profile")
        if not profile:
            return
        unavailable = bool(metadata.get("model_unavailable"))
        existing = dict(self.model_health.get(profile, {}))
        updated = {
            **existing,
            "profile": profile,
            "provider": metadata.get("llm_provider", ""),
            "model": metadata.get("llm_model", ""),
            "status": "unavailable" if unavailable else "ok",
            "model_unavailable": unavailable,
            "provider_wire_api": metadata.get("provider_wire_api", ""),
            "provider_request_format": metadata.get(
                "provider_request_format",
                "",
            ),
            "last_latency_ms": metadata.get("provider_latency_ms"),
            "updated_at": observed_at,
        }
        if unavailable:
            updated["last_failure_class"] = metadata.get(
                "provider_failure_class",
                "",
            )
            updated["last_failure_reason"] = metadata.get(
                "provider_failure_reason",
                "",
            )
            updated["last_failure_type"] = metadata.get(
                "provider_failure_type",
                "",
            )
        else:
            updated["last_success_at"] = observed_at
        self.model_health[profile] = updated
        self._queue_state_value("model_health", self.model_health)

    def record_managed_host_edge_status(
        self,
        *,
        state: str,
        retry_attempt: int,
        latest_failure_class: str | None,
        next_retry_delay_s: float | None,
        updated_at: str,
    ) -> None:
        self.managed_host_edge = {
            "state": state,
            "retry_attempt": retry_attempt,
            "latest_failure_class": latest_failure_class,
            "next_retry_delay_s": next_retry_delay_s,
            "updated_at": updated_at,
        }
        self._queue_state_value("managed_host_edge", self.managed_host_edge)

    def upsert_goal(
        self,
        goal_id: str,
        title: str,
        status: str,
        summary: str,
        updated_at: str,
    ) -> None:
        goal_payload = {
            "goal_id": goal_id,
            "title": title,
            "status": status,
            "summary": summary,
            "updated_at": updated_at,
        }
        for index, existing_goal in enumerate(self.tasks):
            if existing_goal.get("goal_id") == goal_id:
                self.tasks[index] = goal_payload
                self._queue_state_value("tasks", self.tasks)
                return
        self.tasks.append(goal_payload)
        self._queue_state_value("tasks", self.tasks)

    def _trim_history(
        self,
        collection: str,
        limit: int,
        *,
        preserve_active: bool = False,
        preserve_active_links: bool = False,
    ) -> None:
        records = getattr(self, collection)
        if len(records) <= limit:
            return
        active_ids = set()
        if preserve_active or preserve_active_links:
            active_ids = {
                item.get("interaction_id")
                for item in self.interactions
                if isinstance(item, dict)
                and item.get("interaction_id")
                and item.get("status", "planned") != "completed"
            }
        preserved_indexes = []
        if preserve_active:
            preserved_indexes = [
                index
                for index, item in enumerate(records)
                if isinstance(item, dict)
                and item.get("status", "planned") != "completed"
            ]
        elif preserve_active_links:
            preserved_indexes = [
                index
                for index, item in enumerate(records)
                if isinstance(item, dict)
                and item.get("interaction_id") in active_ids
            ]
        preserved_indexes = preserved_indexes[-limit:]
        selected = set(preserved_indexes)
        for index in range(len(records) - 1, -1, -1):
            if len(selected) >= limit:
                break
            selected.add(index)
        setattr(self, collection, [item for index, item in enumerate(records) if index in selected])

    def _trim_hot_histories(self) -> None:
        self._trim_history("interactions", INTERACTION_HISTORY_LIMIT, preserve_active=True)
        self._trim_history("events", EVENT_HISTORY_LIMIT)
        self._trim_history("observations", OBSERVATION_HISTORY_LIMIT)
        self._trim_history(
            "action_results",
            ACTION_RESULT_HISTORY_LIMIT,
            preserve_active_links=True,
        )
        self._trim_history(
            "interventions",
            INTERVENTION_HISTORY_LIMIT,
            preserve_active_links=True,
        )
        self._trim_history(
            "memory_consolidation_candidates",
            MEMORY_CONSOLIDATION_HISTORY_LIMIT,
            preserve_active_links=True,
        )
        self._trim_history(
            "harness_traces",
            HARNESS_TRACE_HISTORY_LIMIT,
            preserve_active_links=True,
        )
        for kind, records in self.harness_memory.items():
            self.harness_memory[kind] = records[-HARNESS_MEMORY_LIMIT:]

    def to_dict(self) -> dict:
        return {
            "devices": self._devices_payload(),
            "device_registry": self.device_registry,
            "capability_registry": self.capability_registry,
            "observation_registry": self.observation_registry,
            "proxy_screen_profiles": self.proxy_screen_profiles,
            "context_facts": self.context_facts,
            "main_session": self.main_session,
            "interaction_work": self.interaction_work,
            "events": self.events,
            "tasks": self.tasks,
            "action_results": self.action_results,
            "interactions": self.interactions,
            "interaction_sequence": self.interaction_sequence,
            "interaction_turn_sequence": self.interaction_turn_sequence,
            "proactive_trigger_state": self.proactive_trigger_state,
            "observations": [
                observation.to_dict() for observation in self.observations
            ],
            "interventions": self.interventions,
            "model_health": self.model_health,
            "mobile_liveness": self.mobile_liveness,
            "managed_host_edge": self.managed_host_edge,
            "action_registry": self.action_registry,
            "harness_memory": self.harness_memory,
            "memory_consolidation_candidates": self.memory_consolidation_candidates,
            "harness_traces": self.harness_traces,
            "internal_tool_events": self.internal_tool_events,
            "hermes_memory_events": self.hermes_memory_events,
        }

    def _devices_payload(self) -> dict:
        return {
            device_id: {
                "device_type": payload["device_type"],
                "capabilities": sorted(payload["capabilities"]),
            }
            for device_id, payload in self.devices.items()
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "RuntimeState":
        state = cls()
        for device_id, device_payload in payload.get("devices", {}).items():
            state.devices[device_id] = {
                "device_type": device_payload["device_type"],
                "capabilities": set(device_payload.get("capabilities", [])),
            }
        state.device_registry = dict(payload.get("device_registry", {}))
        state.capability_registry = dict(payload.get("capability_registry", {}))
        state.observation_registry = dict(payload.get("observation_registry", {}))
        state.proxy_screen_profiles = dict(payload.get("proxy_screen_profiles", {}))
        state.context_facts = dict(payload.get("context_facts", {}))
        state.main_session = dict(payload.get("main_session", {}))
        state.interaction_work = list(payload.get("interaction_work", []))
        state.events = list(payload.get("events", []))
        state.tasks = list(payload.get("tasks", []))
        state.action_results = list(payload.get("action_results", []))
        state.interactions = list(payload.get("interactions", []))
        state.interaction_sequence = int(payload.get("interaction_sequence", 0))
        state.interaction_turn_sequence = int(
            payload.get("interaction_turn_sequence", 0)
        )
        state.proactive_trigger_state = dict(
            payload.get("proactive_trigger_state", {})
        )
        state.observations = [
            RuntimeObservation.from_dict(observation_payload)
            for observation_payload in payload.get("observations", [])
        ]
        state.interventions = list(payload.get("interventions", []))
        state.model_health = dict(payload.get("model_health", {}))
        state.mobile_liveness = dict(payload.get("mobile_liveness", {}))
        state.managed_host_edge = dict(payload.get("managed_host_edge", {}))
        state.action_registry.update(dict(payload.get("action_registry", {})))
        stored_harness_memory = dict(payload.get("harness_memory", {}))
        for kind in state.harness_memory:
            state.harness_memory[kind] = list(stored_harness_memory.get(kind, []))
        state.memory_consolidation_candidates = list(
            payload.get("memory_consolidation_candidates", [])
        )
        state.harness_traces = list(payload.get("harness_traces", []))
        for event in payload.get("internal_tool_events", []):
            if not isinstance(event, dict):
                continue
            state.record_internal_tool_events(
                [event],
                interaction_id=event.get("interaction_id", ""),
                interaction_turn_id=event.get("interaction_turn_id", ""),
            )
        for event in payload.get("hermes_memory_events", []):
            if not isinstance(event, dict):
                continue
            state.record_hermes_memory_events(
                [event],
                interaction_id=event.get("interaction_id", ""),
                interaction_turn_id=event.get("interaction_turn_id", ""),
            )
        state._trim_hot_histories()
        state._storage_operations = []
        return state


def sanitize_event_for_storage(event: dict) -> dict:
    payload = dict(event)
    body = payload.get("payload")
    if not isinstance(body, dict) or not isinstance(body.get("observations"), list):
        return payload
    observations = body["observations"]
    projected_body = {
        key: value for key, value in body.items() if key != "observations"
    }
    projected_body["observation_count"] = len(observations)
    projected_body["observation_names"] = sorted(
        {
            item.get("name")
            for item in observations
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
    )
    payload["payload"] = projected_body
    return payload


def _compatibility_capability_registration(capability_name: str) -> dict | None:
    defaults = {
        "notification.show": {
            "name": "notification.show",
            "direction": "runtime_to_edge",
            "kind": "action",
            "affordances": ["notify_user", "deliver_private_text"],
            "modality": "visual_text",
            "content_capacity": "short_text",
            "privacy": "personal",
            "interruptiveness": "medium",
            "side_effect": "user_visible",
            "input_schema": {
                "type": "object",
                "required": ["body"],
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string", "minLength": 1},
                },
            },
        },
        "text.input": {
            "name": "text.input",
            "direction": "edge_to_runtime",
            "kind": "event_source",
            "affordances": ["user_text"],
            "modality": "text",
            "content_capacity": "short_text",
            "privacy": "personal",
        },
        "runtime.control": {
            "name": "runtime.control",
            "direction": "runtime_to_edge",
            "kind": "action",
            "affordances": ["runtime_control"],
            "modality": "machine_action",
            "content_capacity": "structured",
            "privacy": "runtime_internal",
            "interruptiveness": "low",
            "side_effect": "runtime_side_effect",
        },
        "runtime.health": {
            "name": "runtime.health",
            "direction": "edge_to_runtime",
            "kind": "observation_provider",
            "observations": [
                {
                    "name": "runtime.health_state",
                    "schema": {
                        "type": "string",
                        "enum": [
                            "healthy",
                            "degraded",
                            "unhealthy",
                            "offline",
                            "down",
                            "failed",
                            "unknown",
                        ],
                    },
                    "semantics": ["runtime_health"],
                    "privacy": "runtime_internal",
                    "freshness_seconds": 120,
                },
                {
                    "name": "runtime.process_present",
                    "schema": {"type": "boolean"},
                    "semantics": ["runtime_health"],
                    "privacy": "runtime_internal",
                    "freshness_seconds": 120,
                },
                {
                    "name": "runtime.process_pid",
                    "schema": {"type": "integer"},
                    "semantics": ["runtime_health"],
                    "privacy": "runtime_internal",
                    "freshness_seconds": 120,
                },
                {
                    "name": "runtime.process_started_at",
                    "schema": {"type": "string", "nullable": True},
                    "semantics": ["runtime_health"],
                    "privacy": "runtime_internal",
                    "freshness_seconds": 120,
                },
                {
                    "name": "runtime.process_memory_rss_bytes",
                    "schema": {"type": "integer"},
                    "semantics": ["runtime_health"],
                    "privacy": "runtime_internal",
                    "freshness_seconds": 120,
                },
            ],
        },
        "host.metrics": {
            "name": "host.metrics",
            "direction": "edge_to_runtime",
            "kind": "observation_provider",
            "observations": [
                {
                    "name": "host.cpu_load_ratio",
                    "schema": {"type": "number"},
                    "semantics": ["host_metrics"],
                    "privacy": "runtime_internal",
                    "freshness_seconds": 120,
                },
                {
                    "name": "host.memory_available_bytes",
                    "schema": {"type": "integer"},
                    "semantics": ["host_metrics"],
                    "privacy": "runtime_internal",
                    "freshness_seconds": 120,
                },
                {
                    "name": "host.memory_used_bytes",
                    "schema": {"type": "integer"},
                    "semantics": ["host_metrics"],
                    "privacy": "runtime_internal",
                    "freshness_seconds": 120,
                },
                {
                    "name": "host.memory_pressure",
                    "schema": {"type": "string"},
                    "semantics": ["host_metrics"],
                    "privacy": "runtime_internal",
                    "freshness_seconds": 120,
                },
                {
                    "name": "host.net_rx_bytes",
                    "schema": {"type": "integer"},
                    "semantics": ["host_metrics"],
                    "privacy": "runtime_internal",
                    "freshness_seconds": 120,
                },
                {
                    "name": "host.net_tx_bytes",
                    "schema": {"type": "integer"},
                    "semantics": ["host_metrics"],
                    "privacy": "runtime_internal",
                    "freshness_seconds": 120,
                },
            ],
        },
        "terminal.context": {
            "name": "terminal.context",
            "direction": "edge_to_runtime",
            "kind": "observation_provider",
            "observations": [
                {
                    "name": "terminal.activity_state",
                    "schema": {
                        "type": "string",
                        "enum": ["active", "idle", "unknown"],
                    },
                    "semantics": ["device_activity"],
                    "privacy": "personal_device_state",
                    "freshness_seconds": 120,
                },
                {
                    "name": "terminal.input_state",
                    "schema": {"type": "string"},
                    "semantics": ["device_activity"],
                    "privacy": "personal_device_state",
                    "freshness_seconds": 120,
                },
                {
                    "name": "terminal.input_draft_length",
                    "schema": {"type": "integer"},
                    "semantics": ["device_activity"],
                    "privacy": "personal_device_state",
                    "freshness_seconds": 120,
                },
            ],
        },
        "desktop_context": {
            "name": "desktop_context",
            "direction": "edge_to_runtime",
            "kind": "observation_provider",
            "observations": [
                {
                    "name": "user.location",
                    "schema": {"type": "string"},
                    "semantics": ["user_context"],
                    "privacy": "personal",
                    "freshness_seconds": 600,
                },
            ],
        },
        "mobile_context": {
            "name": "mobile_context",
            "direction": "edge_to_runtime",
            "kind": "observation_provider",
            "observations": [
                {
                    "name": "user.location",
                    "schema": {"type": "string"},
                    "semantics": ["user_context"],
                    "privacy": "personal",
                    "freshness_seconds": 600,
                },
            ],
        },
    }
    return defaults.get(capability_name)
