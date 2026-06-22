"""Local action execution shared by simple edge surfaces."""


def execute_action(
    action: dict,
    output_stream=None,
    delivered_via: str = "stdout",
) -> dict:
    capability = action["capability"]
    if capability != "notification.show":
        return {"status": "error", "reason": "unsupported"}

    print(action["payload"]["message"], file=output_stream)
    return {
        "status": "ok",
        "details": {
            "delivered_via": delivered_via,
            "message": action["payload"]["message"],
        },
    }
