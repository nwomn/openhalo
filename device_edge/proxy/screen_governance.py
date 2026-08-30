"""Governed, local-first screen observations for Proxy Edge.

This module deliberately does not interpret arbitrary GUI semantics.  It tracks
capture health and bounded pixel change locally, and retains a small evidence
index.  The safe base observations are Profile-independent; the legacy Screen
Profile remains only for the bounded experiment and optional HID gate. Raw JPEG
bytes can return only as a bounded ordinary action-result attachment.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from hashlib import sha256

from device_edge.proxy.adapter import ProxyAdapterError
from device_edge.proxy.contracts import CapturedFrame
from device_edge.proxy.contracts import ProxyTargetAttachment
from device_edge.proxy.contracts import SCREEN_EVIDENCE_ID_MAX_LENGTH
from device_edge.proxy.contracts import SCREEN_FEATURE_CAPABILITY
from device_edge.proxy.contracts import SCREEN_PROFILE_CAPABILITY


CAPTURE_HEALTH_FEATURE = "proxy.screen.capture_health.v1"
CHANGE_FEATURE = "proxy.screen.change.v1"
ACTION_EFFECT_FEATURE = "proxy.screen.action_effect.v1"
SUPPORTED_FEATURES = frozenset(
    {CAPTURE_HEALTH_FEATURE, CHANGE_FEATURE, ACTION_EFFECT_FEATURE}
)
MAX_SCREEN_READ_BYTES = 98_304


def _parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty RFC3339 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be a valid RFC3339 timestamp.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone.")
    return parsed.astimezone(UTC)


def _validate_evidence_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > SCREEN_EVIDENCE_ID_MAX_LENGTH
        or not value.isascii()
        or any(character.isspace() or ord(character) < 0x21 for character in value)
    ):
        raise ValueError("invalid_evidence_id")
    return value


@dataclass(frozen=True, slots=True)
class ScreenProfile:
    profile_id: str
    revision: int
    features: tuple[str, ...]
    expires_at: str
    max_evidence_bytes: int
    visual_action_policy: str

    @classmethod
    def from_action_payload(cls, payload: dict, attachment: ProxyTargetAttachment) -> "ScreenProfile":
        if payload.get("target_id") != attachment.target_id:
            raise ValueError("target_mismatch")
        if payload.get("surface_id") != attachment.surface_id:
            raise ValueError("surface_mismatch")
        profile_id = payload.get("profile_id")
        revision = payload.get("revision")
        features = payload.get("features")
        expires_at = payload.get("expires_at")
        max_evidence_bytes = payload.get("max_evidence_bytes", 262_144)
        policy = payload.get("visual_action_policy", "require_understanding")
        if not isinstance(profile_id, str) or not profile_id:
            raise ValueError("invalid_profile_id")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ValueError("invalid_profile_revision")
        if not isinstance(features, list) or not features or len(features) > len(SUPPORTED_FEATURES):
            raise ValueError("invalid_screen_features")
        if not all(isinstance(feature, str) and feature in SUPPORTED_FEATURES for feature in features):
            raise ValueError("unsupported_screen_feature")
        if len(set(features)) != len(features):
            raise ValueError("duplicate_screen_feature")
        if not isinstance(max_evidence_bytes, int) or isinstance(max_evidence_bytes, bool) or not 1 <= max_evidence_bytes <= 524_288:
            raise ValueError("invalid_max_evidence_bytes")
        if policy not in {"require_understanding", "allow_safe"}:
            raise ValueError("invalid_visual_action_policy")
        _parse_timestamp(expires_at, "expires_at")
        return cls(
            profile_id=profile_id,
            revision=revision,
            features=tuple(features),
            expires_at=expires_at,
            max_evidence_bytes=max_evidence_bytes,
            visual_action_policy=policy,
        )

    def is_active(self, now: datetime) -> bool:
        return _parse_timestamp(self.expires_at, "expires_at") > now.astimezone(UTC)


class ProxyScreenGovernance:
    """Local Screen Profile, bounded evidence index, and action authorization."""

    def __init__(self, *, max_items: int = 64, clock=None) -> None:
        if not 1 <= max_items <= 64:
            raise ValueError("max_items must be between 1 and 64.")
        self.max_items = max_items
        self.clock = clock or (lambda: datetime.now(UTC))
        self.profile: ScreenProfile | None = None
        self._evidence: OrderedDict[str, CapturedFrame] = OrderedDict()
        self._last_sha256: str | None = None
        self._understanding: dict | None = None

    def configure(self, payload: dict, attachment: ProxyTargetAttachment) -> ScreenProfile:
        profile = ScreenProfile.from_action_payload(payload, attachment)
        self.profile = profile
        self._understanding = None
        return profile

    def has_active_profile(self) -> bool:
        return self.profile is not None and self.profile.is_active(self.clock())

    def observe_base(
        self,
        frame: CapturedFrame,
        attachment: ProxyTargetAttachment,
        *,
        action_request_id: str | None = None,
    ) -> list[dict]:
        """Record one local frame and emit safe Profile-independent facts."""

        self._remember_frame(frame)
        changed = self._last_sha256 is None or self._last_sha256 != frame.sha256
        self._last_sha256 = frame.sha256
        base = {
            "target_id": attachment.target_id,
            "surface_id": attachment.surface_id,
        }
        observations = [
            {
                "name": CAPTURE_HEALTH_FEATURE,
                "value": {
                    **base,
                    "feature_version": "capture_health.v1",
                    "state": "ready",
                    "width": frame.width,
                    "height": frame.height,
                    "capture_latency_ms": frame.capture_latency_ms,
                },
                "observed_at": frame.captured_at,
                "confidence": 1.0,
                "context_disposition": "structural",
            },
            {
                "name": CHANGE_FEATURE,
                "value": {
                    **base,
                    "feature_version": "screen_change.v1",
                    "state": "changed" if changed else "unchanged",
                    "evidence_ref": frame.evidence_ref,
                    "evidence_id": frame.evidence_ref,
                },
                "observed_at": frame.captured_at,
                "confidence": 1.0,
                "evidence_ref": frame.evidence_ref,
                "evidence_id": frame.evidence_ref,
                "context_disposition": "structural",
            },
        ]
        if action_request_id is not None:
            observations.append(
                {
                    "name": ACTION_EFFECT_FEATURE,
                    "value": {
                        **base,
                        "feature_version": "action_effect.v1",
                        "action_request_id": action_request_id,
                        "state": "changed" if changed else "unchanged",
                        "evidence_ref": frame.evidence_ref,
                        "evidence_id": frame.evidence_ref,
                    },
                    "observed_at": frame.captured_at,
                    "confidence": 1.0,
                    "evidence_ref": frame.evidence_ref,
                    "evidence_id": frame.evidence_ref,
                    "context_disposition": "structural",
                }
            )
        return observations

    def observe_profile_features(
        self,
        frame: CapturedFrame,
        attachment: ProxyTargetAttachment,
        *,
        action_request_id: str | None = None,
    ) -> list[dict]:
        """Retain the old hard Profile activation protocol as an experiment."""

        if not self.has_active_profile():
            return []
        assert self.profile is not None
        observations = self.observe_base(
            frame,
            attachment,
            action_request_id=action_request_id,
        )
        selected = [
            observation
            for observation in observations
            if observation["name"] in self.profile.features
        ]
        for observation in selected:
            observation["value"].update(
                {
                    "profile_id": self.profile.profile_id,
                    "profile_revision": self.profile.revision,
                }
            )
        return selected

    def read_latest(
        self,
        *,
        payload: dict,
        adapter,
        attachment: ProxyTargetAttachment,
    ) -> dict:
        """Return one current or Edge-cached frame as a normal action result."""

        if payload.get("target_id") != attachment.target_id:
            raise ValueError("target_mismatch")
        if payload.get("surface_id") != attachment.surface_id:
            raise ValueError("surface_mismatch")
        requested_max = payload.get("max_bytes")
        if (
            not isinstance(requested_max, int)
            or isinstance(requested_max, bool)
            or not 1 <= requested_max <= MAX_SCREEN_READ_BYTES
        ):
            raise ValueError("invalid_evidence_max_bytes")
        freshness = payload.get("freshness")
        if freshness == "cached":
            evidence_id = payload.get("evidence_id")
            _validate_evidence_id(evidence_id)
            frame = self._lookup_frame(evidence_id, adapter)
            body = adapter.read_evidence(evidence_id, requested_max)
        elif freshness == "latest":
            if payload.get("evidence_id") is not None:
                raise ValueError("evidence_id_not_allowed_for_latest")
            frame = adapter.capture_frame()
            self._remember_frame(frame)
            body = adapter.read_evidence(frame.evidence_ref, requested_max)
        else:
            raise ValueError("unsupported_screen_freshness")
        if len(body) != frame.size_bytes or len(body) > MAX_SCREEN_READ_BYTES:
            raise ValueError("evidence_exceeds_policy_limit")
        if sha256(body).hexdigest() != frame.sha256:
            raise ValueError("evidence_integrity_mismatch")
        import base64

        return {
            "target_id": attachment.target_id,
            "surface_id": attachment.surface_id,
            "observed_at": frame.captured_at,
            "mime_type": frame.mime_type,
            "size_bytes": frame.size_bytes,
            "sha256": frame.sha256,
            "evidence_id": frame.evidence_ref,
            "encoding": "base64",
            "jpeg_bytes": base64.b64encode(body).decode("ascii"),
        }

    def _remember_frame(self, frame: CapturedFrame) -> None:
        self._evidence[frame.evidence_ref] = frame
        self._evidence.move_to_end(frame.evidence_ref)
        while len(self._evidence) > self.max_items:
            self._evidence.popitem(last=False)

    def _lookup_frame(self, evidence_id: str, adapter) -> CapturedFrame:
        frame = self._evidence.get(evidence_id)
        if frame is not None:
            return frame
        describe = getattr(adapter, "read_evidence_metadata", None)
        if describe is None:
            raise ValueError("evidence_unavailable")
        try:
            stored = describe(evidence_id)
        except (ProxyAdapterError, ValueError) as exc:
            raise ValueError("evidence_unavailable") from exc
        size_bytes = getattr(stored, "size_bytes", None)
        if not isinstance(size_bytes, int) or size_bytes < 1:
            raise ValueError("evidence_unavailable")
        return CapturedFrame(
            evidence_ref=stored.evidence_id,
            captured_at=stored.captured_at,
            width=getattr(stored, "width", 0) or 1,
            height=getattr(stored, "height", 0) or 1,
            mime_type="image/jpeg",
            size_bytes=size_bytes,
            sha256=stored.sha256,
        )

    def accept_understanding_update(self, frame: dict, attachment: ProxyTargetAttachment) -> None:
        update = frame.get("understanding")
        if not isinstance(update, dict):
            raise ValueError("invalid_understanding_update")
        if update.get("target_id") != attachment.target_id or update.get("surface_id") != attachment.surface_id:
            raise ValueError("understanding_target_mismatch")
        if self.profile is not None:
            if (
                update.get("profile_id") != self.profile.profile_id
                or update.get("profile_revision") != self.profile.revision
            ):
                raise ValueError("understanding_profile_mismatch")
        if update.get("state") != "understanding_ready":
            self._understanding = None
            return
        understanding_id = update.get("understanding_id")
        if not isinstance(understanding_id, str) or not understanding_id:
            raise ValueError("invalid_understanding_id")
        expires_at = update.get("expires_at")
        if _parse_timestamp(expires_at, "understanding expires_at") <= self.clock():
            raise ValueError("understanding_expired")
        self._understanding = {
            "understanding_id": understanding_id,
            "expires_at": expires_at,
            "target_id": attachment.target_id,
            "surface_id": attachment.surface_id,
            "evidence_ref": update.get("evidence_ref"),
        }
        if self.profile is not None and update.get("profile_id") is not None:
            self._understanding.update(
                {
                    "profile_id": self.profile.profile_id,
                    "profile_revision": self.profile.revision,
                }
            )

    def validate_hid_action(self, payload: dict) -> str | None:
        if not self.has_active_profile():
            return None
        assert self.profile is not None
        if self.profile.visual_action_policy != "require_understanding":
            return None
        authorization = payload.get("visual_authorization")
        if not isinstance(authorization, dict):
            return "visual_understanding_required"
        understanding = self._understanding
        if understanding is None:
            return "visual_understanding_unavailable"
        if authorization.get("understanding_id") != understanding["understanding_id"]:
            return "visual_understanding_mismatch"
        if _parse_timestamp(understanding["expires_at"], "understanding expires_at") <= self.clock():
            self._understanding = None
            return "visual_understanding_expired"
        return None
