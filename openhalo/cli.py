"""The owner-facing command for a personal OpenHalo Runtime."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path

from openhalo.home import PersonalHome
from openhalo.runtime_config_template import DEFAULT_RUNTIME_CONFIG
from openhalo.runtime_supervisor import RuntimeSupervisor
from personal_runtime.pairing_store import PairingStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage your personal OpenHalo Runtime.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup = subparsers.add_parser("setup", help="Create or update personal Runtime configuration.")
    setup.add_argument("--host", default="127.0.0.1", help="Runtime bind host.")
    setup.add_argument("--port", default=8765, type=int, help="Runtime bind port.")
    setup.add_argument(
        "--runtime-config",
        type=Path,
        help="Copy this model configuration into the private OpenHalo home.",
    )

    subparsers.add_parser("start", help="Start the personal Runtime.")
    subparsers.add_parser("stop", help="Stop the personal Runtime.")
    subparsers.add_parser("status", help="Show Runtime status.")
    logs = subparsers.add_parser("logs", help="Show recent Runtime logs.")
    logs.add_argument("--lines", type=int, default=100, help="Number of log lines.")
    subparsers.add_parser("doctor", help="Check local OpenHalo setup.")

    pair = subparsers.add_parser("pair", help="Create a one-time device pairing code.")
    pair.add_argument("--ttl-seconds", type=int, default=600)
    subparsers.add_parser("devices", help="List paired-device metadata.")
    revoke = subparsers.add_parser("revoke", help="Revoke one paired device.")
    revoke.add_argument("device_id")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    home: PersonalHome | None = None,
    supervisor_factory: Callable[[PersonalHome], RuntimeSupervisor] = RuntimeSupervisor,
) -> int:
    args = build_parser().parse_args(argv)
    personal_home = home or PersonalHome.from_environment()

    if args.command == "setup":
        runtime = personal_home.initialize_runtime(host=args.host, port=args.port)
        _install_runtime_config(personal_home, args.runtime_config)
        _emit({"state": "configured", "host": runtime["host"], "port": runtime["port"]})
        return 0

    if args.command == "pair":
        _require_runtime_configuration(personal_home)
        pairing_code = PairingStore(personal_home.pairing_store_path).create_pairing_code(
            ttl_seconds=args.ttl_seconds
        )
        _emit({"pairing_code": pairing_code, "ttl_seconds": args.ttl_seconds})
        return 0

    if args.command == "devices":
        _require_runtime_configuration(personal_home)
        _emit({"devices": PairingStore(personal_home.pairing_store_path).list_devices()})
        return 0

    if args.command == "revoke":
        _require_runtime_configuration(personal_home)
        revoked = PairingStore(personal_home.pairing_store_path).revoke_device(args.device_id)
        _emit({"device_id": args.device_id, "revoked": revoked})
        return 0 if revoked else 1

    supervisor = supervisor_factory(personal_home)
    if args.command == "start":
        _emit(supervisor.start())
        return 0
    if args.command == "stop":
        _emit(supervisor.stop())
        return 0
    if args.command == "status":
        _emit(supervisor.status())
        return 0
    if args.command == "logs":
        print(supervisor.read_logs(lines=args.lines), end="")
        return 0

    _emit(_doctor(personal_home))
    return 0


def _install_runtime_config(home: PersonalHome, source: Path | None) -> None:
    if source is not None:
        if not source.is_file():
            raise ValueError(f"runtime configuration does not exist: {source}")
        shutil.copyfile(source, home.runtime_config_path)
        os.chmod(home.runtime_config_path, 0o600)
        return
    if not home.runtime_config_path.exists():
        home.runtime_config_path.write_text(DEFAULT_RUNTIME_CONFIG, encoding="utf-8")
        os.chmod(home.runtime_config_path, 0o600)


def _require_runtime_configuration(home: PersonalHome) -> None:
    if not isinstance(home.load_configuration().get("runtime"), dict):
        raise ValueError("OpenHalo Runtime is not configured; run openhalo setup")


def _doctor(home: PersonalHome) -> dict:
    configuration = home.load_configuration()
    runtime = configuration.get("runtime")
    if not isinstance(runtime, dict):
        return {"state": "needs_setup"}
    missing = []
    if not home.runtime_config_path.exists():
        missing.append("runtime_config")
    return {"state": "ready" if not missing else "needs_attention", "missing": missing}


def _emit(payload: dict) -> None:
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
