"""Validation and transient interpretation of bounded action-result attachments."""

from __future__ import annotations

import base64
import binascii
from hashlib import sha256


MAX_ATTACHMENT_BYTES = 98_304
MAX_EVIDENCE_ID_LENGTH = 256


class ActionResultAttachmentService:
    """Strip binary attachments before action results enter Runtime state.

    The action protocol remains generic: any Edge may return a bounded JPEG in
    ``result.payload``.  This service validates the bytes, calls the optional
    vision evaluator synchronously, then replaces bytes with its safe textual
    result.  The original byte string never reaches the state store or Hermes.
    """

    def __init__(self, *, vision_evaluator=None) -> None:
        self.vision_evaluator = vision_evaluator

    def sanitize(self, frame: dict) -> dict:
        result = frame.get("result")
        if not isinstance(result, dict) or result.get("status") != "ok":
            return frame
        payload = result.get("payload")
        if not isinstance(payload, dict) or "jpeg_bytes" not in payload:
            return frame
        try:
            body, safe_attachment = self._decode(payload)
            safe_payload = {
                key: value
                for key, value in payload.items()
                if key not in {"jpeg_bytes", "encoding"}
            }
            safe_payload["attachment"] = safe_attachment
            safe_payload["visual_understanding"] = self._understanding(
                body, safe_attachment
            )
            return {
                **frame,
                "result": {**result, "payload": safe_payload},
            }
        except ValueError as exc:
            # Never retain an invalid raw payload just to report the error.
            return {
                **frame,
                "result": {
                    "status": "error",
                    "capability": result.get("capability", "unknown"),
                    "reason": str(exc),
                },
            }

    @staticmethod
    def _decode(payload: dict) -> tuple[bytes, dict]:
        observed_at = payload.get("observed_at")
        mime_type = payload.get("mime_type")
        size_bytes = payload.get("size_bytes")
        digest = payload.get("sha256")
        evidence_id = payload.get("evidence_id")
        encoded = payload.get("jpeg_bytes")
        if not isinstance(observed_at, str) or not observed_at:
            raise ValueError("invalid_attachment_observed_at")
        if mime_type != "image/jpeg":
            raise ValueError("unsupported_attachment_mime_type")
        if (
            not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or not 1 <= size_bytes <= MAX_ATTACHMENT_BYTES
            or not isinstance(digest, str)
            or len(digest) != 64
            or not isinstance(encoded, str)
        ):
            raise ValueError("invalid_action_result_attachment")
        if evidence_id is not None:
            if (
                not isinstance(evidence_id, str)
                or not evidence_id
                or len(evidence_id) > MAX_EVIDENCE_ID_LENGTH
                or not evidence_id.isascii()
                or any(character.isspace() or ord(character) < 0x21 for character in evidence_id)
            ):
                raise ValueError("invalid_evidence_id")
        try:
            body = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("invalid_action_result_attachment_encoding") from exc
        if len(body) != size_bytes or sha256(body).hexdigest() != digest:
            raise ValueError("action_result_attachment_integrity_mismatch")
        safe_attachment = {
            "observed_at": observed_at,
            "mime_type": mime_type,
            "sha256": digest,
            "size_bytes": size_bytes,
        }
        if evidence_id is not None:
            safe_attachment["evidence_id"] = evidence_id
        return body, safe_attachment

    def _understanding(self, body: bytes, attachment: dict) -> dict:
        if self.vision_evaluator is None:
            return {"state": "unavailable", "reason": "vision_provider_unconfigured"}
        value = self.vision_evaluator(body, dict(attachment))
        if not isinstance(value, dict):
            raise ValueError("invalid_vision_evaluator_result")
        summary = value.get("summary")
        if not isinstance(summary, str) or not summary or len(summary) > 512:
            raise ValueError("invalid_vision_summary")
        labels = value.get("labels", [])
        if not isinstance(labels, list) or len(labels) > 16 or not all(
            isinstance(label, str) and 0 < len(label) <= 64 for label in labels
        ):
            raise ValueError("invalid_vision_labels")
        confidence = value.get("confidence")
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("invalid_vision_confidence")
        return {
            "state": "ready",
            "summary": summary,
            "labels": labels,
            "confidence": float(confidence),
        }
