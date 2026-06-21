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


def required_device_capability_for_action(action_capability: str) -> str:
    if action_capability.startswith("runtime."):
        return "runtime.control"
    return action_capability


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


def build_planned_action(
    target_device_id: str,
    proposal: dict,
    trace_recorder=None,
) -> dict:
    action_capability = proposal["action_capability"]
    if action_capability == "notification.show":
        from personal_runtime.agent_executor import generate_reply

        message = proposal["action_payload"].get("message")
        if message is None:
            message = generate_reply(
                proposal["message"],
                trace_recorder=trace_recorder,
            )
        return build_notification_action(
            target_device_id,
            message,
            trace_recorder=trace_recorder,
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
    )
