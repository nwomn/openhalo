import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from device_edge.media_memory import InMemoryMediaProviderCredentials
from device_edge.media_memory import LocalHotRing
from device_edge.media_provider import OpenAICompatibleVideoAdapter


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
