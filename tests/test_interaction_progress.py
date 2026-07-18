import asyncio
import io
import threading
import unittest

import websockets

from device_edge.cli.terminal_daemon import TerminalEdgeDaemon
from device_edge.shared.session_client import SessionClient
from openhalo_common.diagnostics import InMemoryDiagnosticRecorder
from personal_runtime.agent_executor import InterventionProposal
from personal_runtime.agent_harness import ActionExecutorKind
from personal_runtime.agent_harness import ActionBatch
from personal_runtime.agent_harness import ActionGovernance
from personal_runtime.agent_harness import ActionSideEffect
from personal_runtime.agent_harness import ActionVisibility
from personal_runtime.agent_harness import HarnessOutcome
from personal_runtime.agent_harness import RuntimeActionIntent
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.runtime_state import RuntimeState


class InteractionProgressRuntimeTests(unittest.TestCase):
    def _connect_terminal(self, gateway: RuntimeGateway, *, supports_progress: bool) -> SessionClient:
        capabilities = ["text.input", "notification.show", "terminal.context"]
        if supports_progress:
            capabilities.append("interaction.progress")
        client = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=capabilities,
        )
        gateway.run_roundtrip(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
            ]
        )
        return client

    def test_visible_terminal_interaction_emits_safe_ordered_progress(self) -> None:
        diagnostics = InMemoryDiagnosticRecorder(
            timestamp_provider=lambda: "2026-07-18T10:00:00Z"
        )
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            diagnostic_recorder=diagnostics,
        )
        client = self._connect_terminal(gateway, supports_progress=True)

        replies = gateway.run_roundtrip([client.build_text_event("hello runtime")])

        progress_frames = [
            reply for reply in replies if reply["type"] == "interaction_progress"
        ]
        self.assertGreaterEqual(len(progress_frames), 2)
        progress = [reply["progress"] for reply in progress_frames]
        self.assertEqual(progress[0]["phase"], "deliberating")
        self.assertIn("planning", [item["phase"] for item in progress])
        self.assertEqual(
            [item["sequence"] for item in progress],
            list(range(1, len(progress) + 1)),
        )
        self.assertTrue(
            all(reply["device_id"] == "terminal-edge-1" for reply in progress_frames)
        )
        allowed_fields = {
            "version",
            "interaction_id",
            "interaction_turn_id",
            "sequence",
            "phase",
            "state",
            "occurred_at",
            "presentation_hint",
        }
        self.assertTrue(all(set(item) == allowed_fields for item in progress))
        rendered_diagnostics = [
            event
            for event in diagnostics.events
            if event.module == "Display Lifecycle"
        ]
        self.assertTrue(rendered_diagnostics)
        self.assertNotIn("hello runtime", str(rendered_diagnostics))
        self.assertNotIn("Hermes", str(rendered_diagnostics))

    def test_interaction_without_progress_capability_keeps_normal_result_path(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token", persist_state=False)
        client = self._connect_terminal(gateway, supports_progress=False)

        replies = gateway.run_roundtrip([client.build_text_event("hello runtime")])

        self.assertFalse(
            any(reply["type"] == "interaction_progress" for reply in replies)
        )
        self.assertTrue(any(reply["type"] == "interaction_update" for reply in replies))

    def test_action_result_reentry_advances_progress_to_completion(self) -> None:
        class ActionThenCompleteHarness:
            def run(self, harness_input):
                if harness_input.operation.value == "post_action":
                    return HarnessOutcome.from_proposal(
                        operation=harness_input.operation,
                        proposal=InterventionProposal(
                            kind="no_intervention",
                            proposal_type="no_intervention",
                            source="post_action",
                            action_capability=None,
                            required_capability=None,
                            action_payload={},
                            message="",
                            metadata={},
                        ),
                    )
                return HarnessOutcome.from_proposal(
                    operation=harness_input.operation,
                    proposal=InterventionProposal(
                        kind="action",
                        proposal_type="action",
                        source="sense_first",
                        action_capability="notification.show",
                        required_capability="notification.show",
                        action_payload={"title": "OpenHalo", "body": "Action result"},
                        message="Action result",
                        metadata={},
                        target_device_hint="terminal-edge-1",
                    ),
                    action_intent=RuntimeActionIntent(
                        action_id="progress-action-1",
                        executor_kind=ActionExecutorKind.DEVICE_EDGE,
                        capability="notification.show",
                        payload={"title": "OpenHalo", "body": "Action result"},
                        side_effect_class=ActionSideEffect.EXTERNAL,
                        visibility=ActionVisibility.USER_VISIBLE,
                        governance=ActionGovernance.RUNTIME_GOVERNED,
                        provenance={"origin": "progress-test"},
                    ),
                )

        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            agent_harness=ActionThenCompleteHarness(),
        )
        client = self._connect_terminal(gateway, supports_progress=True)

        initial_replies = gateway.run_roundtrip([client.build_text_event("act")])
        action_request = next(
            reply for reply in initial_replies if reply["type"] == "action_request"
        )
        initial_phases = [
            reply["progress"]["phase"]
            for reply in initial_replies
            if reply["type"] == "interaction_progress"
        ]
        completion_replies = gateway.run_roundtrip(
            [client.handle_action_request(action_request)]
        )
        completion_phases = [
            reply["progress"]["phase"]
            for reply in completion_replies
            if reply["type"] == "interaction_progress"
        ]

        self.assertIn("executing", initial_phases)
        self.assertIn("awaiting_action_result", initial_phases)
        self.assertEqual(completion_phases, ["completing", "completed"])
        self.assertEqual(
            completion_replies[-1]["type"],
            "interaction_update",
        )

    def test_action_result_reentry_marks_follow_up_action_as_executing(self) -> None:
        class ActionThenFollowUpHarness:
            def run(self, harness_input):
                action_id = (
                    "progress-follow-up-2"
                    if harness_input.operation.value == "post_action"
                    else "progress-follow-up-1"
                )
                return HarnessOutcome.from_proposal(
                    operation=harness_input.operation,
                    proposal=InterventionProposal(
                        kind="action",
                        proposal_type="action",
                        source=(
                            "post_action"
                            if harness_input.operation.value == "post_action"
                            else "sense_first"
                        ),
                        action_capability="notification.show",
                        required_capability="notification.show",
                        action_payload={"title": "OpenHalo", "body": action_id},
                        message=action_id,
                        metadata={},
                        target_device_hint="terminal-edge-1",
                    ),
                    action_intent=RuntimeActionIntent(
                        action_id=action_id,
                        executor_kind=ActionExecutorKind.DEVICE_EDGE,
                        capability="notification.show",
                        payload={"title": "OpenHalo", "body": action_id},
                        side_effect_class=ActionSideEffect.EXTERNAL,
                        visibility=ActionVisibility.USER_VISIBLE,
                        governance=ActionGovernance.RUNTIME_GOVERNED,
                        provenance={"origin": "progress-test"},
                    ),
                )

        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            agent_harness=ActionThenFollowUpHarness(),
        )
        client = self._connect_terminal(gateway, supports_progress=True)

        initial_replies = gateway.run_roundtrip([client.build_text_event("act")])
        first_action = next(
            reply for reply in initial_replies if reply["type"] == "action_request"
        )
        follow_up_replies = gateway.run_roundtrip(
            [client.handle_action_request(first_action)]
        )

        self.assertEqual(
            [
                reply["progress"]["phase"]
                for reply in follow_up_replies
                if reply["type"] == "interaction_progress"
            ],
            ["completing", "executing", "awaiting_action_result"],
        )
        self.assertEqual(
            [reply["type"] for reply in follow_up_replies],
            [
                "interaction_progress",
                "interaction_progress",
                "action_request",
                "interaction_progress",
            ],
        )

    def test_restart_preserves_the_progress_sequence_for_an_active_interaction(self) -> None:
        state = RuntimeState()
        state.register_device("terminal-edge-1", "desktop-cli")
        state.register_capability("terminal-edge-1", "interaction.progress")
        state.record_interaction(
            {
                "interaction_id": "interaction-1",
                "requesting_device_id": "terminal-edge-1",
                "outcome_delivery_required": True,
            }
        )
        first_gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            state=state,
        )
        first_gateway.online_device_ids.add("terminal-edge-1")
        first = first_gateway.emit_interaction_progress(
            interaction_id="interaction-1",
            interaction_turn_id="interaction-turn-1",
            phase="deliberating",
            state="active",
            presentation_hint="working",
        )[0]

        restarted_gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            state=state,
        )
        restarted_gateway.online_device_ids.add("terminal-edge-1")
        second = restarted_gateway.emit_interaction_progress(
            interaction_id="interaction-1",
            interaction_turn_id="interaction-turn-1",
            phase="planning",
            state="active",
            presentation_hint="working",
        )[0]

        self.assertEqual(first["progress"]["sequence"], 1)
        self.assertEqual(second["progress"]["sequence"], 2)

    def test_action_batch_emits_one_waiting_phase_after_all_actions_dispatch(self) -> None:
        def intent(action_id: str, body: str) -> RuntimeActionIntent:
            return RuntimeActionIntent(
                action_id=action_id,
                executor_kind=ActionExecutorKind.DEVICE_EDGE,
                capability="notification.show",
                payload={"title": "OpenHalo", "body": body},
                side_effect_class=ActionSideEffect.EXTERNAL,
                visibility=ActionVisibility.USER_VISIBLE,
                governance=ActionGovernance.RUNTIME_GOVERNED,
                provenance={"origin": "progress-test", "target_device_hint": "terminal-edge-1"},
            )

        class BatchHarness:
            def run(self, harness_input):
                first = intent("progress-batch-1", "First action")
                return HarnessOutcome.from_proposal(
                    operation=harness_input.operation,
                    proposal=InterventionProposal(
                        kind="action",
                        proposal_type="action",
                        source="sense_first",
                        action_capability=first.capability,
                        required_capability="notification.show",
                        action_payload=first.payload,
                        message="First action",
                        metadata={},
                        target_device_hint="terminal-edge-1",
                    ),
                    action_batch=ActionBatch(
                        batch_id="progress-batch",
                        action_intents=(first, intent("progress-batch-2", "Second action")),
                    ),
                )

        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            agent_harness=BatchHarness(),
        )
        client = self._connect_terminal(gateway, supports_progress=True)

        replies = gateway.run_roundtrip([client.build_text_event("run batch")])
        phases = [
            reply["progress"]["phase"]
            for reply in replies
            if reply["type"] == "interaction_progress"
        ]

        self.assertEqual(
            len([reply for reply in replies if reply["type"] == "action_request"]),
            2,
        )
        self.assertIn("executing", phases)
        self.assertEqual(phases.count("awaiting_action_result"), 1)


class InteractionProgressWebSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_gateway_streams_execution_before_ack_then_returns_action_and_waiting(
        self,
    ) -> None:
        class ActionHarness:
            def run(self, harness_input):
                return HarnessOutcome.from_proposal(
                    operation=harness_input.operation,
                    proposal=InterventionProposal(
                        kind="action",
                        proposal_type="action",
                        source="sense_first",
                        action_capability="notification.show",
                        required_capability="notification.show",
                        action_payload={"title": "OpenHalo", "body": "Action result"},
                        message="Action result",
                        metadata={},
                        target_device_hint="terminal-edge-1",
                    ),
                    action_intent=RuntimeActionIntent(
                        action_id="streamed-progress-action-1",
                        executor_kind=ActionExecutorKind.DEVICE_EDGE,
                        capability="notification.show",
                        payload={"title": "OpenHalo", "body": "Action result"},
                        side_effect_class=ActionSideEffect.EXTERNAL,
                        visibility=ActionVisibility.USER_VISIBLE,
                        governance=ActionGovernance.RUNTIME_GOVERNED,
                        provenance={"origin": "progress-test"},
                    ),
                )

        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            agent_harness=ActionHarness(),
        )
        client = SessionClient(
            device_id="terminal-edge-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=[
                "text.input",
                "notification.show",
                "terminal.context",
                "interaction.progress",
            ],
        )
        gateway.run_roundtrip(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
            ]
        )
        streamed: list[dict] = []

        async def capture_stream(replies: list[dict]) -> None:
            streamed.extend(replies)

        remaining = await gateway._handle_websocket_frame(
            client.build_text_event("run action"),
            progress_sink=capture_stream,
        )

        def lifecycle_item(reply: dict) -> str:
            if reply["type"] != "interaction_progress":
                return reply["type"]
            return reply["progress"]["phase"]

        self.assertEqual(
            [lifecycle_item(reply) for reply in streamed],
            [
                "deliberating",
                "planning",
                "executing",
            ],
        )
        self.assertEqual(
            [lifecycle_item(reply) for reply in remaining],
            ["event_ack", "action_request", "awaiting_action_result"],
        )

    async def test_terminal_renders_deliberating_before_slow_harness_returns(
        self,
    ) -> None:
        class SlowHarness:
            def __init__(self) -> None:
                self.started = threading.Event()
                self.release = threading.Event()

            def run(self, harness_input):
                self.started.set()
                if not self.release.wait(timeout=1):
                    raise RuntimeError("slow harness was not released")
                return HarnessOutcome.from_proposal(
                    operation=harness_input.operation,
                    proposal=InterventionProposal(
                        kind="no_intervention",
                        proposal_type="no_intervention",
                        source="sense_first",
                        action_capability=None,
                        required_capability=None,
                        action_payload={},
                        message="Reply after release",
                        metadata={},
                    ),
                )

        class RecordingTerminalEdgeDaemon(TerminalEdgeDaemon):
            def __init__(self, **kwargs) -> None:
                super().__init__(**kwargs)
                self.deliberating_rendered = asyncio.Event()
                self.received_updates: list[dict] = []

            def handle_interaction_progress_frame(self, frame: dict) -> None:
                super().handle_interaction_progress_frame(frame)
                if frame.get("progress", {}).get("phase") == "deliberating":
                    self.deliberating_rendered.set()

            def handle_interaction_frame(self, frame: dict) -> None:
                self.received_updates.append(frame)
                super().handle_interaction_frame(frame)

        harness = SlowHarness()
        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            agent_harness=harness,
        )
        terminal = RecordingTerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=io.StringIO(),
        )

        async with gateway.run_test_server() as server_info:
            async with websockets.connect(server_info["url"]) as websocket:
                session_task = asyncio.create_task(
                    terminal.run_scripted_session(
                        websocket=websocket,
                        scripted_inputs=[
                            {
                                "text": "wait for me",
                                "observed_at": "2026-07-19T10:00:00Z",
                            }
                        ],
                        startup_observed_at="2026-07-19T10:00:00Z",
                        idle_after_inputs=True,
                        idle_timeout_s=0.01,
                        max_idle_cycles=1,
                        max_action_requests=1,
                    )
                )
                try:
                    self.assertTrue(
                        await asyncio.to_thread(harness.started.wait, 1),
                        "slow harness did not start",
                    )
                    try:
                        await asyncio.wait_for(
                            terminal.deliberating_rendered.wait(),
                            timeout=0.1,
                        )
                    except TimeoutError:
                        self.fail(
                            "Terminal did not render deliberating before the "
                            "slow harness returned"
                        )
                    self.assertEqual(terminal.received_updates, [])
                finally:
                    harness.release.set()
                    await asyncio.wait_for(session_task, timeout=1)

    async def test_terminal_receives_ordered_progress_and_final_update_over_websocket(
        self,
    ) -> None:
        class RecordingTerminalEdgeDaemon(TerminalEdgeDaemon):
            def __init__(self, **kwargs) -> None:
                super().__init__(**kwargs)
                self.received_progress: list[dict] = []
                self.received_updates: list[dict] = []

            def handle_interaction_progress_frame(self, frame: dict) -> None:
                self.received_progress.append(frame)
                super().handle_interaction_progress_frame(frame)

            def handle_interaction_frame(self, frame: dict) -> None:
                self.received_updates.append(frame)
                super().handle_interaction_frame(frame)

        class ActionThenCompleteHarness:
            def run(self, harness_input):
                if harness_input.operation.value == "post_action":
                    return HarnessOutcome.from_proposal(
                        operation=harness_input.operation,
                        proposal=InterventionProposal(
                            kind="no_intervention",
                            proposal_type="no_intervention",
                            source="post_action",
                            action_capability=None,
                            required_capability=None,
                            action_payload={},
                            message="",
                            metadata={},
                        ),
                    )
                return HarnessOutcome.from_proposal(
                    operation=harness_input.operation,
                    proposal=InterventionProposal(
                        kind="action",
                        proposal_type="action",
                        source="sense_first",
                        action_capability="notification.show",
                        required_capability="notification.show",
                        action_payload={"title": "OpenHalo", "body": "Action result"},
                        message="Action result",
                        metadata={},
                        target_device_hint="terminal-edge-1",
                    ),
                    action_intent=RuntimeActionIntent(
                        action_id="websocket-progress-action-1",
                        executor_kind=ActionExecutorKind.DEVICE_EDGE,
                        capability="notification.show",
                        payload={"title": "OpenHalo", "body": "Action result"},
                        side_effect_class=ActionSideEffect.EXTERNAL,
                        visibility=ActionVisibility.USER_VISIBLE,
                        governance=ActionGovernance.RUNTIME_GOVERNED,
                        provenance={"origin": "progress-test"},
                    ),
                )

        gateway = RuntimeGateway(
            shared_token="dev-token",
            persist_state=False,
            agent_harness=ActionThenCompleteHarness(),
        )
        terminal = RecordingTerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            output_stream=io.StringIO(),
        )

        async with gateway.run_test_server() as server_info:
            async with websockets.connect(server_info["url"]) as websocket:
                results = await asyncio.wait_for(
                    terminal.run_scripted_session(
                        websocket=websocket,
                        scripted_inputs=[
                            {
                                "text": "run action",
                                "observed_at": "2026-07-19T10:00:00Z",
                            }
                        ],
                        startup_observed_at="2026-07-19T10:00:00Z",
                        idle_after_inputs=True,
                        idle_timeout_s=0.01,
                        max_idle_cycles=1,
                    ),
                    timeout=1,
                )

        progress = [frame["progress"] for frame in terminal.received_progress]
        self.assertEqual(
            [item["phase"] for item in progress],
            [
                "deliberating",
                "planning",
                "executing",
                "awaiting_action_result",
                "completing",
                "completed",
            ],
        )
        self.assertEqual(
            [item["sequence"] for item in progress],
            list(range(1, len(progress) + 1)),
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(terminal.received_updates[-1]["interaction"]["status"], "completed")
        self.assertIsNone(terminal.active_progress_phase)
        rendered = terminal.output_stream.getvalue()
        self.assertLess(
            rendered.index("[runtime] Action result"),
            rendered.index("[progress] 正在等待设备确认..."),
        )
        self.assertLess(
            rendered.index("[progress] 正在等待设备确认..."),
            rendered.index("[progress] 正在确认处理结果..."),
        )
        self.assertNotIn("run action", str(progress))
        self.assertNotIn("Hermes", str(progress))


if __name__ == "__main__":
    unittest.main()
