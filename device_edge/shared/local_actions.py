"""Local action execution shared by simple edge surfaces."""


def execute_action(
    action: dict,
    output_stream=None,
    delivered_via: str = "stdout",
    message_prefix: str = "",
) -> dict:
    capability = action["capability"]
    if capability != "notification.show":
        return {
            "status": "error",
            "capability": capability,
            "reason": "unsupported",
        }

    payload = action["payload"]
    title = payload.get("title") or "OpenHalo"
    body = payload["body"]
    print(f"{message_prefix}{body}", file=output_stream)
    return {
        "status": "ok",
        "capability": capability,
        "details": {
            "delivered_via": delivered_via,
            "title": title,
            "body": body,
        },
    }
