"""Immutable program-release bookkeeping for a personal OpenHalo install."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import venv
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import quote
from urllib.parse import urlparse
from urllib.request import Request
from urllib.request import urlopen


_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    commit: str
    sha256: str
    archive_url: str | None = None
    tag: str | None = None
    archive_name: str | None = None

    @classmethod
    def from_dict(cls, payload: object) -> "ReleaseManifest":
        if not isinstance(payload, dict):
            raise ValueError("release manifest must be an object")
        version = payload.get("version")
        commit = payload.get("commit")
        archive_url = payload.get("archive_url")
        sha256 = payload.get("sha256")
        tag = payload.get("tag")
        archive_name = payload.get("archive_name")
        if not isinstance(version, str) or not version:
            raise ValueError("release manifest requires a version")
        if not isinstance(commit, str) or not _COMMIT_PATTERN.fullmatch(commit):
            raise ValueError("release manifest requires a 40-character commit")
        if archive_url is not None and (
            not isinstance(archive_url, str)
            or urlparse(archive_url).scheme not in {"https", "file"}
        ):
            raise ValueError("release manifest archive URL must use HTTPS or file")
        if archive_url is None and not isinstance(archive_name, str):
            raise ValueError("release manifest requires an archive name")
        if tag is not None and (not isinstance(tag, str) or not tag):
            raise ValueError("release manifest tag must be a non-empty string")
        if archive_name is not None and (
            not isinstance(archive_name, str)
            or not archive_name
            or Path(archive_name).name != archive_name
        ):
            raise ValueError("release manifest archive name must be a filename")
        if not isinstance(sha256, str) or not _SHA256_PATTERN.fullmatch(sha256):
            raise ValueError("release manifest requires a SHA-256 checksum")
        return cls(
            version=version,
            commit=commit,
            sha256=sha256,
            archive_url=archive_url,
            tag=tag,
            archive_name=archive_name,
        )


class GitHubReleaseFeed:
    """Resolve one complete immutable Runtime release from GitHub Release assets."""

    def __init__(
        self,
        repository: str,
        *,
        download_json: Callable[[str], object] | None = None,
        download_text: Callable[[str], str] | None = None,
    ) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("GitHub repository must be an owner/name pair")
        self.repository = repository
        self._download_json = download_json or _download_json
        self._download_text = download_text or _download_text

    def latest(self) -> ReleaseManifest:
        manifest = ReleaseManifest.from_dict(
            self._download_json(self._latest_asset_url("release-manifest.json"))
        )
        if manifest.tag is None:
            raise ValueError("release manifest requires a tag")
        if manifest.archive_name is None:
            raise ValueError("release manifest requires an archive name")
        expected_checksum = _checksum_for(
            self._download_text(self._release_asset_url(manifest.tag, "SHA256SUMS")),
            manifest.archive_name,
        )
        if expected_checksum != manifest.sha256:
            raise ValueError("release manifest checksum does not match SHA256SUMS")
        return ReleaseManifest(
            version=manifest.version,
            commit=manifest.commit,
            sha256=manifest.sha256,
            archive_url=self._release_asset_url(manifest.tag, manifest.archive_name),
            tag=manifest.tag,
            archive_name=manifest.archive_name,
        )

    def _latest_asset_url(self, name: str) -> str:
        return (
            f"https://github.com/{self.repository}/releases/latest/download/"
            f"{quote(name, safe='')}"
        )

    def _release_asset_url(self, tag: str, name: str) -> str:
        return (
            f"https://github.com/{self.repository}/releases/download/{quote(tag, safe='')}/"
            f"{quote(name, safe='')}"
        )


def _checksum_for(contents: str, archive_name: str) -> str:
    matches: list[str] = []
    for line in contents.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2 and parts[1].lstrip(" *") == archive_name:
            checksum = parts[0]
            if _SHA256_PATTERN.fullmatch(checksum):
                matches.append(checksum)
                continue
            raise ValueError("SHA256SUMS contains an invalid checksum")
    if not matches:
        raise ValueError(f"SHA256SUMS has no checksum for {archive_name}")
    if len(matches) != 1:
        raise ValueError(f"SHA256SUMS has an ambiguous checksum for {archive_name}")
    return matches[0]


def _download_json(url: str) -> dict:
    return json.loads(_download_text(url))


def _download_text(url: str) -> str:
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "openhalo"})
    with urlopen(request, timeout=15) as response:  # noqa: S310 - URL was validated by caller.
        if urlparse(response.url).scheme != "https":
            raise ValueError("GitHub Release download redirected outside HTTPS")
        return response.read().decode("utf-8")


class ReleaseStager:
    """Build a verified candidate under the immutable release root."""

    def __init__(
        self,
        layout: "ReleaseLayout",
        *,
        download: Callable[[str, Path], None] | None = None,
        install: Callable[[Path, Path], None] | None = None,
    ) -> None:
        self.layout = layout
        self._download = download or _download_archive
        self._install = install or _install_release

    def stage(self, manifest: ReleaseManifest) -> Path:
        if manifest.archive_url is None:
            raise ValueError("release manifest has no resolved archive URL")
        target = self.layout.release_directory(manifest.commit)
        python = target / "venv/bin/python"
        if target.exists():
            if python.is_file():
                return target
            raise ValueError(f"existing release is incomplete: {manifest.commit}")

        self.layout._ensure_private_directories()
        staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=self.layout.releases_directory))
        installed_target = False
        try:
            archive = staging / "release.tar.gz"
            self._download(manifest.archive_url, archive)
            verify_archive(archive, manifest)
            source = staging / "source"
            _extract_archive(archive, source)
            os.replace(staging, target)
            installed_target = True
            self._install(target / "source", target)
            if not (target / "venv/bin/python").is_file():
                raise RuntimeError("release installation did not create a Python executable")
            return target
        except Exception:
            shutil.rmtree(target if installed_target else staging, ignore_errors=True)
            raise


def _download_archive(url: str, destination: Path) -> None:
    if urlparse(url).scheme not in {"https", "file"}:
        raise ValueError("release archive URL must use HTTPS or file")
    request = Request(url, headers={"User-Agent": "openhalo"})
    with urlopen(request, timeout=60) as response:  # noqa: S310 - URL was validated above.
        if urlparse(response.url).scheme not in {"https", "file"}:
            raise ValueError("release archive download redirected outside HTTPS")
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def _extract_archive(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:*") as input_archive:
        for member in input_archive.getmembers():
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("release archive contains an unsafe path")
            if not (member.isdir() or member.isfile()):
                raise ValueError("release archive contains an unsupported member type")
            target = destination.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = input_archive.extractfile(member)
            if source is None:
                raise ValueError("release archive member could not be read")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _install_release(source: Path, release: Path) -> None:
    environment = venv.EnvBuilder(with_pip=True)
    environment.create(release / "venv")
    python = release / "venv/bin/python"
    subprocess.run(
        [str(python), "-m", "pip", "install", "--upgrade", "pip"],
        check=True,
    )
    subprocess.run([str(python), "-m", "pip", "install", str(source)], check=True)


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
        if previous == commit:
            return commit
        self._ensure_private_directories()
        self._set_release_links(
            current_target=target,
            previous_target=self.release_directory(previous) if previous is not None else None,
        )
        return commit

    def rollback(self) -> str:
        current = self.active_release()
        previous = self.previous_release()
        if current is None or previous is None:
            raise ValueError("no previous OpenHalo release is available")
        self._set_release_links(
            current_target=self.release_directory(previous),
            previous_target=self.release_directory(current),
        )
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

    def _set_release_links(self, *, current_target: Path, previous_target: Path | None) -> None:
        current_before = self.active_release()
        previous_before = self.previous_release()
        try:
            self._switch_link(self.current_path, current_target)
            if previous_target is None:
                self._clear_link(self.previous_path)
            else:
                self._switch_link(self.previous_path, previous_target)
        except Exception:
            self._restore_link(self.current_path, current_before)
            self._restore_link(self.previous_path, previous_before)
            raise

    def _restore_link(self, link: Path, release: str | None) -> None:
        if release is None:
            self._clear_link(link)
            return
        self._switch_link(link, self.release_directory(release))

    def _clear_link(self, link: Path) -> None:
        if link.is_symlink():
            link.unlink()


def verify_archive(path: Path, manifest: ReleaseManifest) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != manifest.sha256:
        raise ValueError("release archive checksum did not match")
