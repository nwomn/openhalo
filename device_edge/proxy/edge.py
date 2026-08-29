"""Proxy Interaction Edge composition over the normal public Edge Session Link."""

from device_edge.proxy.contracts import OBSERVATION_CAPABILITY
from device_edge.proxy.contracts import ProxyTargetAttachment
from device_edge.proxy.contracts import build_proxy_capability_registrations
from device_edge.proxy.contracts import unavailable_capabilities
from device_edge.proxy.executor import ProxyActionExecutor
from device_edge.proxy.adapter import ProxyAdapterError
from device_edge.proxy.screen_governance import SCREEN_FEATURE_CAPABILITY
from device_edge.proxy.screen_governance import ProxyScreenGovernance
from device_edge.shared.session_client import SessionClient


class ProxyInteractionEdge:
    def __init__(
        self,
        device_id: str,
        audience: str,
        target_id: str,
        surface_id: str,
        target_class: str,
        adapter,
        observed_at: str,
        identity=None,
        display_name: str | None = None,
        native_device_id: str | None = None,
    ) -> None:
        self.device_id = device_id
        self.adapter = adapter
        self.target_id = target_id
        self.surface_id = surface_id
        self.target_class = target_class
        self.native_device_id = native_device_id
        self.attachment = self._build_attachment(observed_at)
        self.screen_governance = ProxyScreenGovernance()
        self.action_executor = ProxyActionExecutor(
            device_id,
            self.attachment,
            adapter,
            screen_governance=self.screen_governance,
        )
        self.client = SessionClient(
            device_id=device_id,
            device_type="proxy-interaction",
            audience=audience,
            identity=identity,
            display_name=display_name,
            capabilities=build_proxy_capability_registrations(self.attachment),
            action_executor=self.action_executor,
        )

    def _build_attachment(self, observed_at: str) -> ProxyTargetAttachment:
        compatible = self.target_class in self.adapter.supported_target_classes
        if not compatible:
            capabilities = unavailable_capabilities("incompatible_target_class")
            attachment_state = "incompatible"
        else:
            try:
                probe = self.adapter.probe()
                capabilities = probe.capabilities
            except ProxyAdapterError as exc:
                capabilities = unavailable_capabilities(str(exc))
            required_states = [
                capabilities[name].state for name in ("screen", "keyboard", "pointer")
            ]
            if all(state == "unavailable" for state in required_states):
                attachment_state = "detached"
            elif any(state != "available" for state in required_states):
                attachment_state = "degraded"
            else:
                attachment_state = "attached"
        return ProxyTargetAttachment(
            target_id=self.target_id,
            surface_id=self.surface_id,
            target_class=self.target_class,
            attachment_state=attachment_state,
            capabilities=capabilities,
            observed_at=observed_at,
            adapter_id=self.adapter.adapter_id,
            adapter_kind=self.adapter.adapter_kind,
            requirements=tuple(self.adapter.requirements),
            native_device_id=self.native_device_id,
        )

    def refresh_attachment(self, observed_at: str) -> ProxyTargetAttachment:
        """Re-probe the adapter and make its current safe state authoritative."""

        self.attachment = self._build_attachment(observed_at)
        self.action_executor.attachment = self.attachment
        self.client.capability_runtime.capabilities = build_proxy_capability_registrations(
            self.attachment
        )
        return self.attachment

    def build_connect_frame(self) -> dict:
        return self.client.build_connect_frame()

    def build_capability_announce_frame(self) -> dict:
        return self.client.build_capability_announce_frame()

    def build_attachment_observation_frame(self) -> dict:
        return self.client.build_observation_event(
            OBSERVATION_CAPABILITY,
            [self.attachment.to_observation()],
        )

    def build_screen_observation_frame(
        self,
        *,
        action_request_id: str | None = None,
    ) -> dict:
        availability = self.attachment.capability_state("screen")
        if availability.state == "unavailable":
            raise ValueError(availability.reason or "screen_unavailable")
        frame = self.adapter.capture_frame()
        observation = frame.to_observation(self.attachment)
        if action_request_id is not None:
            observation["value"]["action_request_id"] = action_request_id
        return self.client.build_observation_event(
            OBSERVATION_CAPABILITY,
            [observation],
        )

    def build_screen_feature_observation_frame(
        self,
        *,
        action_request_id: str | None = None,
    ) -> dict | None:
        """Capture only when an active Runtime Screen Profile has subscribed."""

        availability = self.attachment.capability_state("screen")
        if availability.state == "unavailable" or not self.screen_governance.has_active_profile():
            return None
        frame = self.adapter.capture_frame()
        observations = self.screen_governance.observe(
            frame,
            self.attachment,
            action_request_id=action_request_id,
        )
        if not observations:
            return None
        return self.client.build_observation_event(SCREEN_FEATURE_CAPABILITY, observations)

    def drain_evidence_transfers(self) -> list[dict]:
        return self.action_executor.drain_evidence_transfers()

    def handle_understanding_update(self, frame: dict) -> None:
        self.screen_governance.accept_understanding_update(frame, self.attachment)

    def handle_action_request(self, frame: dict) -> dict:
        return self.client.handle_action_request(frame)
