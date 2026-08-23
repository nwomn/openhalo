from __future__ import annotations

import asyncio
import base64
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from device_edge.camera.openssl_session import OpenSslCameraSessionClient
from device_edge.camera.openssl_session import build_challenge_payload
from device_edge.camera.openssl_session import load_or_create_openssl_identity
from edge_api.auth import verify_challenge_signature


OPENSSL_PATH = os.environ.get("OPENSSL", "openssl")


def test_openssl_identity_is_persistent_and_signs_a_gateway_compatible_proof() -> None:
    with TemporaryDirectory() as directory:
        home = Path(directory) / "camera-home"
        identity = load_or_create_openssl_identity(
            home,
            "camera-edge-1",
            openssl_path=OPENSSL_PATH,
        )
        payload = build_challenge_payload(
            audience="ws://runtime.example.test/openhalo/edge",
            device_id="camera-edge-1",
            session_id="session-1",
            challenge_id="challenge-1",
            nonce="nonce-1",
            expires_at="2030-01-01T00:00:00Z",
        )

        signature = identity.sign(payload)
        public_key_der = base64.urlsafe_b64decode(
            identity.public_key + "=" * (-len(identity.public_key) % 4)
        )

        assert identity.private_key_path.name == "identity.p256.pk8.der"
        assert identity.private_key_path.exists()
        assert verify_challenge_signature(public_key_der, payload, signature)
        assert load_or_create_openssl_identity(
            home,
            "camera-edge-1",
            openssl_path=OPENSSL_PATH,
        ).public_key == identity.public_key


def test_openssl_camera_client_emits_gateway_compatible_pairing_frames() -> None:
    async def scenario() -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            client = OpenSslCameraSessionClient(
                device_id="camera-edge-1",
                audience="wss://runtime.example.test/openhalo/edge",
                identity_home=root / "camera-home",
                display_name="Desk Camera",
                openssl_path=OPENSSL_PATH,
            )
            capabilities = ["camera.health"]
            pairing_code = "one-time-pairing-code"
            session_id = "pair-session-1"
            challenge = {
                "api_version": "edge.runtime.v2",
                "type": "auth_challenge",
                "device_id": client.device_id,
                "session_id": session_id,
                "audience": client.audience,
                "challenge": {
                    "challenge_id": "challenge-1",
                    "nonce": "nonce-1",
                    "expires_at": "2030-01-01T00:00:00Z",
                },
            }

            class FakeWebSocket:
                def __init__(self) -> None:
                    self.sent: list[dict] = []
                    self.replies = [challenge, {"type": "connect_ok"}]

                async def send(self, payload: str) -> None:
                    self.sent.append(json.loads(payload))

                async def recv(self) -> str:
                    return json.dumps(self.replies.pop(0))

            class FakeConnect:
                async def __aenter__(self):
                    return websocket

                async def __aexit__(self, *_args) -> bool:
                    return False

            websocket = FakeWebSocket()
            connect = FakeConnect()

            with patch(
                "device_edge.camera.openssl_session.websockets.connect",
                return_value=connect,
            ), patch("secrets.token_urlsafe", return_value="session-1"):
                credentials = await client.pair(pairing_code, capabilities)

            assert credentials.device_id == "camera-edge-1"
            assert credentials.public_key_fingerprint.startswith("sha256:")
            assert [frame["type"] for frame in websocket.sent] == [
                "connect",
                "auth_proof",
                "capability_announce",
            ]
            connect_frame, proof, capability_frame = websocket.sent
            assert connect_frame["auth"]["kind"] == "pairing"
            assert connect_frame["auth"]["display_name"] == "Desk Camera"
            assert capability_frame["capabilities"] == capabilities
            payload = build_challenge_payload(
                audience=client.audience,
                device_id=client.device_id,
                session_id=session_id,
                challenge_id="challenge-1",
                nonce="nonce-1",
                expires_at="2030-01-01T00:00:00Z",
            )
            public_key_der = base64.urlsafe_b64decode(
                client.identity.public_key + "=" * (-len(client.identity.public_key) % 4)
            )
            signature = base64.urlsafe_b64decode(
                proof["signature"] + "=" * (-len(proof["signature"]) % 4)
            )
            assert verify_challenge_signature(public_key_der, payload, signature)

    asyncio.run(scenario())


def test_maixcam_cli_reads_pairing_code_only_from_stdin() -> None:
    from device_edge.camera import maixcam_cli

    class FakeClient:
        device_id = "camera-edge-1"

        async def pair(self, pairing_code: str, capabilities: list[str]):
            assert pairing_code == "one-time-code"
            assert capabilities == ["camera.health"]
            return type(
                "Credentials",
                (),
                {
                    "device_id": self.device_id,
                    "display_name": "Desk Camera",
                    "public_key_fingerprint": "sha256:test",
                },
            )()

    with patch("device_edge.camera.maixcam_cli._client_from_args", return_value=FakeClient()), patch(
        "sys.stdin", io.StringIO("one-time-code\n")
    ), patch("sys.stdout", new_callable=io.StringIO) as stdout:
        assert (
            maixcam_cli.main(
                [
                    "--url",
                    "ws://runtime.example.test:8765",
                    "pair",
                    "--pairing-code-stdin",
                ]
            )
            == 0
        )

    assert json.loads(stdout.getvalue())["state"] == "paired"
