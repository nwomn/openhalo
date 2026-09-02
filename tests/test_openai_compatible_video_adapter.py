import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from device_edge.media_memory import InMemoryMediaProviderCredentials
from device_edge.media_memory import LocalHotRing
from device_edge.media_provider import OpenAICompatibleVideoAdapter
from device_edge.media_provider import _decode_http_body
from device_edge.media_provider import _provider_error_code
from device_edge.media_provider import _provider_error_hint


def test_adapter_sends_local_video_as_data_url_and_returns_markdown():
    async def scenario():
        with TemporaryDirectory() as directory:
            ring = LocalHotRing(source_ref="camera-edge-1/camera.main/camera.capture/video", directory=Path(directory), retention_seconds=86_400, max_bytes=1024)
            ring.append_segment(start_at="2026-09-01T10:00:00Z", end_at="2026-09-01T10:00:02Z", body=b"private-mp4", mime_type="video/mp4")
            selection = ring.select(start_at="2026-09-01T10:00:00Z", end_at="2026-09-01T10:00:02Z")
            credentials = InMemoryMediaProviderCredentials()
            credentials.configure(provider={"name": "dashscope_camera", "adapter_type": "openai_compatible", "base_url": "https://dashscope.example/v1", "wire_api": "chat_completions", "api_key": "private-key", "timeout_seconds": 30, "default_headers": {}}, model={"name": "qwen_video", "model_id": "qwen3-vl-flash", "supports_vision": True, "supports_video": True})
            seen = {}
            async def transport(url, payload, headers, timeout):
                seen.update(url=url, payload=payload, headers=headers, timeout=timeout)
                return {"choices": [{"message": {"content": "## Understanding\nA person entered."}}]}
            adapter = OpenAICompatibleVideoAdapter(credentials=credentials, provider_name="dashscope_camera", model_name="qwen_video", transport=transport)
            result = await adapter(selection, "What happened?", ring)
            return result, seen
    result, seen = asyncio.run(scenario())
    content = seen["payload"]["messages"][0]["content"]
    assert seen["url"] == "https://dashscope.example/v1/chat/completions"
    assert content[1]["type"] == "video_url"
    assert "cHJpdmF0ZS1tcDQ=" in content[1]["video_url"]["url"]
    assert result["markdown"] == "## Understanding\nA person entered."
    assert "private-key" not in str(result)


def test_adapter_rejects_total_inline_video_budget():
    async def scenario():
        with TemporaryDirectory() as directory:
            ring = LocalHotRing(source_ref="camera-edge-1/camera.main/camera.capture/video", directory=Path(directory), retention_seconds=86_400, max_bytes=8 * 1024 * 1024)
            ring.append_segment(start_at="2026-09-01T10:00:00Z", end_at="2026-09-01T10:00:02Z", body=b"x" * (4 * 1024 * 1024), mime_type="video/mp4")
            ring.append_segment(start_at="2026-09-01T10:00:02Z", end_at="2026-09-01T10:00:04Z", body=b"y" * (4 * 1024 * 1024), mime_type="video/mp4")
            selection = ring.select(start_at="2026-09-01T10:00:00Z", end_at="2026-09-01T10:00:04Z")
            credentials = InMemoryMediaProviderCredentials()
            credentials.configure(provider={"name": "dashscope_camera", "adapter_type": "openai_compatible", "base_url": "https://dashscope.example/v1", "wire_api": "chat_completions", "api_key": "private-key", "timeout_seconds": 30, "default_headers": {}}, model={"name": "qwen_video", "model_id": "qwen3-vl-flash", "supports_vision": True, "supports_video": True})
            adapter = OpenAICompatibleVideoAdapter(credentials=credentials, provider_name="dashscope_camera", model_name="qwen_video", transport=lambda *_args: None)
            try:
                await adapter(selection, "What happened?", ring)
            except ValueError as error:
                return str(error)
            return ""
    assert asyncio.run(scenario()) == "video_query_exceeds_provider_inline_limit"


