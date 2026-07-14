"""Local edge action execution and action-result diagnostics."""

from device_edge.shared.local_actions import execute_action
from edge_api.protocol import with_api_version
from openhalo_common.diagnostics import DiagnosticBoundaryRecorder
from openhalo_common.diagnostics import correlation_from_frame


class LocalActionExecutor:
    def __init__(
        self,
        device_id: str,
        device_type: str,
        diagnostic_recorder=None,
        trace_recorder=None,
    ) -> None:
        self.device_id = device_id
        self.trace_recorder = trace_recorder
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

    def handle_action_request(self, frame: dict) -> dict:
        correlation = correlation_from_frame(frame)
        with self.diagnostics.boundary(
            module="Local Action Executor",
            operation="execute_action",
            correlation=correlation,
            input_payload={"action": frame["action"]},
            summary="Executed local action request.",
        ) as boundary:
            result = execute_action(frame["action"])
            if self.trace_recorder is not None:
                capability = frame["action"]["capability"]
                self.trace_recorder.record(
                    "EDGE",
                    f"executed {capability}",
                    status=result["status"],
                )
            action_result = with_api_version(
                {
                    "type": "action_result",
                    "device_id": self.device_id,
                    "result": result,
                }
            )
            if frame.get("request_id"):
                action_result["request_id"] = frame["request_id"]
            if frame.get("interaction_id"):
                action_result["interaction_id"] = frame["interaction_id"]
            if frame.get("interaction_turn_id"):
                action_result["interaction_turn_id"] = frame["interaction_turn_id"]
            for key in (
                "trace_id",
                "session_id",
                "turn_id",
                "event_id",
                "parent_event_id",
            ):
                if frame.get(key) is not None:
                    action_result[key] = frame[key]
            boundary.output({"result": result, "frame": action_result})
            return action_result
