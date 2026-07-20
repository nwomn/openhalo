from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from openhalo.release_manager import ReleaseLayout
from openhalo.release_manager import ReleaseManifest
from openhalo.release_manager import verify_archive


def _manifest(*, archive: Path, sha256: str, commit: str = "a" * 40) -> ReleaseManifest:
    return ReleaseManifest.from_dict(
        {
            "version": "0.1.0-test",
            "commit": commit,
            "archive_url": archive.as_uri(),
            "sha256": sha256,
        }
    )


def test_manifest_requires_an_immutable_commit_and_sha256() -> None:
    with TemporaryDirectory() as directory:
        archive = Path(directory) / "release.tar.gz"
        archive.write_bytes(b"release")

        with pytest.raises(ValueError, match="40-character commit"):
            _manifest(
                archive=archive,
                sha256=hashlib.sha256(b"release").hexdigest(),
                commit="main",
            )


def test_archive_verification_rejects_tampering_before_activation() -> None:
    with TemporaryDirectory() as directory:
        archive = Path(directory) / "release.tar.gz"
        archive.write_bytes(b"tampered")
        manifest = _manifest(
            archive=archive,
            sha256=hashlib.sha256(b"expected").hexdigest(),
        )

        with pytest.raises(ValueError, match="checksum"):
            verify_archive(archive, manifest)


def test_activation_and_rollback_only_switch_program_releases() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory) / "release-home"
        layout = ReleaseLayout(root)
        first = layout.release_directory("a" * 40)
        second = layout.release_directory("b" * 40)
        first.mkdir(parents=True)
        second.mkdir(parents=True)

        layout.activate("a" * 40)
        layout.activate("b" * 40)
        active_after_rollback = layout.rollback()

        assert layout.active_release() == "a" * 40
        assert active_after_rollback == "a" * 40
        assert layout.previous_release() == "b" * 40


def test_installer_requires_a_pinned_ref_and_creates_user_bin_links() -> None:
    installer = Path(__file__).resolve().parents[1] / "scripts" / "install.sh"

    contents = installer.read_text(encoding="utf-8")

    assert "--ref" in contents
    assert "--edge-only" in contents
    assert "^[0-9a-f]{40}$" in contents
    assert "main" not in contents
    assert ".local/bin" in contents
    assert "current" in contents
