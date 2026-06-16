import importlib
import tomllib
import unittest
from pathlib import Path

from personal_runtime.protocol import build_connect_frame, validate_frame


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
            ["agent_guard", "device_edge", "personal_runtime"],
        )


class ProtocolTests(unittest.TestCase):
    def test_builds_connect_frame(self) -> None:
        frame = build_connect_frame(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )

        self.assertEqual(frame["type"], "connect")
        self.assertEqual(frame["device"]["device_id"], "desktop-dev-1")

    def test_rejects_frame_without_type(self) -> None:
        with self.assertRaises(ValueError):
            validate_frame({"device": {}})


if __name__ == "__main__":
    unittest.main()
