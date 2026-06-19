"""Minimal capability registry for the v0 device edge."""


class CapabilityRuntime:
    def __init__(self, capabilities: list[str] | None = None) -> None:
        self.capabilities = capabilities or ["text.input", "notification.show"]
