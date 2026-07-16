"""In-memory runtime state for the v0 single-edge loop."""

from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.harness_provenance import RUNTIME_PROVENANCE_HISTORY_LIMIT
from personal_runtime.harness_provenance import sanitize_hermes_memory_events
from personal_runtime.harness_provenance import sanitize_internal_tool_events


HARNESS_PROVENANCE_HISTORY_LIMIT = RUNTIME_PROVENANCE_HISTORY_LIMIT


class RuntimeState:
    def __init__(self) -> None:
        self.devices = {}
        self.device_registry = {}
        self.capability_registry = {}
        self.observation_registry = {}
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

    def register_device(
        self,
        device_id: str,
        device_type: str,
        role: str | None = None,
        profile: dict | None = None,
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

    def record_action_result(self, result: dict) -> None:
        self.action_results.append(result)

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

    def record_memory_consolidation_candidate(self, candidate: dict) -> None:
        self.memory_consolidation_candidates.append(dict(candidate))

    def record_harness_trace(self, trace: dict) -> None:
        self.harness_traces.append(dict(trace))

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
        self.hermes_memory_events = self.hermes_memory_events[
            -HARNESS_PROVENANCE_HISTORY_LIMIT:
        ]

    def record_interaction(self, interaction: dict) -> None:
        self.interactions.append(interaction)

    def allocate_interaction_id(self) -> str:
        existing_ids = {
            interaction.get("interaction_id") for interaction in self.interactions
        }
        next_index = self.interaction_sequence + 1
        while f"interaction-{next_index}" in existing_ids:
            next_index += 1
        self.interaction_sequence = next_index
        return f"interaction-{next_index}"

    def allocate_interaction_turn_id(self) -> str:
        self.interaction_turn_sequence += 1
        return f"interaction-turn-{self.interaction_turn_sequence}"

    def update_interaction(
        self,
        interaction_id: str,
        **changes,
    ) -> dict:
        for index, existing in enumerate(self.interactions):
            if existing.get("interaction_id") == interaction_id:
                updated = {**existing, **changes}
                self.interactions[index] = updated
                return updated
        created = {"interaction_id": interaction_id, **changes}
        self.interactions.append(created)
        return created

    def record_observation(self, observation: RuntimeObservation) -> None:
        self.observations.append(observation)

    def record_observations(self, observations: list[RuntimeObservation]) -> None:
        self.observations.extend(observations)

    def record_intervention(self, intervention: dict) -> None:
        self.interventions.append(intervention)

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
                return
        self.tasks.append(goal_payload)

    def to_dict(self) -> dict:
        return {
            "devices": {
                device_id: {
                    "device_type": payload["device_type"],
                    "capabilities": sorted(payload["capabilities"]),
                }
                for device_id, payload in self.devices.items()
            },
            "device_registry": self.device_registry,
            "capability_registry": self.capability_registry,
            "observation_registry": self.observation_registry,
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
            "action_registry": self.action_registry,
            "harness_memory": self.harness_memory,
            "memory_consolidation_candidates": self.memory_consolidation_candidates,
            "harness_traces": self.harness_traces,
            "internal_tool_events": self.internal_tool_events,
            "hermes_memory_events": self.hermes_memory_events,
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
        return state


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
