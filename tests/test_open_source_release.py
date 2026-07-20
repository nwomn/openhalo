"""Regression checks for the repository's public collaboration baseline."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OpenSourceReleaseTests(unittest.TestCase):
    def test_root_license_is_mit(self) -> None:
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")

        self.assertIn("MIT License", license_text)
        self.assertIn("Permission is hereby granted", license_text)

    def test_security_policy_uses_private_reporting(self) -> None:
        security_text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

        self.assertIn("Report a vulnerability", security_text)
        self.assertIn("Do not open a public issue", security_text)

    def test_contribution_guide_requires_safe_local_verification(self) -> None:
        contributing_text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

        self.assertIn("bin/test -m pytest -q tests", contributing_text)
        self.assertIn("Do not commit credentials", contributing_text)

    def test_development_extra_declares_test_tools(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        development_dependencies = metadata["project"]["optional-dependencies"]["dev"]

        self.assertTrue(any(dependency.startswith("pytest") for dependency in development_dependencies))
        self.assertTrue(any(dependency.startswith("coverage") for dependency in development_dependencies))

    def test_ci_covers_python_and_android_unit_tests(self) -> None:
        workflow_text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("python -m venv .venv", workflow_text)
        self.assertIn(".venv/bin/python -m pip install -e \".[dev]\"", workflow_text)
        self.assertIn("PYTHONPATH=. .venv/bin/python -m coverage run", workflow_text)
        self.assertIn("coverage run", workflow_text)
        self.assertIn("-m pytest -q tests", workflow_text)
        self.assertIn("bash ./gradlew testDebugUnitTest", workflow_text)
