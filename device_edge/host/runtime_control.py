"""Runtime control adapters for the first host-edge slice."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path


class PythonProcessAdapter:
    def __init__(
        self,
        process_match_substring: str,
        start_command: list[str],
        log_path: Path | None = None,
        reload_command: list[str] | None = None,
        status_supplier: Callable[[], dict] | None = None,
        restart_handler: Callable[[], None] | None = None,
        edge_history_supplier: Callable[[int], dict] | None = None,
        proc_root: Path = Path("/proc"),
    ) -> None:
        self.process_match_substring = process_match_substring
        self.start_command = start_command
        self.log_path = log_path
        self.reload_command = reload_command
        self.proc_root = proc_root
        self.status_supplier = status_supplier or self._discover_runtime_status
        self.restart_handler = restart_handler or (lambda: None)
        self.edge_history_supplier = edge_history_supplier or self._default_edge_history

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
        if capability == "runtime.edge_history":
            limit = action["payload"].get("limit", 20)
            requested_capability = action["payload"].get("capability")
            history_supplier = action["payload"].get(
                "history_supplier",
                self.edge_history_supplier,
            )
            supplier_parameters = inspect.signature(history_supplier).parameters
            if len(supplier_parameters) >= 2:
                details = history_supplier(limit, requested_capability)
            else:
                details = history_supplier(limit)
            details.setdefault("history_kind", "observation_window")
            details.setdefault("entries", [])
            details.setdefault("available_entries", len(details["entries"]))
            details["returned_entries"] = len(details["entries"])
            return self._build_result("ok", capability, details)
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

    def _discover_runtime_status(self) -> dict:
        for pid_dir in self.proc_root.iterdir():
            if not pid_dir.is_dir() or not pid_dir.name.isdigit():
                continue

            cmdline_path = pid_dir / "cmdline"
            if not cmdline_path.exists():
                continue

            raw_cmdline = cmdline_path.read_text(encoding="utf-8")
            command = raw_cmdline.replace("\x00", " ").strip()
            if self.process_match_substring not in command:
                continue

            memory_rss_bytes = 0
            statm_path = pid_dir / "statm"
            if statm_path.exists():
                rss_pages = int(statm_path.read_text(encoding="utf-8").split()[1])
                memory_rss_bytes = rss_pages * 4096

            return {
                "state": "running",
                "pid": int(pid_dir.name),
                "uptime_s": None,
                "memory_rss_bytes": memory_rss_bytes,
                "started_at": None,
                "last_error": None,
                "process_match_substring": self.process_match_substring,
            }

        return self._default_status_payload()

    def _default_status_payload(self) -> dict:
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

    def _default_edge_history(
        self,
        limit: int,
        capability: str | None = None,
    ) -> dict:
        del limit
        del capability
        return {
            "history_kind": "observation_window",
            "entries": [],
            "available_entries": 0,
        }

    def _build_result(self, status: str, capability: str, details: dict) -> dict:
        return {
            "status": status,
            "capability": capability,
            "details": details,
        }

    def _now(self) -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

__all__ = ["PythonProcessAdapter"]
