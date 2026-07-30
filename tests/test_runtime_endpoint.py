from __future__ import annotations

import pytest

from edge_api.endpoint import validate_runtime_endpoint


@pytest.mark.parametrize(
    "url",
    [
        "wss://runtime.example.test/openhalo/edge",
        "ws://runtime.example.test/openhalo/edge",
        "ws://192.0.2.10:8765",
        "ws://127.0.0.1:8765",
        "ws://localhost:8765",
        "ws://[::1]:8765",
    ],
)
def test_runtime_endpoint_allows_complete_ws_or_wss_urls(url: str) -> None:
    assert validate_runtime_endpoint(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8765",
        "wss://",
        "ws:///openhalo/edge",
    ],
)
def test_runtime_endpoint_rejects_invalid_or_non_websocket_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_runtime_endpoint(url)
