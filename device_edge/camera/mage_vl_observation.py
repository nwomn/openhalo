"""Bounded local adapter for Mage-VL structured output."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Iterator


MAGE_VL_SCHEMA_VERSION = "mage_vl_understanding.v1"
MAX_SCENE_CHARS = 240
MAX_READABLE_TEXT_ITEMS = 3
MAX_READABLE_TEXT_CHARS = 120
_REQUIRED_FIELDS = frozenset({"people_count", "scene", "readable_text", "confidence"})


class MageVLOutputError(ValueError):
    """Raised when model output cannot be admitted to the bounded local shape."""


@dataclass(frozen=True)
class MageVLUnderstanding:
    """Media-free meaning extracted from one Mage-VL response."""

    people_count: int | None
    scene: str
    readable_text: tuple[str, ...]
    confidence: float

    def to_value(self) -> dict[str, Any]:
        return {
            "people_count": self.people_count,
            "scene": self.scene,
            "readable_text": list(self.readable_text),
            "confidence": self.confidence,
        }

    def to_local_annotation(
        self,
        *,
        observed_at: str,
        source_device_id: str,
        source_event_id: str,
        model_revision: str = "unknown",
    ) -> dict[str, Any]:
        """Build a local-only annotation, never a Runtime Observation frame."""
        for name, value in (
            ("observed_at", observed_at),
            ("source_device_id", source_device_id),
            ("source_event_id", source_event_id),
            ("model_revision", model_revision),
        ):
            if not isinstance(value, str) or not value.strip():
                raise MageVLOutputError(f"{name} must be a non-empty string")
        return {
            "kind": "camera.semantic_understanding_annotation",
            "schema_version": MAGE_VL_SCHEMA_VERSION,
            "observed_at": observed_at,
            "source": {"device_id": source_device_id, "event_id": source_event_id},
            "model": {"name": "Mage-VL", "revision": model_revision},
            "value": self.to_value(),
            "privacy": {"raw_media_included": False, "retention": "local_only"},
        }


def _iter_json_objects(raw_output: str) -> Iterator[dict[str, Any]]:
    decoder = json.JSONDecoder()
    for index, character in enumerate(raw_output):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(raw_output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            yield value


def _validate_value(value: dict[str, Any]) -> MageVLUnderstanding | None:
    if set(value) != _REQUIRED_FIELDS:
        return None
    people_count = value["people_count"]
    if people_count is not None and (
        isinstance(people_count, bool)
        or not isinstance(people_count, int)
        or people_count < 0
    ):
        return None
    scene = value["scene"]
    if not isinstance(scene, str):
        return None
    scene = scene.strip()
    if not scene or len(scene) > MAX_SCENE_CHARS:
        return None
    readable_text = value["readable_text"]
    if not isinstance(readable_text, list) or len(readable_text) > MAX_READABLE_TEXT_ITEMS:
        return None
    normalized_text: list[str] = []
    for item in readable_text:
        if not isinstance(item, str):
            return None
        item = item.strip()
        if not item or len(item) > MAX_READABLE_TEXT_CHARS:
            return None
        normalized_text.append(item)
    confidence = value["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return None
    try:
        confidence_float = float(confidence)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(confidence_float) or not 0 <= confidence_float <= 1:
        return None
    return MageVLUnderstanding(
        people_count=people_count,
        scene=scene,
        readable_text=tuple(normalized_text),
        confidence=confidence_float,
    )


def parse_mage_vl_output(raw_output: str) -> MageVLUnderstanding:
    """Extract exactly one bounded Mage-VL object from CLI output.

    Native CLI logs may surround the model response. Ambiguous output, extra
    fields, unbounded strings, and invalid numeric values fail closed.
    """
    if not isinstance(raw_output, str) or not raw_output.strip():
        raise MageVLOutputError("Mage-VL output must be a non-empty string")
    matches = [
        understanding
        for value in _iter_json_objects(raw_output)
        if (understanding := _validate_value(value)) is not None
    ]
    if len(matches) != 1:
        raise MageVLOutputError(
            "expected exactly one valid Mage-VL object; "
            f"found {len(matches)}",
        )
    return matches[0]
