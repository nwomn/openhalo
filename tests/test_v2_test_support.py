from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.pairing_store import PairingStore

from tests.v2_test_support import TEST_AUDIENCE
from tests.v2_test_support import authenticate_gateway_edge
from tests.v2_test_support import build_test_edge
from tests.v2_test_support import connect_test_edge
from tests.v2_test_support import connect_test_edge_sync
from tests.v2_test_support import create_test_gateway
from tests.v2_test_support import provision_test_edge
from tests.v2_test_support import V2RuntimeGateway
from tests.v2_test_support import V2SessionClient


class V2TestSupportTests(unittest.IsolatedAsyncioTestCase):
    async def test_creates_an_isolated_non_persistent_runtime_by_default(self) -> None:
        gateway = create_test_gateway()

        self.assertFalse(gateway.persist_state)
        self.assertEqual(gateway.state.events, [])

    async def test_provisions_ephemeral_public_key_and_completes_v2_authentication(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            pairing_store = PairingStore(Path(directory) / "pairing.json")
            gateway = RuntimeGateway(
                pairing_store=pairing_store,
                persist_state=False,
                audience=TEST_AUDIENCE,
            )
            edge = build_test_edge(
                device_id="terminal-edge-1",
                device_type="desktop-cli",
                display_name="Test Terminal",
            )

            provision_test_edge(gateway, edge)
            connect_ok = await authenticate_gateway_edge(gateway, edge)

            self.assertEqual(connect_ok["type"], "connect_ok")
            self.assertEqual(
                gateway.state.device_registry["terminal-edge-1"]["display_name"],
                "Test Terminal",
            )
            self.assertEqual(
                pairing_store.get_active_device("terminal-edge-1")["public_key"],
                edge.identity.public_key,
            )

    async def test_connects_a_provisioned_edge_before_capability_announcement(self) -> None:
        gateway = create_test_gateway(persist_state=False)
        edge = build_test_edge(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            display_name="Test Terminal",
            capabilities=["text.input", "interaction.progress"],
        )

        replies = await connect_test_edge(gateway, edge)

        self.assertEqual(replies[-1]["type"], "connect_ok")
        self.assertEqual(
            gateway.state.devices["terminal-edge-1"]["capabilities"],
            {"text.input", "interaction.progress"},
        )

    async def test_sync_helper_uses_the_same_p256_authentication_ceremony(self) -> None:
        gateway = create_test_gateway()
        edge = build_test_edge(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            display_name="Test Terminal",
        )

        replies = connect_test_edge_sync(gateway, edge)

        self.assertEqual(replies[-1]["type"], "connect_ok")
        self.assertIn("terminal-edge-1", gateway.state.devices)

    async def test_behavior_gateway_bootstraps_a_real_v2_session_before_frames(self) -> None:
        gateway = V2RuntimeGateway(persist_state=False)
        client = V2SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
        )

        replies = gateway.run_roundtrip(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
            ]
        )

        self.assertEqual(replies[-1]["type"], "connect_ok")
        self.assertEqual(
            gateway.state.devices["terminal-edge-1"]["capabilities"],
            {"text.input", "notification.show"},
        )
