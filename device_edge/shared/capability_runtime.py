"""Minimal capability registry shared across edge surfaces."""


class CapabilityRuntime:
    def __init__(self, capabilities: list[str] | None = None) -> None:
        self.capabilities = capabilities or ["text.input", "notification.show"]
