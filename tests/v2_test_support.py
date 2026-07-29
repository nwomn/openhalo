"""Reusable P-256 authentication support for Runtime and Edge tests."""

from __future__ import annotations

import atexit
from dataclasses import dataclass
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from device_edge.shared.identity import DeviceIdentity
from device_edge.shared.identity import create_ephemeral_identity
from device_edge.shared.session_client import SessionClient
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.pairing_store import PairingStore


TEST_AUDIENCE = "ws://127.0.0.1:18765"
_test_pairing_directories: list[TemporaryDirectory] = []


def _cleanup_test_pairing_directories() -> None:
    while _test_pairing_directories:
        _test_pairing_directories.pop().cleanup()


atexit.register(_cleanup_test_pairing_directories)


@dataclass(frozen=True)
class TestEdge:
    client: SessionClient
    identity: DeviceIdentity
    display_name: str


class V2SessionClient(SessionClient):
    """A v2 SessionClient with a stable test audience and identity registry.

    This exists only for behavior tests whose subject begins after an Edge is
    authenticated. It never transmits a bearer credential.
    """

    _clients_by_session: dict[tuple[str, str], "V2SessionClient"] = {}

    def __init__(self, *args, **kwargs) -> None:
        # Historical callers may still pass this field while their fixtures are
        # being migrated. It is discarded before the production client exists.
        kwargs.pop("token", None)
        kwargs.setdefault("audience", TEST_AUDIENCE)
        super().__init__(*args, **kwargs)
        self._clients_by_session[(self.device_id, self.session_id)] = self


class V2RuntimeGateway(RuntimeGateway):
    """Runtime behavior-test fixture that establishes genuine P-256 sessions."""

    def __init__(self, *args, **kwargs) -> None:
        # Product RuntimeGateway ignores this legacy constructor argument. The
        # fixture removes it too, before constructing the product object.
        kwargs.pop("shared_token", None)
        directory = TemporaryDirectory()
        _test_pairing_directories.append(directory)
        kwargs.setdefault("audience", TEST_AUDIENCE)
        pairing_store = kwargs.pop(
            "pairing_store",
            PairingStore(Path(directory.name) / "pairing.json"),
        )
        super().__init__(*args, pairing_store=pairing_store, **kwargs)
        self._v2_test_pairing_directory = directory
        self._v2_test_provisioned_sessions: set[tuple[str, str]] = set()

    def _test_client_for_connect(self, frame: dict) -> V2SessionClient | None:
        device = frame.get("device")
        session_id = frame.get("session_id")
        if not isinstance(device, dict):
            return None
        device_id = device.get("device_id")
        if not isinstance(device_id, str):
            return None
        if isinstance(session_id, str):
            client = V2SessionClient._clients_by_session.get((device_id, session_id))
            if client is not None:
                return client
        auth = frame.get("auth")
        if (
            not isinstance(auth, dict)
            or auth.get("kind") is not None
            or "token" not in auth
        ):
            return None
        # A raw legacy connect is converted to an ephemeral Device Edge; the
        # old token is not consulted and cannot authenticate anything.
        return V2SessionClient(
            device_id=device_id,
            device_type=device.get("device_type", "test-edge"),
            audience=self.audience,
            display_name=device.get("display_name") or device_id,
        )

    def _authenticate_test_client(
        self,
        frame: dict,
        client: V2SessionClient,
    ) -> list[dict]:
        session_key = (client.device_id, client.session_id)
        if session_key not in self._v2_test_provisioned_sessions:
            self.pairing_store.provision_local_device(
                device_id=client.device_id,
                device_type=client.device_type,
                display_name=client.session_link.display_name,
                audience=self.audience,
                public_key=client.identity.public_key,
            )
            self._v2_test_provisioned_sessions.add(session_key)
        connect_frame = client.build_connect_frame()
        source_device = frame.get("device")
        if isinstance(source_device, dict):
            for field_name in ("role", "profile"):
                if isinstance(source_device.get(field_name), str):
                    connect_frame["device"][field_name] = source_device[field_name]
        challenge = super()._handle_frames_sync([connect_frame])[-1]
        if challenge.get("type") != "auth_challenge":
            raise AssertionError("Behavior fixture did not receive a v2 challenge.")
        connect_ok = super()._handle_frames_sync(
            [client.build_auth_proof_frame(challenge)]
        )[-1]
        if connect_ok.get("type") != "connect_ok":
            raise AssertionError("Behavior fixture v2 authentication was rejected.")
        return [connect_ok]

    def run_roundtrip(self, frames: list[dict]) -> list[dict]:
        replies: list[dict] = []
        for frame in frames:
            if frame.get("type") == "connect":
                client = self._test_client_for_connect(frame)
                if client is not None:
                    replies.extend(self._authenticate_test_client(frame, client))
                    continue
            replies.extend(super()._handle_frames_sync([frame]))
        return replies

    async def handle_test_frames(self, frames: list[dict]) -> list[dict]:
        return self.run_roundtrip(frames)

    @asynccontextmanager
    async def run_test_server(self):
        async with super().run_test_server() as server_info:
            # Behavior tests bind an ephemeral loopback port. Its canonical
            # audience is the actual bound URL, never the fixture default.
            self.audience = server_info["url"]
            yield server_info


