"""Direct Edge-side media providers.

The first concrete adapter targets an OpenAI-compatible Chat Completions
endpoint that accepts video data URLs, such as the explicitly configured
DashScope/Qwen video profile. It only receives bytes from the local Hot Ring.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
from urllib.parse import urlparse


_MAX_PROVIDER_INLINE_BYTES = 7 * 1024 * 1024
_MAX_PROVIDER_RESPONSE_BYTES = 1 * 1024 * 1024
_MAX_PROVIDER_ACTION_SECONDS = 30


class OpenAICompatibleVideoAdapter:
    """Call one configured Edge-local OpenAI-compatible video provider."""

    def __init__(
        self,
        *,
        credentials,
        provider_name: str,
        model_name: str,
        transport=None,
        diagnostic_sink=None,
        max_request_seconds: float = _MAX_PROVIDER_ACTION_SECONDS,
    ) -> None:
        if max_request_seconds <= 0:
            raise ValueError("max_request_seconds must be positive")
        self.credentials = credentials
        self.provider_name = provider_name
        self.model_name = model_name
        self.transport = transport or _post_json
        self.diagnostic_sink = diagnostic_sink
        self.max_request_seconds = max_request_seconds

    def is_configured(self) -> bool:
        profile = self.credentials.profile_for(provider=self.provider_name, model=self.model_name)
        return profile is not None and profile["model"].get("supports_video") is True

    async def __call__(self, selection, question: str, hot_ring) -> dict:
        profile = self.credentials.profile_for(provider=self.provider_name, model=self.model_name)
        if profile is None or not profile["model"].get("supports_video"):
            raise ValueError("provider_unconfigured")
        provider = profile["provider"]
        if provider["adapter_type"] != "openai_compatible" or provider["wire_api"] != "chat_completions":
            raise ValueError("unsupported_video_provider_profile")
        videos = []
        total_bytes = 0
        for segment in selection.segments:
            body = hot_ring.read_segment(segment)
            total_bytes += len(body)
            if total_bytes > _MAX_PROVIDER_INLINE_BYTES:
                raise ValueError("video_query_exceeds_provider_inline_limit")
            encoded = base64.b64encode(body).decode("ascii")
            # DashScope OpenAI-compatible video data URLs are only suitable
            # for small clips. Keep the raw segment at or below 7 MiB so its
            # Base64 data URL remains below the documented 10 MiB ceiling.
            if len(body) > 7 * 1024 * 1024 or len(encoded) > 10 * 1024 * 1024:
                raise ValueError("video_segment_exceeds_provider_inline_limit")
            videos.append({"type": "video_url", "video_url": {"url": f"data:{segment.mime_type};base64,{encoded}"}})
        request = {
            "model": profile["model"]["model_id"],
            "stream": False,
            "enable_thinking": False,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": _prompt(question, selection.coverage)},
                *videos,
            ]}],
        }
        headers = {"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json", **provider["default_headers"]}
        timeout_seconds = min(provider["timeout_seconds"], self.max_request_seconds)
        self._diagnose({
            "event": "media_provider_request",
            "phase": "request_started",
            "provider": self.provider_name,
            "model": self.model_name,
            "segment_count": len(videos),
            "raw_video_bytes": total_bytes,
            "timeout_seconds": timeout_seconds,
        })
        try:
            response = await asyncio.wait_for(
                self.transport(
                    f"{provider['base_url'].rstrip('/')}/chat/completions",
                    request,
                    headers,
                    provider["timeout_seconds"],
                ),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            self._diagnose({
                "event": "media_provider_request",
                "phase": "request_timed_out",
                "provider": self.provider_name,
                "model": self.model_name,
                "timeout_seconds": timeout_seconds,
            })
            raise
        except Exception as error:
            # The action result deliberately stays provider-agnostic, but the
            # device-local diagnostic must retain enough information to
            # distinguish TLS/connectivity, HTTP, and response-shape failures.
            # Never include request headers, payloads, or exception attributes:
            # those could contain the configured credential or video bytes.
            self._diagnose({
                "event": "media_provider_request",
                "phase": "request_failed",
                "provider": self.provider_name,
                "model": self.model_name,
                "error_type": type(error).__name__,
                "error_message": _safe_diagnostic_message(error),
            })
            raise
        markdown = _response_text(response)
        self._diagnose({
            "event": "media_provider_request",
            "phase": "response_received",
            "provider": self.provider_name,
            "model": self.model_name,
            "response_chars": len(markdown),
        })
        return {
            "markdown": markdown,
            "model": profile["model"]["model_id"],
            "limitations": ["provider_direct_video", f"segments={len(selection.segments)}"],
        }

    def _diagnose(self, event: dict) -> None:
        if self.diagnostic_sink is not None:
            self.diagnostic_sink(event)


def _prompt(question: str, coverage: dict) -> str:
    return (
        "根据所附本地摄像头视频回答问题。用 Markdown 简洁回答；仅陈述视频可支持的内容，"
        "不确定、遮挡或时间覆盖不足时必须明确说明。\n"
        f"问题：{question}\n覆盖范围：{json.dumps(coverage, ensure_ascii=False)}"
    )


def _response_text(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValueError("invalid_provider_response")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("invalid_provider_response")
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("invalid_provider_response")
    return content.strip()


def _safe_diagnostic_message(error: Exception) -> str:
    """Return a bounded, single-line error description safe for local logs."""

    return " ".join(str(error).replace("\x00", " ").split())[:512]


async def _post_json(url: str, payload: dict, headers: dict[str, str], timeout_seconds: int) -> dict:
    """Minimal asynchronous HTTPS POST without a blocking provider SDK."""

    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("invalid_provider_endpoint")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(parsed.hostname, parsed.port or 443, ssl=True), timeout=timeout_seconds
    )
    try:
        target = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
        request_headers = {"Host": parsed.hostname, "Connection": "close", "Content-Length": str(len(body)), **headers}
        lines = [f"POST {target} HTTP/1.1", *(f"{name}: {value}" for name, value in request_headers.items()), "", ""]
        writer.write("\r\n".join(lines).encode("utf-8") + body)
        await asyncio.wait_for(writer.drain(), timeout=timeout_seconds)
        raw = await asyncio.wait_for(reader.read(_MAX_PROVIDER_RESPONSE_BYTES + 1), timeout=timeout_seconds)
        if len(raw) > _MAX_PROVIDER_RESPONSE_BYTES:
            raise ValueError("provider_response_exceeds_limit")
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=2)
        except (TimeoutError, OSError):
            pass
    head, separator, response_body = raw.partition(b"\r\n\r\n")
    if not separator or not head.startswith(b"HTTP/"):
        raise ValueError("invalid_provider_response")
    status = int(head.split(b" ", 2)[1])
    response_body = _decode_http_body(head, response_body)
    if not 200 <= status < 300:
        raise ValueError(
            f"provider_http_error:{status}:{_provider_error_code(response_body)}:"
            f"{_provider_error_hint(response_body)}"
        )
    return json.loads(response_body.decode("utf-8"))


def _decode_http_body(head: bytes, body: bytes) -> bytes:
    """Decode the HTTP/1.1 response framing used by OpenAI-compatible APIs."""

    header_lines = head.decode("iso-8859-1").split("\r\n")
    has_chunked_encoding = any(
        line.lower().startswith("transfer-encoding:") and "chunked" in line.lower()
        for line in header_lines[1:]
    )
    if not has_chunked_encoding:
        return body
    decoded = bytearray()
    cursor = 0
    while True:
        line_end = body.find(b"\r\n", cursor)
        if line_end < 0:
            raise ValueError("invalid_chunked_provider_response")
        size_token = body[cursor:line_end].split(b";", 1)[0].strip()
        try:
            size = int(size_token, 16)
        except ValueError as error:
            raise ValueError("invalid_chunked_provider_response") from error
        cursor = line_end + 2
        if size == 0:
            return bytes(decoded)
        if size < 0 or cursor + size + 2 > len(body) or body[cursor + size:cursor + size + 2] != b"\r\n":
            raise ValueError("invalid_chunked_provider_response")
        decoded.extend(body[cursor:cursor + size])
        if len(decoded) > _MAX_PROVIDER_RESPONSE_BYTES:
            raise ValueError("provider_response_exceeds_limit")
        cursor += size + 2


def _provider_error_code(response_body: bytes) -> str:
    """Extract only a compact machine error code from an HTTP error body."""

    try:
        payload = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "unparseable"
    if not isinstance(payload, dict):
        return "unparseable"
    error = payload.get("error")
    candidate = error.get("code") if isinstance(error, dict) else payload.get("code")
    if not isinstance(candidate, (str, int)):
        return "unspecified"
    normalized = str(candidate).strip()
    if not normalized or len(normalized) > 96 or not all(char.isalnum() or char in "-_." for char in normalized):
        return "unspecified"
    return normalized


def _provider_error_hint(response_body: bytes) -> str:
    """Keep a short, redacted provider explanation for fixing malformed input."""

    try:
        payload = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "unparseable"
    if not isinstance(payload, dict):
        return "unparseable"
    error = payload.get("error")
    message = error.get("message") if isinstance(error, dict) else payload.get("message")
    if not isinstance(message, str):
        return "unspecified"
    return _redact_diagnostic_text(message)


def _redact_diagnostic_text(value: str) -> str:
    redacted = re.sub(r"(?i)data:[^,\s]+;base64,[A-Za-z0-9+/=_-]+", "<data-url-redacted>", value)
    redacted = re.sub(r"\bsk-[A-Za-z0-9_-]+\b", "<credential-redacted>", redacted)
    redacted = re.sub(r"(?i)\b(bearer|api[_ -]?key)\s*[:=]?\s*\S+", r"\1=<credential-redacted>", redacted)
    return " ".join(redacted.replace("\x00", " ").split())[:256]
