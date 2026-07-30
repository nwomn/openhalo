#!/usr/bin/env python3
"""Create the three immutable assets required by an OpenHalo GitHub Release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
_TAG_PATTERN = re.compile(r"v?[0-9][A-Za-z0-9._-]*")


def build_release(*, tag: str, commit: str, output: Path, repository: Path) -> dict:
    if not _TAG_PATTERN.fullmatch(tag):
        raise ValueError("release tag must be a simple immutable version tag")
    if not _COMMIT_PATTERN.fullmatch(commit):
        raise ValueError("release commit must be a 40-character lowercase SHA")
    resolved = subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", f"{commit}^{{commit}}"],
        text=True,
    ).strip()
    if resolved != commit:
        raise ValueError("release commit did not resolve exactly")
    output.mkdir(parents=True, exist_ok=True)
    archive_name = f"openhalo-{tag}.tar.gz"
    archive = output / archive_name
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "archive",
            "--format=tar.gz",
            f"--output={archive}",
            resolved,
        ],
        check=True,
    )
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest = {
        "archive_name": archive_name,
        "commit": resolved,
        "sha256": digest,
        "tag": tag,
        "version": tag[1:] if tag.startswith("v") else tag,
    }
    (output / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "SHA256SUMS").write_text(f"{digest}  {archive_name}\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build immutable OpenHalo GitHub Release assets.")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repository", default=Path.cwd(), type=Path)
    args = parser.parse_args(argv)
    manifest = build_release(
        tag=args.tag,
        commit=args.commit,
        output=args.output,
        repository=args.repository,
    )
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
