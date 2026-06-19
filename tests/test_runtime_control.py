import unittest
from pathlib import Path
from unittest.mock import Mock

from device_edge.runtime_control import PythonProcessAdapter


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


if __name__ == "__main__":
    unittest.main()
