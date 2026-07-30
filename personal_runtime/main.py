"""Manual demo entrypoint for the v0 personal runtime."""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from device_edge.host.host_daemon import HostEdgeDaemon
from device_edge.host.host_daemon import build_runtime_health_provider
from device_edge.host.host_observers import read_host_metric_snapshot
from device_edge.host.runtime_control import PythonProcessAdapter
from openhalo_common.diagnostics import JsonlDiagnosticRecorder
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.managed_host_edge import ManagedHostEdgeSupervisor
from personal_runtime.model_provider import DEFAULT_CONFIG_PATH
from personal_runtime.pairing_store import PairingStore


def build_runtime_server_message(
    url: str,
    runtime_config_path: Path | None = None,
) -> str:
    config_path = runtime_config_path or DEFAULT_CONFIG_PATH
    return (
        "Personal runtime WebSocket server is ready.\n"
        f"WebSocket URL: {url}\n"
        f"Runtime config: {config_path}"
    )


def build_managed_host_edge_url(gateway_url: str) -> str:
    parsed = urlsplit(gateway_url)
    if parsed.hostname not in {"0.0.0.0", "::"}:
        return gateway_url
    port = f":{parsed.port}" if parsed.port is not None else ""
    return parsed._replace(netloc=f"127.0.0.1{port}").geturl()


def build_gateway(
    state_path: Path,
    llm_config_path: Path | None = None,
    diagnostic_log_path: Path | None = None,
    pairing_store_path: Path | None = None,
    ready_file_path: Path | None = None,
    audience: str = "wss://runtime.invalid/openhalo/edge",
) -> RuntimeGateway:
    del ready_file_path
    return RuntimeGateway(
        state_path=state_path,
        runtime_event_emitter=print,
        llm_config_path=llm_config_path,
        diagnostic_recorder=JsonlDiagnosticRecorder(diagnostic_log_path)
        if diagnostic_log_path is not None
        else None,
        pairing_store=PairingStore(pairing_store_path)
        if pairing_store_path is not None
        else None,
        audience=audience,
    )


def build_managed_host_edge_supervisor(
    *,
    gateway: RuntimeGateway,
    url: str,
    device_id: str,
    identity_home: Path,
    idle_timeout_s: float,
) -> ManagedHostEdgeSupervisor:
    runtime_control_adapter = PythonProcessAdapter(
        process_match_substring="personal_runtime.main",
        start_command=[sys.executable, "-m", "personal_runtime.main"],
    )
    if gateway.pairing_store is None:
        raise ValueError("Managed Host Edge requires a PairingStore.")
    from device_edge.shared.identity import load_or_create_identity

    identity = load_or_create_identity(identity_home, device_id)
    gateway.pairing_store.provision_local_device(
        device_id=device_id,
        device_type="server",
        display_name="Runtime Host",
        audience=gateway.audience,
        public_key=identity.public_key,
    )
    daemon = HostEdgeDaemon(
        device_id=device_id,
        audience=gateway.audience,
        runtime_control_adapter=runtime_control_adapter,
        host_metrics_provider=read_host_metric_snapshot,
        runtime_health_provider=build_runtime_health_provider(runtime_control_adapter),
        identity=identity,
        display_name="Runtime Host",
        diagnostic_recorder=getattr(gateway, "diagnostic_recorder", None),
    )

    def write_status(status: dict) -> None:
        gateway.state.record_managed_host_edge_status(**status)
        gateway._persist_state()

    supervisor = ManagedHostEdgeSupervisor(
        daemon=daemon,
        url=url,
        status_writer=write_status,
        idle_timeout_s=idle_timeout_s,
    )
    return supervisor


