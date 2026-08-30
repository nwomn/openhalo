"""Adapter boundary and first ESP-KVM implementation for Proxy Interaction Edge."""

from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
from http.cookiejar import CookieJar
import json
from time import monotonic
import secrets
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor
from urllib.request import Request
from urllib.request import build_opener

from device_edge.proxy.contracts import CapabilityAvailability
from device_edge.proxy.contracts import CapturedFrame
from device_edge.proxy.contracts import PROXY_CAPABILITY_FACETS


class ProxyAdapterError(RuntimeError):
    """A bounded adapter failure safe to expose as an action-result reason."""


@dataclass(frozen=True, slots=True)
class AdapterProbe:
    capabilities: dict[str, CapabilityAvailability]
    details: dict

    def __post_init__(self) -> None:
        if set(self.capabilities) != set(PROXY_CAPABILITY_FACETS):
            raise ValueError("Adapter probe must report every proxy capability facet.")


class ProxyAdapter(Protocol):
    adapter_id: str
    adapter_kind: str
    requirements: tuple[str, ...]
    supported_target_classes: frozenset[str]

    def probe(self) -> AdapterProbe: ...

    def capture_frame(self) -> CapturedFrame: ...

    def read_evidence(self, evidence_ref: str, max_bytes: int) -> bytes: ...

    def execute_keyboard(self, payload: dict) -> dict: ...

    def execute_pointer(self, payload: dict) -> dict: ...


FRAME_STORE_MAX_FRAMES = 64
FRAME_STORE_MAX_AGE_SECONDS = 300.0
FRAME_STORE_MAX_TOTAL_BYTES = 6 * 1024 * 1024
FRAME_STORE_MAX_FRAME_BYTES = 96 * 1024


@dataclass(frozen=True, slots=True)
class StoredFrame:
    """Metadata plus one raw JPEG retained only in the Edge-local ring."""

    evidence_id: str
    body: bytes
    sha256: str
    captured_at: str
    stored_at: float


@dataclass(frozen=True, slots=True)
class StoredFrameMetadata:
    """Body-free description used when the governance index misses an ID."""

    evidence_id: str
    sha256: str
    captured_at: str
    size_bytes: int


class BoundedFrameStore:
    """Five-minute Edge-local raw-frame ring; Runtime sees only its index."""

    def __init__(
        self,
        max_frames: int = FRAME_STORE_MAX_FRAMES,
        *,
        max_age_seconds: float = FRAME_STORE_MAX_AGE_SECONDS,
        max_total_bytes: int = FRAME_STORE_MAX_TOTAL_BYTES,
        max_frame_bytes: int = FRAME_STORE_MAX_FRAME_BYTES,
        boot_id: str | None = None,
        clock=None,
    ) -> None:
        if max_frames < 1 or max_frames > FRAME_STORE_MAX_FRAMES:
            raise ValueError(
                f"Frame store capacity must be between 1 and {FRAME_STORE_MAX_FRAMES}."
            )
        if max_age_seconds <= 0:
            raise ValueError("Frame store TTL must be positive.")
        if max_frame_bytes < 1 or max_frame_bytes > FRAME_STORE_MAX_FRAME_BYTES:
            raise ValueError(
                f"Frame store frame bound must be between 1 and {FRAME_STORE_MAX_FRAME_BYTES}."
            )
        if max_total_bytes < max_frame_bytes:
            raise ValueError("Frame store total bound must fit one frame.")
        if boot_id is not None and (
            not isinstance(boot_id, str) or not boot_id or len(boot_id) > 32
        ):
            raise ValueError("Frame store boot_id must be a short non-empty string.")
        self.max_frames = max_frames
        self.max_age_seconds = float(max_age_seconds)
        self.max_total_bytes = max_total_bytes
        self.max_frame_bytes = max_frame_bytes
        self.boot_id = boot_id or secrets.token_hex(4)
        self.clock = clock or monotonic
        self._frames: OrderedDict[str, StoredFrame] = OrderedDict()
        self._total_bytes = 0
        self._sequence = 0

    def put(
        self,
        owner_id: str,
        body: bytes,
        *,
        captured_at: str = "",
    ) -> tuple[str, str]:
        if not isinstance(owner_id, str) or not owner_id:
            raise ValueError("Frame store owner_id must be non-empty.")
        if not isinstance(body, (bytes, bytearray, memoryview)):
            raise ValueError("Frame store body must be bytes.")
        body = bytes(body)
        if not body or len(body) > self.max_frame_bytes:
            raise ValueError("frame_exceeds_store_limit")
        self._evict_expired()
        self._sequence += 1
        digest = sha256(body).hexdigest()
        evidence_id = f"{owner_id}/boot-{self.boot_id}/frame-{self._sequence}"
        entry = StoredFrame(
            evidence_id=evidence_id,
            body=body,
            sha256=digest,
            captured_at=captured_at,
            stored_at=self.clock(),
        )
        while self._frames and (
            len(self._frames) >= self.max_frames
            or self._total_bytes + len(body) > self.max_total_bytes
        ):
            _, evicted = self._frames.popitem(last=False)
            self._total_bytes -= len(evicted.body)
        self._frames[evidence_id] = entry
        self._total_bytes += len(body)
        return evidence_id, digest

    def get_entry(self, evidence_id: str) -> StoredFrame | None:
        self._evict_expired()
        entry = self._frames.get(evidence_id)
        return entry

    def get(self, evidence_id: str) -> bytes | None:
        entry = self.get_entry(evidence_id)
        return bytes(entry.body) if entry is not None else None

    def get_metadata(self, evidence_id: str) -> StoredFrameMetadata | None:
        entry = self.get_entry(evidence_id)
        if entry is None:
            return None
        return StoredFrameMetadata(
            evidence_id=entry.evidence_id,
            sha256=entry.sha256,
            captured_at=entry.captured_at,
            size_bytes=len(entry.body),
        )

    def _evict_expired(self) -> None:
        now = self.clock()
        while self._frames:
            first_key, first = next(iter(self._frames.items()))
            if now - first.stored_at <= self.max_age_seconds:
                break
            self._frames.pop(first_key)
            self._total_bytes -= len(first.body)


