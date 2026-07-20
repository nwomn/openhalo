"""Immutable program-release bookkeeping for a personal OpenHalo install."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    commit: str
    archive_url: str
    sha256: str

    @classmethod
    def from_dict(cls, payload: dict) -> "ReleaseManifest":
        version = payload.get("version")
        commit = payload.get("commit")
        archive_url = payload.get("archive_url")
        sha256 = payload.get("sha256")
        if not isinstance(version, str) or not version:
            raise ValueError("release manifest requires a version")
        if not isinstance(commit, str) or not _COMMIT_PATTERN.fullmatch(commit):
            raise ValueError("release manifest requires a 40-character commit")
        if not isinstance(archive_url, str) or urlparse(archive_url).scheme not in {
            "https",
            "file",
        }:
            raise ValueError("release manifest requires an HTTPS or file archive URL")
        if not isinstance(sha256, str) or not _SHA256_PATTERN.fullmatch(sha256):
            raise ValueError("release manifest requires a SHA-256 checksum")
        return cls(version=version, commit=commit, archive_url=archive_url, sha256=sha256)


class ReleaseLayout:
    """Atomically select an executable release without touching personal data."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser()

    @property
    def releases_directory(self) -> Path:
        return self.root / "releases"

    @property
    def current_path(self) -> Path:
        return self.root / "current"

    @property
    def previous_path(self) -> Path:
        return self.root / "previous"

    def release_directory(self, commit: str) -> Path:
        if not _COMMIT_PATTERN.fullmatch(commit):
            raise ValueError("release commit must be a 40-character commit")
        return self.releases_directory / commit

    def active_release(self) -> str | None:
        return self._linked_release(self.current_path)

    def previous_release(self) -> str | None:
        return self._linked_release(self.previous_path)

    def activate(self, commit: str) -> str:
        target = self.release_directory(commit)
        if not target.is_dir():
            raise ValueError(f"release is not staged: {commit}")
        previous = self.active_release()
        self._ensure_private_directories()
        self._switch_link(self.current_path, target)
        if previous is not None and previous != commit:
            self._switch_link(self.previous_path, self.release_directory(previous))
        return commit

    def rollback(self) -> str:
        current = self.active_release()
        previous = self.previous_release()
        if current is None or previous is None:
            raise ValueError("no previous OpenHalo release is available")
        self._switch_link(self.current_path, self.release_directory(previous))
        self._switch_link(self.previous_path, self.release_directory(current))
        return previous

    def _ensure_private_directories(self) -> None:
        for directory in (self.root, self.releases_directory):
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 0o700)

    def _linked_release(self, link: Path) -> str | None:
        if not link.is_symlink():
            return None
        try:
            target = link.resolve(strict=True)
        except OSError:
            return None
        if target.parent != self.releases_directory:
            return None
        name = target.name
        return name if _COMMIT_PATTERN.fullmatch(name) else None

    def _switch_link(self, link: Path, target: Path) -> None:
        self._ensure_private_directories()
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.root,
            prefix=f".{link.name}.",
            suffix=".tmp",
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            temporary_path.unlink()
            temporary_path.symlink_to(target)
            os.replace(temporary_path, link)
        finally:
            temporary_path.unlink(missing_ok=True)


def verify_archive(path: Path, manifest: ReleaseManifest) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != manifest.sha256:
        raise ValueError("release archive checksum did not match")