async def run_server(
    host: str,
    port: int,
    state_path: Path,
    llm_config_path: Path | None = None,
    diagnostic_log_path: Path | None = None,
    pairing_store_path: Path | None = None,
    ready_file_path: Path | None = None,
    manage_host_edge: bool = True,
    host_edge_device_id: str = "host-edge-1",
    host_edge_idle_timeout_s: float = 30.0,
    audience: str | None = None,
    identity_home: Path | None = None,
    host_edge_supervisor_factory=build_managed_host_edge_supervisor,
) -> None:
    gateway_kwargs = dict(
        state_path=state_path,
        llm_config_path=llm_config_path,
        diagnostic_log_path=diagnostic_log_path,
    )
    if audience is not None:
        gateway_kwargs["audience"] = audience
    if pairing_store_path is not None:
        gateway_kwargs["pairing_store_path"] = pairing_store_path
    gateway = build_gateway(**gateway_kwargs)
    async with gateway.run_server(host=host, port=port) as server_info:
        supervisor = None
        try:
            if ready_file_path is not None:
                _write_ready_file(ready_file_path)
            if manage_host_edge:
                host_edge_url = build_managed_host_edge_url(server_info["url"])
                if audience is None:
                    gateway.audience = host_edge_url
                supervisor = host_edge_supervisor_factory(
                    gateway=gateway,
                    url=host_edge_url,
                    device_id=host_edge_device_id,
                    identity_home=identity_home
                    or (pairing_store_path or state_path).parent.parent,
                    idle_timeout_s=host_edge_idle_timeout_s,
                )
                await supervisor.start()
            print(
                build_runtime_server_message(
                    server_info["url"],
                    runtime_config_path=llm_config_path,
                )
            )
            await asyncio.Future()
        finally:
            if supervisor is not None:
                await supervisor.stop()
            if ready_file_path is not None:
                ready_file_path.unlink(missing_ok=True)


def build_runtime_server_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the v0 personal runtime server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind.")
    parser.add_argument(
        "--edge-audience",
        help="Canonical Runtime audience signed by Device Edges.",
    )
    parser.add_argument(
        "--state-path",
        default=".runtime/state.json",
        help="Path to the persisted runtime state file.",
    )
    parser.add_argument(
        "--pairing-store-path",
        default=".runtime/pairing.json",
        help="Path to the Runtime-local device pairing registry.",
    )
    parser.add_argument(
        "--runtime-config-path",
        "--llm-config-path",
        dest="runtime_config_path",
        help=(
            "Optional explicit OpenHalo runtime config path. Defaults to "
            "config/runtime-config.toml."
        ),
    )
    parser.add_argument(
        "--diagnostic-log-path",
        type=Path,
        help="Optional local JSONL path for runtime diagnostic.v1 module-boundary events.",
    )
    parser.add_argument(
        "--ready-file-path",
        type=Path,
        help="Private path created only after the Gateway starts listening.",
    )
    parser.set_defaults(host_edge_enabled=True)
    parser.add_argument(
        "--disable-host-edge",
        action="store_false",
        dest="host_edge_enabled",
        help="Do not start the colocated managed Host Edge.",
    )
    parser.add_argument(
        "--host-edge-device-id",
        default="host-edge-1",
        help="Device identity for the Runtime-managed Host Edge.",
    )
    parser.add_argument(
        "--host-edge-idle-timeout",
        type=float,
        default=30.0,
        help="Seconds between idle Host Edge observation cycles.",
    )
    return parser


def main() -> None:
    parser = build_runtime_server_parser()
    args = parser.parse_args()

    asyncio.run(
        run_server(
            host=args.host,
            port=args.port,
            state_path=Path(args.state_path),
            pairing_store_path=Path(args.pairing_store_path),
            llm_config_path=Path(args.runtime_config_path)
            if args.runtime_config_path
            else None,
            diagnostic_log_path=args.diagnostic_log_path,
            ready_file_path=args.ready_file_path,
            manage_host_edge=args.host_edge_enabled,
            host_edge_device_id=args.host_edge_device_id,
            host_edge_idle_timeout_s=args.host_edge_idle_timeout,
            audience=args.edge_audience,
        )
    )


def _write_ready_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ready\n", encoding="utf-8")
    os.chmod(path, 0o600)


__all__ = [
    "build_gateway",
    "build_managed_host_edge_url",
    "build_managed_host_edge_supervisor",
    "build_runtime_server_message",
    "build_runtime_server_parser",
    "main",
    "run_server",
]


if __name__ == "__main__":
    main()
