import unittest

from personal_runtime.runtime_memory import build_model_grounding_bundle
from personal_runtime.runtime_state import RuntimeState


class RuntimeMemoryTests(unittest.TestCase):
    def test_build_model_grounding_bundle_projects_online_action_device_roster(self) -> None:
        state = RuntimeState()
        state.register_device(
            "android-edge-1",
            "android-phone",
            role="interactive_surface",
        )
        state.register_capability(
            "android-edge-1",
            {
                "name": "notification.show",
                "direction": "runtime_to_edge",
                "kind": "action",
                "affordances": ["notify_user", "deliver_private_text"],
                "modality": "visual_text",
                "privacy": "personal",
                "content_capacity": "short_text",
                "interruptiveness": "medium",
            },
        )
        state.register_capability(
            "android-edge-1",
            {
                "name": "mobile.context",
                "direction": "edge_to_runtime",
                "kind": "observation_provider",
            },
        )
        state.register_device("terminal-edge-1", "desktop-cli")
        state.register_capability(
            "terminal-edge-1",
            {
                "name": "notification.show",
                "direction": "runtime_to_edge",
                "kind": "action",
                "affordances": ["notify_user"],
                "modality": "visual_text",
                "privacy": "personal",
                "content_capacity": "short_text",
                "interruptiveness": "medium",
            },
        )

        grounding = build_model_grounding_bundle(
            state=state,
            snapshot={},
            online_device_ids={"android-edge-1", "terminal-edge-1"},
            request_source_device_id="terminal-edge-1",
        )

        self.assertEqual(
            grounding["device_roster"],
            {
                "request_source_device_id": "terminal-edge-1",
                "devices": [
                    {
                        "device_id": "android-edge-1",
                        "device_type": "android-phone",
                        "role": "interactive_surface",
                        "online": True,
                        "action_capabilities": [
                            {
                                "name": "notification.show",
                                "affordances": [
                                    "deliver_private_text",
                                    "notify_user",
                                ],
                                "modality": "visual_text",
                                "privacy": "personal",
                                "content_capacity": "short_text",
                                "interruptiveness": "medium",
                            }
                        ],
                    },
                    {
                        "device_id": "terminal-edge-1",
                        "device_type": "desktop-cli",
                        "role": None,
                        "online": True,
                        "action_capabilities": [
                            {
                                "name": "notification.show",
                                "affordances": ["notify_user"],
                                "modality": "visual_text",
                                "privacy": "personal",
                                "content_capacity": "short_text",
                                "interruptiveness": "medium",
                            }
                        ],
                    },
                ],
            },
        )

    def test_build_model_grounding_bundle_includes_snapshot_goals_and_recent_runtime_memory(
        self,
    ) -> None:
        state = RuntimeState()
        state.upsert_goal(
            goal_id="goal-1",
            title="Keep runtime healthy",
            status="active",
            summary="Watch health and notify on regressions.",
            updated_at="2026-06-22T10:00:00Z",
        )
        state.events.append(
            {
                "type": "event_push",
                "device_id": "terminal-edge-1",
                "capability": "text.input",
                "payload": {
                    "text": "hello runtime",
                    "observed_at": "2026-06-22T10:10:00Z",
                },
            }
        )
        state.record_intervention(
            {
                "target_device_id": "terminal-edge-1",
                "action_capability": "notification.show",
                "decision": "allow",
                "reason": "context_clear",
                "proposal": {
                    "source": "sense_first",
                    "action_capability": "notification.show",
                    "message": "hello runtime",
                },
                "recorded_at": "2026-06-22T10:10:01Z",
            }
        )
        state.record_action_result(
            {
                "status": "ok",
                "capability": "notification.show",
                "details": {
                    "title": "OpenHalo",
                    "body": "Runtime heard: hello runtime",
                },
            }
        )

        grounding = build_model_grounding_bundle(
            state=state,
            snapshot={"runtime.current_health_state": "healthy"},
            edge_history={
                "history_kind": "observation_window",
                "device_id": "host-edge-1",
                "entries": [
                    {
                        "capability": "runtime.health",
                        "observed_at": "2026-06-22T10:09:00Z",
                        "observations": [
                            {
                                "name": "runtime.health_state",
                                "value": "healthy",
                                "confidence": 1.0,
                            }
                        ],
                    }
                ],
                "returned_entries": 1,
                "available_entries": 3,
            },
        )

        self.assertEqual(grounding["bundle_version"], "m10.v1")
        self.assertEqual(
            grounding["snapshot"]["runtime.current_health_state"], "healthy"
        )
        self.assertEqual(len(grounding["active_goals"]), 1)
        self.assertEqual(grounding["active_goals"][0]["goal_id"], "goal-1")
        self.assertEqual(len(grounding["recent_memory"]["user_inputs"]), 1)
        self.assertEqual(
            grounding["recent_memory"]["user_inputs"][0]["text"], "hello runtime"
        )
        self.assertEqual(len(grounding["recent_memory"]["interventions"]), 1)
        self.assertEqual(len(grounding["recent_memory"]["action_results"]), 1)
        self.assertEqual(grounding["edge_history"]["device_id"], "host-edge-1")
        self.assertEqual(grounding["edge_history"]["returned_entries"], 1)

    def test_build_model_grounding_bundle_is_bounded(self) -> None:
        state = RuntimeState()
        state.upsert_goal(
            goal_id="goal-1",
            title="Goal 1",
            status="active",
            summary="active",
            updated_at="2026-06-22T10:00:00Z",
        )
        state.upsert_goal(
            goal_id="goal-2",
            title="Goal 2",
            status="active",
            summary="active",
            updated_at="2026-06-22T10:01:00Z",
        )
        state.upsert_goal(
            goal_id="goal-3",
            title="Goal 3",
            status="done",
            summary="completed",
            updated_at="2026-06-22T10:02:00Z",
        )
        for index in range(5):
            state.events.append(
                {
                    "type": "event_push",
                    "device_id": "terminal-edge-1",
                    "capability": "text.input",
                    "payload": {
                        "text": f"message {index}",
                        "observed_at": f"2026-06-22T10:1{index}:00Z",
                    },
                }
            )
            state.record_intervention(
                {
                    "target_device_id": "terminal-edge-1",
                    "action_capability": "notification.show",
                    "decision": "allow",
                    "reason": "context_clear",
                    "proposal": {
                        "source": "sense_first",
                        "action_capability": "notification.show",
                        "message": f"message {index}",
                    },
                    "recorded_at": f"2026-06-22T10:1{index}:10Z",
                }
            )
            state.record_action_result(
                {
                    "status": "ok",
                    "capability": "notification.show",
                    "details": {
                        "title": "OpenHalo",
                        "body": f"reply {index}",
                    },
                }
            )

        grounding = build_model_grounding_bundle(
            state=state,
            snapshot={"runtime.current_health_state": "healthy"},
        )

        self.assertEqual(len(grounding["active_goals"]), 2)
        self.assertEqual(len(grounding["recent_memory"]["user_inputs"]), 3)
        self.assertEqual(len(grounding["recent_memory"]["interventions"]), 3)
        self.assertEqual(len(grounding["recent_memory"]["action_results"]), 3)
        self.assertEqual(
            [item["text"] for item in grounding["recent_memory"]["user_inputs"]],
            ["message 2", "message 3", "message 4"],
        )


if __name__ == "__main__":
    unittest.main()
