"""Minimal capability registry shared across edge surfaces."""

from openhalo_common.diagnostics import DiagnosticBoundaryRecorder


class CapabilityRuntime:
    def __init__(
        self,
        capabilities: list[str] | None = None,
        diagnostic_recorder=None,
        device: dict | None = None,
    ) -> None:
        self.capabilities = capabilities or ["text.input", "notification.show"]
        self.diagnostics = DiagnosticBoundaryRecorder(
            recorder=diagnostic_recorder,
            side="edge",
            device=device,
        )

    def normalize_user_input(
        self,
        text: str,
        correlation: dict | None = None,
    ) -> dict:
        with self.diagnostics.boundary(
            module="Local Capability Runtime",
            operation="normalize_user_input",
            correlation=correlation or {},
            input_payload={"text": text},
            summary="Normalized text input into text.input event.",
        ) as boundary:
            normalized = {
                "capability": "text.input",
                "payload": {"text": text},
            }
            boundary.output(
                {
                    "capability": normalized["capability"],
                    "payload_keys": list(normalized["payload"].keys()),
                }
            )
            return normalized

    def normalize_observations(
        self,
        capability: str,
        observations: list[dict],
        correlation: dict | None = None,
    ) -> dict:
        with self.diagnostics.boundary(
            module="Local Capability Runtime",
            operation="normalize_observations",
            correlation=correlation or {},
            input_payload={"capability": capability, "observations": observations},
            summary="Normalized observations into observation_push frame.",
        ) as boundary:
            normalized = {
                "capability": capability,
                "observations": observations,
            }
            boundary.output(
                {
                    "capability": capability,
                    "observation_count": len(observations),
                }
            )
            return normalized
