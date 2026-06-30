"""Edge API frame construction and session-link diagnostics."""

from edge_api.protocol import build_capability_announce_frame
from edge_api.protocol import build_connect_frame
from edge_api.protocol import build_event_push_frame
from edge_api.protocol import build_observation_push_frame
from openhalo_common.diagnostics import DiagnosticBoundaryRecorder
from openhalo_common.diagnostics import build_session_id


class EdgeSessionLink:
    def __init__(
        self,
        device_id: str,
        device_type: str,
        token: str,
        diagnostic_recorder=None,
    ) -> None:
        self.device_id = device_id
        self.device_type = device_type
        self.token = token
        self.session_id = build_session_id(device_id)
        self.device = {
            "device_id": device_id,
            "device_name": device_id,
            "device_type": device_type,
        }
        self.diagnostics = DiagnosticBoundaryRecorder(
            recorder=diagnostic_recorder,
            side="edge",
            device=self.device,
        )

    def build_connect_frame(self) -> dict:
        return build_connect_frame(
            self.device_id,
            self.device_type,
            self.token,
            session_id=self.session_id,
        )

    def build_capability_announce_frame(self, capabilities: list[str]) -> dict:
        return build_capability_announce_frame(
            self.device_id,
            capabilities,
            session_id=self.session_id,
        )

    def build_event_frame(
        self,
        capability: str,
        payload: dict,
        correlation: dict,
        summary: str = "Prepared event_push frame for runtime.",
    ) -> dict:
        with self.diagnostics.boundary(
            module="Edge Session Link",
            operation="send_frame",
            correlation=correlation,
            input_payload={"capability": capability},
            summary=summary,
        ) as boundary:
            frame = build_event_push_frame(
                device_id=self.device_id,
                capability=capability,
                payload=payload,
                **correlation,
            )
            boundary.output(frame)
            return frame

    def build_observation_frame(
        self,
        capability: str,
        observations: list[dict],
        correlation: dict,
    ) -> dict:
        with self.diagnostics.boundary(
            module="Edge Session Link",
            operation="send_frame",
            correlation=correlation,
            input_payload={"capability": capability},
            summary="Prepared observation_push frame for runtime.",
        ) as boundary:
            frame = build_observation_push_frame(
                device_id=self.device_id,
                capability=capability,
                observations=observations,
                **correlation,
            )
            boundary.output(frame)
            return frame
