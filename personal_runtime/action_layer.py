"""Minimal action construction for the v0 runtime."""

from itertools import count

from edge_api.protocol import with_api_version
from openhalo_common.diagnostics import add_correlation_to_frame


_action_request_counter = count(1)


def build_interaction_update(
    target_device_id: str,
    interaction: dict,
    trace_recorder=None,
    correlation: dict | None = None,
) -> dict:
    if trace_recorder is not None:
        trace_recorder.record(
            "ACTION",
            "built interaction update",
            target_device_id=target_device_id,
            interaction_id=interaction.get("interaction_id", ""),
            status=interaction.get("status", ""),
        )
    frame = with_api_version(
        {
            "type": "interaction_update",
            "device_id": target_device_id,
            "interaction": interaction,
        }
    )
    return add_correlation_to_frame(frame, correlation or {})


def build_action_request(
    target_device_id: str,
    action: dict,
    trace_recorder=None,
    correlation: dict | None = None,
) -> dict:
    if trace_recorder is not None:
        if action["capability"] == "notification.show":
            trace_recorder.record(
                "ACTION",
                "built notification.show request",
                target_device_id=target_device_id,
            )
        trace_recorder.record(
            "ACTION",
            "built action request",
            target_device_id=target_device_id,
            capability=action["capability"],
        )
    frame = with_api_version(
        {
            "type": "action_request",
            "request_id": f"action-{next(_action_request_counter)}",
            "device_id": target_device_id,
            "action": action,
        }
    )
    return add_correlation_to_frame(frame, correlation or {})


def required_device_capability_for_action(action_capability: str) -> str:
    if action_capability is None:
        return ""
    if action_capability.startswith("runtime."):
        return "runtime.control"
    return action_capability


def build_notification_action(
    target_device_id: str,
    message: str,
    trace_recorder=None,
    correlation: dict | None = None,
) -> dict:
    if trace_recorder is not None:
        trace_recorder.record(
            "ACTION",
            "built notification.show request",
            target_device_id=target_device_id,
        )
    return build_action_request(
        target_device_id,
        {
            "capability": "notification.show",
            "payload": {"message": message},
        },
        trace_recorder=trace_recorder,
        correlation=correlation,
    )


def build_planned_action(
    target_device_id: str,
    proposal: dict,
    trace_recorder=None,
    correlation: dict | None = None,
) -> dict:
    action_capability = proposal["action_capability"]
    if action_capability is None:
        raise ValueError("cannot build action request for no_intervention proposal")
    if action_capability == "notification.show":
        message = proposal["action_payload"].get("message")
        return build_notification_action(
            target_device_id,
            message,
            trace_recorder=trace_recorder,
            correlation=correlation,
        )

    if trace_recorder is not None:
        trace_recorder.record(
            "ACTION",
            "planned runtime action request",
            target_device_id=target_device_id,
            capability=action_capability,
        )
    return build_action_request(
        target_device_id,
        {
            "capability": action_capability,
            "payload": proposal["action_payload"],
        },
        trace_recorder=trace_recorder,
        correlation=correlation,
    )
