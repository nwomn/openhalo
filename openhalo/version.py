"""Version identity for installed and development OpenHalo commands."""

from __future__ import annotations

import re
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from pathlib import Path


_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
_FALLBACK_VERSION = "0.1.0"


def format_cli_version(command: str, *, executable: str | Path | None = None) -> str:
    """Return a human-readable package version and immutable release revision."""
    runtime_executable = Path(executable) if executable is not None else Path(sys.executable)
    revision = _release_commit_from_executable(runtime_executable)
    identity = revision[:7] if revision is not None else "dev"
    return f"{command} {_package_version()} ({identity})"


def _package_version() -> str:
    try:
        return distribution_version("openhalo")
    except PackageNotFoundError:
        return _FALLBACK_VERSION


def _release_commit_from_executable(executable: Path) -> str | None:
    for parent in executable.expanduser().parents:
        if parent.parent.name == "releases" and _COMMIT_PATTERN.fullmatch(parent.name):
            return parent.name
    return None
