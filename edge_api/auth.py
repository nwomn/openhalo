"""P-256 challenge authentication primitives shared by product Edges and Runtime.

The helpers deliberately expose wire-safe DER/base64url values only.  Callers
must keep private key bytes in their local protected store.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC
from datetime import datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.hazmat.primitives.serialization import NoEncryption
from cryptography.hazmat.primitives.serialization import PrivateFormat
from cryptography.hazmat.primitives.serialization import PublicFormat


AUTH_VERSION = "edge.runtime.v2.auth"


def generate_private_key() -> ec.EllipticCurvePrivateKey:
    """Create the product's only supported device-key algorithm."""

    return ec.generate_private_key(ec.SECP256R1())


def public_key_spki_der(public_key: ec.EllipticCurvePublicKey) -> bytes:
    return public_key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)


def private_key_pkcs8_der(private_key: ec.EllipticCurvePrivateKey) -> bytes:
    return private_key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())


def load_p256_private_key(private_key_der: bytes) -> ec.EllipticCurvePrivateKey:
    from cryptography.hazmat.primitives.serialization import load_der_private_key

    private_key = load_der_private_key(private_key_der, password=None)
    if not isinstance(private_key, ec.EllipticCurvePrivateKey) or not isinstance(
        private_key.curve, ec.SECP256R1
    ):
        raise ValueError("Device private key must be P-256 PKCS8 DER.")
    return private_key


def encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def decode_base64url(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("Expected a non-empty base64url string.")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, UnicodeEncodeError) as error:
        raise ValueError("Invalid base64url value.") from error


def public_key_fingerprint(public_key_der: bytes) -> str:
    return f"sha256:{hashlib.sha256(public_key_der).hexdigest()}"


def is_p256_public_key(public_key_der: bytes) -> bool:
    from cryptography.hazmat.primitives.serialization import load_der_public_key

    try:
        public_key = load_der_public_key(public_key_der)
    except (ValueError, TypeError):
        return False
    return isinstance(public_key, ec.EllipticCurvePublicKey) and isinstance(
        public_key.curve, ec.SECP256R1
    )


def build_challenge_payload(
    *,
    audience: str,
    device_id: str,
    session_id: str,
    challenge_id: str,
    nonce: str,
    expires_at: str,
) -> bytes:
    """Return the canonical signed payload for an Edge authentication proof."""

    required = {
        "audience": audience,
        "device_id": device_id,
        "session_id": session_id,
        "challenge_id": challenge_id,
        "nonce": nonce,
        "expires_at": expires_at,
    }
    if any(not isinstance(value, str) or not value for value in required.values()):
        raise ValueError("Challenge payload fields must be non-empty strings.")
    return "\n".join(
        (
            AUTH_VERSION,
            audience,
            device_id,
            session_id,
            challenge_id,
            nonce,
            expires_at,
        )
    ).encode("utf-8")


def sign_challenge(private_key: ec.EllipticCurvePrivateKey, payload: bytes) -> bytes:
    return private_key.sign(payload, ec.ECDSA(hashes.SHA256()))


def verify_challenge_signature(
    public_key_der: bytes,
    payload: bytes,
    signature: bytes,
) -> bool:
    try:
        from cryptography.hazmat.primitives.serialization import load_der_public_key

        public_key = load_der_public_key(public_key_der)
        if not is_p256_public_key(public_key_der):
            return False
        public_key.verify(signature, payload, ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def is_expired(expires_at: str, *, now: datetime) -> bool:
    expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    return expiry < now.astimezone(UTC)
