"""Governed Proxy Interaction Edge action execution."""

from device_edge.proxy.adapter import ProxyAdapterError
from device_edge.proxy.contracts import KEYBOARD_CAPABILITY
from device_edge.proxy.contracts import POINTER_CAPABILITY
from device_edge.proxy.contracts import SCREEN_EVIDENCE_CAPABILITY
from device_edge.proxy.contracts import SCREEN_PROFILE_CAPABILITY
from edge_api.protocol import with_api_version


class ProxyActionExecutor:
    def __init__(self, device_id: str, attachment, adapter, screen_governance=None) -> None:
        self.device_id = device_id
        self.attachment = attachment
        self.adapter = adapter
        self.screen_governance = screen_governance
        self._pending_evidence_transfers = []

    def drain_evidence_transfers(self) -> list[dict]:
        transfers = self._pending_evidence_transfers
        self._pending_evidence_transfers = []
        return transfers

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
        if capability == SCREEN_PROFILE_CAPABILITY:
            if self.screen_governance is None:
                return self._error(capability, "screen_governance_unavailable")
            try:
                profile = self.screen_governance.configure(payload, self.attachment)
            except ValueError as exc:
                return self._error(capability, str(exc))
            return {
                "status": "ok",
                "capability": capability,
                "observed_at": self.attachment.observed_at,
                "details": {
                    "target_id": self.attachment.target_id,
                    "surface_id": self.attachment.surface_id,
                    "profile_id": profile.profile_id,
                    "revision": profile.revision,
                    "features": list(profile.features),
                    "expires_at": profile.expires_at,
                    "visual_action_policy": profile.visual_action_policy,
                },
            }

        if self.attachment.attachment_state in {"detached", "incompatible"}:
            return self._error(capability, f"target_{self.attachment.attachment_state}")

        if capability == SCREEN_EVIDENCE_CAPABILITY:
            if self.screen_governance is None:
                return self._error(capability, "screen_governance_unavailable")
            request_id = frame.get("request_id")
            if not isinstance(request_id, str) or not request_id:
                return self._error(capability, "missing_request_id")
            try:
                transfer = self.screen_governance.prepare_evidence_transfer(
                    device_id=self.device_id,
                    request_id=request_id,
                    payload=payload,
                    adapter=self.adapter,
                    attachment=self.attachment,
                )
            except (ProxyAdapterError, ValueError) as exc:
                return self._error(capability, str(exc))
            self._pending_evidence_transfers.append(transfer.payload)
            return {
                "status": "ok",
                "capability": capability,
                "observed_at": self.attachment.observed_at,
                "details": {
                    "transfer_id": transfer.transfer_id,
                    "evidence_ref": payload["evidence_ref"],
                    "understanding_state": "pending_understanding",
                },
            }

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
        if self.screen_governance is not None:
            visual_error = self.screen_governance.validate_hid_action(payload)
            if visual_error is not None:
                return self._error(capability, visual_error)
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
