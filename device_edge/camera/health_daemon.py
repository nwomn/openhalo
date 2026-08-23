"""Persistent, health-only Camera Edge session for the MaixCAM bootstrap.

This first M17.10 service deliberately reports only connection, capture-probe,
and storage health. It never opens the camera, records media, or uploads media.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import shutil
import sys
import tempfile
from dataclasses import asdict
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path

import websockets

try:  # Support both ``python -m`` and the copied single-directory device form.
    from .openssl_session import API_VERSION
    from .openssl_session import OpenSslCameraSessionClient
except ImportError:  # pragma: no cover - exercised on the copied MaixCAM files.
    from openssl_session import API_VERSION
    from openssl_session import OpenSslCameraSessionClient


CAPABILITY_NAME = "camera.health"
DEFAULT_CAPABILITIES = [
    {
        "name": CAPABILITY_NAME,
        "direction": "edge_to_runtime",
        "kind": "observation_provider",
        "observations": [
            {
                "name": "camera.connection_state",
                "schema": {
                    "type": "string",
                    "enum": ["connected", "reconnecting", "auth_failed"],
                },
                "semantics": ["device_health"],
                "privacy": "device_health",
                "freshness_seconds": 120,
                "confidence": {"type": "edge_reported"},
            },
            {
                "name": "camera.capture_state",
                "schema": {
                    "type": "string",
                    "enum": ["not_checked", "ready", "unavailable"],
                },
                "semantics": ["device_health"],
                "privacy": "device_health",
                "freshness_seconds": 120,
                "confidence": {"type": "edge_reported"},
            },
            {
                "name": "camera.storage_state",
                "schema": {"type": "string", "enum": ["ready", "degraded"]},
                "semantics": ["device_health"],
                "privacy": "device_health",
                "freshness_seconds": 120,
                "confidence": {"type": "edge_reported"},
            },
            {
                "name": "camera.storage_free_mib",
                "schema": {"type": "integer", "minimum": 0},
                "semantics": ["device_health"],
                "privacy": "device_health",
                "freshness_seconds": 120,
                "confidence": {"type": "edge_reported"},
            },
        ],
    }
]


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class CameraHealthStatus:
    updated_at: str
    connection_state: str
    capture_state: str
    storage_state: str
    storage_free_mib: int
    last_error: str | None = None


class LocalStatusStore:
    """Atomically writes the bounded local status payload for a display/UI."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, status: CameraHealthStatus) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(asdict(status), output, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_name, self.path)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise


def collect_health(*, min_free_mib: int, connection_state: str, last_error: str | None = None) -> CameraHealthStatus:
    free_mib = shutil.disk_usage("/").free // (1024 * 1024)
    return CameraHealthStatus(
        updated_at=_utc_timestamp(),
        connection_state=connection_state,
        # Camera initialization is an explicit later operation; this daemon
        # must never compete with a MaixVision preview for the sensor.
        capture_state="not_checked",
        storage_state="ready" if free_mib >= min_free_mib else "degraded",
        storage_free_mib=free_mib,
        last_error=last_error,
    )


def build_health_frame(device_id: str, status: CameraHealthStatus) -> dict:
    observations = [
        {
            "name": "camera.connection_state",
            "value": status.connection_state,
            "observed_at": status.updated_at,
            "confidence": 1.0,
        },
        {
            "name": "camera.capture_state",
            "value": status.capture_state,
            "observed_at": status.updated_at,
            "confidence": 1.0,
        },
        {
            "name": "camera.storage_state",
            "value": status.storage_state,
            "observed_at": status.updated_at,
            "confidence": 1.0,
        },
        {
            "name": "camera.storage_free_mib",
            "value": status.storage_free_mib,
            "observed_at": status.updated_at,
            "confidence": 1.0,
        },
    ]
    return {
        "api_version": API_VERSION,
        "type": "observation_push",
        "device_id": device_id,
        "capability": CAPABILITY_NAME,
        "event_id": f"camera-health-{secrets.token_urlsafe(12)}",
        "observations": observations,
        "payload": {"observations": observations},
    }


class CameraHealthDaemon:
    def __init__(
        self,
        *,
        client: OpenSslCameraSessionClient,
        status_store: LocalStatusStore,
        interval_seconds: float,
        min_free_mib: int,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive.")
        if min_free_mib < 0:
            raise ValueError("min_free_mib must be non-negative.")
        self.client = client
        self.status_store = status_store
        self.interval_seconds = interval_seconds
        self.min_free_mib = min_free_mib

    def _record_status(self, connection_state: str, last_error: str | None = None) -> CameraHealthStatus:
        status = collect_health(
            min_free_mib=self.min_free_mib,
            connection_state=connection_state,
            last_error=last_error,
        )
        self.status_store.write(status)
        return status

    async def _run_session(self, *, once: bool) -> None:
        self._record_status("reconnecting")
        async with websockets.connect(self.client.audience) as websocket:
            await self.client.authenticate(websocket, DEFAULT_CAPABILITIES)
            while True:
                status = self._record_status("connected")
                await websocket.send(json.dumps(build_health_frame(self.client.device_id, status)))
                if once:
                    return
                try:
                    raw_frame = await asyncio.wait_for(
                        websocket.recv(), timeout=self.interval_seconds
                    )
                except TimeoutError:
                    continue
                reply = json.loads(raw_frame)
                if reply.get("type") == "error":
                    raise RuntimeError(reply.get("message", "Runtime rejected a Camera Edge frame."))

    async def run_once(self) -> None:
        await self._run_session(once=True)

    async def run_forever(self) -> None:
        delay_seconds = 1.0
        while True:
            try:
                await self._run_session(once=False)
                delay_seconds = 1.0
            except (OSError, RuntimeError, websockets.exceptions.ConnectionClosed) as error:
                self._record_status("auth_failed" if isinstance(error, RuntimeError) else "reconnecting", type(error).__name__)
                await asyncio.sleep(delay_seconds)
                delay_seconds = min(delay_seconds * 2, 30.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the health-only MaixCAM Camera Edge service."
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--device-id", default="camera-edge-1")
    parser.add_argument("--display-name", default="Desk Camera")
    parser.add_argument("--identity-home", default="/root/.openhalo-camera-edge")
    parser.add_argument("--status-path", default="/root/.openhalo-camera-edge/status.json")
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--min-free-mib", type=int, default=256)
    parser.add_argument("--once", action="store_true", help="Authenticate and publish one health snapshot.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = OpenSslCameraSessionClient(
        device_id=args.device_id,
        audience=args.url,
        identity_home=Path(args.identity_home),
        display_name=args.display_name,
        device_type="camera-edge",
    )
    daemon = CameraHealthDaemon(
        client=client,
        status_store=LocalStatusStore(Path(args.status_path)),
        interval_seconds=args.interval_seconds,
        min_free_mib=args.min_free_mib,
    )
    if args.once:
        asyncio.run(daemon.run_once())
    else:
        asyncio.run(daemon.run_forever())
    return 0


if __name__ == "__main__":  # pragma: no cover - command-line entry point.
    raise SystemExit(main())
