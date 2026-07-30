"""Runtime endpoint trust rules shared by Python Device Edges."""

from __future__ import annotations

from urllib.parse import urlsplit


def validate_runtime_endpoint(url: str) -> str:
    """Accept a complete owner-selected WebSocket Runtime endpoint."""

    if not isinstance(url, str) or not url:
        raise ValueError("Runtime endpoint must be a non-empty WebSocket URL.")
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ValueError("Runtime endpoint must be a valid WebSocket URL.") from exc
    if parsed.scheme in {"ws", "wss"} and parsed.hostname:
        return url
    raise ValueError("Runtime endpoint must be a complete ws:// or wss:// URL.")
