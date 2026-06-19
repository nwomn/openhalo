"""Runtime control adapters for the first host-edge slice."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Callable


class PythonProcessAdapter:
    def __init__(
        self,
        process_match_substring: str,
        start_command: list[str],
        log_path: Path | None = None,
        reload_command: list[str] | None = None,
        status_supplier: Callable[[], dict] | None = None,
        restart_handler: Callable[[], None] | None = None,
    ) -> None:
        self.process_match_substring = process_match_substring
        self.start_command = start_command
        self.log_path = log_path
        self.reload_command = reload_command
        self.status_supplier = status_supplier or self._default_status_supplier
        self.restart_handler = restart_handler or (lambda: None)

    def execute(self, action: dict) -> dict:
        capability = action["capability"]
        if capability == "runtime.status":
            return self._build_result("ok", capability, self.status_supplier())
        if capability == "runtime.collect_logs":
            return self._build_result("ok", capability, self._collect_logs())
        if capability == "runtime.reload":
            if self.reload_command is None:
                return self._build_result(
                    "unsupported",
                    capability,
                    {"reason": "reload command is not configured"},
                )
            return self._build_result("ok", capability, {"command": self.reload_command})
        if capability == "runtime.restart":
            self.restart_handler()
            return self._build_result(
                "accepted",
                capability,
                {"handoff_expected": True},
            )
        return self._build_result(
            "error",
            capability,
            {"reason": f"unsupported capability: {capability}"},
        )

    def _default_status_supplier(self) -> dict:
        return {
            "state": "unknown",
            "pid": None,
            "uptime_s": None,
            "memory_rss_bytes": None,
            "started_at": None,
            "last_error": None,
            "process_match_substring": self.process_match_substring,
        }

    def _collect_logs(self) -> dict:
        if self.log_path is None or not self.log_path.exists():
            return {
                "entries": [],
                "tail_text": "",
                "captured_at": self._now(),
                "source": str(self.log_path) if self.log_path is not None else None,
            }

        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        entries = [
            {"line": line, "line_number": line_number}
            for line_number, line in enumerate(lines, start=1)
        ]
        return {
            "entries": entries,
            "tail_text": self.log_path.read_text(encoding="utf-8"),
            "captured_at": self._now(),
            "source": str(self.log_path),
        }

    def _build_result(self, status: str, capability: str, details: dict) -> dict:
        return {
            "status": status,
            "capability": capability,
            "details": details,
        }

    def _now(self) -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")
