"""Public Edge API frame helpers.

This module is intentionally small and dependency-free so external edges can
reuse the same frame contract without importing Personal Runtime internals.
"""

API_VERSION = "edge.runtime.v1"

REQUIRED_TYPES = {
    "connect",
    "connect_ok",
    "capability_announce",
    "event_push",
    "observation_push",
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
    api_version = frame.get("api_version")
    if api_version is not None and api_version != API_VERSION:
        raise ValueError(f"Unsupported api_version: {api_version!r}")
    return frame


def with_api_version(frame: dict) -> dict:
    return {"api_version": API_VERSION, **frame}


def build_connect_frame(
    device_id: str,
    device_type: str,
    token: str,
    role: str | None = None,
) -> dict:
    device = {
        "device_id": device_id,
        "device_type": device_type,
    }
    if role is not None:
        device["role"] = role
    return with_api_version(
        {
            "type": "connect",
            "device": device,
            "auth": {"token": token},
        }
    )


def build_capability_announce_frame(
    device_id: str,
    capabilities: list[str | dict],
) -> dict:
    return with_api_version(
        {
            "type": "capability_announce",
            "device_id": device_id,
            "capabilities": capabilities,
        }
    )


def build_event_push_frame(
    device_id: str,
    capability: str,
    payload: dict,
    event_id: str | None = None,
) -> dict:
    frame = {
        "type": "event_push",
        "device_id": device_id,
        "capability": capability,
        "payload": payload,
    }
    if event_id is not None:
        frame["event_id"] = event_id
    return with_api_version(frame)


def build_observation_push_frame(
    device_id: str,
    capability: str,
    observations: list[dict],
    event_id: str | None = None,
) -> dict:
    frame = {
        "type": "observation_push",
        "device_id": device_id,
        "capability": capability,
        "observations": observations,
        "payload": {"observations": observations},
    }
    if event_id is not None:
        frame["event_id"] = event_id
    return with_api_version(frame)
