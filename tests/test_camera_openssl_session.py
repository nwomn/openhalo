from __future__ import annotations

import asyncio
import base64
import importlib.util
import io
import json
import os
import sys
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


def test_camera_health_contract_and_status_file_are_bounded() -> None:
    from device_edge.camera.health_daemon import CAPABILITY_NAME
    from device_edge.camera.health_daemon import CameraHealthStatus
    from device_edge.camera.health_daemon import DEFAULT_CAPABILITIES
    from device_edge.camera.health_daemon import LocalStatusStore
    from device_edge.camera.health_daemon import build_health_frame

    with TemporaryDirectory() as directory:
        status = CameraHealthStatus(
            updated_at="2030-01-01T00:00:00Z",
            connection_state="connected",
            capture_state="not_checked",
            storage_state="ready",
            storage_free_mib=1024,
        )
        path = Path(directory) / "status.json"
        LocalStatusStore(path).write(status)
        assert json.loads(path.read_text(encoding="utf-8")) == {
            "capture_state": "not_checked",
            "connection_state": "connected",
            "last_error": None,
            "storage_free_mib": 1024,
            "storage_state": "ready",
            "updated_at": "2030-01-01T00:00:00Z",
        }

    capability = DEFAULT_CAPABILITIES[0]
    assert capability["name"] == CAPABILITY_NAME
    assert [item["name"] for item in capability["observations"]] == [
        "camera.connection_state",
        "camera.capture_state",
        "camera.storage_state",
        "camera.storage_free_mib",
    ]
    frame = build_health_frame("camera-edge-1", status)
    assert frame["type"] == "observation_push"
    assert frame["capability"] == CAPABILITY_NAME
    assert frame["observations"] == frame["payload"]["observations"]
    assert "raw_media" not in json.dumps(frame)


def test_camera_health_daemon_authenticates_before_publishing() -> None:
    from device_edge.camera import health_daemon

    class FakeClient:
        audience = "ws://runtime.example.test:8765"
        device_id = "camera-edge-1"

        async def authenticate(self, websocket, capabilities):
            assert capabilities == health_daemon.DEFAULT_CAPABILITIES
            websocket.authenticated = True

    class FakeWebSocket:
        authenticated = False

        def __init__(self) -> None:
            self.sent: list[dict] = []

        async def send(self, payload: str) -> None:
            assert self.authenticated
            self.sent.append(json.loads(payload))

    class FakeConnect:
        def __init__(self, websocket: FakeWebSocket) -> None:
            self.websocket = websocket
            self.entered = 0

        async def __aenter__(self):
            self.entered += 1
            return self.websocket

        async def __aexit__(self, *_args) -> bool:
            return False

    with TemporaryDirectory() as directory:
        websocket = FakeWebSocket()
        connect = FakeConnect(websocket)
        daemon = health_daemon.CameraHealthDaemon(
            client=FakeClient(),
            status_store=health_daemon.LocalStatusStore(Path(directory) / "status.json"),
            interval_seconds=60,
            min_free_mib=0,
        )
        with patch("device_edge.camera.health_daemon.websockets.connect", return_value=connect):
            asyncio.run(daemon.run_once())

    assert connect.entered == 1
    assert websocket.sent[0]["type"] == "observation_push"
    assert websocket.sent[0]["capability"] == "camera.health"


def test_camera_health_daemon_runs_capture_probe_only_when_enabled() -> None:
    from device_edge.camera import health_daemon

    class FakeClient:
        audience = "ws://runtime.example.test:8765"
        device_id = "camera-edge-1"

    with TemporaryDirectory() as directory, patch(
        "device_edge.camera.health_daemon.probe_camera_capture", return_value="ready"
    ) as probe:
        enabled = health_daemon.CameraHealthDaemon(
            client=FakeClient(),
            status_store=health_daemon.LocalStatusStore(Path(directory) / "enabled.json"),
            interval_seconds=60,
            min_free_mib=0,
            capture_probe_enabled=True,
        )
        disabled = health_daemon.CameraHealthDaemon(
            client=FakeClient(),
            status_store=health_daemon.LocalStatusStore(Path(directory) / "disabled.json"),
            interval_seconds=60,
            min_free_mib=0,
        )

    probe.assert_called_once_with()
    assert enabled.capture_state == "ready"
    assert disabled.capture_state == "not_checked"


