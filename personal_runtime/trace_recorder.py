"""Lightweight human-readable execution tracing for local demos."""

from __future__ import annotations

from collections.abc import Callable


class TraceRecorder:
    def __init__(
        self,
        emitters: list[Callable[[str], None]] | None = None,
        retain_entries: bool = True,
    ) -> None:
        self.entries: list[tuple[str, str, dict]] = []
        self.emitters = emitters or []
        self.retain_entries = retain_entries

    def record(self, component: str, message: str, **fields: str) -> None:
        entry = (component, message, fields)
        if self.retain_entries:
            self.entries.append(entry)

        line = self._format_entry(entry)
        for emitter in self.emitters:
            emitter(line)

    def format_lines(self) -> list[str]:
        return [self._format_entry(entry) for entry in self.entries]

    def _format_entry(self, entry: tuple[str, str, dict]) -> str:
        component, message, fields = entry
        line = f"{component} {message}"
        if fields:
            details = ", ".join(f"{key}={value}" for key, value in fields.items())
            line = f"{line} [{details}]"
        return line
