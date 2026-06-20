import unittest
from pathlib import Path
from unittest.mock import Mock

from device_edge.host.runtime_control import PythonProcessAdapter


class RuntimeControlTests(unittest.TestCase):
    def test_runtime_status_returns_structured_details(self) -> None:
        adapter = PythonProcessAdapter(
            process_match_substring="personal_runtime.main",
            start_command=["python", "-m", "personal_runtime.main"],
            status_supplier=lambda: {
                "state": "running",
                "pid": 42137,
                "uptime_s": 183,
                "memory_rss_bytes": 28114944,
                "started_at": "2026-06-19T09:00:00Z",
                "last_error": None,
            },
        )

        result = adapter.execute({"capability": "runtime.status", "payload": {}})

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["capability"], "runtime.status")
        self.assertEqual(result["details"]["pid"], 42137)

    def test_runtime_collect_logs_returns_entries_and_tail_text(self) -> None:
        log_path = Mock(spec=Path)
        log_path.exists.return_value = True
        log_path.read_text.return_value = "line one\nline two\n"
        log_path.__str__ = Mock(return_value="/virtual/runtime.log")
        adapter = PythonProcessAdapter(
            process_match_substring="personal_runtime.main",
            start_command=["python", "-m", "personal_runtime.main"],
            log_path=log_path,
        )

        result = adapter.execute({"capability": "runtime.collect_logs", "payload": {}})

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["capability"], "runtime.collect_logs")
        self.assertEqual(result["details"]["entries"][0]["line"], "line one")
        self.assertIn("line two", result["details"]["tail_text"])

    def test_runtime_reload_returns_unsupported_without_reload_command(self) -> None:
        adapter = PythonProcessAdapter(
            process_match_substring="personal_runtime.main",
            start_command=["python", "-m", "personal_runtime.main"],
        )

        result = adapter.execute({"capability": "runtime.reload", "payload": {}})

        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["capability"], "runtime.reload")

    def test_runtime_restart_returns_accepted_with_handoff_expected(self) -> None:
        adapter = PythonProcessAdapter(
            process_match_substring="personal_runtime.main",
            start_command=["python", "-m", "personal_runtime.main"],
            restart_handler=lambda: None,
        )

        result = adapter.execute({"capability": "runtime.restart", "payload": {}})

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["capability"], "runtime.restart")
        self.assertTrue(result["details"]["handoff_expected"])

    def test_runtime_edge_history_returns_bounded_entries_from_supplier(self) -> None:
        adapter = PythonProcessAdapter(
            process_match_substring="personal_runtime.main",
            start_command=["python", "-m", "personal_runtime.main"],
            edge_history_supplier=lambda limit: {
                "history_kind": "observation_window",
                "entries": [
                    {
                        "capability": "runtime.health",
                        "observed_at": "2026-06-19T09:31:00Z",
                        "observations": [
                            {
                                "name": "runtime.health_state",
                                "value": "healthy",
                                "confidence": 1.0,
                            }
                        ],
                    }
                ][:limit],
                "available_entries": 1,
            },
        )

        result = adapter.execute(
            {"capability": "runtime.edge_history", "payload": {"limit": 1}}
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["capability"], "runtime.edge_history")
        self.assertEqual(result["details"]["history_kind"], "observation_window")
        self.assertEqual(result["details"]["returned_entries"], 1)
        self.assertEqual(result["details"]["entries"][0]["capability"], "runtime.health")

    def test_runtime_edge_history_passes_capability_filter_to_supplier(self) -> None:
        captured_filters: list[tuple[int, str | None]] = []

        def supplier(limit: int, capability: str | None = None) -> dict:
            captured_filters.append((limit, capability))
            return {
                "history_kind": "observation_window",
                "entries": [],
                "available_entries": 0,
            }

        adapter = PythonProcessAdapter(
            process_match_substring="personal_runtime.main",
            start_command=["python", "-m", "personal_runtime.main"],
            edge_history_supplier=supplier,
        )

        adapter.execute(
            {
                "capability": "runtime.edge_history",
                "payload": {"limit": 5, "capability": "runtime.health"},
            }
        )

        self.assertEqual(captured_filters, [(5, "runtime.health")])


if __name__ == "__main__":
    unittest.main()