def test_person_presence_feature_keeps_frames_and_geometry_local() -> None:
    from device_edge.camera.person_presence import MaixPersonPresenceFeature
    from device_edge.camera.person_presence import PersonPresenceSample
    from device_edge.camera.person_presence import PresenceDebouncer

    class Detection:
        class_id = 0
        score = 0.87
        x = 12
        y = 34
        w = 56
        h = 78

    class Detector:
        labels = ["person", "chair"]

        def __init__(self, **kwargs) -> None:
            assert kwargs == {"model": "/tmp/yolo11.mud", "dual_buff": True}

        def input_width(self) -> int:
            return 320

        def input_height(self) -> int:
            return 224

        def input_format(self):
            return "rgb"

        def detect(self, frame, **kwargs):
            assert frame == "private-frame"
            assert kwargs == {"conf_th": 0.6, "iou_th": 0.45}
            return [Detection()]

    class Camera:
        def __init__(self, *args) -> None:
            assert args == (320, 224, "rgb")
            self.closed = False

        def read(self, **kwargs):
            assert kwargs == {"block": True, "block_ms": 3000}
            return "private-frame"

        def close(self) -> None:
            self.closed = True

    feature = MaixPersonPresenceFeature(
        model_path="/tmp/yolo11.mud",
        confidence_threshold=0.6,
        detector_factory=Detector,
        camera_factory=Camera,
    )
    assert feature.sample() == PersonPresenceSample("present", 1, 0.87)
    feature.close()

    debouncer = PresenceDebouncer(confirm_samples=2)
    assert debouncer.observe(PersonPresenceSample("present", 1, 0.9)) is None
    decision = debouncer.observe(PersonPresenceSample("present", 1, 0.8))
    assert decision is not None
    assert (decision.state, decision.count, decision.confidence) == ("present", 1, 0.8)


def test_person_presence_daemon_registers_and_publishes_only_semantic_observation() -> None:
    from device_edge.camera import health_daemon
    from device_edge.camera.person_presence import PersonPresenceSample

    class FakeClient:
        audience = "ws://runtime.example.test:8765"
        device_id = "camera-edge-1"

        async def authenticate(self, websocket, capabilities):
            assert [capability["name"] for capability in capabilities] == [
                "camera.health",
                "camera.person_presence",
            ]
            websocket.authenticated = True

    class Feature:
        closed = False

        def sample(self):
            return PersonPresenceSample("present", 1, 0.91)

        def close(self) -> None:
            self.closed = True

    class FakeWebSocket:
        authenticated = False

        def __init__(self) -> None:
            self.sent: list[dict] = []

        async def send(self, payload: str) -> None:
            assert self.authenticated
            self.sent.append(json.loads(payload))

    class FakeConnect:
        def __init__(self, websocket: FakeWebSocket) -> None:
            self.websocket = websocket

        async def __aenter__(self):
            return self.websocket

        async def __aexit__(self, *_args) -> bool:
            return False

    with TemporaryDirectory() as directory:
        websocket = FakeWebSocket()
        feature = Feature()
        daemon = health_daemon.CameraHealthDaemon(
            client=FakeClient(),
            status_store=health_daemon.LocalStatusStore(Path(directory) / "status.json"),
            interval_seconds=60,
            min_free_mib=0,
            person_presence_feature=feature,
            presence_confirm_samples=1,
        )
        with patch("device_edge.camera.health_daemon.websockets.connect", return_value=FakeConnect(websocket)):
            asyncio.run(daemon.run_once())

    presence_frame = websocket.sent[1]
    assert presence_frame["capability"] == "camera.person_presence"
    assert presence_frame["observations"][0]["value"] == {
        "state": "present",
        "count": 1,
        "feature_version": "person_presence.v1",
    }
    assert "raw_media" not in json.dumps(presence_frame)
    assert "bbox" not in json.dumps(presence_frame)
    assert feature.closed is True




def test_maix_app_requires_private_runtime_configuration() -> None:
    app_directory = Path(__file__).parents[1] / "device_edge" / "camera" / "maix_app" / "openhalo_camera_edge"
    camera_directory = Path(__file__).parents[1] / "device_edge" / "camera"
    previous_path = list(sys.path)
    try:
        sys.path.insert(0, str(camera_directory))
        spec = importlib.util.spec_from_file_location("openhalo_camera_edge_app", app_directory / "main.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "app-config.json"
            config_path.write_text('{"runtime_url":"ws://runtime.example.test:8765"}', encoding="utf-8")
            assert module.load_config(config_path)["runtime_url"] == "ws://runtime.example.test:8765"
            config_path.write_text("{}", encoding="utf-8")
            try:
                module.load_config(config_path)
            except RuntimeError as error:
                assert "runtime_url" in str(error)
            else:
                raise AssertionError("App accepted a missing Runtime endpoint.")
    finally:
        sys.path[:] = previous_path
