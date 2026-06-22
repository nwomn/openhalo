"""In-memory runtime state for the v0 single-edge loop."""

from personal_runtime.context_contracts import RuntimeObservation


class RuntimeState:
    def __init__(self) -> None:
        self.devices = {}
        self.events = []
        self.tasks = []
        self.action_results = []
        self.observations = []
        self.interventions = []

    def register_device(self, device_id: str, device_type: str) -> None:
        self.devices.setdefault(
            device_id,
            {"device_type": device_type, "capabilities": set()},
        )

    def register_capability(self, device_id: str, capability_name: str) -> None:
        self.devices[device_id]["capabilities"].add(capability_name)

    def record_action_result(self, result: dict) -> None:
        self.action_results.append(result)

    def record_observation(self, observation: RuntimeObservation) -> None:
        self.observations.append(observation)

    def record_observations(self, observations: list[RuntimeObservation]) -> None:
        self.observations.extend(observations)

    def record_intervention(self, intervention: dict) -> None:
        self.interventions.append(intervention)

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
            "observations": [
                observation.to_dict() for observation in self.observations
            ],
            "interventions": self.interventions,
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
        state.observations = [
            RuntimeObservation.from_dict(observation_payload)
            for observation_payload in payload.get("observations", [])
        ]
        state.interventions = list(payload.get("interventions", []))
        return state
