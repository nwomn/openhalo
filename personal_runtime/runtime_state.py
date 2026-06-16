"""In-memory runtime state for the v0 single-edge loop."""


class RuntimeState:
    def __init__(self) -> None:
        self.devices = {}
        self.events = []
        self.tasks = []
        self.action_results = []

    def register_device(self, device_id: str, device_type: str) -> None:
        self.devices.setdefault(
            device_id,
            {"device_type": device_type, "capabilities": set()},
        )

    def register_capability(self, device_id: str, capability_name: str) -> None:
        self.devices[device_id]["capabilities"].add(capability_name)

    def record_action_result(self, result: dict) -> None:
        self.action_results.append(result)

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
        return state
