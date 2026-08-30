"""Bounded MaixCAM capability manifest and non-invasive SDK probes.

The manifest distinguishes an importable SDK surface from an enabled OpenHalo
Feature.  It never opens the camera, starts recording, scans nearby devices,
or exposes raw media.
"""

from __future__ import annotations

import importlib
import os
import shutil
from collections.abc import Callable
from collections.abc import Iterable


CAPABILITY_NAME = "camera.capability_manifest"
OBSERVATION_NAME = "camera.capability_manifest.v1"
MANIFEST_VERSION = "maixcam.capability_manifest.v1"

CAPABILITY_REGISTRATION = {
    "name": CAPABILITY_NAME,
    "direction": "edge_to_runtime",
    "kind": "observation_provider",
    "observations": [
        {
            "name": OBSERVATION_NAME,
            "schema": {
                "type": "object",
                "required": ["manifest_version", "capabilities"],
                "properties": {
                    "manifest_version": {"type": "string", "enum": [MANIFEST_VERSION]},
                    "capabilities": {"type": "array"},
                },
            },
            "semantics": ["device_capability", "device_health"],
            "privacy": "device_health",
            "freshness_seconds": 3600,
            "confidence": {"type": "edge_reported"},
        }
    ],
}


def _module_available(module_loader: Callable[[str], object], *module_names: str) -> bool:
    for module_name in module_names:
        try:
            module_loader(module_name)
        except Exception:
            return False
    return True


def _network_state(interface_names: Iterable[str] | None) -> str:
    if interface_names is None:
        try:
            interface_names = os.listdir("/sys/class/net")
        except OSError:
            return "not_checked"
    return "available" if any(name != "lo" for name in interface_names) else "unavailable"


def _storage_state() -> str:
    try:
        shutil.disk_usage("/")
    except OSError:
        return "unavailable"
    return "available"


def collect_capability_manifest(
    *,
    person_presence_enabled: bool,
    module_loader: Callable[[str], object] = importlib.import_module,
    interface_names: Iterable[str] | None = None,
) -> dict:
    """Return the declared MaixCAM surface without claiming every Feature runs.

    ``available`` from an SDK probe means only that the relevant local module
    imported.  Sensor ownership, model files, calibration, and Feature-level
    acceptance remain separate checks reflected by ``implementation_state``.
    """

    camera_sdk = _module_available(module_loader, "maix.camera")
    vision_sdk = _module_available(module_loader, "maix.camera", "maix.nn")
    audio_sdk = _module_available(module_loader, "maix.audio")
    display_sdk = _module_available(module_loader, "maix.display")

    def entry(
        capability_id: str,
        *,
        state: str,
        implementation_state: str,
        probe: str,
    ) -> dict:
        return {
            "id": capability_id,
            "state": state,
            "implementation_state": implementation_state,
            "probe": probe,
        }

    return {
        "manifest_version": MANIFEST_VERSION,
        "capabilities": [
            entry(
                "camera.capture",
                state="available" if camera_sdk else "unavailable",
                implementation_state="limited",
                probe="maix.camera_import",
            ),
            entry(
                "camera.quality",
                state="available" if camera_sdk else "unavailable",
                implementation_state="planned",
                probe="maix.camera_import",
            ),
            entry(
                "vision.person_presence",
                state="available" if vision_sdk else "unavailable",
                implementation_state="enabled" if person_presence_enabled else "implemented_disabled",
                probe="maix.camera_and_nn_import",
            ),
            *[
                entry(
                    capability_id,
                    state="available" if vision_sdk else "unavailable",
                    implementation_state="planned",
                    probe="maix.camera_and_nn_import",
                )
                for capability_id in (
                    "vision.object_presence",
                    "vision.ocr",
                    "vision.face",
                    "vision.gesture",
                    "vision.pose",
                    "camera.visual_foreground",
                )
            ],
            entry(
                "audio.microphone",
                state="available" if audio_sdk else "unavailable",
                implementation_state="declared",
                probe="maix.audio_import",
            ),
            *[
                entry(
                    capability_id,
                    state="available" if audio_sdk else "unavailable",
                    implementation_state="planned",
                    probe="maix.audio_import",
                )
                for capability_id in ("audio.speech_activity", "audio.addressing")
            ],
            entry(
                "device.display",
                state="available" if display_sdk else "unavailable",
                implementation_state="deferred",
                probe="maix.display_import",
            ),
            entry(
                "network.link",
                state=_network_state(interface_names),
                implementation_state="implemented",
                probe="sysfs_interface_listing",
            ),
            entry(
                "storage.local",
                state=_storage_state(),
                implementation_state="implemented",
                probe="root_filesystem_usage",
            ),
        ],
    }
