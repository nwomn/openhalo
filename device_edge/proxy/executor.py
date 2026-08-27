"""Governed Proxy Interaction Edge action execution."""

from device_edge.proxy.adapter import ProxyAdapterError
from device_edge.proxy.contracts import KEYBOARD_CAPABILITY
from device_edge.proxy.contracts import POINTER_CAPABILITY
from edge_api.protocol import with_api_version


class ProxyActionExecutor:
    def __init__(self, device_id: str, attachment, adapter) -> None:
        self.device_id = device_id
        self.attachment = attachment
        self.adapter = adapter

    def handle_action_request(self, frame: dict) -> dict:
        action = frame.get("action", {})
        capability = action.get("capability")
        payload = action.get("payload", {})
        result = self._execute(frame, capability, payload)
        response = with_api_version(
            {
                "type": "action_result",
                "device_id": self.device_id,
                "result": result,
            }
        )
        for key in (
            "request_id",
            "interaction_id",
            "interaction_turn_id",
            "trace_id",
            "session_id",
            "turn_id",
            "event_id",
            "parent_event_id",
        ):
            if frame.get(key) is not None:
                response[key] = frame[key]
        return response

    def _execute(self, frame: dict, capability: object, payload: object) -> dict:
        if frame.get("device_id") != self.device_id:
            return self._error(capability, "device_mismatch")
        if not isinstance(payload, dict):
            return self._error(capability, "invalid_action_payload")
        if payload.get("target_id") != self.attachment.target_id:
            return self._error(capability, "target_mismatch")
        if payload.get("surface_id") != self.attachment.surface_id:
            return self._error(capability, "surface_mismatch")
        if self.attachment.attachment_state in {"detached", "incompatible"}:
            return self._error(capability, f"target_{self.attachment.attachment_state}")

        if capability == KEYBOARD_CAPABILITY:
            facet = "keyboard"
            execute = self.adapter.execute_keyboard
        elif capability == POINTER_CAPABILITY:
            facet = "pointer"
            execute = self.adapter.execute_pointer
        else:
            return self._error(capability, "unsupported_proxy_capability")

        availability = self.attachment.capability_state(facet)
        if availability.state == "unavailable":
            return self._error(capability, availability.reason or "capability_unavailable")
        try:
            details = execute(payload)
        except ProxyAdapterError as exc:
            return self._error(capability, str(exc))
        except Exception:
            return self._error(capability, "adapter_execution_failed")
        return {
            "status": "ok",
            "capability": capability,
            "observed_at": self.attachment.observed_at,
            "details": {
                "target_id": self.attachment.target_id,
                "surface_id": self.attachment.surface_id,
                "adapter_result": details,
            },
        }

    @staticmethod
    def _error(capability: object, reason: str) -> dict:
        return {
            "status": "error",
            "capability": capability if isinstance(capability, str) else "unknown",
            "reason": reason,
        }
