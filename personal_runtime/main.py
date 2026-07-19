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
    token: str,
    state_path: Path,
    llm_config_path: Path | None = None,
    diagnostic_log_path: Path | None = None,
    pairing_store_path: Path | None = None,
) -> RuntimeGateway:
    return RuntimeGateway(
        shared_token=token,
        state_path=state_path,
        runtime_event_emitter=print,
        llm_config_path=llm_config_path,
        diagnostic_recorder=JsonlDiagnosticRecorder(diagnostic_log_path)
        if diagnostic_log_path is not None
        else None,
        pairing_store=PairingStore(pairing_store_path)
        if pairing_store_path is not None
        else None,
    )


def build_managed_host_edge_supervisor(
    *,
    gateway: RuntimeGateway,
    url: str,
    token: str,
    device_id: str,
    idle_timeout_s: float,
) -> ManagedHostEdgeSupervisor:
    runtime_control_adapter = PythonProcessAdapter(
        process_match_substring="personal_runtime.main",
        start_command=[sys.executable, "-m", "personal_runtime.main"],
    )
    daemon = HostEdgeDaemon(
        device_id=device_id,
        token=token,
        runtime_control_adapter=runtime_control_adapter,
        host_metrics_provider=read_host_metric_snapshot,
        runtime_health_provider=build_runtime_health_provider(runtime_control_adapter),
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
    token: str,
    state_path: Path,
    llm_config_path: Path | None = None,
    diagnostic_log_path: Path | None = None,
    pairing_store_path: Path | None = None,
    manage_host_edge: bool = True,
    host_edge_device_id: str = "host-edge-1",
    host_edge_idle_timeout_s: float = 30.0,
    host_edge_supervisor_factory=build_managed_host_edge_supervisor,
) -> None:
    gateway_kwargs = dict(
        token=token,
        state_path=state_path,
        llm_config_path=llm_config_path,
        diagnostic_log_path=diagnostic_log_path,
    )
    if pairing_store_path is not None:
        gateway_kwargs["pairing_store_path"] = pairing_store_path
    gateway = build_gateway(**gateway_kwargs)
    async with gateway.run_server(host=host, port=port) as server_info:
        supervisor = None
        if manage_host_edge:
            supervisor = host_edge_supervisor_factory(
                gateway=gateway,
                url=build_managed_host_edge_url(server_info["url"]),
                token=token,
                device_id=host_edge_device_id,
                idle_timeout_s=host_edge_idle_timeout_s,
            )
            await supervisor.start()
        try:
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


def build_runtime_server_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the v0 personal runtime server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind.")
    parser.add_argument("--token", default="dev-token", help="Shared development token.")
    parser.add_argument(
        "--token-env",
        help=(
            "Name of an environment variable containing the shared edge token. "
            "When set, this value takes precedence over --token."
        ),
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


def resolve_runtime_token(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser | None = None,
) -> str:
    token_env = getattr(args, "token_env", None)
    if not token_env:
        return args.token

    token = os.environ.get(token_env)
    if token:
        return token

    message = f"environment variable {token_env!r} is required by --token-env"
    if parser is not None:
        parser.error(message)
    raise SystemExit(message)


def main() -> None:
    parser = build_runtime_server_parser()
    args = parser.parse_args()

    asyncio.run(
        run_server(
            host=args.host,
            port=args.port,
            token=resolve_runtime_token(args, parser),
            state_path=Path(args.state_path),
            pairing_store_path=Path(args.pairing_store_path),
            llm_config_path=Path(args.runtime_config_path)
            if args.runtime_config_path
            else None,
            diagnostic_log_path=args.diagnostic_log_path,
            manage_host_edge=args.host_edge_enabled,
            host_edge_device_id=args.host_edge_device_id,
            host_edge_idle_timeout_s=args.host_edge_idle_timeout,
        )
    )


__all__ = [
    "build_gateway",
    "build_managed_host_edge_url",
    "build_managed_host_edge_supervisor",
    "build_runtime_server_message",
    "build_runtime_server_parser",
    "main",
    "resolve_runtime_token",
    "run_server",
]


if __name__ == "__main__":
    main()