def test_adapter_bounds_hung_provider_request_and_records_non_secret_stage():
    async def scenario():
        with TemporaryDirectory() as directory:
            ring = LocalHotRing(source_ref="camera-edge-1/camera.main/camera.capture/video", directory=Path(directory), retention_seconds=86_400, max_bytes=1024)
            ring.append_segment(start_at="2026-09-01T10:00:00Z", end_at="2026-09-01T10:00:02Z", body=b"private-mp4", mime_type="video/mp4")
            selection = ring.select(start_at="2026-09-01T10:00:00Z", end_at="2026-09-01T10:00:02Z")
            credentials = InMemoryMediaProviderCredentials()
            credentials.configure(provider={"name": "dashscope_camera", "adapter_type": "openai_compatible", "base_url": "https://dashscope.example/v1", "wire_api": "chat_completions", "api_key": "private-key", "timeout_seconds": 30, "default_headers": {}}, model={"name": "qwen_video", "model_id": "qwen3-vl-flash", "supports_vision": True, "supports_video": True})
            events = []

            async def transport(*_args):
                await asyncio.Event().wait()

            adapter = OpenAICompatibleVideoAdapter(
                credentials=credentials,
                provider_name="dashscope_camera",
                model_name="qwen_video",
                transport=transport,
                diagnostic_sink=events.append,
                max_request_seconds=0.01,
            )
            try:
                await adapter(selection, "What happened?", ring)
            except TimeoutError:
                return events
            raise AssertionError("hung provider request was not bounded")

    events = asyncio.run(scenario())
    assert [event["phase"] for event in events] == ["request_started", "request_timed_out"]
    assert "private-key" not in str(events)
    assert "private-mp4" not in str(events)


def test_adapter_records_non_secret_diagnostic_for_provider_failure():
    async def scenario():
        with TemporaryDirectory() as directory:
            ring = LocalHotRing(source_ref="camera-edge-1/camera.main/camera.capture/video", directory=Path(directory), retention_seconds=86_400, max_bytes=1024)
            ring.append_segment(start_at="2026-09-01T10:00:00Z", end_at="2026-09-01T10:00:02Z", body=b"private-mp4", mime_type="video/mp4")
            selection = ring.select(start_at="2026-09-01T10:00:00Z", end_at="2026-09-01T10:00:02Z")
            credentials = InMemoryMediaProviderCredentials()
            credentials.configure(provider={"name": "dashscope_camera", "adapter_type": "openai_compatible", "base_url": "https://dashscope.example/v1", "wire_api": "chat_completions", "api_key": "private-key", "timeout_seconds": 30, "default_headers": {}}, model={"name": "qwen_video", "model_id": "qwen3-vl-flash", "supports_vision": True, "supports_video": True})
            events = []

            async def transport(*_args):
                raise ValueError("provider_http_error")

            adapter = OpenAICompatibleVideoAdapter(
                credentials=credentials,
                provider_name="dashscope_camera",
                model_name="qwen_video",
                transport=transport,
                diagnostic_sink=events.append,
            )
            try:
                await adapter(selection, "What happened?", ring)
            except ValueError:
                return events
            raise AssertionError("provider failure was not propagated")

    events = asyncio.run(scenario())
    assert [event["phase"] for event in events] == ["request_started", "request_failed"]
    assert events[-1]["error_type"] == "ValueError"
    assert events[-1]["error_message"] == "provider_http_error"
    assert "private-key" not in str(events)
    assert "private-mp4" not in str(events)


def test_provider_error_code_only_keeps_a_compact_machine_code():
    assert _provider_error_code(b'{"error":{"code":"InvalidParameter"}}') == "InvalidParameter"
    assert _provider_error_code(b'{"error":{"code":"message with spaces"}}') == "unspecified"
    assert _provider_error_code(b"not-json") == "unparseable"


def test_provider_error_hint_redacts_credentials_and_data_urls():
    response = b'{"error":{"message":"api_key=sk-private data:video/mp4;base64,SGVsbG8="}}'
    assert _provider_error_hint(response) == "api_key=<credential-redacted> <data-url-redacted>"


def test_chunked_provider_http_body_is_decoded_before_json_parsing():
    head = b"HTTP/1.1 400 Bad Request\r\nTransfer-Encoding: chunked"
    body = b"d\r\n{\"error\":{\"co\r\n14\r\nde\":\"InvalidParam\"}}\r\n0\r\n\r\n"
    decoded = _decode_http_body(head, body)
    assert _provider_error_code(decoded) == "InvalidParam"
