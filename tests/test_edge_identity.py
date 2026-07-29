from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from device_edge.shared.identity import load_or_create_identity


def test_device_identity_is_p256_and_private_file_is_owner_only() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory) / ".openhalo"

        identity = load_or_create_identity(root, "terminal-edge-1")
        reloaded = load_or_create_identity(root, "terminal-edge-1")
        key_path = root / "devices" / "terminal-edge-1" / "identity.ed25519"

        assert identity.public_key == reloaded.public_key
        assert identity.public_key_fingerprint.startswith("sha256:")
        assert key_path.exists()
        assert os.stat(key_path).st_mode & 0o777 == 0o600
        assert os.stat(key_path.parent).st_mode & 0o777 == 0o700
