"""Lightweight human-readable execution tracing for local demos."""


class TraceRecorder:
    def __init__(self) -> None:
        self.entries: list[tuple[str, str, dict]] = []

    def record(self, component: str, message: str, **fields: str) -> None:
        self.entries.append((component, message, fields))

    def format_lines(self) -> list[str]:
        lines = []
        for component, message, fields in self.entries:
            line = f"{component} {message}"
            if fields:
                details = ", ".join(
                    f"{key}={value}" for key, value in fields.items()
                )
                line = f"{line} [{details}]"
            lines.append(line)
        return lines
