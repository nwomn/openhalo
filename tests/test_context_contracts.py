import unittest

from personal_runtime.context_contracts import CapabilityContract
from personal_runtime.context_contracts import DeviceContract
from personal_runtime.context_contracts import RuntimeObservation


class ContextContractTests(unittest.TestCase):
    def test_device_contract_captures_identity_role_profile_and_capabilities(self) -> None:
        contract = DeviceContract(
            device_id="phone-1",
            device_type="phone",
            role="personal_mobile",
            profile="mobile_interactive",
            capabilities=["notification", "location"],
        )

        self.assertEqual(contract.device_id, "phone-1")
        self.assertEqual(contract.role, "personal_mobile")
        self.assertEqual(contract.profile, "mobile_interactive")
        self.assertEqual(contract.capabilities, ["notification", "location"])

    def test_capability_contract_tracks_observations_and_actions(self) -> None:
        contract = CapabilityContract(
            name="notification",
            observations=["interaction.notification_result"],
            actions=["notification.show"],
        )

        self.assertEqual(contract.name, "notification")
        self.assertEqual(
            contract.observations,
            ["interaction.notification_result"],
        )
        self.assertEqual(contract.actions, ["notification.show"])

    def test_runtime_observation_carries_normalized_value_and_provenance(self) -> None:
        observation = RuntimeObservation(
            name="user.activity_mode",
            value="desk_work",
            source_device_id="host-1",
            source_capability="desktop_context",
            source_event_id="evt-123",
            observed_at="2026-06-18T10:30:00Z",
            confidence=0.82,
        )

        self.assertEqual(observation.name, "user.activity_mode")
        self.assertEqual(observation.value, "desk_work")
        self.assertEqual(observation.source_device_id, "host-1")
        self.assertEqual(observation.source_capability, "desktop_context")
        self.assertEqual(observation.source_event_id, "evt-123")
        self.assertEqual(observation.observed_at, "2026-06-18T10:30:00Z")
        self.assertEqual(observation.confidence, 0.82)


if __name__ == "__main__":
    unittest.main()
