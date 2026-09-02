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

try:  # Packaged Maix App: all new modules are sibling files.
    from camera_edge_service import CameraEdgeService
    from maix_media_pipeline import MaixCameraCaptureOwner
    from maix_media_pipeline import MaixH264Mp4SegmentRecorder
    from media_memory import InMemoryMediaProviderCredentials
    from media_memory import LocalHotRing
    from media_memory import MediaMemoryActionExecutor
    from media_provider import OpenAICompatibleVideoAdapter
except ImportError:  # Repository import used by desktop tests.
    from device_edge.camera.camera_edge_service import CameraEdgeService
    from device_edge.camera.maix_media_pipeline import MaixCameraCaptureOwner
    from device_edge.camera.maix_media_pipeline import MaixH264Mp4SegmentRecorder
    from device_edge.media_memory import InMemoryMediaProviderCredentials
    from device_edge.media_memory import LocalHotRing
    from device_edge.media_memory import MediaMemoryActionExecutor
    from device_edge.media_provider import OpenAICompatibleVideoAdapter


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
        object_labels=config.get("object_labels", ()),
        regions=config.get("regions", {}),
    )
    media_enabled = bool(config.get("media_memory_enabled", False))
    source_ref = f"{client.device_id}/camera.main/camera.capture/video"
    identity_home.mkdir(parents=True, exist_ok=True)
    hot_ring = LocalHotRing(
        source_ref=source_ref,
        directory=Path(config.get("hot_ring_path", str(identity_home / "hot-ring"))),
        retention_seconds=int(config.get("hot_ring_retention_seconds", 300)),
        max_bytes=int(config.get("hot_ring_max_bytes", 64 * 1024 * 1024)),
    )
    provider_credentials = InMemoryMediaProviderCredentials()
    adapter = OpenAICompatibleVideoAdapter(
        credentials=provider_credentials,
        provider_name=config.get("media_provider_name", "camera_video_dashscope"),
        model_name=config.get("media_model_name", "camera_video_qwen3_vl_flash"),
    )
    media_executor = MediaMemoryActionExecutor(
        device_id=client.device_id,
        hot_ring=hot_ring,
        understanding_provider=adapter,
        provider_configured=adapter.is_configured,
    )
    daemon = CameraHealthDaemon(
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
        media_memory_executor=media_executor if media_enabled else None,
        provider_credentials=provider_credentials if media_enabled else None,
    )
    # MaixCAM runs the detector, ISP, and H.264 encoder from the same bounded
    # multimedia pools.  Keep the default capture profile aligned with the
    # bundled YOLO11 model (320x224) rather than assuming a desktop-class
    # 640x480 pipeline will fit alongside both consumers.
    width = int(config.get("capture_width", 320))
    height = int(config.get("capture_height", 224))
    fps = int(config.get("capture_fps", 5))
    daemon.camera_edge_service = CameraEdgeService(
        capture_owner=MaixCameraCaptureOwner(width=width, height=height, fps=fps),
        segment_recorder=MaixH264Mp4SegmentRecorder(
            directory=Path(config.get("recording_spool_path", str(identity_home / "recording-spool"))),
            width=width,
            height=height,
            fps=fps,
            bitrate=int(config.get("recording_bitrate", 1_000_000)),
            segment_seconds=float(config.get("recording_segment_seconds", 2.0)),
            enabled=media_enabled,
        ),
        hot_ring=hot_ring,
        media_query_executor=media_executor,
        feature_worker=daemon,
        feature_interval_seconds=float(config.get("presence_interval_seconds", 1.0)),
        capture_interval_seconds=0.0,
        provider_credentials=provider_credentials,
    )
    return daemon


def main() -> int:
    daemon = build_daemon(load_config())
    asyncio.run(daemon.run_forever())
    return 0


if __name__ == "__main__":  # pragma: no cover - launched by Maix App Launcher.
    raise SystemExit(main())
