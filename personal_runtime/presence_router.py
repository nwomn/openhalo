"""Presence routing rules for the v0 runtime."""


def choose_response_device(
    source_device_id: str,
    devices: dict | None = None,
    required_capability: str | None = None,
) -> str:
    if devices and required_capability:
        for device_id, payload in devices.items():
            if device_id == source_device_id:
                continue
            if required_capability in payload["capabilities"]:
                return device_id
    return source_device_id
