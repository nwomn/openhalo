from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.main import build_managed_host_edge_supervisor
from personal_runtime.pairing_store import PairingStore


def test_managed_host_is_owner_provisioned_but_uses_normal_v2_connect() -> None:
    with TemporaryDirectory() as directory:
        home = Path(directory) / ".openhalo"
        store = PairingStore(home / "runtime" / "pairing.json")
        gateway = RuntimeGateway(
            pairing_store=store,
            persist_state=False,
            audience="ws://127.0.0.1:8765",
        )

        supervisor = build_managed_host_edge_supervisor(
            gateway=gateway,
            url="ws://127.0.0.1:8765",
            device_id="host-edge-1",
            identity_home=home,
            idle_timeout_s=1.0,
        )

        host = store.get_active_device("host-edge-1")
        connect = supervisor.daemon.build_bootstrap_frames()[0]
        assert host is not None
        assert host["provisioned_by"] == "local_owner"
        assert connect["type"] == "connect"
        assert "auth" not in connect
