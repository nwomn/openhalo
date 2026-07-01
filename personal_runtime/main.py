"""Manual demo entrypoint for the v0 personal runtime."""

import argparse
import asyncio
import os
from pathlib import Path

from openhalo_common.diagnostics import JsonlDiagnosticRecorder
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.model_provider import DEFAULT_CONFIG_PATH


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


def build_gateway(
    token: str,
    state_path: Path,
    llm_config_path: Path | None = None,
    diagnostic_log_path: Path | None = None,
) -> RuntimeGateway:
    return RuntimeGateway(
        shared_token=token,
        state_path=state_path,
        runtime_event_emitter=print,
        llm_config_path=llm_config_path,
        diagnostic_recorder=JsonlDiagnosticRecorder(diagnostic_log_path)
        if diagnostic_log_path is not None
        else None,
    )


async def run_server(
    host: str,
    port: int,
    token: str,
    state_path: Path,
    llm_config_path: Path | None = None,
    diagnostic_log_path: Path | None = None,
) -> None:
    gateway = build_gateway(
        token=token,
        state_path=state_path,
        llm_config_path=llm_config_path,
        diagnostic_log_path=diagnostic_log_path,
    )
    async with gateway.run_server(host=host, port=port) as server_info:
        print(
            build_runtime_server_message(
                server_info["url"],
                runtime_config_path=llm_config_path,
            )
        )
        await asyncio.Future()


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
            llm_config_path=Path(args.runtime_config_path)
            if args.runtime_config_path
            else None,
            diagnostic_log_path=args.diagnostic_log_path,
        )
    )


__all__ = [
    "build_gateway",
    "build_runtime_server_message",
    "build_runtime_server_parser",
    "main",
    "resolve_runtime_token",
    "run_server",
]


if __name__ == "__main__":
    main()
