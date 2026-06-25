"""Shared frame helpers for the v0 runtime protocol."""

REQUIRED_TYPES = {
    "connect",
    "connect_ok",
    "capability_announce",
    "event_push",
    "event_ack",
    "action_request",
    "action_result",
    "interaction_update",
    "error",
}


def validate_frame(frame: dict) -> dict:
    frame_type = frame.get("type")
    if frame_type not in REQUIRED_TYPES:
        raise ValueError(f"Unsupported frame type: {frame_type!r}")
    return frame


def build_connect_frame(device_id: str, device_type: str, token: str) -> dict:
    return {
        "type": "connect",
        "device": {
            "device_id": device_id,
            "device_type": device_type,
        },
        "auth": {"token": token},
    }
