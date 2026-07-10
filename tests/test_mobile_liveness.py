import unittest

from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.mobile_liveness import build_mobile_liveness_view
from personal_runtime.mobile_liveness import evaluate_mobile_liveness_recovery
from personal_runtime.mobile_liveness import record_mobile_session_state
from personal_runtime.mobile_liveness import request_mobile_wake_recovery
from personal_runtime.mobile_liveness import update_mobile_liveness_after_observations
from personal_runtime.runtime_state import RuntimeState


class MobileObservationLivenessTests(unittest.TestCase):
    def test_classifies_recent_mobile_screen_context_as_fresh(self) -> None:
        state = RuntimeState()
        _register_phone(state)
        state.record_observation(
            RuntimeObservation(
                name="mobile.screen_context",
                value={"screen_kind": "launcher"},
                source_device_id="android-edge-1",
                source_capability="mobile.screen_context",
                source_event_id="event-1",
                observed_at="2026-07-10T10:00:00Z",
                confidence=0.9,
            )
        )

        view = build_mobile_liveness_view(
            state,
            online_device_ids={"android-edge-1"},
            current_time="2026-07-10T10:00:20Z",
        )

        self.assertEqual(view["android-edge-1"]["state"], "fresh")
        self.assertEqual(
            view["android-edge-1"]["last_screen_context_at"],
            "2026-07-10T10:00:00Z",
        )
        self.assertTrue(view["android-edge-1"]["expected_active_observation"])

    def test_classifies_expected_active_phone_silence_as_degraded(self) -> None:
        state = RuntimeState()
        _register_phone(state)
        state.record_observation(
            RuntimeObservation(
                name="mobile.screen_capture_health",
                value={
                    "accessibility_service_state": "enabled",
                    "capture_mode": "accessibility_tree",
                    "capture_pause_reason": "none",
                },
                source_device_id="android-edge-1",
                source_capability="mobile.screen_context",
                source_event_id="event-2",
                observed_at="2026-07-10T10:00:00Z",
                confidence=1.0,
            )
        )
        state.record_observation(
            RuntimeObservation(
                name="mobile.screen_context",
                value={"screen_kind": "launcher"},
                source_device_id="android-edge-1",
                source_capability="mobile.screen_context",
                source_event_id="event-3",
                observed_at="2026-07-10T10:00:00Z",
                confidence=0.9,
            )
        )

        view = build_mobile_liveness_view(
            state,
            online_device_ids={"android-edge-1"},
            current_time="2026-07-10T10:03:10Z",
        )

        self.assertEqual(view["android-edge-1"]["state"], "degraded")
        self.assertEqual(view["android-edge-1"]["silence_seconds"], 190)
        self.assertFalse(view["android-edge-1"]["wake_recovery_eligible"])

    def test_requests_bounded_privacy_preserving_wake_for_offline_stale_phone(self) -> None:
        state = RuntimeState()
        _register_phone(state)
        state.record_observation(
            RuntimeObservation(
                name="mobile.screen_capture_health",
                value={
                    "accessibility_service_state": "enabled",
                    "capture_mode": "accessibility_tree",
                    "capture_pause_reason": "none",
                },
                source_device_id="android-edge-1",
                source_capability="mobile.screen_context",
                source_event_id="event-4",
                observed_at="2026-07-10T10:00:00Z",
                confidence=1.0,
            )
        )
        state.record_observation(
            RuntimeObservation(
                name="mobile.screen_context",
                value={"visible_text_summary": "private text must not leave runtime"},
                source_device_id="android-edge-1",
                source_capability="mobile.screen_context",
                source_event_id="event-5",
                observed_at="2026-07-10T10:00:00Z",
                confidence=0.9,
            )
        )

        request = request_mobile_wake_recovery(
            state,
            device_id="android-edge-1",
            current_time="2026-07-10T10:06:00Z",
            online_device_ids=set(),
            configured=True,
        )
        view = build_mobile_liveness_view(
            state,
            online_device_ids=set(),
            current_time="2026-07-10T10:06:00Z",
        )

        self.assertEqual(request["state"], "wake_requested")
        self.assertEqual(request["ttl_seconds"], 120)
        self.assertEqual(request["dispatch_status"], "audit_only")
        self.assertEqual(request["payload"], {"reason": "mobile_observation_recovery"})
        self.assertNotIn("private text", str(request))
        self.assertEqual(view["android-edge-1"]["state"], "wake_requested")
        self.assertEqual(
            view["android-edge-1"]["last_recovery_attempt"]["attempt_id"],
            request["attempt_id"],
        )

    def test_rate_limits_repeated_wake_requests(self) -> None:
        state = RuntimeState()
        _register_phone(state)
        state.mobile_liveness["android-edge-1"] = {
            "last_recovery_attempt": {
                "attempt_id": "wake-android-edge-1-20260710T100600Z",
                "requested_at": "2026-07-10T10:06:00Z",
                "ttl_seconds": 120,
                "payload": {"reason": "mobile_observation_recovery"},
            }
        }

        request = request_mobile_wake_recovery(
            state,
            device_id="android-edge-1",
            current_time="2026-07-10T10:06:30Z",
            online_device_ids=set(),
            configured=True,
        )

        self.assertEqual(request["state"], "rate_limited")
        self.assertEqual(request["last_recovery_attempt"]["attempt_id"], "wake-android-edge-1-20260710T100600Z")

    def test_suppresses_wake_during_recent_server_or_network_failure(self) -> None:
        state = RuntimeState()
        _register_phone(state)
        _record_expected_active_screen(state, observed_at="2026-07-10T10:00:00Z")
        state.register_device("host-edge-1", "host")
        state.record_observation(
            RuntimeObservation(
                name="runtime.health_state",
                value="degraded",
                source_device_id="host-edge-1",
                source_capability="runtime.health",
                source_event_id="event-runtime",
                observed_at="2026-07-10T10:05:30Z",
                confidence=1.0,
            )
        )

        request = request_mobile_wake_recovery(
            state,
            device_id="android-edge-1",
            current_time="2026-07-10T10:06:00Z",
            online_device_ids=set(),
            configured=True,
        )
        view = build_mobile_liveness_view(
            state,
            online_device_ids=set(),
            current_time="2026-07-10T10:06:00Z",
        )

        self.assertEqual(request["state"], "suppressed")
        self.assertEqual(request["reason"], "server_or_network_unhealthy")
        self.assertFalse(view["android-edge-1"]["wake_recovery_eligible"])

    def test_records_recovery_provenance_after_fresh_reconnect(self) -> None:
        state = RuntimeState()
        _register_phone(state)
        state.mobile_liveness["android-edge-1"] = {
            "last_recovery_attempt": {
                "attempt_id": "wake-android-edge-1-20260710T100600Z",
                "requested_at": "2026-07-10T10:06:00Z",
                "ttl_seconds": 120,
                "payload": {"reason": "mobile_observation_recovery"},
            }
        }
        state.record_observation(
            RuntimeObservation(
                name="mobile.screen_capture_health",
                value={
                    "accessibility_service_state": "enabled",
                    "capture_pause_reason": "none",
                    "recovery_provenance": "websocket_reconnect",
                },
                source_device_id="android-edge-1",
                source_capability="mobile.screen_context",
                source_event_id="event-health",
                observed_at="2026-07-10T10:06:20Z",
                confidence=1.0,
            )
        )
        state.record_observation(
            RuntimeObservation(
                name="mobile.screen_context",
                value={"screen_kind": "launcher"},
                source_device_id="android-edge-1",
                source_capability="mobile.screen_context",
                source_event_id="event-screen",
                observed_at="2026-07-10T10:06:20Z",
                confidence=0.9,
            )
        )

        view = update_mobile_liveness_after_observations(
            state,
            device_id="android-edge-1",
            online_device_ids={"android-edge-1"},
            current_time="2026-07-10T10:06:25Z",
        )

        self.assertEqual(view["state"], "fresh")
        recovery = state.mobile_liveness["android-edge-1"]["last_recovery_attempt"][
            "recovery"
        ]
        self.assertEqual(recovery["status"], "recovered")
        self.assertEqual(recovery["recovered_at"], "2026-07-10T10:06:20Z")

    def test_stale_buffered_replay_does_not_restore_freshness_after_wake(self) -> None:
        state = RuntimeState()
        _register_phone(state)
        state.mobile_liveness["android-edge-1"] = {
            "last_recovery_attempt": {
                "attempt_id": "wake-android-edge-1-20260710T100600Z",
                "requested_at": "2026-07-10T10:06:00Z",
                "ttl_seconds": 120,
                "payload": {"reason": "mobile_observation_recovery"},
            }
        }
        _record_expected_active_screen(state, observed_at="2026-07-10T10:05:30Z")

        view = update_mobile_liveness_after_observations(
            state,
            device_id="android-edge-1",
            online_device_ids={"android-edge-1"},
            current_time="2026-07-10T10:06:20Z",
        )

        self.assertEqual(view["state"], "stale")
        self.assertTrue(view["stale_buffered_replay"])
        recovery = state.mobile_liveness["android-edge-1"]["last_recovery_attempt"][
            "recovery"
        ]
        self.assertEqual(recovery["status"], "stale_replay_ignored")

    def test_records_mobile_session_state_for_registered_phone(self) -> None:
        state = RuntimeState()
        _register_phone(state)

        record_mobile_session_state(
            state,
            "android-edge-1",
            status="disconnected",
            observed_at="2026-07-10T10:07:00Z",
        )

        self.assertEqual(
            state.mobile_liveness["android-edge-1"]["last_session"]["status"],
            "disconnected",
        )

    def test_watchdog_evaluation_triggers_configured_wake_transport(self) -> None:
        state = RuntimeState()
        _register_phone(state)
        _record_expected_active_screen(state, observed_at="2026-07-10T10:00:00Z")
        sent_payloads = []

        def wake_transport(payload: dict) -> dict:
            sent_payloads.append(payload)
            return {
                "status": "sent",
                "provider_message_id": "push-1",
                "visible_text_summary": "must not be persisted",
            }

        result = evaluate_mobile_liveness_recovery(
            state,
            current_time="2026-07-10T10:06:00Z",
            online_device_ids=set(),
            configured_device_ids={"android-edge-1"},
            wake_transports={"android-edge-1": wake_transport},
        )

        attempt = result["recovery_attempts"]["android-edge-1"]
        self.assertEqual(attempt["state"], "wake_requested")
        self.assertEqual(attempt["dispatch_status"], "sent")
        self.assertEqual(sent_payloads, [{"reason": "mobile_observation_recovery"}])
        self.assertNotIn("visible_text_summary", str(attempt))
        self.assertEqual(
            result["mobile_liveness"]["android-edge-1"]["state"],
            "wake_requested",
        )


