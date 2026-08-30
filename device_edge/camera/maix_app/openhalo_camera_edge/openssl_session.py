"""OpenSSL-backed P-256 session bootstrap for the MaixCAM Camera Edge.

This module intentionally has no dependency on ``cryptography``.  MaixCAM's
RISC-V image provides OpenSSL and ``websockets``, but does not ship a compatible
``cryptography`` wheel or a compiler toolchain.  It produces the same P-256
PKCS#8, SPKI DER, and DER ECDSA-SHA256 values as the public Edge API.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import websockets


API_VERSION = "edge.runtime.v2"
AUTH_VERSION = "edge.runtime.v2.auth"


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _validate_endpoint(url: str) -> str:
    parsed = urlsplit(url)
    if not isinstance(url, str) or not url or parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
        raise ValueError("Runtime endpoint must be a complete ws:// or wss:// URL.")
    return url


def _validate_device_id(device_id: str) -> str:
    if not isinstance(device_id, str) or not device_id or device_id in {".", ".."} or "/" in device_id or "\\" in device_id:
        raise ValueError("device_id must be a non-empty path-safe value.")
    return device_id


def _run_openssl(openssl_path: str, arguments: list[str]) -> None:
    result = subprocess.run(
        [openssl_path, *arguments],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "unknown OpenSSL failure"
        raise RuntimeError(f"OpenSSL command failed: {detail}")


def _public_spki_der(openssl_path: str, private_key_path: Path) -> bytes:
    with tempfile.TemporaryDirectory(dir=private_key_path.parent, prefix="public-") as temporary_directory:
        output_path = Path(temporary_directory) / "identity.spki.der"
        _run_openssl(
            openssl_path,
            [
                "pkey",
                "-inform",
                "DER",
                "-in",
                str(private_key_path),
                "-pubout",
                "-outform",
                "DER",
                "-out",
                str(output_path),
            ],
        )
        return output_path.read_bytes()


def build_challenge_payload(
    *,
    audience: str,
    device_id: str,
    session_id: str,
    challenge_id: str,
    nonce: str,
    expires_at: str,
) -> bytes:
    values = (audience, device_id, session_id, challenge_id, nonce, expires_at)
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("Challenge payload fields must be non-empty strings.")
    return "\n".join(
        (AUTH_VERSION, audience, device_id, session_id, challenge_id, nonce, expires_at)
    ).encode("utf-8")


@dataclass(frozen=True)
class OpenSslP256Identity:
    """A file-backed P-256 identity whose private-key operations use OpenSSL."""

    private_key_path: Path
    public_key: str
    public_key_fingerprint: str
    openssl_path: str

    def sign(self, payload: bytes) -> bytes:
        if not isinstance(payload, bytes) or not payload:
            raise ValueError("OpenSSL signer payload must be non-empty bytes.")
        with tempfile.TemporaryDirectory(
            dir=self.private_key_path.parent,
            prefix="signature-",
        ) as temporary_directory:
            directory = Path(temporary_directory)
            payload_path = directory / "payload.bin"
            signature_path = directory / "signature.der"
            payload_path.write_bytes(payload)
            _run_openssl(
                self.openssl_path,
                [
                    "dgst",
                    "-sha256",
                    "-keyform",
                    "DER",
                    "-sign",
                    str(self.private_key_path),
                    "-out",
                    str(signature_path),
                    str(payload_path),
                ],
            )
            return signature_path.read_bytes()


def load_or_create_openssl_identity(
    home: Path,
    device_id: str,
    *,
    openssl_path: str = "openssl",
) -> OpenSslP256Identity:
    """Load or create a persistent prime256v1 private key without pyca/cryptography."""

    device_id = _validate_device_id(device_id)
    identity_directory = Path(home) / "devices" / device_id
    identity_directory.mkdir(parents=True, exist_ok=True)
    for path in (Path(home), Path(home) / "devices", identity_directory):
        os.chmod(path, 0o700)
    private_key_path = identity_directory / "identity.p256.pk8.der"
    if not private_key_path.exists():
        with tempfile.TemporaryDirectory(dir=identity_directory, prefix="create-") as temporary_directory:
            directory = Path(temporary_directory)
            pem_path = directory / "identity.pem"
            der_path = directory / "identity.pk8.der"
            _run_openssl(
                openssl_path,
                ["ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", str(pem_path)],
            )
            _run_openssl(
                openssl_path,
                [
                    "pkcs8",
                    "-topk8",
                    "-nocrypt",
                    "-in",
                    str(pem_path),
                    "-outform",
                    "DER",
                    "-out",
                    str(der_path),
                ],
            )
            os.chmod(der_path, 0o600)
            os.replace(der_path, private_key_path)
    os.chmod(private_key_path, 0o600)
    public_key_der = _public_spki_der(openssl_path, private_key_path)
    return OpenSslP256Identity(
        private_key_path=private_key_path,
        public_key=_base64url(public_key_der),
        public_key_fingerprint=f"sha256:{hashlib.sha256(public_key_der).hexdigest()}",
        openssl_path=openssl_path,
    )


@dataclass(frozen=True)
class CameraEdgeCredentials:
    device_id: str
    display_name: str
    public_key_fingerprint: str


class OpenSslCameraSessionClient:
    """Minimal pairing and reconnect client for a MaixCAM Camera Edge.

    Capture, feature extraction, evidence buffering, and action dispatch stay
    outside this bootstrap module.  It owns only the normal public Edge API
    session boundary.
    """

    def __init__(
        self,
        *,
        device_id: str,
        audience: str,
        identity_home: Path,
        display_name: str = "Camera Edge",
        device_type: str = "camera-edge",
        openssl_path: str = "openssl",
    ) -> None:
        self.device_id = _validate_device_id(device_id)
        self.audience = _validate_endpoint(audience)
        if not isinstance(display_name, str) or not display_name:
            raise ValueError("display_name must be non-empty.")
        if not isinstance(device_type, str) or not device_type:
            raise ValueError("device_type must be non-empty.")
        self.display_name = display_name
        self.device_type = device_type
        self.identity = load_or_create_openssl_identity(
            identity_home,
            self.device_id,
            openssl_path=openssl_path,
        )

    async def pair(self, pairing_code: str, capabilities: list[str | dict]) -> CameraEdgeCredentials:
        if not isinstance(pairing_code, str) or not pairing_code:
            raise ValueError("pairing_code must be non-empty.")
        session_id = f"pair-{secrets.token_urlsafe(16)}"
        connect = self._build_connect_frame(
            session_id=session_id,
            pairing_code=pairing_code,
        )
        async with websockets.connect(self.audience) as websocket:
            await websocket.send(json.dumps(connect))
            await self._complete_authentication(websocket, session_id)
            await websocket.send(json.dumps(self.build_capability_announce_frame(session_id, capabilities)))
        return CameraEdgeCredentials(
            device_id=self.device_id,
            display_name=self.display_name,
            public_key_fingerprint=self.identity.public_key_fingerprint,
        )

    async def authenticate(self, websocket, capabilities: list[str | dict]) -> str:
        """Authenticate an already-open WebSocket and register capabilities."""

        session_id = f"session-{secrets.token_urlsafe(16)}"
        await websocket.send(json.dumps(self._build_connect_frame(session_id=session_id)))
        await self._complete_authentication(websocket, session_id)
        await websocket.send(json.dumps(self.build_capability_announce_frame(session_id, capabilities)))
        return session_id

    def build_capability_announce_frame(
        self,
        session_id: str,
        capabilities: list[str | dict],
    ) -> dict:
        if not isinstance(capabilities, list) or not capabilities:
            raise ValueError("Camera Edge must register at least one capability.")
        return {
            "api_version": API_VERSION,
            "type": "capability_announce",
            "device_id": self.device_id,
            "session_id": session_id,
            "capabilities": capabilities,
        }

    def _build_connect_frame(self, *, session_id: str, pairing_code: str | None = None) -> dict:
        frame = {
            "api_version": API_VERSION,
            "type": "connect",
            "device": {
                "device_id": self.device_id,
                "device_type": self.device_type,
            },
            "audience": self.audience,
            "session_id": session_id,
        }
        if pairing_code is not None:
            frame["auth"] = {
                "kind": "pairing",
                "pairing_code": pairing_code,
                "public_key": self.identity.public_key,
                "display_name": self.display_name,
            }
        return frame

    async def _complete_authentication(self, websocket, session_id: str) -> None:
        challenge_frame = json.loads(await websocket.recv())
        if challenge_frame.get("type") == "error":
            raise ValueError(challenge_frame.get("message", "Runtime rejected the Camera Edge."))
        challenge = challenge_frame.get("challenge")
        if (
            challenge_frame.get("type") != "auth_challenge"
            or challenge_frame.get("device_id") != self.device_id
            or challenge_frame.get("session_id") != session_id
            or challenge_frame.get("audience") != self.audience
            or not isinstance(challenge, dict)
        ):
            raise ValueError("Runtime returned an invalid authentication challenge.")
        try:
            payload = build_challenge_payload(
                audience=self.audience,
                device_id=self.device_id,
                session_id=session_id,
                challenge_id=challenge["challenge_id"],
                nonce=challenge["nonce"],
                expires_at=challenge["expires_at"],
            )
        except KeyError as error:
            raise ValueError("Runtime challenge omitted a required field.") from error
        await websocket.send(
            json.dumps(
                {
                    "api_version": API_VERSION,
                    "type": "auth_proof",
                    "device_id": self.device_id,
                    "session_id": session_id,
                    "audience": self.audience,
                    "challenge_id": challenge["challenge_id"],
                    "signature": _base64url(self.identity.sign(payload)),
                }
            )
        )
        reply = json.loads(await websocket.recv())
        if reply.get("type") == "error":
            raise ValueError(reply.get("message", "Runtime rejected the Camera Edge proof."))
        if reply.get("type") != "connect_ok":
            raise ValueError("Runtime did not accept the Camera Edge proof.")
