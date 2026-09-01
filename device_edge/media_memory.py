"""Source-local media-memory primitives shared by Edge surfaces.

This module deliberately has no Runtime dependency.  It keeps encoded media in
an Edge-local segmented Hot Ring and executes ``media.memory.query`` by giving a
selected local interval directly to an Edge-configured understanding provider.
Only the provider's bounded text result and deterministic coverage metadata are
returned through the normal action-result frame.
"""

from __future__ import annotations

import json
import inspect
import re
from dataclasses import asdict
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path
from uuid import uuid4

try:
    from edge_api.protocol import with_api_version
except ImportError:  # pragma: no cover - copied MaixCAM files.
    def with_api_version(frame: dict) -> dict:
        return {"api_version": "edge.runtime.v2", **frame}


MEDIA_MEMORY_QUERY_CAPABILITY = "media.memory.query"
MEDIA_PROVIDER_CONFIGURE_CAPABILITY = "media.provider.configure"
_MAX_QUERY_CHARS = 2_000
_MAX_UNDERSTANDING_CHARS = 8_000
_MAX_LIMITATIONS = 16
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


def media_memory_query_capability(source_ref: str) -> dict:
    """Return the registered runtime-to-Edge contract for one media source."""

    _validate_source_ref(source_ref)
    return {
        "name": MEDIA_MEMORY_QUERY_CAPABILITY,
        "direction": "runtime_to_edge",
        "kind": "action",
        "affordances": ["understand_local_media_interval"],
        "privacy": "source_local_media",
        "contract_version": 1,
        "input_schema": {
            "type": "object",
            "required": ["source_ref", "start_at", "end_at", "question"],
            "additionalProperties": False,
            "properties": {
                "source_ref": {"type": "string", "maxLength": 256},
                "start_at": {"type": "string", "maxLength": 64},
                "end_at": {"type": "string", "maxLength": 64},
                "question": {"type": "string", "minLength": 1, "maxLength": _MAX_QUERY_CHARS},
            },
        },
        "machine_contract": {
            "input_schema": {
                "type": "object", "required": ["source_ref", "start_at", "end_at", "question"], "additionalProperties": False,
                "properties": {"source_ref": {"type": "string", "maxLength": 256}, "start_at": {"type": "string", "maxLength": 64}, "end_at": {"type": "string", "maxLength": 64}, "question": {"type": "string", "minLength": 1, "maxLength": _MAX_QUERY_CHARS}},
            },
            "side_effect": "edge_local_media_read_and_provider_call", "result_states": ["ok", "error"], "requires_confirmation": False,
        },
        "semantic_contract": {
            "purpose": "Ask one named source to understand a bounded locally retained media interval.",
            "success_meaning": "A returned Understanding describes only the selected interval and its reported coverage.",
            "limitations": "It does not prove facts outside coverage, transfer raw media to Runtime, or identify people beyond source evidence.",
        },
    }


def media_provider_configure_capability() -> dict:
    """Return the v1 action contract for directly provisioning an Edge key."""

    return {
        "name": MEDIA_PROVIDER_CONFIGURE_CAPABILITY,
        "direction": "runtime_to_edge",
        "kind": "action",
        "affordances": ["configure_local_media_provider"],
        "privacy": "provider_credential",
        "contract_version": 1,
        "input_schema": {
            "type": "object",
            "required": ["provider", "model"],
            "additionalProperties": False,
            "properties": {
                "provider": {"type": "object"},
                "model": {"type": "object"},
            },
        },
        "machine_contract": {"input_schema": {"type": "object", "required": ["provider", "model"], "additionalProperties": False, "properties": {"provider": {"type": "object"}, "model": {"type": "object"}}}, "side_effect": "ephemeral_edge_provider_configuration", "result_states": ["ok", "error"], "requires_confirmation": False},
        "semantic_contract": {"purpose": "Provision an explicitly selected direct-media provider profile to this Edge for the current process.", "success_meaning": "The Edge can use that named profile until restart or revocation.", "limitations": "Success never means credentials were persisted, broadly shared, or authorized for another Edge."},
    }


