from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def test_build_release_writes_archive_manifest_and_checksum_for_exact_commit() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    script = repository_root / "scripts/build_release.py"
    with TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "source"
        output = root / "output"
        source.mkdir()
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "config", "user.email", "test@example.test"], check=True)
        subprocess.run(["git", "-C", str(source), "config", "user.name", "Test"], check=True)
        (source / "README.md").write_text("release source\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(source), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(source), "commit", "-qm", "release source"], check=True)
        commit = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
        ).strip()

        subprocess.run(
            [
                sys.executable,
                str(script),
                "--tag",
                "v0.22.0",
                "--commit",
                commit,
                "--output",
                str(output),
                "--repository",
                str(source),
            ],
            check=True,
        )

        archive = output / "openhalo-v0.22.0.tar.gz"
        manifest = json.loads((output / "release-manifest.json").read_text(encoding="utf-8"))
        checksum = (output / "SHA256SUMS").read_text(encoding="utf-8")
        assert archive.is_file()
        assert manifest == {
            "archive_name": archive.name,
            "commit": commit,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "tag": "v0.22.0",
            "version": "0.22.0",
        }
        assert checksum == f"{manifest['sha256']}  {archive.name}\n"
