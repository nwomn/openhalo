"""Minimal action construction for the v0 runtime."""

from edge_api.protocol import with_api_version
from openhalo_common.diagnostics import add_correlation_to_frame

DEFAULT_NOTIFICATION_TITLE = "OpenHalo"
RUNTIME_CONTROL_ACTION_CAPABILITIES = frozenset(
    {
        "runtime.status",
        "runtime.collect_logs",
        "runtime.reload",
        "runtime.restart",
    }
)


def build_notification_payload(body: str) -> dict:
    """Build the canonical payload shared by notification-capable edges."""

    if not isinstance(body, str) or not body.strip():
        raise ValueError("notification body must be a non-empty string")
    return {
        "title": DEFAULT_NOTIFICATION_TITLE,
        "body": body,
    }


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
    request_id: str,
    trace_recorder=None,
    correlation: dict | None = None,
) -> dict:
    if action.get("capability") == "notification.show":
        payload = action.get("payload")
        body = payload.get("body") if isinstance(payload, dict) else None
        action = {
            **action,
            "payload": build_notification_payload(body),
        }
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
            "request_id": request_id,
            "device_id": target_device_id,
            "action": action,
        }
    )
    return add_correlation_to_frame(frame, correlation or {})


def required_device_capability_for_action(action_capability: object) -> str:
    if not isinstance(action_capability, str):
        return ""
    if action_capability in RUNTIME_CONTROL_ACTION_CAPABILITIES:
        return "runtime.control"
    return action_capability


def build_notification_action(
    target_device_id: str,
    body: str,
    request_id: str,
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
            "payload": build_notification_payload(body),
        },
        request_id=request_id,
        trace_recorder=trace_recorder,
        correlation=correlation,
    )


def build_planned_action(
    target_device_id: str,
    proposal: dict,
    request_id: str,
    trace_recorder=None,
    correlation: dict | None = None,
) -> dict:
    action_capability = proposal["action_capability"]
    if action_capability is None:
        raise ValueError("cannot build action request for no_intervention proposal")
    if action_capability == "notification.show":
        payload = proposal["action_payload"]
        return build_notification_action(
            target_device_id,
            payload["body"],
            request_id=request_id,
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
        request_id=request_id,
        trace_recorder=trace_recorder,
        correlation=correlation,
    )