def create_test_gateway(**kwargs) -> RuntimeGateway:
    """Build a bearer-free Runtime with an isolated durable pairing registry."""

    directory = TemporaryDirectory()
    _test_pairing_directories.append(directory)
    audience = kwargs.setdefault("audience", TEST_AUDIENCE)
    kwargs.setdefault("persist_state", False)
    pairing_store_path = kwargs.pop(
        "pairing_store_path",
        Path(directory.name) / "pairing.json",
    )
    gateway = RuntimeGateway(
        pairing_store=PairingStore(pairing_store_path),
        **kwargs,
    )
    # Keep the directory alive for the test gateway's complete lifetime. Test
    # classes that retain a gateway beyond one test may call cleanup explicitly.
    gateway._v2_test_pairing_directory = directory
    if gateway.audience != audience:
        raise AssertionError("Test gateway audience must match its test identity.")
    return gateway


def build_test_edge(
    *,
    device_id: str,
    device_type: str,
    display_name: str,
    audience: str = TEST_AUDIENCE,
    capabilities: list[str] | None = None,
) -> TestEdge:
    identity = create_ephemeral_identity()
    return TestEdge(
        client=SessionClient(
            device_id=device_id,
            device_type=device_type,
            audience=audience,
            identity=identity,
            display_name=display_name,
            capabilities=capabilities,
        ),
        identity=identity,
        display_name=display_name,
    )


def provision_test_edge(gateway, edge: TestEdge) -> None:
    if gateway.pairing_store is None:
        raise ValueError("v2 test support requires a PairingStore.")
    gateway.pairing_store.provision_local_device(
        device_id=edge.client.device_id,
        device_type=edge.client.device_type,
        display_name=edge.display_name,
        audience=edge.client.audience,
        public_key=edge.identity.public_key,
    )


async def authenticate_gateway_edge(gateway, edge: TestEdge) -> dict:
    challenge = (await gateway.handle_test_frames([edge.client.build_connect_frame()]))[-1]
    if challenge.get("type") != "auth_challenge":
        raise AssertionError("Test edge did not receive an authentication challenge.")
    connect_ok = (
        await gateway.handle_test_frames(
            [edge.client.build_auth_proof_frame(challenge)]
        )
    )[-1]
    if connect_ok.get("type") != "connect_ok":
        raise AssertionError("Test edge authentication was not accepted.")
    return connect_ok


def authenticate_gateway_edge_sync(gateway, edge: TestEdge) -> dict:
    """Synchronous variant for in-process unittest coverage."""

    challenge = gateway.run_roundtrip([edge.client.build_connect_frame()])[-1]
    if challenge.get("type") != "auth_challenge":
        raise AssertionError("Test edge did not receive an authentication challenge.")
    connect_ok = gateway.run_roundtrip(
        [edge.client.build_auth_proof_frame(challenge)]
    )[-1]
    if connect_ok.get("type") != "connect_ok":
        raise AssertionError("Test edge authentication was not accepted.")
    return connect_ok


async def connect_test_edge(gateway, edge: TestEdge) -> list[dict]:
    """Provision, authenticate, and register capabilities for one test Edge."""

    provision_test_edge(gateway, edge)
    connect_ok = await authenticate_gateway_edge(gateway, edge)
    capability_replies = await gateway.handle_test_frames(
        [edge.client.build_capability_announce_frame()]
    )
    if any(reply.get("type") == "error" for reply in capability_replies):
        raise AssertionError("Test edge capability registration was not accepted.")
    return [connect_ok, *capability_replies]


def connect_test_edge_sync(gateway, edge: TestEdge) -> list[dict]:
    """Synchronously provision, authenticate, and register one test Edge."""

    provision_test_edge(gateway, edge)
    connect_ok = authenticate_gateway_edge_sync(gateway, edge)
    capability_replies = gateway.run_roundtrip(
        [edge.client.build_capability_announce_frame()]
    )
    if any(reply.get("type") == "error" for reply in capability_replies):
        raise AssertionError("Test edge capability registration was not accepted.")
    return [connect_ok, *capability_replies]


async def authenticate_websocket_edge(websocket, edge: TestEdge) -> dict:
    import json

    await websocket.send(json.dumps(edge.client.build_connect_frame()))
    challenge = json.loads(await websocket.recv())
    if challenge.get("type") != "auth_challenge":
        raise AssertionError("Test edge did not receive an authentication challenge.")
    await websocket.send(json.dumps(edge.client.build_auth_proof_frame(challenge)))
    connect_ok = json.loads(await websocket.recv())
    if connect_ok.get("type") != "connect_ok":
        raise AssertionError("Test edge authentication was not accepted.")
    return connect_ok
