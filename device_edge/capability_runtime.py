"""Minimal capability registry for the v0 device edge."""


class CapabilityRuntime:
    def __init__(self) -> None:
        self.capabilities = ["text.input", "notification.show"]
