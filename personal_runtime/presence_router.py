"""Presence routing rules for the v0 runtime."""


def choose_response_device(source_device_id: str) -> str:
    return source_device_id
