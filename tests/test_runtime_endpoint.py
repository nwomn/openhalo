from __future__ import annotations

import pytest

from edge_api.endpoint import validate_runtime_endpoint


@pytest.mark.parametrize(
    "url",
    [
        "wss://runtime.example.test/openhalo/edge",
        "ws://127.0.0.1:8765",
        "ws://localhost:8765",
        "ws://[::1]:8765",
    ],
)
def test_runtime_endpoint_allows_tls_or_explicit_loopback_development(url: str) -> None:
    assert validate_runtime_endpoint(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "ws://runtime.example.test/openhalo/edge",
        "ws://192.0.2.10:8765",
        "http://127.0.0.1:8765",
        "wss://",
    ],
)
def test_runtime_endpoint_rejects_insecure_or_invalid_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_runtime_endpoint(url)
