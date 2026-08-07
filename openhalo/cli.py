"""The owner-facing command for a personal OpenHalo Runtime."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import time
from collections.abc import Callable
from datetime import UTC
from datetime import datetime
from pathlib import Path

from openhalo.home import PersonalHome
from openhalo.outbound_proxy import OutboundProxyManager
from openhalo.outbound_proxy import ProxyOperationError
from openhalo.release_manager import GitHubReleaseFeed
from openhalo.release_manager import ReleaseLayout
from openhalo.release_manager import ReleaseStager
from openhalo.runtime_config_template import DEFAULT_RUNTIME_CONFIG
from openhalo.runtime_supervisor import RuntimeSupervisor
from openhalo.updater import ReleaseUpdater
from openhalo.version import format_cli_version
from personal_runtime.pairing_store import PairingStore
from personal_runtime.state_migration import export_sqlite_to_json
from personal_runtime.state_migration import migrate_json_to_sqlite
from personal_runtime.state_migration import sha256_file
from personal_runtime.state_migration import write_bounded_legacy_snapshot
from personal_runtime.sqlite_state_store import SQLiteRuntimeStateStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage your personal OpenHalo Runtime.")
    parser.add_argument(
        "--version",
        action="version",
        version=format_cli_version("openhalo"),
        help="Show the installed OpenHalo version.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup = subparsers.add_parser("setup", help="Create or update personal Runtime configuration.")
    setup.add_argument("--host", default="0.0.0.0", help="Runtime bind host.")
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
    storage = subparsers.add_parser("storage", help="Inspect and maintain Runtime storage.")
    storage_commands = storage.add_subparsers(dest="storage_command", required=True)
    storage_commands.add_parser("status", help="Show Runtime storage posture.")
    compact = storage_commands.add_parser("compact", help="Compact eligible Runtime history.")
    compact.add_argument("--before", help="Delete eligible records before this UTC timestamp.")
    export_parser = storage_commands.add_parser("export", help="Export replay/eval history.")
    export_parser.add_argument("output", type=Path)
    export_parser.add_argument("--since", help="Include records at or after this UTC timestamp.")
    proxy = subparsers.add_parser("proxy", help="Manage Runtime outbound HTTP proxy.")
    proxy_commands = proxy.add_subparsers(dest="proxy_command", required=True)
    proxy_commands.add_parser("show", help="Show the redacted outbound proxy state.")
    proxy_commands.add_parser("test", help="Test the selected Runtime outbound path.")
    proxy_commands.add_parser("set", help="Set the outbound proxy from hidden input.")
    proxy_commands.add_parser("clear", help="Clear the outbound proxy and use direct access.")
    update = subparsers.add_parser("update", help="Install the latest stable Runtime release.")
    update.add_argument("--check", action="store_true", help="Check for an update without changing Runtime files.")
    subparsers.add_parser("rollback", help="Restore the previous Runtime release.")

    pair = subparsers.add_parser("pair", help="Create a one-time device pairing code.")
    pair.add_argument("--ttl-seconds", type=int, default=600)
    subparsers.add_parser("devices", help="List paired-device metadata.")
    rename = subparsers.add_parser("rename", help="Rename one paired device.")
    rename.add_argument("device_id")
    rename.add_argument("display_name")
    revoke = subparsers.add_parser("revoke", help="Revoke one paired device.")
    revoke.add_argument("device_id")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    home: PersonalHome | None = None,
    supervisor_factory: Callable[[PersonalHome], RuntimeSupervisor] = RuntimeSupervisor,
    updater_factory: Callable[[PersonalHome], ReleaseUpdater] | None = None,
    proxy_manager_factory: Callable[[PersonalHome], OutboundProxyManager] | None = None,
    proxy_url_reader: Callable[[], str] | None = None,
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

    if args.command == "rename":
        _require_runtime_configuration(personal_home)
        renamed = PairingStore(personal_home.pairing_store_path).rename_device(
            args.device_id,
            args.display_name,
        )
        _emit({"device_id": args.device_id, "renamed": renamed})
        return 0 if renamed else 1

    if args.command == "revoke":
        _require_runtime_configuration(personal_home)
        revoked = PairingStore(personal_home.pairing_store_path).revoke_device(args.device_id)
        _emit({"device_id": args.device_id, "revoked": revoked})
        return 0 if revoked else 1

    if args.command == "proxy":
        try:
            _require_runtime_configuration(personal_home)
            manager = (
                proxy_manager_factory(personal_home)
                if proxy_manager_factory is not None
                else OutboundProxyManager(
                    personal_home,
                    supervisor_factory=supervisor_factory,
                )
            )
            if args.proxy_command == "show":
                result = manager.show()
            elif args.proxy_command == "test":
                result = manager.test()
            elif args.proxy_command == "set":
                reader = proxy_url_reader or (lambda: getpass.getpass("Proxy URL: "))
                result = manager.set(reader())
            else:
                result = manager.clear()
            _emit(result)
            return 0
        except ProxyOperationError as exc:
            _emit(
                {
                    "failure_class": exc.failure_class,
                    "operation": exc.operation,
                    "reason": exc.safe_reason,
                    "state": (
                        "proxy_rollback_failed"
                        if exc.rollback_failed
                        else "proxy_failed"
                    ),
                }
            )
            return 1
        except (OSError, ValueError):
            _emit(
                {
                    "failure_class": "invalid_configuration",
                    "operation": args.proxy_command,
                    "reason": "Runtime proxy configuration is invalid",
                    "state": "proxy_failed",
                }
            )
            return 1

    if args.command == "storage":
        try:
            _require_runtime_configuration(personal_home)
            if args.storage_command == "status":
                _emit(_storage_status(personal_home))
                return 0
            if args.storage_command == "export":
                _require_sqlite_storage(personal_home)
                store = SQLiteRuntimeStateStore(personal_home.state_database_path)
                try:
                    result = store.export_json(args.output, since=args.since)
                finally:
                    store.close()
                result["replay_storage"] = _prune_replay_exports(personal_home)
                _emit(result)
                return 0
            _emit(
                _compact_storage(
                    personal_home,
                    supervisor_factory=supervisor_factory,
                    before=args.before,
                )
            )
            return 0
        except (OSError, RuntimeError, ValueError) as exc:
            _emit({"state": "storage_failed", "reason": str(exc)})
            return 1

    if args.command == "update":
        try:
            updater = (updater_factory or _build_updater)(personal_home)
            result = updater.check() if args.check else updater.update()
            _emit(result)
            return 1 if result.get("state") == "rolled_back" else 0
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
            _emit({"state": "update_failed", "reason": str(exc)})
            return 1

    if args.command == "rollback":
        try:
            updater = (updater_factory or _build_updater)(personal_home)
            _emit(updater.rollback())
            return 0
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
            _emit({"state": "update_failed", "reason": str(exc)})
            return 1

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
    if home.legacy_state_path.exists() and not home.state_database_path.exists():
        missing.append("runtime_state_migration")
    return {"state": "ready" if not missing else "needs_attention", "missing": missing}


def _build_updater(home: PersonalHome) -> ReleaseUpdater:
    release_root = Path(
        os.environ.get("OPENHALO_RELEASE_HOME", Path.home() / ".local/share/openhalo")
    )
    repository = os.environ.get("OPENHALO_GITHUB_REPOSITORY", "nwomn/openhalo")
    layout = ReleaseLayout(release_root)
    return ReleaseUpdater(
        layout=layout,
        feed=GitHubReleaseFeed(repository),
        stager=ReleaseStager(layout),
        supervisor_factory=lambda executable: RuntimeSupervisor(home, executable=executable),
        state_health_check=lambda: _validate_runtime_state(home),
        state_migrator=lambda manifest: _migrate_runtime_state(home, manifest.state_schema),
        state_commit_migrator=lambda manifest: _commit_runtime_state_migration(
            home,
            manifest.state_schema,
        ),
        state_rollback_migrator=lambda: _export_runtime_state_for_rollback(home),
    )


def _migrate_runtime_state(home: PersonalHome, state_schema: str) -> None:
    if state_schema != "sqlite-v1":
        return
    stale_path = None
    if home.state_database_path.exists() and home.legacy_state_path.exists():
        existing = SQLiteRuntimeStateStore(home.state_database_path)
        try:
            metadata = existing.metadata()
        finally:
            existing.close()
        if metadata.get("legacy_source_sha256") == sha256_file(home.legacy_state_path):
            return
        stale_path = home.state_database_path.with_suffix(".sqlite3.stale")
        _move_sqlite_artifacts(home.state_database_path, stale_path)
    elif home.state_database_path.exists():
        return
    if not home.legacy_state_path.exists():
        SQLiteRuntimeStateStore(home.state_database_path).close()
        return
    Path(f"{home.state_database_path}.migrating").unlink(missing_ok=True)
    try:
        migrate_json_to_sqlite(home.legacy_state_path, home.state_database_path)
    except Exception:
        if stale_path is not None and stale_path.exists() and not home.state_database_path.exists():
            _move_sqlite_artifacts(stale_path, home.state_database_path)
        raise
    if stale_path is not None:
        _remove_sqlite_artifacts(stale_path)


def _export_runtime_state_for_rollback(home: PersonalHome) -> None:
    if not home.state_database_path.exists():
        return
    legacy_path = home.legacy_state_path
    staged_path = legacy_path.with_name(f".{legacy_path.name}.rollback-stage")
    staged_path.unlink(missing_ok=True)
    export_sqlite_to_json(home.state_database_path, staged_path)
    backup = legacy_path.with_suffix(".json.pre-rollback")
    had_legacy = legacy_path.exists()
    if had_legacy:
        os.replace(legacy_path, backup)
    try:
        os.replace(staged_path, legacy_path)
    except Exception:
        if had_legacy and backup.exists():
            os.replace(backup, legacy_path)
        raise
    database_backup = home.state_database_path.with_suffix(".sqlite3.pre-rollback")
    _move_sqlite_artifacts(home.state_database_path, database_backup)


def _validate_runtime_state(home: PersonalHome) -> None:
    """Refuse a release switch when the durable SQLite state is corrupt."""

    database = home.state_database_path
    if not database.exists():
        return
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=2)
    try:
        result = connection.execute("PRAGMA integrity_check(1)").fetchone()[0]
    finally:
        connection.close()
    if result != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {result}")


def _move_sqlite_artifacts(source: Path, destination: Path) -> None:
    """Move a SQLite database together with its WAL and shared-memory files."""

    _remove_sqlite_artifacts(destination)
    for suffix in ("", "-wal", "-shm"):
        source_path = Path(f"{source}{suffix}")
        if source_path.exists():
            os.replace(source_path, Path(f"{destination}{suffix}"))


def _remove_sqlite_artifacts(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def _commit_runtime_state_migration(home: PersonalHome, state_schema: str) -> None:
    if state_schema == "sqlite-v1":
        write_bounded_legacy_snapshot(
            home.state_database_path,
            home.legacy_state_path,
        )


def _storage_status(home: PersonalHome) -> dict:
    _require_sqlite_storage(home)
    store = SQLiteRuntimeStateStore(home.state_database_path)
    try:
        status = store.storage_status()
        limit_bytes = status.get("database_limit_bytes", 512 * 1024 * 1024)
        footprint_bytes = status["bytes"].get(
            "footprint",
            status["bytes"].get("live_pages", 0),
        )
        status.update(
            {
                "retention_profile": "balanced",
                "diagnostics": _diagnostic_storage_status(home),
                "pressure": (
                    "critical"
                    if footprint_bytes >= limit_bytes
                    else "warning"
                    if footprint_bytes >= int(limit_bytes * 0.8)
                    else "normal"
                ),
            }
        )
        return status
    finally:
        store.close()


def _diagnostic_storage_status(home: PersonalHome) -> dict:
    paths = [home.runtime_diagnostic_log_path]
    paths.extend(sorted(home.log_directory.glob("runtime-diagnostics.jsonl.*")))
    existing = [path for path in paths if path.exists()]
    return {
        "bytes": sum(path.stat().st_size for path in existing),
        "files": len(existing),
        "limit_bytes": 80 * 1024 * 1024,
    }


def _compact_storage(
    home: PersonalHome,
    *,
    supervisor_factory: Callable[[PersonalHome], RuntimeSupervisor],
    before: str | None,
) -> dict:
    _require_sqlite_storage(home)
    timestamp = before
    maintenance_time = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    supervisor = supervisor_factory(home)
    was_running = supervisor.status().get("state") == "running"
    if was_running:
        supervisor.stop()
        wait = getattr(supervisor, "wait_until_stopped", None)
        if wait is not None:
            wait()
    try:
        store = SQLiteRuntimeStateStore(home.state_database_path)
        try:
            if timestamp is None:
                result = store.enforce_retention(now=maintenance_time)
            else:
                result = store.compact(before=timestamp, preserve_active=True)
        finally:
            store.close()
        result.update({"state": "compacted", "before": timestamp or maintenance_time})
        result["replay_storage"] = _prune_replay_exports(home)
    finally:
        if was_running:
            supervisor.start()
    return result


def _require_sqlite_storage(home: PersonalHome) -> None:
    if not home.state_database_path.exists() and home.legacy_state_path.exists():
        raise ValueError(
            "legacy Runtime state requires migration before SQLite storage operations"
        )
    if home.state_database_path.exists() and home.legacy_state_path.exists():
        store = SQLiteRuntimeStateStore(home.state_database_path)
        try:
            metadata = store.metadata()
        finally:
            store.close()
        if metadata.get("legacy_source_sha256") != sha256_file(home.legacy_state_path):
            raise ValueError(
                "SQLite Runtime state requires migration before storage operations"
            )


def _prune_replay_exports(home: PersonalHome) -> dict:
    directory = home.replay_directory
    if not directory.exists():
        return {"bytes": 0, "files": 0, "limit_bytes": 256 * 1024 * 1024}
    files = sorted(
        (path for path in directory.iterdir() if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    cutoff = time.time() - 30 * 24 * 60 * 60
    for path in list(files):
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
    files = [path for path in files if path.exists()]
    total = sum(path.stat().st_size for path in files)
    limit = 256 * 1024 * 1024
    for path in files:
        if total <= limit:
            break
        total -= path.stat().st_size
        path.unlink(missing_ok=True)
    remaining = [path for path in files if path.exists()]
    return {
        "bytes": sum(path.stat().st_size for path in remaining),
        "files": len(remaining),
        "limit_bytes": limit,
    }


def _emit(payload: dict) -> None:
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