class InMemoryMediaProviderCredentials:
    """Process-local provider credentials provisioned by ``action_request``.

    This deliberately has no file persistence.  A Camera Edge restart requires
    a new configuration action, which is acceptable for the first functional
    loop and prevents key material from being written to the device filesystem.
    """

    def __init__(self) -> None:
        self._credentials: dict[tuple[str, str], str] = {}

    def configure(self, *, provider: object, model: object) -> dict:
        if not isinstance(provider, dict) or not isinstance(model, dict):
            raise ValueError("invalid_media_provider_profile")
        provider_name = provider.get("name")
        model_name = model.get("name")
        required_provider = ("name", "adapter_type", "base_url", "wire_api", "api_key", "timeout_seconds")
        if not all(field in provider for field in required_provider):
            raise ValueError("invalid_media_provider_profile")
        if not _is_bounded_text(provider_name, 64) or not _is_bounded_text(model_name, 128):
            raise ValueError("invalid_media_provider_identity")
        if not _is_bounded_text(provider.get("api_key"), 4096):
            raise ValueError("invalid_media_provider_key")
        if not _is_bounded_text(provider.get("adapter_type"), 64) or not _is_bounded_text(provider.get("base_url"), 1_024) or not _is_bounded_text(provider.get("wire_api"), 64):
            raise ValueError("invalid_media_provider_profile")
        if not isinstance(provider.get("timeout_seconds"), int) or not 1 <= provider["timeout_seconds"] <= 300:
            raise ValueError("invalid_media_provider_profile")
        headers = provider.get("default_headers", {})
        if not isinstance(headers, dict) or len(headers) > 16 or not all(_is_bounded_text(key, 128) and _is_bounded_text(value, 1_024) for key, value in headers.items()):
            raise ValueError("invalid_media_provider_profile")
        if not _is_bounded_text(model.get("model_id"), 256) or not isinstance(model.get("supports_vision"), bool) or not isinstance(model.get("supports_video"), bool):
            raise ValueError("invalid_media_model_profile")
        provider_profile = {
            "name": provider_name.strip(),
            "adapter_type": provider["adapter_type"].strip(),
            "base_url": provider["base_url"].strip(),
            "wire_api": provider["wire_api"].strip(),
            "api_key": provider["api_key"],
            "timeout_seconds": provider["timeout_seconds"],
            "default_headers": dict(headers),
        }
        model_profile = {
            "name": model_name.strip(),
            "model_id": model["model_id"].strip(),
            "supports_vision": model["supports_vision"],
            "supports_video": model["supports_video"],
        }
        self._credentials[(provider_profile["name"], model_profile["name"])] = {
            "provider": provider_profile,
            "model": model_profile,
        }
        return {
            "provider": provider_profile["name"],
            "model": model_profile["name"],
            "model_id": model_profile["model_id"],
            "adapter_type": provider_profile["adapter_type"],
            "state": "configured",
        }

    def profile_for(self, *, provider: str, model: str) -> dict | None:
        """Return one full profile only to an Edge-local provider adapter."""

        profile = self._credentials.get((provider, model))
        if profile is None:
            return None
        return {
            "provider": {**profile["provider"], "default_headers": dict(profile["provider"]["default_headers"])},
            "model": dict(profile["model"]),
        }

    def handle_action_request(self, frame: dict) -> dict:
        action = frame.get("action")
        capability = action.get("capability") if isinstance(action, dict) else "unknown"
        if capability != MEDIA_PROVIDER_CONFIGURE_CAPABILITY:
            result = {"status": "error", "capability": capability, "reason": "unsupported_media_provider_capability"}
        elif not isinstance(action.get("payload"), dict):
            result = {"status": "error", "capability": capability, "reason": "invalid_media_provider_payload"}
        else:
            try:
                details = self.configure(**action["payload"])
                result = {"status": "ok", "capability": capability, "details": details}
            except ValueError as exc:
                result = {"status": "error", "capability": capability, "reason": str(exc)}
        response = with_api_version({"type": "action_result", "device_id": frame.get("device_id"), "result": result})
        for key in ("request_id", "interaction_id", "interaction_turn_id", "trace_id", "session_id", "turn_id", "event_id", "parent_event_id"):
            if frame.get(key) is not None:
                response[key] = frame[key]
        return response


