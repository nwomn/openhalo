"""Shared runtime context contract types."""

from dataclasses import asdict
from dataclasses import dataclass


@dataclass(slots=True)
class DeviceContract:
    device_id: str
    device_type: str
    role: str
    profile: str
    capabilities: list[str]


@dataclass(slots=True)
class CapabilityContract:
    name: str
    observations: list[str]
    actions: list[str]


@dataclass(slots=True)
class RuntimeObservation:
    name: str
    value: str
    source_device_id: str
    source_capability: str
    source_event_id: str
    observed_at: str
    confidence: float
    parent_event_id: str | None = None
    reentry_parent: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "RuntimeObservation":
        return cls(**payload)
