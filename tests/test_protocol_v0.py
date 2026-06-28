import importlib
import tomllib
import unittest
from pathlib import Path

from edge_api.protocol import API_VERSION
from edge_api.protocol import build_capability_announce_frame
from edge_api.protocol import build_connect_frame
from edge_api.protocol import build_observation_push_frame
from edge_api.protocol import validate_frame


class ImportSmokeTests(unittest.TestCase):
    def test_runtime_package_imports(self) -> None:
        self.assertEqual(
            importlib.import_module("personal_runtime").__doc__,
            "Personal runtime v0 package.",
        )
        self.assertEqual(
            importlib.import_module("device_edge").__doc__,
            "Device edge v0 package.",
        )

    def test_pyproject_declares_explicit_package_discovery(self) -> None:
        payload = tomllib.loads(
            Path("pyproject.toml").read_text(encoding="utf-8")
        )

        self.assertEqual(
            payload["tool"]["setuptools"]["packages"]["find"]["include"],
            ["agent_guard", "device_edge", "edge_api", "personal_runtime"],
        )


class ProtocolTests(unittest.TestCase):
    def test_builds_connect_frame(self) -> None:
        frame = build_connect_frame(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )

        self.assertEqual(frame["type"], "connect")
        self.assertEqual(frame["api_version"], API_VERSION)
        self.assertEqual(frame["device"]["device_id"], "desktop-dev-1")

    def test_builds_object_capability_announce_frame(self) -> None:
        frame = build_capability_announce_frame(
            device_id="desktop-dev-1",
            capabilities=[
                {
                    "name": "notification.show",
                    "direction": "runtime_to_edge",
                }
            ],
        )

        self.assertEqual(frame["api_version"], API_VERSION)
        self.assertEqual(frame["type"], "capability_announce")
        self.assertEqual(
            frame["capabilities"][0],
            {
                "name": "notification.show",
                "direction": "runtime_to_edge",
            },
        )

    def test_builds_observation_push_frame(self) -> None:
        frame = build_observation_push_frame(
            device_id="host-edge-1",
            capability="runtime.health",
            observations=[
                {
                    "name": "runtime.health_state",
                    "value": "healthy",
                    "observed_at": "2026-06-29T10:00:00Z",
                    "confidence": 1.0,
                }
            ],
        )

        self.assertEqual(frame["api_version"], API_VERSION)
        self.assertEqual(frame["type"], "observation_push")
        self.assertEqual(frame["capability"], "runtime.health")
        self.assertEqual(
            frame["observations"][0]["name"],
            "runtime.health_state",
        )

    def test_rejects_frame_without_type(self) -> None:
        with self.assertRaises(ValueError):
            validate_frame({"device": {}})


if __name__ == "__main__":
    unittest.main()
