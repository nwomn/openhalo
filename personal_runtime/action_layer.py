"""Minimal action construction for the v0 runtime."""


def build_notification_action(target_device_id: str, message: str) -> dict:
    return {
        "type": "action_request",
        "device_id": target_device_id,
        "action": {
            "capability": "notification.show",
            "payload": {"message": message},
        },
    }
