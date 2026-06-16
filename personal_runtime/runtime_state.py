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