@dataclass(frozen=True, slots=True)
class MediaSegment:
    segment_id: str
    start_at: str
    end_at: str
    path: str
    size_bytes: int
    mime_type: str


@dataclass(frozen=True, slots=True)
class HotRingSelection:
    source_ref: str
    requested_start_at: str
    requested_end_at: str
    selected_start_at: str
    selected_end_at: str
    segments: tuple[MediaSegment, ...]

    @property
    def coverage(self) -> dict:
        return {
            "state": "partial" if (
                self.selected_start_at != self.requested_start_at
                or self.selected_end_at != self.requested_end_at
            ) else "complete",
            "requested_start_at": self.requested_start_at,
            "requested_end_at": self.requested_end_at,
            "selected_start_at": self.selected_start_at,
            "selected_end_at": self.selected_end_at,
            "segment_count": len(self.segments),
        }


class LocalHotRing:
    """Small persistent local ring of already encoded media segments.

    Capture/encoding is intentionally outside this class: a camera, screen, or
    audio adapter passes one closed encoded segment to :meth:`append_segment`.
    The segment bytes never leave this Edge through this module.
    """

    def __init__(
        self, *, source_ref: str, directory: Path, retention_seconds: int, max_bytes: int
    ) -> None:
        _validate_source_ref(source_ref)
        if retention_seconds < 1 or max_bytes < 1:
            raise ValueError("Hot Ring retention_seconds and max_bytes must be positive.")
        self.source_ref = source_ref
        self.directory = Path(directory)
        self.retention_seconds = retention_seconds
        self.max_bytes = max_bytes
        self.directory.mkdir(parents=True, exist_ok=True)
        self._index_path = self.directory / "hot-ring-index.json"
        self._segments = self._load_index()
        self._prune(reference_at=None)

    def append_segment(
        self, *, start_at: str, end_at: str, body: bytes, mime_type: str
    ) -> MediaSegment:
        start = _parse_timestamp(start_at)
        end = _parse_timestamp(end_at)
        if end <= start:
            raise ValueError("Media segment end_at must be after start_at.")
        if not isinstance(body, bytes) or not body:
            raise ValueError("Media segment body must be non-empty bytes.")
        if not isinstance(mime_type, str) or not mime_type.startswith(("video/", "audio/", "image/")):
            raise ValueError("Media segment mime_type is unsupported.")
        if len(body) > self.max_bytes:
            raise ValueError("Media segment exceeds Hot Ring capacity.")
        segment_id = f"segment-{uuid4().hex}"
        path = self.directory / f"{segment_id}.media"
        temporary = self.directory / f".{segment_id}.tmp"
        temporary.write_bytes(body)
        temporary.replace(path)
        segment = MediaSegment(
            segment_id=segment_id,
            start_at=_format_timestamp(start),
            end_at=_format_timestamp(end),
            path=path.name,
            size_bytes=len(body),
            mime_type=mime_type,
        )
        self._segments.append(segment)
        self._segments.sort(key=lambda item: item.start_at)
        self._prune(reference_at=end)
        self._save_index()
        return segment

    def select(self, *, start_at: str, end_at: str) -> HotRingSelection | None:
        start = _parse_timestamp(start_at)
        end = _parse_timestamp(end_at)
        if end <= start:
            raise ValueError("Query end_at must be after start_at.")
        self._prune(reference_at=None)
        selected = tuple(
            segment for segment in self._segments
            if _parse_timestamp(segment.end_at) > start and _parse_timestamp(segment.start_at) < end
        )
        if not selected:
            return None
        return HotRingSelection(
            source_ref=self.source_ref,
            requested_start_at=_format_timestamp(start),
            requested_end_at=_format_timestamp(end),
            selected_start_at=max(_format_timestamp(start), selected[0].start_at),
            selected_end_at=min(_format_timestamp(end), selected[-1].end_at),
            segments=selected,
        )

    def read_segment(self, segment: MediaSegment) -> bytes:
        """Read local bytes for an Edge-side provider invocation only."""

        if segment not in self._segments:
            raise ValueError("Media segment is no longer available.")
        path = self.directory / segment.path
        if not path.is_file():
            raise ValueError("Media segment is no longer available.")
        body = path.read_bytes()
        if len(body) != segment.size_bytes:
            raise ValueError("Media segment integrity mismatch.")
        return body

    def _load_index(self) -> list[MediaSegment]:
        if not self._index_path.is_file():
            return []
        try:
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return []
            segments = [MediaSegment(**item) for item in raw if isinstance(item, dict)]
            return [item for item in segments if (self.directory / item.path).is_file()]
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return []

    def _prune(self, *, reference_at: datetime | None) -> None:
        reference = reference_at or datetime.now(UTC)
        cutoff = reference.timestamp() - self.retention_seconds
        retained = [
            item for item in self._segments
            if _parse_timestamp(item.end_at).timestamp() >= cutoff
        ]
        while sum(item.size_bytes for item in retained) > self.max_bytes:
            retained.pop(0)
        removed = {item.path for item in self._segments}.difference(item.path for item in retained)
        for name in removed:
            try:
                (self.directory / name).unlink(missing_ok=True)
            except OSError:
                pass
        self._segments = retained
        self._save_index()

    def _save_index(self) -> None:
        temporary = self.directory / ".hot-ring-index.tmp"
        temporary.write_text(json.dumps([asdict(item) for item in self._segments]), encoding="utf-8")
        temporary.replace(self._index_path)


