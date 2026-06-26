"""In-memory runtime state for the v0 single-edge loop."""

from personal_runtime.context_contracts import RuntimeObservation


class RuntimeState:
    def __init__(self) -> None:
        self.devices = {}
        self.events = []
        self.tasks = []
        self.action_results = []
        self.interactions = []
        self.observations = []
        self.interventions = []
        self.model_health = {}

    def register_device(self, device_id: str, device_type: str) -> None:
        self.devices.setdefault(
            device_id,
            {"device_type": device_type, "capabilities": set()},
        )

    def register_capability(self, device_id: str, capability_name: str) -> None:
        self.devices[device_id]["capabilities"].add(capability_name)

    def record_action_result(self, result: dict) -> None:
        self.action_results.append(result)

    def record_interaction(self, interaction: dict) -> None:
        self.interactions.append(interaction)

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
            "events": self.events,
            "tasks": self.tasks,
            "action_results": self.action_results,
            "interactions": self.interactions,
            "observations": [
                observation.to_dict() for observation in self.observations
            ],
            "interventions": self.interventions,
            "model_health": self.model_health,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "RuntimeState":
        state = cls()
        for device_id, device_payload in payload.get("devices", {}).items():
            state.devices[device_id] = {
                "device_type": device_payload["device_type"],
                "capabilities": set(device_payload.get("capabilities", [])),
            }
        state.events = list(payload.get("events", []))
        state.tasks = list(payload.get("tasks", []))
        state.action_results = list(payload.get("action_results", []))
        state.interactions = list(payload.get("interactions", []))
        state.observations = [
            RuntimeObservation.from_dict(observation_payload)
            for observation_payload in payload.get("observations", [])
        ]
        state.interventions = list(payload.get("interventions", []))
        state.model_health = dict(payload.get("model_health", {}))
        return state
