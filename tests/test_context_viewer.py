import json
import tempfile
import unittest
from pathlib import Path

from personal_runtime.context_contracts import RuntimeObservation
from personal_runtime.context_viewer import build_context_view
from personal_runtime.context_viewer import load_diagnostic_events
from personal_runtime.context_viewer import render_context_view
from personal_runtime.runtime_state import RuntimeState
from personal_runtime.state_store import JsonStateStore


class ContextViewerTests(unittest.TestCase):
    def test_builds_view_with_latest_observations_and_snapshot_evidence(self) -> None:
        state = RuntimeState()
        state.register_device("terminal-edge-1", "terminal")
        state.register_capability("terminal-edge-1", "terminal.context")
        state.events.append(
            {
                "type": "event_push",
                "device_id": "terminal-edge-1",
                "capability": "terminal.context",
                "payload": {
                    "observations": [
                        {
                            "name": "terminal.activity_state",
                            "value": "active",
                        }
                    ]
                },
            }
        )
        state.record_observation(
            RuntimeObservation(
                name="terminal.activity_state",
                value="active",
                source_device_id="terminal-edge-1",
                source_capability="terminal.context",
                source_event_id="event-1",
                observed_at="2026-07-05T14:40:00Z",
                confidence=1.0,
            )
        )

        view = build_context_view(
            state.to_dict(),
            current_time="2026-07-05T14:40:30Z",
        )

        self.assertEqual(view["counts"]["observations"], 1)
        self.assertEqual(
            view["current_snapshot"]["terminal.current_activity_state"],
            "active",
        )
        latest = view["latest_observations"][-1]
        self.assertTrue(latest["in_current_snapshot_evidence"])
        self.assertEqual(
            latest["snapshot_fields"],
            ["terminal.current_activity_state"],
        )

    def test_marks_mobile_screen_context_as_stored_but_not_snapshot_evidence(self) -> None:
        state = RuntimeState()
        state.register_device("android-edge-1", "android-phone")
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
                    }
                ],
            },
        )
        state.record_observation(
            RuntimeObservation(
                name="mobile.screen_context",
                value={
                    "trigger": "accessibility_event",
                    "event_kind": "view_clicked",
                    "source": "accessibility",
                    "screen_state": "unlocked",
                    "capture_mode": "accessibility_tree",
                    "screen_kind": "conversation_or_feed",
                    "visible_text_summary": "Chat with reply box.",
                    "sensitivity": "normal",
                    "raw_screenshot_uploaded": False,
                },
                source_device_id="android-edge-1",
                source_capability="mobile.screen_context",
                source_event_id="event-2",
                observed_at="2026-07-05T14:41:00Z",
                confidence=0.76,
            )
        )

        view = build_context_view(
            state.to_dict(),
            current_time="2026-07-05T14:41:30Z",
            online_device_ids={"android-edge-1"},
        )
        latest = view["latest_observations"][-1]

        self.assertEqual(latest["name"], "mobile.screen_context")
        self.assertFalse(latest["in_current_snapshot_evidence"])
        self.assertEqual(latest["snapshot_fields"], [])
        self.assertEqual(
            view["mobile_liveness"]["android-edge-1"]["state"],
            "fresh",
        )
        self.assertTrue(view["mobile_liveness"]["android-edge-1"]["online"])

    def test_includes_latest_agent_prompt_context_from_intervention(self) -> None:
        state = RuntimeState()
        state.record_intervention(
            {
                "interaction_id": "interaction-1",
                "proposal": {
                    "proposal_type": "action",
                    "source": "normal",
                    "message": "hello runtime",
                },
                "decision": "allow",
                "reason": "source edge is active",
                "target_device_id": "terminal-edge-1",
                "snapshot_contract": {
                    "snapshot_time": "2026-07-05T14:42:00Z",
                    "fields": {
                        "terminal.current_activity_state": {
                            "observation_name": "terminal.activity_state",
                            "value": "active",
                            "status": "fresh",
                            "evidence": [],
                        }
                    },
                },
                "grounding_bundle": {
                    "bundle_version": "m10.v1",
                    "active_goals": [{"goal_id": "goal-1"}],
                    "recent_memory": {"observations": []},
                    "edge_history": {"returned_entries": 0},
                },
            }
        )

        view = build_context_view(
            state.to_dict(),
            current_time="2026-07-05T14:42:30Z",
        )
        prompt_context = view["latest_prompt_context"]["prompt_context"]

        self.assertEqual(prompt_context["user_text"], "hello runtime")
        self.assertEqual(
            prompt_context["sections"]["compact_snapshot"][
                "terminal.current_activity_state"
            ],
            "active",
        )

    def test_render_context_view_reads_state_and_diagnostic_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            diagnostic_path = Path(directory) / "runtime.jsonl"
            state = RuntimeState()
            state.record_observation(
                RuntimeObservation(
                    name="runtime.health_state",
                    value="healthy",
                    source_device_id="host-edge-1",
                    source_capability="runtime.health",
                    source_event_id="event-3",
                    observed_at="2026-07-05T14:43:00Z",
                    confidence=1.0,
                )
            )
            JsonStateStore(state_path).save(state)
            diagnostic_path.write_text(
                json.dumps(
                    {
                        "module": "Gateway",
                        "operation": "receive_frame",
                        "phase": "input",
                        "summary": "Received mobile.screen_context observation.",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            rendered = render_context_view(
                state_path=state_path,
                diagnostic_log_path=diagnostic_path,
            )

        self.assertIn("OpenHalo Runtime Context Viewer", rendered)
        self.assertIn("runtime.current_health_state", rendered)
        self.assertIn("Latest Accepted Ingress Events", rendered)
        self.assertIn("Latest Normalized Observations", rendered)
        self.assertNotIn("Latest Diagnostic Events", rendered)
        self.assertNotIn("Received mobile.screen_context observation.", rendered)

    def test_render_context_view_keeps_observation_uploads_visible_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state = RuntimeState()
            state.events.append(
                {
                    "type": "event_push",
                    "device_id": "old-android-edge",
                    "capability": "mobile.context",
                    "payload": {},
                }
            )
            state.record_observation(
                RuntimeObservation(
                    name="mobile.screen_context",
                    value={"screen_kind": "launcher"},
                    source_device_id="android-edge-1",
                    source_capability="mobile.screen_context",
                    source_event_id="event-5",
                    observed_at="2026-07-05T14:44:00Z",
                    confidence=0.8,
                )
            )
            JsonStateStore(state_path).save(state)

            rendered = render_context_view(
                state_path=state_path,
            )

        self.assertIn("old-android-edge", rendered)
        self.assertIn("mobile.screen_context", rendered)
        self.assertIn("launcher", rendered)

    def test_current_view_treats_old_observations_as_stale_at_view_time(self) -> None:
        state = RuntimeState()
        state.record_observation(
            RuntimeObservation(
                name="terminal.activity_state",
                value="active",
                source_device_id="terminal-edge-1",
                source_capability="terminal.context",
                source_event_id="event-4",
                observed_at="2026-07-05T14:00:00Z",
                confidence=1.0,
            )
        )

        view = build_context_view(
            state.to_dict(),
            current_time="2026-07-05T14:10:01Z",
        )

        field = view["current_snapshot_contract"]["fields"][
            "terminal.current_activity_state"
        ]
        self.assertEqual(view["current_snapshot"]["terminal.current_activity_state"], "unknown")
        self.assertEqual(field["status"], "stale")
        self.assertEqual(view["current_snapshot_evidence"][0]["snapshot_field_status"], "stale")

    def test_load_diagnostic_events_tolerates_malformed_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.jsonl"
            path.write_text('{"module": "Gateway"}\nnot-json\n', encoding="utf-8")

            events = load_diagnostic_events(path, limit=2)

        self.assertEqual(events[0]["module"], "Gateway")
        self.assertEqual(events[1]["malformed_jsonl"], "not-json")


if __name__ == "__main__":
    unittest.main()
