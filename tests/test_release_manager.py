from __future__ import annotations

import hashlib
import io
import shutil
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from openhalo.release_manager import ReleaseLayout
from openhalo.release_manager import ReleaseManifest
from openhalo.release_manager import ReleaseStager
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


def test_activation_restores_both_links_when_previous_link_switch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory) / "release-home"
        layout = ReleaseLayout(root)
        first = "a" * 40
        second = "b" * 40
        third = "c" * 40
        for commit in (first, second, third):
            layout.release_directory(commit).mkdir(parents=True)
        layout.activate(first)
        layout.activate(second)
        original_switch = layout._switch_link
        calls = 0

        def fail_once(link: Path, target: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("disk error")
            original_switch(link, target)

        monkeypatch.setattr(layout, "_switch_link", fail_once)

        with pytest.raises(OSError, match="disk error"):
            layout.activate(third)

        assert layout.active_release() == second
        assert layout.previous_release() == first


def test_installer_requires_a_pinned_ref_and_creates_user_bin_links() -> None:
    installer = Path(__file__).resolve().parents[1] / "scripts" / "install.sh"

    contents = installer.read_text(encoding="utf-8")

    assert "--ref" in contents
    assert "--edge-only" in contents
    assert "^[0-9a-f]{40}$" in contents
    assert "main" not in contents
    assert ".local/bin" in contents
    assert "current" in contents


def test_staging_a_verified_release_preserves_current_program_and_personal_data() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        archive = root / "candidate.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            payload = b"[project]\nname = 'candidate'\nversion = '0.0.0'\n"
            member = tarfile.TarInfo("pyproject.toml")
            member.size = len(payload)
            output.addfile(member, io.BytesIO(payload))
        layout = ReleaseLayout(root / "releases")
        current = "a" * 40
        candidate = "b" * 40
        current_python = layout.release_directory(current) / "venv/bin/python"
        current_python.parent.mkdir(parents=True)
        current_python.touch()
        layout.activate(current)
        personal_state = root / "home/runtime/state.json"
        personal_state.parent.mkdir(parents=True)
        personal_state.write_text('{"owner": "unchanged"}\n', encoding="utf-8")
        manifest = _manifest(
            archive=archive,
            sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
            commit=candidate,
        )

        def install(source: Path, release: Path) -> None:
            assert (source / "pyproject.toml").is_file()
            assert release == layout.release_directory(candidate)
            python = release / "venv/bin/python"
            python.parent.mkdir(parents=True)
            python.touch()
            launcher = release / "venv/bin/openhalo"
            launcher.write_text(f"#!{python}\n", encoding="utf-8")

        staged = ReleaseStager(
            layout,
            download=lambda url, destination: shutil.copyfile(Path(url.removeprefix("file://")), destination),
            install=install,
        ).stage(manifest)

        assert staged == layout.release_directory(candidate)
        assert (staged / "venv/bin/python").is_file()
        assert (staged / "venv/bin/openhalo").read_text(encoding="utf-8") == (
            f"#!{staged / 'venv/bin/python'}\n"
        )
        assert layout.active_release() == current
        assert personal_state.read_text(encoding="utf-8") == '{"owner": "unchanged"}\n'
