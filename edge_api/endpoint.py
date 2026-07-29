"""Runtime endpoint trust rules shared by Python Device Edges."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


def validate_runtime_endpoint(url: str) -> str:
    """Reject a non-loopback plaintext Runtime endpoint."""

    if not isinstance(url, str) or not url:
        raise ValueError("Runtime endpoint must be a non-empty WebSocket URL.")
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ValueError("Runtime endpoint must be a valid WebSocket URL.") from exc
    if parsed.scheme == "wss" and parsed.hostname:
        return url
    if parsed.scheme == "ws" and _is_loopback_host(parsed.hostname):
        return url
    raise ValueError(
        "Runtime endpoint must use wss://; ws:// is only allowed for loopback development."
    )


def _is_loopback_host(hostname: str | None) -> bool:
    if hostname is None:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False
