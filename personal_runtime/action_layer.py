"""Minimal action construction for the v0 runtime."""


def build_action_request(target_device_id: str, action: dict, trace_recorder=None) -> dict:
    if trace_recorder is not None:
        trace_recorder.record(
            "ACTION",
            "built action request",
            target_device_id=target_device_id,
            capability=action["capability"],
        )
    return {
        "type": "action_request",
        "device_id": target_device_id,
        "action": action,
    }


def build_notification_action(
    target_device_id: str,
    message: str,
    trace_recorder=None,
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
    )