class EspKvmHttpAdapter:
    """ESP-KVM REST adapter; credentials remain Edge-local and never enter frames."""

    adapter_kind = "esp-kvm-rest-v1"
    requirements = (
        "HDMI-compatible video source",
        "USB HID-capable target port",
        "MJPEG capture mode for still frames",
        "ESP-KVM agent API enabled",
    )
    supported_target_classes = frozenset({"desktop", "laptop", "server", "tablet", "phone"})

    def __init__(
        self,
        adapter_id: str,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
        evidence_owner_id: str | None = None,
        timeout_seconds: float = 3.0,
        frame_store: BoundedFrameStore | None = None,
        opener=None,
        clock=None,
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("ESP-KVM base_url must be an absolute HTTP(S) URL.")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("ESP-KVM base_url must not include a path, query, or fragment.")
        self.adapter_id = adapter_id
        self.evidence_owner_id = evidence_owner_id or adapter_id
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout_seconds = timeout_seconds
        self.frame_store = frame_store or BoundedFrameStore()
        self.opener = opener or build_opener(HTTPCookieProcessor(CookieJar()))
        self.clock = clock or _utc_now

    def probe(self) -> AdapterProbe:
        video = self._request_json("GET", "/api/v1/video/status")
        usb = self._request_json("GET", "/api/v1/system/usbprobe")
        settings = self._request_json("GET", "/api/v1/settings")
        signal = video.get("signal") is True
        usb_attached = bool(usb.get("trace"))
        agent_api_enabled = settings.get("agent_api") is True
        screen_available = signal and agent_api_enabled
        hid_inferred = usb_attached and agent_api_enabled
        capabilities = {
            "screen": CapabilityAvailability(
                "available" if screen_available else "unavailable",
                None
                if screen_available
                else "agent_api_disabled"
                if not agent_api_enabled
                else "no_video_signal",
            ),
            "audio": CapabilityAvailability("unavailable", "adapter_does_not_capture_audio"),
            "keyboard": CapabilityAvailability(
                "degraded" if hid_inferred else "unavailable",
                "usb_enumeration_seen_live_hid_unverified"
                if hid_inferred
                else "agent_api_disabled"
                if not agent_api_enabled
                else "no_usb_target",
            ),
            "pointer": CapabilityAvailability(
                "degraded" if hid_inferred else "unavailable",
                "usb_enumeration_seen_live_hid_unverified"
                if hid_inferred
                else "agent_api_disabled"
                if not agent_api_enabled
                else "no_usb_target",
            ),
            "virtual_media": CapabilityAvailability("unavailable", "not_enabled_by_adapter"),
            "power": CapabilityAvailability("unavailable", "not_enabled_by_adapter"),
        }
        return AdapterProbe(
            capabilities=capabilities,
            details={
                "video": {
                    "signal": signal,
                    "width": video.get("width"),
                    "height": video.get("height"),
                    "codec": video.get("codec"),
                    "fps": video.get("fps"),
                },
                "usb": {"attached": usb_attached, "target_os": usb.get("os", "unknown")},
                "agent_api_enabled": agent_api_enabled,
            },
        )

    def capture_frame(self) -> CapturedFrame:
        video = self._request_json("GET", "/api/v1/video/status")
        if video.get("signal") is not True:
            raise ProxyAdapterError("no_video_signal")
        if video.get("codec") != "mjpeg":
            raise ProxyAdapterError("snapshot_requires_mjpeg")
        started = monotonic()
        body, content_type = self._request_bytes("GET", "/api/v1/video/frame.jpg")
        latency_ms = round((monotonic() - started) * 1000)
        if not body or not content_type.startswith("image/jpeg"):
            raise ProxyAdapterError("invalid_jpeg_frame")
        captured_at = self.clock()
        try:
            evidence_ref, digest = self.frame_store.put(
                self.evidence_owner_id,
                body,
                captured_at=captured_at,
            )
        except ValueError as exc:
            raise ProxyAdapterError("evidence_unavailable") from exc
        return CapturedFrame(
            evidence_ref=evidence_ref,
            captured_at=captured_at,
            width=_positive_int(video.get("width"), "video width"),
            height=_positive_int(video.get("height"), "video height"),
            mime_type="image/jpeg",
            size_bytes=len(body),
            sha256=digest,
            capture_latency_ms=latency_ms,
        )

    def read_evidence(self, evidence_ref: str, max_bytes: int) -> bytes:
        """Return one already-captured local item without refetching the screen."""

        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
            raise ProxyAdapterError("invalid_evidence_max_bytes")
        body = self.frame_store.get(evidence_ref)
        if body is None:
            raise ProxyAdapterError("evidence_unavailable")
        if len(body) > max_bytes:
            raise ProxyAdapterError("evidence_exceeds_policy_limit")
        return body

    def read_evidence_metadata(self, evidence_ref: str) -> StoredFrameMetadata:
        """Return metadata for one live ring item without exposing its bytes."""

        entry = self.frame_store.get_metadata(evidence_ref)
        if entry is None:
            raise ProxyAdapterError("evidence_unavailable")
        return entry

    def execute_keyboard(self, payload: dict) -> dict:
        operation = payload.get("operation")
        if operation == "type":
            text = payload.get("text")
            if not isinstance(text, str) or not text or len(text) > 80 or not text.isascii():
                raise ProxyAdapterError("invalid_ascii_text")
            return self._request_json("POST", "/api/v1/hid/type", {"text": text})
        if operation == "chord":
            keys = payload.get("keys", [])
            modifier = payload.get("modifier", 0)
            if (
                not isinstance(keys, list)
                or len(keys) > 6
                or not all(isinstance(key, int) and 0 <= key <= 255 for key in keys)
                or not isinstance(modifier, int)
                or not 0 <= modifier <= 255
                or (not keys and modifier == 0)
            ):
                raise ProxyAdapterError("invalid_key_chord")
            return self._request_json(
                "POST",
                "/api/v1/hid/key",
                {"keys": keys, "modifier": modifier},
            )
        raise ProxyAdapterError("unsupported_keyboard_operation")

    def execute_pointer(self, payload: dict) -> dict:
        operation = payload.get("operation")
        if operation not in {"move", "click"}:
            raise ProxyAdapterError("unsupported_pointer_operation")
        x = payload.get("x")
        y = payload.get("y")
        if (
            not isinstance(x, (int, float))
            or isinstance(x, bool)
            or not 0 <= x <= 1
            or not isinstance(y, (int, float))
            or isinstance(y, bool)
            or not 0 <= y <= 1
        ):
            raise ProxyAdapterError("invalid_pointer_coordinates")
        request = {"x": round(x * 32767), "y": round(y * 32767)}
        if operation == "click":
            button = payload.get("button", "left")
            if button not in {"left", "right", "middle"}:
                raise ProxyAdapterError("invalid_pointer_button")
            request["button"] = button
        return self._request_json("POST", f"/api/v1/hid/{operation}", request)

    def _login(self) -> None:
        if not self.username or self.password is None:
            raise ProxyAdapterError("authentication_required")
        self._raw_request(
            "POST",
            "/api/v1/auth/login",
            {"user": self.username, "password": self.password},
        )

    def _request_json(self, method: str, path: str, body: dict | None = None) -> dict:
        payload, content_type = self._request(method, path, body)
        if "application/json" not in content_type:
            raise ProxyAdapterError("unexpected_response_type")
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProxyAdapterError("invalid_json_response") from exc
        if not isinstance(value, dict):
            raise ProxyAdapterError("invalid_json_response")
        return value

    def _request_bytes(self, method: str, path: str) -> tuple[bytes, str]:
        return self._request(method, path, None)

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None,
    ) -> tuple[bytes, str]:
        try:
            return self._raw_request(method, path, body)
        except ProxyAdapterError as exc:
            if str(exc) != "http_401":
                raise
        self._login()
        return self._raw_request(method, path, body)

    def _raw_request(
        self,
        method: str,
        path: str,
        body: dict | None,
    ) -> tuple[bytes, str]:
        encoded = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json, image/jpeg"}
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.base_url}{path}",
            data=encoded,
            headers=headers,
            method=method,
        )
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                return response.read(), response.headers.get_content_type()
        except HTTPError as exc:
            raise ProxyAdapterError(f"http_{exc.code}") from exc
        except OSError as exc:
            raise ProxyAdapterError("adapter_unreachable") from exc


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ProxyAdapterError(f"invalid_{label.replace(' ', '_')}")
    return value


def _utc_now() -> str:
    from datetime import datetime
    from datetime import timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
