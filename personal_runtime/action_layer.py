"""Minimal action construction for the v0 runtime."""


def build_action_request(target_device_id: str, action: dict) -> dict:
    return {
        "type": "action_request",
        "device_id": target_device_id,
        "action": action,
    }


def build_notification_action(target_device_id: str, message: str) -> dict:
    return build_action_request(
        target_device_id,
        {
            "capability": "notification.show",
            "payload": {"message": message},
        },
    )
