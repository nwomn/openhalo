"""Governed, local-first screen Features and evidence for Proxy Edge.

This module deliberately does not interpret arbitrary GUI semantics.  It tracks
capture health and bounded pixel change locally, retains a small evidence index,
and accepts only a Runtime-confirmed Screen Profile.  Raw JPEG bytes leave the
Edge only through the dedicated bounded evidence-transfer path.
"""

from __future__ import annotations

import base64
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from uuid import uuid4

from device_edge.proxy.contracts import CapturedFrame
from device_edge.proxy.contracts import ProxyTargetAttachment
from device_edge.proxy.contracts import SCREEN_EVIDENCE_CAPABILITY
from device_edge.proxy.contracts import SCREEN_FEATURE_CAPABILITY
from device_edge.proxy.contracts import SCREEN_PROFILE_CAPABILITY


CAPTURE_HEALTH_FEATURE = "proxy.screen.capture_health.v1"
CHANGE_FEATURE = "proxy.screen.change.v1"
ACTION_EFFECT_FEATURE = "proxy.screen.action_effect.v1"
SUPPORTED_FEATURES = frozenset(
    {CAPTURE_HEALTH_FEATURE, CHANGE_FEATURE, ACTION_EFFECT_FEATURE}
)


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


@dataclass(frozen=True, slots=True)
class EvidenceTransfer:
    transfer_id: str
    request_id: str
    payload: dict


class ProxyScreenGovernance:
    """Local Screen Profile, bounded evidence index, and action authorization."""

    def __init__(self, *, max_items: int = 4, clock=None) -> None:
        if not 1 <= max_items <= 16:
            raise ValueError("max_items must be between 1 and 16.")
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

    def observe(
        self,
        frame: CapturedFrame,
        attachment: ProxyTargetAttachment,
        *,
        action_request_id: str | None = None,
    ) -> list[dict]:
        """Record one local frame and emit only Profile-selected Features."""

        if not self.has_active_profile():
            return []
        assert self.profile is not None
        self._evidence[frame.evidence_ref] = frame
        self._evidence.move_to_end(frame.evidence_ref)
        while len(self._evidence) > self.max_items:
            self._evidence.popitem(last=False)
        changed = self._last_sha256 is None or self._last_sha256 != frame.sha256
        self._last_sha256 = frame.sha256
        base = {
            "target_id": attachment.target_id,
            "surface_id": attachment.surface_id,
            "profile_id": self.profile.profile_id,
            "profile_revision": self.profile.revision,
            "feature_version": None,
        }
        observations = []
        if CAPTURE_HEALTH_FEATURE in self.profile.features:
            observations.append(
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
                }
            )
        if CHANGE_FEATURE in self.profile.features:
            observations.append(
                {
                    "name": CHANGE_FEATURE,
                    "value": {
                        **base,
                        "feature_version": "screen_change.v1",
                        "state": "changed" if changed else "unchanged",
                        "evidence_ref": frame.evidence_ref,
                    },
                    "observed_at": frame.captured_at,
                    "confidence": 1.0,
                    "evidence_ref": frame.evidence_ref,
                    "context_disposition": "structural",
                }
            )
        if action_request_id is not None and ACTION_EFFECT_FEATURE in self.profile.features:
            observations.append(
                {
                    "name": ACTION_EFFECT_FEATURE,
                    "value": {
                        **base,
                        "feature_version": "action_effect.v1",
                        "action_request_id": action_request_id,
                        "state": "changed" if changed else "unchanged",
                        "evidence_ref": frame.evidence_ref,
                    },
                    "observed_at": frame.captured_at,
                    "confidence": 1.0,
                    "evidence_ref": frame.evidence_ref,
                    "context_disposition": "structural",
                }
            )
        return observations

    def prepare_evidence_transfer(
        self,
        *,
        device_id: str,
        request_id: str,
        payload: dict,
        adapter,
        attachment: ProxyTargetAttachment,
    ) -> EvidenceTransfer:
        if not self.has_active_profile():
            raise ValueError("screen_profile_inactive")
        assert self.profile is not None
        if payload.get("target_id") != attachment.target_id:
            raise ValueError("target_mismatch")
        if payload.get("surface_id") != attachment.surface_id:
            raise ValueError("surface_mismatch")
        evidence_ref = payload.get("evidence_ref")
        if not isinstance(evidence_ref, str) or not evidence_ref:
            raise ValueError("invalid_evidence_ref")
        frame = self._evidence.get(evidence_ref)
        if frame is None:
            raise ValueError("evidence_unavailable")
        requested_max = payload.get("max_bytes", self.profile.max_evidence_bytes)
        if not isinstance(requested_max, int) or isinstance(requested_max, bool) or requested_max < 1:
            raise ValueError("invalid_evidence_max_bytes")
        max_bytes = min(requested_max, self.profile.max_evidence_bytes)
        body = adapter.read_evidence(evidence_ref, max_bytes)
        if len(body) != frame.size_bytes:
            raise ValueError("evidence_exceeds_policy_limit")
        purpose = payload.get("purpose", "owner_inspection")
        if purpose not in {"owner_inspection", "candidate_review", "action_verification"}:
            raise ValueError("invalid_evidence_purpose")
        ttl_seconds = payload.get("understanding_ttl_seconds", 60)
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 5 <= ttl_seconds <= 300:
            raise ValueError("invalid_understanding_ttl")
        transfer_id = f"screen-evidence-{uuid4().hex}"
        return EvidenceTransfer(
            transfer_id=transfer_id,
            request_id=request_id,
            payload={
                "type": "evidence_transfer",
                "device_id": device_id,
                "request_id": request_id,
                "transfer_id": transfer_id,
                "evidence": {
                    "target_id": attachment.target_id,
                    "surface_id": attachment.surface_id,
                    "profile_id": self.profile.profile_id,
                    "profile_revision": self.profile.revision,
                    "evidence_ref": frame.evidence_ref,
                    "mime_type": frame.mime_type,
                    "size_bytes": frame.size_bytes,
                    "sha256": frame.sha256,
                    "purpose": purpose,
                    "understanding_ttl_seconds": ttl_seconds,
                    "data_base64": base64.b64encode(body).decode("ascii"),
                },
            },
        )

    def accept_understanding_update(self, frame: dict, attachment: ProxyTargetAttachment) -> None:
        update = frame.get("understanding")
        if not isinstance(update, dict):
            raise ValueError("invalid_understanding_update")
        if update.get("target_id") != attachment.target_id or update.get("surface_id") != attachment.surface_id:
            raise ValueError("understanding_target_mismatch")
        if self.profile is None:
            raise ValueError("screen_profile_inactive")
        if update.get("profile_id") != self.profile.profile_id or update.get("profile_revision") != self.profile.revision:
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
            "profile_id": self.profile.profile_id,
            "profile_revision": self.profile.revision,
        }

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
