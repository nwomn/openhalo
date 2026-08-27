"""Public, vendor-neutral contracts for a Proxy Interaction Edge."""

from dataclasses import dataclass
from dataclasses import field


ATTACHMENT_STATES = frozenset({"detached", "attached", "degraded", "incompatible"})
CAPABILITY_STATES = frozenset({"available", "degraded", "unavailable"})
PROXY_CAPABILITY_FACETS = (
    "screen",
    "audio",
    "keyboard",
    "pointer",
    "virtual_media",
    "power",
)

OBSERVATION_CAPABILITY = "proxy.interaction.observe"
KEYBOARD_CAPABILITY = "proxy.keyboard.input"
POINTER_CAPABILITY = "proxy.pointer.input"


@dataclass(frozen=True, slots=True)
class CapabilityAvailability:
    state: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.state not in CAPABILITY_STATES:
            raise ValueError(f"Unsupported proxy capability state: {self.state!r}")
        if self.state != "available" and not self.reason:
            raise ValueError("Degraded and unavailable capabilities require a reason.")

    def to_dict(self, name: str) -> dict:
        value = {"name": name, "state": self.state}
        if self.reason is not None:
            value["reason"] = self.reason
        return value


@dataclass(frozen=True, slots=True)
class ProxyTargetAttachment:
    target_id: str
    surface_id: str
    target_class: str
    attachment_state: str
    capabilities: dict[str, CapabilityAvailability]
    observed_at: str
    adapter_id: str
    adapter_kind: str
    requirements: tuple[str, ...] = ()
    native_device_id: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("target_id", self.target_id),
            ("surface_id", self.surface_id),
            ("target_class", self.target_class),
            ("adapter_id", self.adapter_id),
            ("adapter_kind", self.adapter_kind),
            ("observed_at", self.observed_at),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"Proxy attachment requires non-empty {name}.")
        if self.attachment_state not in ATTACHMENT_STATES:
            raise ValueError(
                f"Unsupported proxy attachment state: {self.attachment_state!r}"
            )
        missing = set(PROXY_CAPABILITY_FACETS).difference(self.capabilities)
        unknown = set(self.capabilities).difference(PROXY_CAPABILITY_FACETS)
        if missing or unknown:
            raise ValueError(
                "Proxy attachment capability facets must be exactly "
                f"{PROXY_CAPABILITY_FACETS!r}; missing={sorted(missing)!r}, "
                f"unknown={sorted(unknown)!r}."
            )

    def capability_state(self, name: str) -> CapabilityAvailability:
        if name not in self.capabilities:
            raise ValueError(f"Unknown proxy capability facet: {name!r}")
        return self.capabilities[name]

    def to_observation(self) -> dict:
        value = {
            "target_id": self.target_id,
            "surface_id": self.surface_id,
            "target_class": self.target_class,
            "attachment_state": self.attachment_state,
            "adapter": {
                "adapter_id": self.adapter_id,
                "adapter_kind": self.adapter_kind,
            },
            "requirements": list(self.requirements),
            "capabilities": [
                self.capabilities[name].to_dict(name)
                for name in PROXY_CAPABILITY_FACETS
            ],
        }
        if self.native_device_id is not None:
            value["native_device_id"] = self.native_device_id
        return {
            "name": "proxy.target_attachment.v1",
            "value": value,
            "observed_at": self.observed_at,
            "confidence": 1.0,
            "context_disposition": "structural",
        }


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    evidence_ref: str
    captured_at: str
    width: int
    height: int
    mime_type: str
    size_bytes: int
    sha256: str
    source_kind: str = "human_visible_pixels"
    capture_latency_ms: int | None = None

    def to_observation(self, attachment: ProxyTargetAttachment) -> dict:
        value = {
            "target_id": attachment.target_id,
            "surface_id": attachment.surface_id,
            "source_kind": self.source_kind,
            "width": self.width,
            "height": self.height,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }
        if self.capture_latency_ms is not None:
            value["capture_latency_ms"] = self.capture_latency_ms
        return {
            "name": "proxy.screen_frame.v1",
            "value": value,
            "observed_at": self.captured_at,
            "confidence": 1.0,
            "evidence_ref": self.evidence_ref,
            "context_disposition": "structural",
        }


