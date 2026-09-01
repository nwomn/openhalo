"""Persistent Camera Edge session with local visual Feature sensing.

Health reporting is always available.  The visual Feature is an explicit
opt-in pipeline that processes frames locally and sends only bounded semantic
Observations.  Person presence remains a separate backward-compatible
capability while the object, region, scene-quality, and transition surfaces
are registered alongside it when the shared pipeline is active.
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
from dataclasses import replace
from datetime import UTC
from datetime import datetime
from pathlib import Path

import websockets

try:
    from device_edge.media_memory import MEDIA_MEMORY_QUERY_CAPABILITY
    from device_edge.media_memory import MEDIA_PROVIDER_CONFIGURE_CAPABILITY
    from device_edge.media_memory import media_memory_query_capability
    from device_edge.media_memory import media_provider_configure_capability
except ImportError:  # pragma: no cover - copied MaixCAM files.
    from media_memory import MEDIA_MEMORY_QUERY_CAPABILITY
    from media_memory import MEDIA_PROVIDER_CONFIGURE_CAPABILITY
    from media_memory import media_memory_query_capability
    from media_memory import media_provider_configure_capability

try:  # Support both ``python -m`` and the copied single-directory device form.
    from .openssl_session import API_VERSION
    from .openssl_session import OpenSslCameraSessionClient
except ImportError:  # pragma: no cover - exercised on the copied MaixCAM files.
    from openssl_session import API_VERSION
    from openssl_session import OpenSslCameraSessionClient


CAPABILITY_NAME = "camera.health"
PERSON_PRESENCE_CAPABILITY_NAME = "camera.person_presence"
PERSON_PRESENCE_OBSERVATION_NAME = "camera.person_presence.v1"
OBJECT_PRESENCE_CAPABILITY_NAME = "camera.object_presence"
OBJECT_PRESENCE_OBSERVATION_NAME = "camera.object_presence.v1"
REGION_OCCUPANCY_CAPABILITY_NAME = "camera.region_occupancy"
REGION_OCCUPANCY_OBSERVATION_NAME = "camera.region_occupancy.v1"
REGION_TRANSITION_CAPABILITY_NAME = "camera.region_occupancy_transition"
REGION_TRANSITION_OBSERVATION_NAME = "camera.region_occupancy_transition.v1"
SCENE_QUALITY_CAPABILITY_NAME = "camera.scene_quality"
SCENE_QUALITY_OBSERVATION_NAME = "camera.scene_quality.v1"
PRESENCE_TRANSITION_CAPABILITY_NAME = "camera.person_presence_transition"
PRESENCE_TRANSITION_OBSERVATION_NAME = "camera.person_presence_transition.v1"
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

OBJECT_PRESENCE_CAPABILITY = {
    "name": OBJECT_PRESENCE_CAPABILITY_NAME,
    "direction": "edge_to_runtime",
    "kind": "observation_provider",
    "observations": [
        {
            "name": OBJECT_PRESENCE_OBSERVATION_NAME,
            "schema": {
                "type": "object",
                "required": ["state", "objects", "feature_version"],
                "properties": {
                    "state": {"type": "string", "enum": ["ready", "unavailable"]},
                    "objects": {"type": "object"},
                    "feature_version": {
                        "type": "string",
                        "enum": ["object_presence.v1"],
                    },
                },
            },
            "semantics": ["ambient_scene", "object_presence"],
            "privacy": "ambient_scene",
            "freshness_seconds": 30,
            "confidence": {"type": "model_score"},
        }
    ],
}

REGION_OCCUPANCY_CAPABILITY = {
    "name": REGION_OCCUPANCY_CAPABILITY_NAME,
    "direction": "edge_to_runtime",
    "kind": "observation_provider",
    "observations": [
        {
            "name": REGION_OCCUPANCY_OBSERVATION_NAME,
            "schema": {
                "type": "object",
                "required": ["state", "regions", "feature_version"],
                "properties": {
                    "state": {"type": "string", "enum": ["ready", "unavailable"]},
                    "regions": {"type": "object"},
                    "feature_version": {
                        "type": "string",
                        "enum": ["region_occupancy.v1"],
                    },
                },
            },
            "semantics": ["ambient_presence", "region_occupancy"],
            "privacy": "ambient_presence",
            "freshness_seconds": 30,
            "confidence": {"type": "model_score"},
        }
    ],
}

REGION_TRANSITION_CAPABILITY = {
    "name": REGION_TRANSITION_CAPABILITY_NAME,
    "direction": "edge_to_runtime",
    "kind": "observation_provider",
    "observations": [
        {
            "name": REGION_TRANSITION_OBSERVATION_NAME,
            "schema": {
                "type": "object",
                "required": [
                    "region",
                    "from_occupied",
                    "to_occupied",
                    "from_count",
                    "to_count",
                    "transition",
                    "feature_version",
                ],
                "properties": {
                    "region": {"type": "string"},
                    "from_occupied": {"type": "boolean", "nullable": True},
                    "to_occupied": {"type": "boolean", "nullable": True},
                    "from_count": {"type": "integer", "nullable": True, "minimum": 0},
                    "to_count": {"type": "integer", "nullable": True, "minimum": 0},
                    "transition": {
                        "type": "string",
                        "enum": ["entered", "left", "count_changed", "availability_changed"],
                    },
                    "feature_version": {
                        "type": "string",
                        "enum": ["region_occupancy_transition.v1"],
                    },
                },
            },
            "semantics": ["ambient_presence", "region_transition"],
            "privacy": "ambient_presence",
            "freshness_seconds": 30,
            "confidence": {"type": "model_score"},
        }
    ],
}

SCENE_QUALITY_CAPABILITY = {
    "name": SCENE_QUALITY_CAPABILITY_NAME,
    "direction": "edge_to_runtime",
    "kind": "observation_provider",
    "observations": [
        {
            "name": SCENE_QUALITY_OBSERVATION_NAME,
            "schema": {
                "type": "object",
                "required": ["state", "camera_state", "width", "height", "feature_version"],
                "properties": {
                    "state": {"type": "string", "enum": ["ready", "unavailable"]},
                    "camera_state": {
                        "type": "string",
                        "enum": ["ready", "unavailable"],
                    },
                    "width": {"type": "integer", "nullable": True, "minimum": 0},
                    "height": {"type": "integer", "nullable": True, "minimum": 0},
                    "feature_version": {
                        "type": "string",
                        "enum": ["scene_quality.v1"],
                    },
                },
            },
            "semantics": ["camera_availability", "capture_quality"],
            "privacy": "device_health",
            "freshness_seconds": 30,
            "confidence": {"type": "edge_reported"},
        }
    ],
}

PRESENCE_TRANSITION_CAPABILITY = {
    "name": PRESENCE_TRANSITION_CAPABILITY_NAME,
    "direction": "edge_to_runtime",
    "kind": "observation_provider",
    "observations": [
        {
            "name": PRESENCE_TRANSITION_OBSERVATION_NAME,
            "schema": {
                "type": "object",
                "required": [
                    "from_state",
                    "to_state",
                    "from_count",
                    "to_count",
                    "transition",
                    "feature_version",
                ],
                "properties": {
                    "from_state": {
                        "type": "string",
                        "nullable": True,
                        "enum": ["present", "absent", "unavailable"],
                    },
                    "to_state": {
                        "type": "string",
                        "enum": ["present", "absent", "unavailable"],
                    },
                    "from_count": {"type": "integer", "nullable": True, "minimum": 0},
                    "to_count": {"type": "integer", "nullable": True, "minimum": 0},
                    "transition": {
                        "type": "string",
                        "enum": ["entered", "left", "count_changed", "availability_changed"],
                    },
                    "feature_version": {
                        "type": "string",
                        "enum": ["person_presence_transition.v1"],
                    },
                },
            },
            "semantics": ["ambient_presence", "presence_transition"],
            "privacy": "ambient_presence",
            "freshness_seconds": 30,
            "confidence": {"type": "model_score"},
        }
    ],
}

VISUAL_CAPABILITIES = [
    OBJECT_PRESENCE_CAPABILITY,
    REGION_OCCUPANCY_CAPABILITY,
    REGION_TRANSITION_CAPABILITY,
    SCENE_QUALITY_CAPABILITY,
    PRESENCE_TRANSITION_CAPABILITY,
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


def _build_visual_frame(
    device_id: str,
    *,
    capability: str,
    observation_name: str,
    value: dict,
    observed_at: str,
    confidence: float,
    event_prefix: str,
) -> dict:
    observation = {
        "name": observation_name,
        "value": value,
        "observed_at": observed_at,
        "confidence": confidence,
    }
    return {
        "api_version": API_VERSION,
        "type": "observation_push",
        "device_id": device_id,
        "capability": capability,
        "event_id": f"{event_prefix}-{secrets.token_urlsafe(12)}",
        "observations": [observation],
        "payload": {"observations": [observation]},
    }


def build_object_presence_frame(
    device_id: str,
    sample,
    *,
    observed_at: str,
) -> dict:
    """Build an allowlisted object-count Observation without geometry."""

    return _build_visual_frame(
        device_id,
        capability=OBJECT_PRESENCE_CAPABILITY_NAME,
        observation_name=OBJECT_PRESENCE_OBSERVATION_NAME,
        value={
            "state": sample.state,
            "objects": dict(sample.object_counts),
            "feature_version": "object_presence.v1",
        },
        observed_at=observed_at,
        confidence=sample.person_confidence if sample.state == "ready" else 0.0,
        event_prefix="camera-object-presence",
    )


def build_region_occupancy_frame(
    device_id: str,
    sample,
    *,
    observed_at: str,
) -> dict:
    """Build configured region occupancy as person counts and booleans."""

    regions = {
        name: {
            "occupied": occupancy.occupied,
            "count": occupancy.count,
        }
        for name, occupancy in sample.regions.items()
    }
    return _build_visual_frame(
        device_id,
        capability=REGION_OCCUPANCY_CAPABILITY_NAME,
        observation_name=REGION_OCCUPANCY_OBSERVATION_NAME,
        value={
            "state": sample.state,
            "regions": regions,
            "feature_version": "region_occupancy.v1",
        },
        observed_at=observed_at,
        confidence=sample.person_confidence if sample.state == "ready" else 0.0,
        event_prefix="camera-region-occupancy",
    )


def _region_transition_kind(previous, current) -> str:
    if previous.occupied is False and current.occupied is True:
        return "entered"
    if previous.occupied is True and current.occupied is False:
        return "left"
    if previous.occupied != current.occupied:
        return "availability_changed"
    return "count_changed"


def build_region_transition_frame(
    device_id: str,
    region_name: str,
    previous,
    current,
    *,
    observed_at: str,
    confidence: float,
) -> dict:
    """Build one confirmed enter/leave/count change for a configured region."""

    return _build_visual_frame(
        device_id,
        capability=REGION_TRANSITION_CAPABILITY_NAME,
        observation_name=REGION_TRANSITION_OBSERVATION_NAME,
        value={
            "region": region_name,
            "from_occupied": previous.occupied,
            "to_occupied": current.occupied,
            "from_count": previous.count,
            "to_count": current.count,
            "transition": _region_transition_kind(previous, current),
            "feature_version": "region_occupancy_transition.v1",
        },
        observed_at=observed_at,
        confidence=confidence,
        event_prefix="camera-region-occupancy-transition",
    )


def build_scene_quality_frame(
    device_id: str,
    sample,
    *,
    observed_at: str,
) -> dict:
    """Build the bounded camera-availability/frame-dimensions Observation."""

    return _build_visual_frame(
        device_id,
        capability=SCENE_QUALITY_CAPABILITY_NAME,
        observation_name=SCENE_QUALITY_OBSERVATION_NAME,
        value={
            "state": sample.state,
            "camera_state": sample.state,
            "width": sample.width,
            "height": sample.height,
            "feature_version": "scene_quality.v1",
        },
        observed_at=observed_at,
        confidence=1.0 if sample.state == "ready" else 0.0,
        event_prefix="camera-scene-quality",
    )


def _presence_transition_kind(previous, current) -> str:
    if previous.state == "absent" and current.state == "present":
        return "entered"
    if previous.state == "present" and current.state == "absent":
        return "left"
    if previous.state != current.state:
        return "availability_changed"
    return "count_changed"


def build_presence_transition_frame(
    device_id: str,
    previous,
    current,
    *,
    observed_at: str,
) -> dict:
    """Build a state/count transition after temporal confirmation."""

    return _build_visual_frame(
        device_id,
        capability=PRESENCE_TRANSITION_CAPABILITY_NAME,
        observation_name=PRESENCE_TRANSITION_OBSERVATION_NAME,
        value={
            "from_state": previous.state,
            "to_state": current.state,
            "from_count": previous.count,
            "to_count": current.count,
            "transition": _presence_transition_kind(previous, current),
            "feature_version": "person_presence_transition.v1",
        },
        observed_at=observed_at,
        confidence=current.confidence,
        event_prefix="camera-person-presence-transition",
    )


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
        media_memory_executor=None,
        provider_credentials=None,
        camera_edge_service=None,
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
        self.visual_features_enabled = bool(
            person_presence_feature is not None
            and (
                getattr(person_presence_feature, "supports_visual_features", False)
                or hasattr(person_presence_feature, "last_visual_sample")
            )
        )
        self.presence_interval_seconds = presence_interval_seconds
        self.presence_freshness_seconds = presence_freshness_seconds
        self._presence_debouncer = None
        self._last_presence_published_at = 0.0
        self._last_visual_published_at = 0.0
        self._last_presence_decision = None
        self._last_visual_sample = None
        self._region_confirm_samples = presence_confirm_samples
        self._region_candidates = {}
        self._confirmed_regions = {}
        self.media_memory_executor = media_memory_executor
        self.provider_credentials = provider_credentials
        self.camera_edge_service = camera_edge_service
        if person_presence_feature is not None:
            try:
                from .person_presence import PresenceDebouncer
            except ImportError:  # pragma: no cover - copied MaixCAM files.
                from person_presence import PresenceDebouncer
            self._presence_debouncer = PresenceDebouncer(presence_confirm_samples)

    @property
    def capabilities(self) -> list[dict]:
        capabilities = [*DEFAULT_CAPABILITIES]
        if self.person_presence_feature is not None:
            capabilities.append(PERSON_PRESENCE_CAPABILITY)
            if self.visual_features_enabled:
                capabilities.extend(VISUAL_CAPABILITIES)
        if self.media_memory_executor is not None:
            capabilities.append(
                media_memory_query_capability(self.media_memory_executor.hot_ring.source_ref)
            )
        if self.provider_credentials is not None:
            capabilities.append(media_provider_configure_capability())
        return capabilities

    def handle_action_request(self, frame: dict) -> dict | None:
        """Handle source-local media queries without exposing their bytes to Runtime."""

        action = frame.get("action", {})
        capability = action.get("capability")
        if capability == MEDIA_MEMORY_QUERY_CAPABILITY and self.media_memory_executor is not None:
            return self.media_memory_executor.handle_action_request(frame)
        if capability == MEDIA_PROVIDER_CONFIGURE_CAPABILITY and self.provider_credentials is not None:
            return self.provider_credentials.handle_action_request(frame)
        return None

    def _next_presence_frame(self, *, force: bool = False) -> dict | None:
        """Compatibility helper returning only the person frame, if any."""

        for frame in self._next_visual_frames(force=force):
            if frame["capability"] == PERSON_PRESENCE_CAPABILITY_NAME:
                return frame
        return None

    def _next_visual_frames(self, *, force: bool = False) -> list[dict]:
        if self.person_presence_feature is None or self._presence_debouncer is None:
            return []
        sample = self.person_presence_feature.sample()
        return self._visual_frames_from_sample(sample, force=force)

    def observe(self, captured) -> list[dict]:
        """Consume one CameraEdgeService-owned frame for local Features."""

        if self.person_presence_feature is None or self._presence_debouncer is None:
            return []
        sample = self.person_presence_feature.sample_frame(captured.frame)
        return self._visual_frames_from_sample(sample)

    def _visual_frames_from_sample(self, sample, *, force: bool = False) -> list[dict]:
        decision = self._presence_debouncer.observe(sample)
        now_monotonic = time.monotonic()
        confirmed = self._presence_debouncer.confirmed
        observed_at = _utc_timestamp()
        frames: list[dict] = []

        presence_due = confirmed is not None and (
            decision is not None
            or force
            or now_monotonic - self._last_presence_published_at
            >= self.presence_freshness_seconds
        )
        if presence_due:
            frames.append(
                build_person_presence_frame(
                    self.client.device_id,
                    confirmed,
                    observed_at=observed_at,
                )
            )
            previous = self._last_presence_decision
            if (
                decision is not None
                and previous is not None
                and (previous.state, previous.count)
                != (confirmed.state, confirmed.count)
            ):
                frames.append(
                    build_presence_transition_frame(
                        self.client.device_id,
                        previous,
                        confirmed,
                        observed_at=observed_at,
                    )
                )
            self._last_presence_decision = confirmed
            self._last_presence_published_at = now_monotonic

        visual = getattr(self.person_presence_feature, "last_visual_sample", None)
        if self.visual_features_enabled and visual is not None:
            visual = self._debounce_regions(visual)
        visual_changed = visual is not None and visual != self._last_visual_sample
        visual_due = self.visual_features_enabled and visual is not None and (
            force
            or visual_changed
            or self._last_visual_published_at == 0.0
            or now_monotonic - self._last_visual_published_at
            >= self.presence_freshness_seconds
        )
        if visual_due:
            frames.append(
                build_object_presence_frame(
                    self.client.device_id,
                    visual,
                    observed_at=observed_at,
                )
            )
            frames.append(
                build_region_occupancy_frame(
                    self.client.device_id,
                    visual,
                    observed_at=observed_at,
                )
            )
            previous_visual = self._last_visual_sample
            if previous_visual is not None:
                for region_name in sorted(
                    set(previous_visual.regions) | set(visual.regions)
                ):
                    previous_region = previous_visual.regions.get(region_name)
                    current_region = visual.regions.get(region_name)
                    if previous_region is None or current_region is None:
                        continue
                    if previous_region != current_region:
                        frames.append(
                            build_region_transition_frame(
                                self.client.device_id,
                                region_name,
                                previous_region,
                                current_region,
                                observed_at=observed_at,
                                confidence=(
                                    visual.person_confidence
                                    if visual.state == "ready"
                                    else 0.0
                                ),
                            )
                        )
            frames.append(
                build_scene_quality_frame(
                    self.client.device_id,
                    visual,
                    observed_at=observed_at,
                )
            )
            self._last_visual_published_at = now_monotonic
            self._last_visual_sample = visual
        return frames

    def _debounce_regions(self, visual):
        """Apply the same temporal confirmation to configured regions.

        The first sample establishes a baseline.  A later region change must
        repeat ``presence_confirm_samples`` times before the occupancy value or
        transition is published.  An unavailable sensor is surfaced
        immediately so it cannot be mistaken for an empty region.
        """

        if visual.state == "unavailable":
            self._region_candidates.clear()
            self._confirmed_regions = dict(visual.regions)
            return visual

        effective_regions = {}
        for name, current in visual.regions.items():
            key = (current.occupied, current.count)
            if name not in self._confirmed_regions:
                self._confirmed_regions[name] = current
                self._region_candidates[name] = (key, 0)
            candidate_key, candidate_samples = self._region_candidates.get(
                name,
                (key, 0),
            )
            if candidate_key == key:
                candidate_samples += 1
            else:
                candidate_key = key
                candidate_samples = 1
            self._region_candidates[name] = (candidate_key, candidate_samples)
            if candidate_samples >= self._region_confirm_samples:
                self._confirmed_regions[name] = current
            effective_regions[name] = self._confirmed_regions[name]

        for name in set(self._confirmed_regions) - set(visual.regions):
            self._confirmed_regions.pop(name, None)
            self._region_candidates.pop(name, None)
        return replace(visual, regions=effective_regions)

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
        capture_stop_event = None
        capture_task = None
        try:
            async with websockets.connect(self.client.audience) as websocket:
                await self.client.authenticate(websocket, self.capabilities)
                if self.camera_edge_service is not None:
                    async def send_observations(frames: list[dict]) -> None:
                        for frame in frames:
                            await websocket.send(json.dumps(frame))

                    async def send_action_result(frame: dict) -> None:
                        await websocket.send(json.dumps(frame))

                    self.camera_edge_service.observation_sink = send_observations
                    self.camera_edge_service.action_result_sink = send_action_result
                    capture_stop_event = asyncio.Event()
                    capture_task = asyncio.create_task(
                        self.camera_edge_service.run(capture_stop_event)
                    )
                while True:
                    now_monotonic = time.monotonic()
                    if now_monotonic >= next_health_at:
                        status = self._record_status("connected")
                        await websocket.send(json.dumps(build_health_frame(self.client.device_id, status)))
                        next_health_at = now_monotonic + self.interval_seconds
                    if (
                        self.camera_edge_service is None
                        and self.person_presence_feature is not None
                        and now_monotonic >= next_presence_at
                    ):
                        for visual_frame in self._next_visual_frames(force=once):
                            await websocket.send(json.dumps(visual_frame))
                        next_presence_at = now_monotonic + self.presence_interval_seconds
                    if once:
                        return
                    next_due = [next_health_at]
                    if self.camera_edge_service is None and self.person_presence_feature is not None:
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
                    if reply.get("type") == "action_request":
                        if self.camera_edge_service is not None:
                            await self.camera_edge_service.submit_action_request(reply)
                        else:
                            action_result = self.handle_action_request(reply)
                            if action_result is not None:
                                await websocket.send(json.dumps(action_result))
        finally:
            if capture_stop_event is not None:
                capture_stop_event.set()
            if capture_task is not None:
                await capture_task
            elif self.person_presence_feature is not None:
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
        description="Run the MaixCAM Camera Edge health and local-visual service."
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
        "--visual-features",
        dest="person_presence",
        action="store_true",
        help="Enable local-only YOLO11 visual Features; no frames or geometry leave the device.",
    )
    parser.add_argument("--presence-model", default="/root/models/yolo11n.mud")
    parser.add_argument("--presence-confidence", type=float, default=0.55)
    parser.add_argument(
        "--object-label",
        dest="object_labels",
        action="append",
        default=[],
        help="Allowlist one detector label for camera.object_presence (repeatable).",
    )
    parser.add_argument(
        "--region",
        action="append",
        default=[],
        type=_parse_region_argument,
        metavar="NAME:X1,Y1,X2,Y2",
        help="Configure a normalized person-occupancy region (repeatable).",
    )
    parser.add_argument("--presence-confirm-samples", type=int, default=2)
    parser.add_argument("--presence-interval-seconds", type=float, default=1.0)
    parser.add_argument("--presence-freshness-seconds", type=float, default=30.0)
    parser.add_argument("--once", action="store_true", help="Authenticate and publish one health snapshot.")
    return parser


def _parse_region_argument(value: str) -> tuple[str, tuple[float, float, float, float]]:
    try:
        name, raw_bounds = value.split(":", 1)
        bounds = tuple(float(item.strip()) for item in raw_bounds.split(","))
    except (ValueError, TypeError) as error:
        raise argparse.ArgumentTypeError(
            "region must use NAME:X1,Y1,X2,Y2"
        ) from error
    if len(bounds) != 4:
        raise argparse.ArgumentTypeError(
            "region must use NAME:X1,Y1,X2,Y2"
        )
    x1, y1, x2, y2 = bounds
    if not name.strip() or not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
        raise argparse.ArgumentTypeError(
            "region bounds must be an ordered rectangle in [0, 1]"
        )
    return name.strip(), bounds


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
    parsed_regions = dict(args.region)
    if args.person_presence or args.object_labels or parsed_regions:
        try:
            from .person_presence import MaixPersonPresenceFeature
        except ImportError:  # pragma: no cover - copied MaixCAM files.
            from person_presence import MaixPersonPresenceFeature
        person_presence_feature = MaixPersonPresenceFeature(
            model_path=args.presence_model,
            confidence_threshold=args.presence_confidence,
            object_labels=args.object_labels,
            regions=parsed_regions,
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
