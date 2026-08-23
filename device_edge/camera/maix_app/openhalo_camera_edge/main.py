"""Maix App entry point for the minimal OpenHalo Camera Edge.

The installed package carries no Runtime endpoint or credentials.  Those stay
in the device-private configuration directory next to the P-256 identity.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from health_daemon import CameraHealthDaemon
from health_daemon import LocalStatusStore
from openssl_session import OpenSslCameraSessionClient
from person_presence import MaixPersonPresenceFeature


DEFAULT_CONFIG_PATH = Path("/root/.openhalo-camera-edge/app-config.json")


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RuntimeError(f"OpenHalo Camera Edge configuration is missing: {path}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"OpenHalo Camera Edge configuration is invalid: {path}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("runtime_url"), str):
        raise RuntimeError("OpenHalo Camera Edge configuration requires a string runtime_url.")
    return payload


def build_daemon(config: dict) -> CameraHealthDaemon:
    identity_home = Path(config.get("identity_home", "/root/.openhalo-camera-edge"))
    client = OpenSslCameraSessionClient(
        device_id=config.get("device_id", "camera-edge-1"),
        audience=config["runtime_url"],
        identity_home=identity_home,
        display_name=config.get("display_name", "Desk Camera"),
        device_type="camera-edge",
    )
    feature = MaixPersonPresenceFeature(
        model_path=config.get("presence_model", "/root/models/yolo11n.mud"),
        confidence_threshold=float(config.get("presence_confidence", 0.55)),
    )
    return CameraHealthDaemon(
        client=client,
        status_store=LocalStatusStore(
            Path(config.get("status_path", str(identity_home / "status.json")))
        ),
        interval_seconds=float(config.get("health_interval_seconds", 60.0)),
        min_free_mib=int(config.get("min_free_mib", 256)),
        person_presence_feature=feature,
        presence_confirm_samples=int(config.get("presence_confirm_samples", 2)),
        presence_interval_seconds=float(config.get("presence_interval_seconds", 1.0)),
        presence_freshness_seconds=float(config.get("presence_freshness_seconds", 30.0)),
    )


def main() -> int:
    daemon = build_daemon(load_config())
    asyncio.run(daemon.run_forever())
    return 0


if __name__ == "__main__":  # pragma: no cover - launched by Maix App Launcher.
    raise SystemExit(main())
