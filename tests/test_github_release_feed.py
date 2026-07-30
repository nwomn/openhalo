from __future__ import annotations

import pytest

from openhalo.release_manager import GitHubReleaseFeed


def test_latest_resolves_matching_verified_github_release_assets() -> None:
    api_url = "https://api.github.com/repos/nwomn/openhalo/releases/latest"
    manifest_url = "https://github.com/nwomn/openhalo/releases/download/v0.22.0/release-manifest.json"
    checksum_url = "https://github.com/nwomn/openhalo/releases/download/v0.22.0/SHA256SUMS"
    archive_url = "https://github.com/nwomn/openhalo/releases/download/v0.22.0/openhalo-v0.22.0.tar.gz"
    commit = "a" * 40
    digest = "b" * 64
    documents = {
        api_url: {
            "tag_name": "v0.22.0",
            "draft": False,
            "prerelease": False,
            "assets": [
                {"name": "release-manifest.json", "browser_download_url": manifest_url},
                {"name": "SHA256SUMS", "browser_download_url": checksum_url},
                {"name": "openhalo-v0.22.0.tar.gz", "browser_download_url": archive_url},
            ],
        },
        manifest_url: {
            "version": "0.22.0",
            "tag": "v0.22.0",
            "commit": commit,
            "archive_name": "openhalo-v0.22.0.tar.gz",
            "sha256": digest,
        },
    }

    def download_json(url: str) -> dict:
        return documents[url]

    def download_text(url: str) -> str:
        assert url == checksum_url
        return f"{digest}  openhalo-v0.22.0.tar.gz\n"

    manifest = GitHubReleaseFeed(
        "nwomn/openhalo",
        download_json=download_json,
        download_text=download_text,
    ).latest()

    assert manifest.version == "0.22.0"
    assert manifest.tag == "v0.22.0"
    assert manifest.commit == commit
    assert manifest.archive_name == "openhalo-v0.22.0.tar.gz"
    assert manifest.archive_url == archive_url
    assert manifest.sha256 == digest


def test_latest_rejects_a_manifest_that_is_not_an_object() -> None:
    api_url = "https://api.github.com/repos/nwomn/openhalo/releases/latest"
    manifest_url = "https://github.com/nwomn/openhalo/releases/download/v0.22.0/release-manifest.json"
    checksum_url = "https://github.com/nwomn/openhalo/releases/download/v0.22.0/SHA256SUMS"
    archive_url = "https://github.com/nwomn/openhalo/releases/download/v0.22.0/openhalo-v0.22.0.tar.gz"
    documents = {
        api_url: {
            "tag_name": "v0.22.0",
            "draft": False,
            "prerelease": False,
            "assets": [
                {"name": "release-manifest.json", "browser_download_url": manifest_url},
                {"name": "SHA256SUMS", "browser_download_url": checksum_url},
                {"name": "openhalo-v0.22.0.tar.gz", "browser_download_url": archive_url},
            ],
        },
        manifest_url: [],
    }

    with pytest.raises(ValueError, match="manifest must be an object"):
        GitHubReleaseFeed(
            "nwomn/openhalo",
            download_json=lambda url: documents[url],
            download_text=lambda url: f"{'b' * 64}  openhalo-v0.22.0.tar.gz\n",
        ).latest()


def test_latest_rejects_ambiguous_checksum_entries() -> None:
    api_url = "https://api.github.com/repos/nwomn/openhalo/releases/latest"
    manifest_url = "https://github.com/nwomn/openhalo/releases/download/v0.22.0/release-manifest.json"
    checksum_url = "https://github.com/nwomn/openhalo/releases/download/v0.22.0/SHA256SUMS"
    archive_url = "https://github.com/nwomn/openhalo/releases/download/v0.22.0/openhalo-v0.22.0.tar.gz"
    digest = "b" * 64
    documents = {
        api_url: {
            "tag_name": "v0.22.0",
            "draft": False,
            "prerelease": False,
            "assets": [
                {"name": "release-manifest.json", "browser_download_url": manifest_url},
                {"name": "SHA256SUMS", "browser_download_url": checksum_url},
                {"name": "openhalo-v0.22.0.tar.gz", "browser_download_url": archive_url},
            ],
        },
        manifest_url: {
            "version": "0.22.0",
            "tag": "v0.22.0",
            "commit": "a" * 40,
            "archive_name": "openhalo-v0.22.0.tar.gz",
            "sha256": digest,
        },
    }

    with pytest.raises(ValueError, match="ambiguous checksum"):
        GitHubReleaseFeed(
            "nwomn/openhalo",
            download_json=lambda url: documents[url],
            download_text=lambda url: (
                f"{digest}  openhalo-v0.22.0.tar.gz\n"
                f"{'c' * 64}  openhalo-v0.22.0.tar.gz\n"
            ),
        ).latest()
