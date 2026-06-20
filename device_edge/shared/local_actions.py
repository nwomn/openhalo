"""Local action execution shared by simple edge surfaces."""


def execute_action(action: dict) -> dict:
    capability = action["capability"]
    if capability != "notification.show":
        return {"status": "error", "reason": "unsupported"}

    print(action["payload"]["message"])
    return {"status": "ok"}
