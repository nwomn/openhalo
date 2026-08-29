"""Ephemeral Runtime handling for bounded Proxy Edge screen evidence.

Raw screen bytes are decoded only to call a configured vision evaluator and are
then discarded.  Runtime keeps only a short-lived structured Understanding and
safe transfer metadata; neither normal context nor persistent Runtime state is
used as a media store.
"""

from __future__ import annotations

import base64
import binascii
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

from edge_api.protocol import with_api_version


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class ProxyScreenEvidenceService:
    """Turn one authorized bounded transfer into an expiring safe update."""

    def __init__(self, *, vision_evaluator=None, clock=None) -> None:
        self.vision_evaluator = vision_evaluator
        self.clock = clock or _now
        self.understandings: dict[str, dict] = {}

    def ingest(self, frame: dict) -> dict:
        evidence = frame.get("evidence")
        if not isinstance(evidence, dict):
            raise ValueError("invalid_evidence_transfer")
        device_id = frame.get("device_id")
        request_id = frame.get("request_id")
        transfer_id = frame.get("transfer_id")
        if not all(isinstance(value, str) and value for value in (device_id, request_id, transfer_id)):
            raise ValueError("invalid_evidence_transfer_correlation")
        body = self._decode_and_validate(evidence)
        now = self.clock()
        ttl = evidence.get("understanding_ttl_seconds")
        if not isinstance(ttl, int) or isinstance(ttl, bool) or not 5 <= ttl <= 300:
            raise ValueError("invalid_understanding_ttl")
        understanding_id = f"screen-understanding-{uuid4().hex}"
        expires_at = _timestamp(now + timedelta(seconds=ttl))
        safe = {
            "understanding_id": understanding_id,
            "transfer_id": transfer_id,
            "request_id": request_id,
            "target_id": evidence.get("target_id"),
            "surface_id": evidence.get("surface_id"),
            "profile_id": evidence.get("profile_id"),
            "profile_revision": evidence.get("profile_revision"),
            "evidence_ref": evidence.get("evidence_ref"),
            "expires_at": expires_at,
            # A board may deliberately have no wall clock.  This bounded lease
            # lets it enforce the same expiry with a monotonic timer instead of
            # treating an RFC3339 timestamp as permanently valid.
            "valid_for_seconds": ttl,
        }
        if not all(isinstance(safe[key], str) and safe[key] for key in ("target_id", "surface_id", "profile_id", "evidence_ref")):
            raise ValueError("invalid_evidence_identity")
        if not isinstance(safe["profile_revision"], int) or isinstance(safe["profile_revision"], bool):
            raise ValueError("invalid_evidence_profile_revision")
        if self.vision_evaluator is None:
            update = {
                **safe,
                "state": "understanding_failed",
                "reason": "vision_provider_unconfigured",
            }
        else:
            update = {
                **safe,
                "state": "understanding_ready",
                "value": self._safe_evaluator_value(body, evidence),
            }
        # ``body`` intentionally has no durable reference after this method.
        self.understandings[understanding_id] = update
        self._expire(now)
        return with_api_version(
            {
                "type": "understanding_update",
                "device_id": device_id,
                "understanding": update,
            }
        )

    def audit_event(self, frame: dict, update: dict) -> dict:
        evidence = frame["evidence"]
        return {
            "type": "proxy_screen_evidence_processed",
            "device_id": frame["device_id"],
            "request_id": frame["request_id"],
            "transfer_id": frame["transfer_id"],
            "evidence_ref": evidence["evidence_ref"],
            "sha256": evidence["sha256"],
            "size_bytes": evidence["size_bytes"],
            "purpose": evidence["purpose"],
            "understanding_id": update["understanding"]["understanding_id"],
            "understanding_state": update["understanding"]["state"],
        }

    def _decode_and_validate(self, evidence: dict) -> bytes:
        encoded = evidence.get("data_base64")
        size_bytes = evidence.get("size_bytes")
        digest = evidence.get("sha256")
        mime_type = evidence.get("mime_type")
        if not isinstance(encoded, str) or not isinstance(size_bytes, int) or isinstance(size_bytes, bool):
            raise ValueError("invalid_evidence_payload")
        if not 1 <= size_bytes <= 524_288 or not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("invalid_evidence_metadata")
        if mime_type != "image/jpeg":
            raise ValueError("unsupported_evidence_mime_type")
        try:
            body = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("invalid_evidence_encoding") from exc
        if len(body) != size_bytes or sha256(body).hexdigest() != digest:
            raise ValueError("evidence_integrity_mismatch")
        return body

    def _safe_evaluator_value(self, body: bytes, evidence: dict) -> dict:
        value = self.vision_evaluator(
            body,
            {
                "mime_type": evidence["mime_type"],
                "evidence_ref": evidence["evidence_ref"],
                "purpose": evidence["purpose"],
            },
        )
        if not isinstance(value, dict):
            raise ValueError("invalid_vision_evaluator_result")
        summary = value.get("summary")
        if not isinstance(summary, str) or not summary or len(summary) > 512:
            raise ValueError("invalid_vision_summary")
        labels = value.get("labels", [])
        if not isinstance(labels, list) or len(labels) > 16 or not all(isinstance(label, str) and 0 < len(label) <= 64 for label in labels):
            raise ValueError("invalid_vision_labels")
        confidence = value.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise ValueError("invalid_vision_confidence")
        return {"summary": summary, "labels": labels, "confidence": float(confidence)}

    def _expire(self, now: datetime) -> None:
        expired = [
            key for key, value in self.understandings.items()
            if datetime.fromisoformat(value["expires_at"].replace("Z", "+00:00")) <= now
        ]
        for key in expired:
            del self.understandings[key]
