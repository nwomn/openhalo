import importlib.util
import unittest
from pathlib import Path


class EdgeLayoutTests(unittest.TestCase):
    def test_legacy_top_level_edge_modules_are_removed(self) -> None:
        legacy_paths = [
            Path("device_edge/cli_edge.py"),
            Path("device_edge/host_daemon.py"),
            Path("device_edge/host_observers.py"),
            Path("device_edge/runtime_control.py"),
            Path("device_edge/session_client.py"),
            Path("device_edge/capability_runtime.py"),
            Path("device_edge/local_actions.py"),
        ]

        for path in legacy_paths:
            self.assertFalse(path.exists(), f"legacy module should be removed: {path}")

        self.assertIsNone(importlib.util.find_spec("device_edge.cli_edge"))
        self.assertIsNone(importlib.util.find_spec("device_edge.host_daemon"))
        self.assertIsNone(importlib.util.find_spec("device_edge.host_observers"))
        self.assertIsNone(importlib.util.find_spec("device_edge.runtime_control"))
        self.assertIsNone(importlib.util.find_spec("device_edge.session_client"))
        self.assertIsNone(importlib.util.find_spec("device_edge.capability_runtime"))
        self.assertIsNone(importlib.util.find_spec("device_edge.local_actions"))


if __name__ == "__main__":
    unittest.main()
