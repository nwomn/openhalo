"""Persistent Camera Edge session with opt-in local person-presence sensing.

Health reporting is always available.  Person presence is an explicit opt-in
Feature that processes frames locally and sends only debounced semantic state.
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
import time
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
PERSON_PRESENCE_CAPABILITY_NAME = "camera.person_presence"
PERSON_PRESENCE_OBSERVATION_NAME = "camera.person_presence.v1"
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
    },
]

PERSON_PRESENCE_CAPABILITY = {
    "name": PERSON_PRESENCE_CAPABILITY_NAME,
    "direction": "edge_to_runtime",
    "kind": "observation_provider",
    "observations": [
        {
            "name": PERSON_PRESENCE_OBSERVATION_NAME,
            "schema": {
                "type": "object",
                "required": ["state", "count", "feature_version"],
                "properties": {
                    "state": {
                        "type": "string",
                        "enum": ["present", "absent", "unavailable"],
                    },
                    "count": {"type": "integer", "nullable": True, "minimum": 0},
                    "feature_version": {"type": "string", "enum": ["person_presence.v1"]},
                },
            },
            "semantics": ["ambient_presence", "person_presence"],
            "privacy": "ambient_presence",
            "freshness_seconds": 30,
            "confidence": {"type": "model_score"},
        }
    ],
}


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


def probe_camera_capture() -> str:
    """Open the sensor once, read one frame, and always release it.

    This has no media side effect: the frame never leaves process memory and
    is immediately discarded. Callers must opt in because it temporarily owns
    the sensor and can conflict with a MaixVision preview.
    """

    camera_device = None
    try:
        from maix import camera

        camera_device = camera.Camera(320, 240, fps=1, buff_num=2)
        frame = camera_device.read(block=True, block_ms=3000)
        if frame is None:
            return "unavailable"
        return "ready"
    except Exception:
        return "unavailable"
    finally:
        if camera_device is not None:
            try:
                camera_device.close()
            except Exception:
                pass


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


def build_person_presence_frame(
    device_id: str,
    decision,
    *,
    observed_at: str,
) -> dict:
    """Build a semantic-only Feature frame; geometry and raw media are absent."""

    observations = [
        {
            "name": PERSON_PRESENCE_OBSERVATION_NAME,
            "value": {
                "state": decision.state,
                "count": decision.count,
                "feature_version": "person_presence.v1",
            },
            "observed_at": observed_at,
            "confidence": decision.confidence,
        }
    ]
    return {
        "api_version": API_VERSION,
        "type": "observation_push",
        "device_id": device_id,
        "capability": PERSON_PRESENCE_CAPABILITY_NAME,
        "event_id": f"camera-person-presence-{secrets.token_urlsafe(12)}",
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
        capture_probe_enabled: bool = False,
        person_presence_feature=None,
        presence_confirm_samples: int = 2,
        presence_interval_seconds: float = 1.0,
        presence_freshness_seconds: float = 30.0,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive.")
        if min_free_mib < 0:
            raise ValueError("min_free_mib must be non-negative.")
        if presence_interval_seconds <= 0 or presence_freshness_seconds <= 0:
            raise ValueError("presence intervals must be positive.")
        self.client = client
        self.status_store = status_store
        self.interval_seconds = interval_seconds
        self.min_free_mib = min_free_mib
        self.capture_state = "not_checked"
        if capture_probe_enabled:
            self.capture_state = probe_camera_capture()
        self.person_presence_feature = person_presence_feature
        self.presence_interval_seconds = presence_interval_seconds
        self.presence_freshness_seconds = presence_freshness_seconds
        self._presence_debouncer = None
        self._last_presence_published_at = 0.0
        if person_presence_feature is not None:
            try:
                from .person_presence import PresenceDebouncer
            except ImportError:  # pragma: no cover - copied MaixCAM files.
                from person_presence import PresenceDebouncer
            self._presence_debouncer = PresenceDebouncer(presence_confirm_samples)

    @property
    def capabilities(self) -> list[dict]:
        if self.person_presence_feature is None:
            return DEFAULT_CAPABILITIES
        return [*DEFAULT_CAPABILITIES, PERSON_PRESENCE_CAPABILITY]

    def _next_presence_frame(self, *, force: bool = False) -> dict | None:
        if self.person_presence_feature is None or self._presence_debouncer is None:
            return None
        decision = self._presence_debouncer.observe(self.person_presence_feature.sample())
        now_monotonic = time.monotonic()
        confirmed = self._presence_debouncer.confirmed
        if decision is None and not (
            force
            or (
                confirmed is not None
                and now_monotonic - self._last_presence_published_at >= self.presence_freshness_seconds
            )
        ):
            return None
        if confirmed is None:
            return None
        self._last_presence_published_at = now_monotonic
        return build_person_presence_frame(
            self.client.device_id,
            confirmed,
            observed_at=_utc_timestamp(),
        )

    def _record_status(self, connection_state: str, last_error: str | None = None) -> CameraHealthStatus:
        status = collect_health(
            min_free_mib=self.min_free_mib,
            connection_state=connection_state,
            last_error=last_error,
        )
        status = CameraHealthStatus(
            updated_at=status.updated_at,
            connection_state=status.connection_state,
            capture_state=self.capture_state,
            storage_state=status.storage_state,
            storage_free_mib=status.storage_free_mib,
            last_error=status.last_error,
        )
        self.status_store.write(status)
        return status

    async def _run_session(self, *, once: bool) -> None:
        self._record_status("reconnecting")
        next_health_at = 0.0
        next_presence_at = 0.0
        try:
            async with websockets.connect(self.client.audience) as websocket:
                await self.client.authenticate(websocket, self.capabilities)
                while True:
                    now_monotonic = time.monotonic()
                    if now_monotonic >= next_health_at:
                        status = self._record_status("connected")
                        await websocket.send(json.dumps(build_health_frame(self.client.device_id, status)))
                        next_health_at = now_monotonic + self.interval_seconds
                    if self.person_presence_feature is not None and now_monotonic >= next_presence_at:
                        presence_frame = self._next_presence_frame(force=once)
                        if presence_frame is not None:
                            await websocket.send(json.dumps(presence_frame))
                        next_presence_at = now_monotonic + self.presence_interval_seconds
                    if once:
                        return
                    next_due = [next_health_at]
                    if self.person_presence_feature is not None:
                        next_due.append(next_presence_at)
                    wait_seconds = min(next_due) - time.monotonic()
                    wait_seconds = max(0.05, wait_seconds)
                    try:
                        raw_frame = await asyncio.wait_for(websocket.recv(), timeout=wait_seconds)
                    except TimeoutError:
                        continue
                    reply = json.loads(raw_frame)
                    if reply.get("type") == "error":
                        raise RuntimeError(reply.get("message", "Runtime rejected a Camera Edge frame."))
        finally:
            if self.person_presence_feature is not None:
                self.person_presence_feature.close()

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
    parser.add_argument(
        "--capture-probe",
        action="store_true",
        help="Open the camera once and report ready/unavailable; does not save or upload a frame.",
    )
    parser.add_argument(
        "--person-presence",
        action="store_true",
        help="Enable local-only YOLO11 person presence; no frames or geometry leave the device.",
    )
    parser.add_argument("--presence-model", default="/root/models/yolo11n.mud")
    parser.add_argument("--presence-confidence", type=float, default=0.55)
    parser.add_argument("--presence-confirm-samples", type=int, default=2)
    parser.add_argument("--presence-interval-seconds", type=float, default=1.0)
    parser.add_argument("--presence-freshness-seconds", type=float, default=30.0)
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
    person_presence_feature = None
    if args.person_presence:
        try:
            from .person_presence import MaixPersonPresenceFeature
        except ImportError:  # pragma: no cover - copied MaixCAM files.
            from person_presence import MaixPersonPresenceFeature
        person_presence_feature = MaixPersonPresenceFeature(
            model_path=args.presence_model,
            confidence_threshold=args.presence_confidence,
        )
    daemon = CameraHealthDaemon(
        client=client,
        status_store=LocalStatusStore(Path(args.status_path)),
        interval_seconds=args.interval_seconds,
        min_free_mib=args.min_free_mib,
        capture_probe_enabled=args.capture_probe,
        person_presence_feature=person_presence_feature,
        presence_confirm_samples=args.presence_confirm_samples,
        presence_interval_seconds=args.presence_interval_seconds,
        presence_freshness_seconds=args.presence_freshness_seconds,
    )
    if args.once:
        asyncio.run(daemon.run_once())
    else:
        asyncio.run(daemon.run_forever())
    return 0


if __name__ == "__main__":  # pragma: no cover - command-line entry point.
    raise SystemExit(main())
