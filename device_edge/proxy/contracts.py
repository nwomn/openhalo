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
SCREEN_BASE_OBSERVATION_CAPABILITY = "proxy.screen.base_observe"
KEYBOARD_CAPABILITY = "proxy.keyboard.input"
POINTER_CAPABILITY = "proxy.pointer.input"
SCREEN_FEATURE_CAPABILITY = "proxy.screen.features"
SCREEN_PROFILE_CAPABILITY = "proxy.screen.profile.configure"
SCREEN_READ_CAPABILITY = "proxy.screen.read"
SCREEN_EVIDENCE_ID_MAX_LENGTH = 256


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
            "evidence_id": self.evidence_ref,
        }
        if self.capture_latency_ms is not None:
            value["capture_latency_ms"] = self.capture_latency_ms
        return {
            "name": "proxy.screen_frame.v1",
            "value": value,
            "observed_at": self.captured_at,
            "confidence": 1.0,
            "evidence_ref": self.evidence_ref,
            "evidence_id": self.evidence_ref,
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
    registrations.append(_screen_feature_registration(attachment))
    registrations.append(_screen_base_observation_registration(attachment))
    registrations.append(_screen_profile_registration(attachment))
    if attachment.capability_state("screen").state != "unavailable":
        registrations.append(_screen_read_registration(attachment))
    if attachment.capability_state("keyboard").state != "unavailable":
        registrations.append(_keyboard_registration(attachment))
    if attachment.capability_state("pointer").state != "unavailable":
        registrations.append(_pointer_registration(attachment))
    return registrations


def _screen_base_observation_registration(attachment: ProxyTargetAttachment) -> dict:
    """Register Profile-independent, safe screen facts.

    These values describe capture availability and pixel change only.  They do
    not interpret a target UI or embed screen bytes, so they are admissible as
    ordinary bounded observations without an Attention Profile.
    """

    return {
        "name": SCREEN_BASE_OBSERVATION_CAPABILITY,
        "direction": "edge_to_runtime",
        "kind": "observation_provider",
        "privacy": "personal_screen",
        "target_relationship": {
            "target_id": attachment.target_id,
            "surface_id": attachment.surface_id,
            "target_class": attachment.target_class,
        },
        "observations": [
            {
                "name": "proxy.screen.capture_health.v1",
                "schema": {
                    "type": "object",
                    "required": ["target_id", "surface_id", "feature_version", "state", "width", "height"],
                    "properties": {
                        "target_id": {"type": "string"},
                        "surface_id": {"type": "string"},
                        "feature_version": {"type": "string", "enum": ["capture_health.v1"]},
                        "state": {"type": "string", "enum": ["ready"]},
                        "width": {"type": "integer", "minimum": 1},
                        "height": {"type": "integer", "minimum": 1},
                        "capture_latency_ms": {"type": "integer", "nullable": True, "minimum": 0},
                    },
                },
                "semantics": ["screen_capture_health"],
                "privacy": "device_health",
                "freshness_seconds": 30,
                "schema_version": 1,
            },
            {
                "name": "proxy.screen.change.v1",
                "schema": {
                    "type": "object",
                    "required": ["target_id", "surface_id", "feature_version", "state", "evidence_ref"],
                    "properties": {
                        "target_id": {"type": "string"},
                        "surface_id": {"type": "string"},
                        "feature_version": {"type": "string", "enum": ["screen_change.v1"]},
                        "state": {"type": "string", "enum": ["changed", "unchanged"]},
                        "evidence_ref": {"type": "string"},
                        "evidence_id": {"type": "string", "maxLength": SCREEN_EVIDENCE_ID_MAX_LENGTH},
                    },
                },
                "semantics": ["screen_change", "candidate_event"],
                "privacy": "personal_screen",
                "freshness_seconds": 30,
                "schema_version": 1,
            },
            {
                "name": "proxy.screen.action_effect.v1",
                "schema": {
                    "type": "object",
                    "required": ["target_id", "surface_id", "feature_version", "action_request_id", "state", "evidence_ref"],
                    "properties": {
                        "target_id": {"type": "string"},
                        "surface_id": {"type": "string"},
                        "feature_version": {"type": "string", "enum": ["action_effect.v1"]},
                        "action_request_id": {"type": "string"},
                        "state": {"type": "string", "enum": ["changed", "unchanged"]},
                        "evidence_ref": {"type": "string"},
                        "evidence_id": {"type": "string", "maxLength": SCREEN_EVIDENCE_ID_MAX_LENGTH},
                    },
                },
                "semantics": ["action_effect", "screen_change"],
                "privacy": "personal_screen",
                "freshness_seconds": 30,
                "schema_version": 1,
            },
        ],
    }


def _screen_feature_registration(attachment: ProxyTargetAttachment) -> dict:
    return {
        "name": SCREEN_FEATURE_CAPABILITY,
        "direction": "edge_to_runtime",
        "kind": "observation_provider",
        "privacy": "personal_screen",
        "target_relationship": {
            "target_id": attachment.target_id,
            "surface_id": attachment.surface_id,
            "target_class": attachment.target_class,
        },
        "observations": [
            {
                "name": "proxy.screen.capture_health.v1",
                "schema": {
                    "type": "object",
                    "required": ["target_id", "surface_id", "profile_id", "profile_revision", "feature_version", "state", "width", "height"],
                    "properties": {
                        "target_id": {"type": "string"},
                        "surface_id": {"type": "string"},
                        "profile_id": {"type": "string"},
                        "profile_revision": {"type": "integer"},
                        "feature_version": {"type": "string", "enum": ["capture_health.v1"]},
                        "state": {"type": "string", "enum": ["ready"]},
                        "width": {"type": "integer", "minimum": 1},
                        "height": {"type": "integer", "minimum": 1},
                        "capture_latency_ms": {"type": "integer", "nullable": True, "minimum": 0},
                    },
                },
                "semantics": ["screen_capture_health"],
                "privacy": "device_health",
                "freshness_seconds": 30,
                "schema_version": 1,
            },
            {
                "name": "proxy.screen.change.v1",
                "schema": {
                    "type": "object",
                    "required": ["target_id", "surface_id", "profile_id", "profile_revision", "feature_version", "state", "evidence_ref"],
                    "properties": {
                        "target_id": {"type": "string"},
                        "surface_id": {"type": "string"},
                        "profile_id": {"type": "string"},
                        "profile_revision": {"type": "integer"},
                        "feature_version": {"type": "string", "enum": ["screen_change.v1"]},
                        "state": {"type": "string", "enum": ["changed", "unchanged"]},
                        "evidence_ref": {"type": "string"},
                        "evidence_id": {"type": "string", "maxLength": SCREEN_EVIDENCE_ID_MAX_LENGTH},
                    },
                },
                "semantics": ["screen_change", "candidate_event"],
                "privacy": "personal_screen",
                "freshness_seconds": 30,
                "schema_version": 1,
            },
            {
                "name": "proxy.screen.action_effect.v1",
                "schema": {
                    "type": "object",
                    "required": ["target_id", "surface_id", "profile_id", "profile_revision", "feature_version", "action_request_id", "state", "evidence_ref"],
                    "properties": {
                        "target_id": {"type": "string"},
                        "surface_id": {"type": "string"},
                        "profile_id": {"type": "string"},
                        "profile_revision": {"type": "integer"},
                        "feature_version": {"type": "string", "enum": ["action_effect.v1"]},
                        "action_request_id": {"type": "string"},
                        "state": {"type": "string", "enum": ["changed", "unchanged"]},
                        "evidence_ref": {"type": "string"},
                        "evidence_id": {"type": "string", "maxLength": SCREEN_EVIDENCE_ID_MAX_LENGTH},
                    },
                },
                "semantics": ["action_effect", "screen_change"],
                "privacy": "personal_screen",
                "freshness_seconds": 30,
                "schema_version": 1,
            },
        ],
    }


def _screen_profile_registration(attachment: ProxyTargetAttachment) -> dict:
    return {
        "name": SCREEN_PROFILE_CAPABILITY,
        "direction": "runtime_to_edge",
        "kind": "action",
        "affordances": ["confirm_screen_profile", "subscribe_screen_features"],
        "privacy": "personal_screen",
        "side_effect": "edge_configuration",
        "target_relationship": {
            "target_id": attachment.target_id,
            "surface_id": attachment.surface_id,
        },
        "input_schema": {
            "type": "object",
            "required": [
                "target_id",
                "surface_id",
                "profile_id",
                "revision",
                "features",
                "expires_at",
            ],
            "additionalProperties": False,
            "properties": {
                **_target_properties(attachment),
                "profile_id": {"type": "string", "maxLength": 96},
                "revision": {"type": "integer", "minimum": 1},
                "features": {"type": "array", "maxItems": 3},
                "expires_at": {"type": "string"},
                "valid_for_seconds": {"type": "integer", "minimum": 5, "maximum": 3600},
                "max_evidence_bytes": {"type": "integer", "minimum": 1, "maximum": 524288},
                "visual_action_policy": {"type": "string", "enum": ["require_understanding", "allow_safe"]},
            },
        },
    }


def _screen_read_registration(attachment: ProxyTargetAttachment) -> dict:
    return {
        "name": SCREEN_READ_CAPABILITY,
        "direction": "runtime_to_edge",
        "kind": "action",
        "affordances": ["read_latest_or_cached_bounded_screen"],
        "privacy": "personal_screen",
        "side_effect": "bounded_private_attachment",
        "target_relationship": {
            "target_id": attachment.target_id,
            "surface_id": attachment.surface_id,
        },
        "input_schema": {
            "type": "object",
            "required": ["target_id", "surface_id", "freshness", "max_bytes"],
            "additionalProperties": False,
            "properties": {
                **_target_properties(attachment),
                "freshness": {"type": "string", "enum": ["latest", "cached"]},
                "evidence_id": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": SCREEN_EVIDENCE_ID_MAX_LENGTH,
                },
                "max_bytes": {"type": "integer", "minimum": 1, "maximum": 98304},
            },
        },
    }


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