def _register_phone(state: RuntimeState) -> None:
    state.register_device(
        "android-edge-1",
        "android-phone",
        role="interactive_surface",
    )
    state.register_capability(
        "android-edge-1",
        {
            "name": "mobile.screen_context",
            "direction": "edge_to_runtime",
            "kind": "observation_provider",
            "observations": [
                {
                    "name": "mobile.screen_context",
                    "schema": {"type": "object"},
                    "freshness_seconds": 30,
                },
                {
                    "name": "mobile.screen_capture_health",
                    "schema": {"type": "object"},
                    "freshness_seconds": 60,
                },
            ],
        },
    )


def _record_expected_active_screen(state: RuntimeState, observed_at: str) -> None:
    state.record_observation(
        RuntimeObservation(
            name="mobile.screen_capture_health",
            value={
                "accessibility_service_state": "enabled",
                "capture_mode": "accessibility_tree",
                "capture_pause_reason": "none",
            },
            source_device_id="android-edge-1",
            source_capability="mobile.screen_context",
            source_event_id=f"health-{observed_at}",
            observed_at=observed_at,
            confidence=1.0,
        )
    )
    state.record_observation(
        RuntimeObservation(
            name="mobile.screen_context",
            value={"screen_kind": "launcher"},
            source_device_id="android-edge-1",
            source_capability="mobile.screen_context",
            source_event_id=f"screen-{observed_at}",
            observed_at=observed_at,
            confidence=0.9,
        )
    )


if __name__ == "__main__":
    unittest.main()
