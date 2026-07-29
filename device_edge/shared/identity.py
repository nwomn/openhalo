"""Protected local P-256 identities for file-backed Device Edges."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from edge_api.auth import encode_base64url
from edge_api.auth import generate_private_key
from edge_api.auth import load_p256_private_key
from edge_api.auth import private_key_pkcs8_der
from edge_api.auth import public_key_fingerprint
from edge_api.auth import public_key_spki_der


@dataclass(frozen=True)
class DeviceIdentity:
    private_key: object
    public_key: str
    public_key_fingerprint: str
    path: Path


def load_or_create_identity(home: Path, device_id: str) -> DeviceIdentity:
    if not isinstance(device_id, str) or not device_id:
        raise ValueError("device_id must not be empty")
    identity_directory = home / "devices" / device_id
    identity_directory.mkdir(parents=True, exist_ok=True)
    os.chmod(home, 0o700)
    os.chmod(home / "devices", 0o700)
    os.chmod(identity_directory, 0o700)
    path = identity_directory / "identity.ed25519"
    if path.exists():
        os.chmod(path, 0o600)
        private_key = load_p256_private_key(path.read_bytes())
    else:
        private_key = generate_private_key()
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(private_key_pkcs8_der(private_key))
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        os.chmod(path, 0o600)
    public_key_der = public_key_spki_der(private_key.public_key())
    return DeviceIdentity(
        private_key=private_key,
        public_key=encode_base64url(public_key_der),
        public_key_fingerprint=public_key_fingerprint(public_key_der),
        path=path,
    )


def create_ephemeral_identity() -> DeviceIdentity:
    """Create a non-persistent identity for isolated tests only."""

    private_key = generate_private_key()
    public_key_der = public_key_spki_der(private_key.public_key())
    return DeviceIdentity(
        private_key=private_key,
        public_key=encode_base64url(public_key_der),
        public_key_fingerprint=public_key_fingerprint(public_key_der),
        path=Path(),
    )
