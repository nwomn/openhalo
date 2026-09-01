"""Direct Edge-side media providers.

The first concrete adapter targets an OpenAI-compatible Chat Completions
endpoint that accepts video data URLs, such as the explicitly configured
DashScope/Qwen video profile. It only receives bytes from the local Hot Ring.
"""

from __future__ import annotations

import asyncio
import base64
import json
from urllib.parse import urlparse


_MAX_PROVIDER_INLINE_BYTES = 7 * 1024 * 1024
_MAX_PROVIDER_RESPONSE_BYTES = 1 * 1024 * 1024


class OpenAICompatibleVideoAdapter:
    """Call one configured Edge-local OpenAI-compatible video provider."""

    def __init__(self, *, credentials, provider_name: str, model_name: str, transport=None) -> None:
        self.credentials = credentials
        self.provider_name = provider_name
        self.model_name = model_name
        self.transport = transport or _post_json

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
        response = await self.transport(
            f"{provider['base_url'].rstrip('/')}/chat/completions",
            request,
            headers,
            provider["timeout_seconds"],
        )
        markdown = _response_text(response)
        return {
            "markdown": markdown,
            "model": profile["model"]["model_id"],
            "limitations": ["provider_direct_video", f"segments={len(selection.segments)}"],
        }


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
        await writer.wait_closed()
    head, separator, response_body = raw.partition(b"\r\n\r\n")
    if not separator or not head.startswith(b"HTTP/"):
        raise ValueError("invalid_provider_response")
    status = int(head.split(b" ", 2)[1])
    if not 200 <= status < 300:
        raise ValueError("provider_http_error")
    return json.loads(response_body.decode("utf-8"))