class MediaMemoryActionExecutor:
    """Execute a bounded local-media query without emitting media bytes."""

    def __init__(self, *, device_id: str, hot_ring: LocalHotRing, understanding_provider, provider_configured=None) -> None:
        self.device_id = device_id
        self.hot_ring = hot_ring
        self.understanding_provider = understanding_provider
        self.provider_configured = provider_configured

    def handle_action_request(self, frame: dict) -> dict:
        action = frame.get("action")
        capability = action.get("capability") if isinstance(action, dict) else "unknown"
        if frame.get("device_id") != self.device_id:
            result = self._error(capability, "device_mismatch")
        elif capability != MEDIA_MEMORY_QUERY_CAPABILITY:
            result = self._error(capability, "unsupported_media_memory_capability")
        else:
            result = self._execute(action.get("payload"))
        response = with_api_version({"type": "action_result", "device_id": self.device_id, "result": result})
        for key in ("request_id", "interaction_id", "interaction_turn_id", "trace_id", "session_id", "turn_id", "event_id", "parent_event_id"):
            if frame.get(key) is not None:
                response[key] = frame[key]
        return response

    async def handle_action_request_async(self, frame: dict) -> dict:
        """Async variant for a single-event-loop Edge service.

        A provider may return an awaitable for network I/O.  Capture and Feature
        loops can therefore continue while the Edge waits for the provider.
        """

        action = frame.get("action")
        capability = action.get("capability") if isinstance(action, dict) else "unknown"
        if frame.get("device_id") != self.device_id:
            result = self._error(capability, "device_mismatch")
        elif capability != MEDIA_MEMORY_QUERY_CAPABILITY:
            result = self._error(capability, "unsupported_media_memory_capability")
        else:
            result = await self._execute_async(action.get("payload"))
        response = with_api_version({"type": "action_result", "device_id": self.device_id, "result": result})
        for key in ("request_id", "interaction_id", "interaction_turn_id", "trace_id", "session_id", "turn_id", "event_id", "parent_event_id"):
            if frame.get(key) is not None:
                response[key] = frame[key]
        return response

    def _execute(self, payload: object) -> dict:
        if not isinstance(payload, dict):
            return self._error(MEDIA_MEMORY_QUERY_CAPABILITY, "invalid_media_memory_payload")
        source_ref = payload.get("source_ref")
        question = payload.get("question")
        if source_ref != self.hot_ring.source_ref:
            return self._error(MEDIA_MEMORY_QUERY_CAPABILITY, "media_source_mismatch")
        if not isinstance(question, str) or not question.strip() or len(question) > _MAX_QUERY_CHARS:
            return self._error(MEDIA_MEMORY_QUERY_CAPABILITY, "invalid_media_memory_question")
        try:
            selection = self.hot_ring.select(start_at=payload.get("start_at"), end_at=payload.get("end_at"))
        except (TypeError, ValueError):
            return self._error(MEDIA_MEMORY_QUERY_CAPABILITY, "invalid_media_memory_interval")
        if selection is None:
            return self._error(MEDIA_MEMORY_QUERY_CAPABILITY, "media_interval_unavailable")
        try:
            value = self.understanding_provider(selection, question.strip(), self.hot_ring)
            understanding = _normalize_understanding(value)
        except Exception:
            return self._error(MEDIA_MEMORY_QUERY_CAPABILITY, "media_understanding_unavailable")
        return {
            "status": "ok",
            "capability": MEDIA_MEMORY_QUERY_CAPABILITY,
            "payload": {
                "source_ref": selection.source_ref,
                "understanding": understanding,
                "coverage": selection.coverage,
            },
        }

    async def _execute_async(self, payload: object) -> dict:
        prepared = self._prepare(payload)
        if isinstance(prepared, dict):
            return prepared
        selection, question = prepared
        try:
            value = self.understanding_provider(selection, question, self.hot_ring)
            if inspect.isawaitable(value):
                value = await value
            understanding = _normalize_understanding(value)
        except Exception:
            return self._error(MEDIA_MEMORY_QUERY_CAPABILITY, "media_understanding_unavailable")
        return self._success(selection, understanding)

    def _prepare(self, payload: object) -> tuple[HotRingSelection, str] | dict:
        if not isinstance(payload, dict):
            return self._error(MEDIA_MEMORY_QUERY_CAPABILITY, "invalid_media_memory_payload")
        source_ref = payload.get("source_ref")
        question = payload.get("question")
        if source_ref != self.hot_ring.source_ref:
            return self._error(MEDIA_MEMORY_QUERY_CAPABILITY, "media_source_mismatch")
        if not isinstance(question, str) or not question.strip() or len(question) > _MAX_QUERY_CHARS:
            return self._error(MEDIA_MEMORY_QUERY_CAPABILITY, "invalid_media_memory_question")
        if self.provider_configured is not None and not self.provider_configured():
            return self._error(MEDIA_MEMORY_QUERY_CAPABILITY, "provider_unconfigured")
        try:
            selection = self.hot_ring.select(start_at=payload.get("start_at"), end_at=payload.get("end_at"))
        except (TypeError, ValueError):
            return self._error(MEDIA_MEMORY_QUERY_CAPABILITY, "invalid_media_memory_interval")
        if selection is None:
            return self._error(MEDIA_MEMORY_QUERY_CAPABILITY, "media_interval_unavailable")
        return selection, question.strip()

    @staticmethod
    def _success(selection: HotRingSelection, understanding: dict) -> dict:
        return {
            "status": "ok",
            "capability": MEDIA_MEMORY_QUERY_CAPABILITY,
            "payload": {
                "source_ref": selection.source_ref,
                "understanding": understanding,
                "coverage": selection.coverage,
            },
        }

    @staticmethod
    def _error(capability: object, reason: str) -> dict:
        return {"status": "error", "capability": capability if isinstance(capability, str) else "unknown", "reason": reason}


def _normalize_understanding(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("invalid provider response")
    markdown = value.get("markdown")
    if not isinstance(markdown, str) or not markdown.strip() or len(markdown) > _MAX_UNDERSTANDING_CHARS:
        raise ValueError("invalid provider markdown")
    model = value.get("model")
    if not isinstance(model, str) or not model or len(model) > 128:
        raise ValueError("invalid provider model")
    limitations = value.get("limitations", [])
    if not isinstance(limitations, list) or len(limitations) > _MAX_LIMITATIONS or not all(isinstance(item, str) and 0 < len(item) <= 256 for item in limitations):
        raise ValueError("invalid provider limitations")
    return {"markdown": markdown.strip(), "model": model, "limitations": limitations}


def _validate_source_ref(value: object) -> None:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ValueError("source_ref must be a bounded safe identifier.")


def _is_bounded_text(value: object, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= maximum
        and not any(character in value for character in ("\x00", "\r", "\n"))
    )


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a non-empty ISO-8601 string.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be ISO-8601.") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include an offset.")
    return parsed.astimezone(UTC)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