def unavailable_capabilities(reason: str) -> dict[str, CapabilityAvailability]:
    return {
        name: CapabilityAvailability("unavailable", reason)
        for name in PROXY_CAPABILITY_FACETS
    }


def build_proxy_capability_registrations(
    attachment: ProxyTargetAttachment,
) -> list[dict]:
    registrations: list[dict] = [
        {
            "name": OBSERVATION_CAPABILITY,
            "direction": "edge_to_runtime",
            "kind": "observation_provider",
            "affordances": ["observe_interaction_surface", "report_attachment_state"],
            "privacy": "personal_screen",
            "target_relationship": {
                "target_id": attachment.target_id,
                "surface_id": attachment.surface_id,
                "target_class": attachment.target_class,
            },
            "exposed_capabilities": [
                attachment.capabilities[name].to_dict(name)
                for name in PROXY_CAPABILITY_FACETS
            ],
            "observations": [
                {
                    "name": "proxy.target_attachment.v1",
                    "schema": {"type": "object"},
                    "semantics": ["proxy_attachment", "capability_availability"],
                    "privacy": "device_relationship",
                    "freshness_seconds": 30,
                    "schema_version": 1,
                },
                {
                    "name": "proxy.screen_frame.v1",
                    "schema": {"type": "object"},
                    "semantics": ["human_visible_screen", "visual_evidence"],
                    "privacy": "personal_screen",
                    "freshness_seconds": 5,
                    "schema_version": 1,
                },
            ],
        }
    ]
    if attachment.capability_state("keyboard").state != "unavailable":
        registrations.append(_keyboard_registration(attachment))
    if attachment.capability_state("pointer").state != "unavailable":
        registrations.append(_pointer_registration(attachment))
    return registrations


def _target_properties(attachment: ProxyTargetAttachment) -> dict:
    return {
        "target_id": {"type": "string", "const": attachment.target_id},
        "surface_id": {"type": "string", "const": attachment.surface_id},
    }


def _keyboard_registration(attachment: ProxyTargetAttachment) -> dict:
    properties = {
        **_target_properties(attachment),
        "operation": {"type": "string", "enum": ["type", "chord"]},
        "text": {"type": "string", "maxLength": 80},
        "keys": {
            "type": "array",
            "maxItems": 6,
            "items": {"type": "integer", "minimum": 0, "maximum": 255},
        },
        "modifier": {"type": "integer", "minimum": 0, "maximum": 255},
    }
    return {
        "name": KEYBOARD_CAPABILITY,
        "direction": "runtime_to_edge",
        "kind": "action",
        "affordances": ["type_text", "press_key_chord"],
        "modality": "usb_hid_keyboard",
        "side_effect": "target_input",
        "target_relationship": {
            "target_id": attachment.target_id,
            "surface_id": attachment.surface_id,
        },
        "input_schema": {
            "type": "object",
            "required": ["target_id", "surface_id", "operation"],
            "additionalProperties": False,
            "properties": properties,
        },
    }


def _pointer_registration(attachment: ProxyTargetAttachment) -> dict:
    properties = {
        **_target_properties(attachment),
        "operation": {"type": "string", "enum": ["move", "click"]},
        "x": {"type": "number", "minimum": 0, "maximum": 1},
        "y": {"type": "number", "minimum": 0, "maximum": 1},
        "button": {"type": "string", "enum": ["left", "right", "middle"]},
    }
    return {
        "name": POINTER_CAPABILITY,
        "direction": "runtime_to_edge",
        "kind": "action",
        "affordances": ["move_pointer", "click_pointer"],
        "modality": "usb_hid_pointer",
        "side_effect": "target_input",
        "target_relationship": {
            "target_id": attachment.target_id,
            "surface_id": attachment.surface_id,
        },
        "input_schema": {
            "type": "object",
            "required": ["target_id", "surface_id", "operation", "x", "y"],
            "additionalProperties": False,
            "properties": properties,
        },
    }
