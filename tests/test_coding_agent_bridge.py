from __future__ import annotations

import asyncio
import json
import unittest

from device_edge.cli.coding_agent_bridge import CODING_CAPABILITY_REGISTRATIONS
from device_edge.cli.coding_agent_bridge import CodingAgentBridge
from device_edge.cli.coding_agent_bridge import validate_coding_action_payload


class FakeCodexClient:
    def __init__(self) -> None:
        self.state = "disconnected"
        self.notification_handler = None
        self.server_request_handler = None
        self.thread_count = 0
        self.turn_count = 0
        self.steer_calls: list[dict] = []
        self.interrupt_calls: list[dict] = []

    async def start(self) -> None:
        self.state = "ready"

    async def close(self) -> None:
        self.state = "disconnected"

    async def start_thread(self, *, cwd: str | None = None) -> dict:
        self.thread_count += 1
        return {"id": f"thread-{self.thread_count}"}

    async def start_turn(self, *, thread_id: str, text: str, cwd: str | None = None) -> dict:
        self.turn_count += 1
        return {"id": f"turn-{self.turn_count}", "status": "inProgress"}

    async def steer(self, *, thread_id: str, expected_turn_id: str, text: str) -> str:
        self.steer_calls.append(
            {
                "thread_id": thread_id,
                "expected_turn_id": expected_turn_id,
                "text": text,
            }
        )
        return expected_turn_id

    async def interrupt(self, *, thread_id: str, turn_id: str) -> None:
        self.interrupt_calls.append({"thread_id": thread_id, "turn_id": turn_id})


class CodingAgentBridgeTests(unittest.IsolatedAsyncioTestCase):
    def make_bridge(self) -> tuple[CodingAgentBridge, FakeCodexClient, list[dict], list[dict]]:
        client = FakeCodexClient()
        observations: list[dict] = []
        prompts: list[dict] = []
        bridge = CodingAgentBridge(
            client=client,
            workspace_path="/workspace/project",
            workspace_ref="project",
            observation_sink=observations.append,
            approval_sink=prompts.append,
        )
        return bridge, client, observations, prompts

    async def test_registers_start_steer_and_activity_capabilities(self) -> None:
        names = {registration["name"] for registration in CODING_CAPABILITY_REGISTRATIONS}

        self.assertEqual(
            names,
            {
                "coding.activity",
                "coding.turn.start",
                "coding.suggestion.offer",
                "coding.turn.steer",
            },
        )

    async def test_coding_start_declares_a_generic_process_completion_contract(self) -> None:
        registration = next(
            item
            for item in CODING_CAPABILITY_REGISTRATIONS
            if item["name"] == "coding.turn.start"
        )

        contract = registration["process_contract"]
        self.assertEqual("until_settled", contract["continuation_policy"])
        self.assertEqual(
            ["coding.activity.v1"],
            contract["watches"][0]["observation_names"],
        )
        self.assertIn("turn_completed", contract["watches"][0]["resolve_when"]["event_kind"])

    async def test_rejects_coding_action_payload_that_breaks_registered_schema(self) -> None:
        with self.assertRaises(ValueError):
            validate_coding_action_payload(
                "coding.turn.steer",
                {
                    "suggestion_id": "suggestion-1",
                    "confirmation_ref": "confirmation-1",
                    "agent_session_id": "thread-1",
                    "agent_turn_id": "turn-1",
                    "instruction": "Run tests",
                    "unexpected": True,
                },
            )

    async def test_starts_independent_threads_and_emits_prompt_observations(self) -> None:
        bridge, client, observations, _ = self.make_bridge()
        await bridge.start()

        first = await bridge.start_turn(
            interaction_id="interaction-1",
            task="Fix the failing login test",
            workspace_ref="project",
        )
        second = await bridge.start_turn(
            interaction_id="interaction-2",
            task="Explain the API error",
            workspace_ref="project",
        )

        self.assertEqual(first["agent_session_id"], "thread-1")
        self.assertEqual(second["agent_session_id"], "thread-2")
        self.assertEqual(client.thread_count, 2)
        self.assertEqual(client.turn_count, 2)
        self.assertEqual(
            [
                observation["value"]["agent_turn_id"]
                for observation in observations
                if observation["value"]["event_kind"] == "prompt_submitted"
            ],
            ["turn-1", "turn-2"],
        )
        self.assertTrue(
            all(
                "workspace_path" not in observation["value"]
                for observation in observations
            )
        )

        await bridge.close()

    async def test_limits_only_simultaneously_active_tasks_not_activity_history(self) -> None:
        bridge, _, _, _ = self.make_bridge()
        await bridge.start()
        for index in range(bridge.active_task_limit):
            await bridge.start_turn(
                interaction_id=f"interaction-{index}",
                task="Keep this task active",
                workspace_ref="project",
            )
        with self.assertRaises(RuntimeError):
            await bridge.start_turn(
                interaction_id="interaction-over-limit",
                task="Must fail closed",
                workspace_ref="project",
            )
        bridge.handle_notification(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "turn": {"status": "completed"},
                },
            }
        )
        await bridge.start_turn(
            interaction_id="interaction-after-completion",
            task="Now one slot is free",
            workspace_ref="project",
        )
        await bridge.close()

    async def test_coalesces_output_without_emitting_raw_content(self) -> None:
        bridge, _, observations, _ = self.make_bridge()
        await bridge.start()
        await bridge.start_turn(
            interaction_id="interaction-1",
            task="Run the tests",
            workspace_ref="project",
        )
        observations.clear()

        bridge.handle_notification(
            {
                "method": "item/commandExecution/outputDelta",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "itemId": "item-1",
                    "delta": "SECRET_OUTPUT",
                },
            }
        )
        bridge.handle_notification(
            {
                "method": "item/commandExecution/outputDelta",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "itemId": "item-1",
                    "delta": "more output",
                },
            }
        )
        await asyncio.sleep(0.55)

        self.assertEqual(len(observations), 1)
        serialized = str(observations[0])
        self.assertNotIn("SECRET_OUTPUT", serialized)
        self.assertNotIn("more output", serialized)
        self.assertEqual(observations[0]["value"]["event_kind"], "command_execution")
        self.assertTrue(observations[0]["value"]["evidence_ref"])

        await bridge.close()

    async def test_foreground_correction_and_interrupt_use_selected_task_lineage(self) -> None:
        bridge, client, observations, _ = self.make_bridge()
        await bridge.start()
        await bridge.start_turn(
            interaction_id="interaction-1",
            task="Fix tests",
            workspace_ref="project",
        )
        await bridge.start_turn(
            interaction_id="interaction-2",
            task="Inspect docs",
            workspace_ref="project",
        )

        await bridge.foreground_steer(
            interaction_id="interaction-2",
            instruction="Focus on the API docs",
        )
        await bridge.interrupt(interaction_id="interaction-2")

        self.assertEqual(
            client.steer_calls[-1],
            {
                "thread_id": "thread-2",
                "expected_turn_id": "turn-2",
                "text": "Focus on the API docs",
            },
        )
        self.assertEqual(
            client.interrupt_calls[-1],
            {"thread_id": "thread-2", "turn_id": "turn-2"},
        )
        self.assertEqual(
            [entry["value"]["event_kind"] for entry in observations[-2:]],
            ["user_correction", "turn_interrupted"],
        )
        with self.assertRaises(ValueError):
            await bridge.foreground_steer(
                interaction_id="missing",
                instruction="Do not guess a task",
            )
        await bridge.close()

    async def test_normalizes_reasoning_plan_agent_and_file_activity_without_raw_output(self) -> None:
        bridge, _, observations, _ = self.make_bridge()
        await bridge.start()
        await bridge.start_turn(
            interaction_id="interaction-1",
            task="Implement the feature",
            workspace_ref="project",
        )
        observations.clear()

        bridge.handle_notification(
            {
                "method": "item/reasoning/summaryTextDelta",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "delta": "Use the existing Runtime ingress.",
                },
            }
        )
        bridge.handle_notification(
            {
                "method": "turn/plan/updated",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "plan": [{"step": "Add tests", "status": "in_progress"}],
                },
            }
        )
        bridge.handle_notification(
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "delta": "I will now run the focused suite.",
                },
            }
        )
        bridge.handle_notification(
            {
                "method": "item/fileChange/completed",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "item": {"type": "fileChange", "path": "/tmp/example.py"},
                    "raw": "SECRET_DIFF",
                },
            }
        )
        bridge.handle_notification(
            {
                "method": "item/completed",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "item": {
                        "type": "commandExecution",
                        "command": "pytest -q tests/test_feature.py",
                        "status": "completed",
                    },
                },
            }
        )
        await asyncio.sleep(0.55)

        kinds = {entry["value"]["event_kind"] for entry in observations}
        self.assertTrue(
            {
                "reasoning_summary",
                "plan_update",
                "agent_message",
                "file_change",
                "test_result",
            }
            <= kinds
        )
        self.assertNotIn("SECRET_DIFF", str(observations))
        self.assertTrue(all(entry["name"] == "coding.activity.v1" for entry in observations))
        await bridge.close()

    async def test_runtime_activity_payload_is_byte_bounded_for_multibyte_summaries(self) -> None:
        bridge, _, observations, _ = self.make_bridge()
        await bridge.start()
        await bridge.start_turn(
            interaction_id="interaction-1",
            task="Summarize the result",
            workspace_ref="project",
        )
        observations.clear()
        await bridge.foreground_steer(
            interaction_id="interaction-1",
            instruction="修复" * 6000,
        )

        payload = observations[0]
        assert len(json.dumps(payload, ensure_ascii=False).encode()) < 16 * 1024
        assert len(payload["value"]["summary"].encode()) <= 4096
        await bridge.close()

    async def test_acceptance_confirmation_is_required_for_exact_turn_steering(self) -> None:
        bridge, client, _, _ = self.make_bridge()
        await bridge.start()
        await bridge.start_turn(
            interaction_id="interaction-1",
            task="Fix tests",
            workspace_ref="project",
        )

        pending = bridge.offer_suggestion(
            suggestion_id="suggestion-1",
            agent_session_id="thread-1",
            agent_turn_id="turn-1",
            summary="Run the failing test first",
        )
        ignored = bridge.resolve_suggestion(pending["prompt_id"], "ignore")
        self.assertEqual(ignored["details"]["choice"], "ignore")
        with self.assertRaises(ValueError):
            await bridge.steer(
                suggestion_id="suggestion-1",
                confirmation_ref="missing",
                agent_session_id="thread-1",
                agent_turn_id="turn-1",
                instruction="Run the failing test first",
            )

        accepted = bridge.offer_suggestion(
            suggestion_id="suggestion-2",
            agent_session_id="thread-1",
            agent_turn_id="turn-1",
            summary="Run the failing test first",
        )
        result = bridge.resolve_suggestion(accepted["prompt_id"], "accept")
        confirmation_ref = result["details"]["confirmation_ref"]
        steer_result = await bridge.steer(
            suggestion_id="suggestion-2",
            confirmation_ref=confirmation_ref,
            agent_session_id="thread-1",
            agent_turn_id="turn-1",
            instruction="Run the failing test first",
        )

        self.assertEqual(steer_result["agent_turn_id"], "turn-1")
        self.assertEqual(client.steer_calls[0]["expected_turn_id"], "turn-1")

        await bridge.close()

    async def test_resolves_local_file_approval_without_runtime_evidence(self) -> None:
        bridge, _, _, prompts = self.make_bridge()
        await bridge.start()

        request = asyncio.create_task(
            bridge.handle_server_request(
                {
                    "id": 42,
                    "method": "item/fileChange/requestApproval",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "itemId": "item-1",
                        "reason": "Apply the proposed change",
                    },
                }
            )
        )
        for _ in range(10):
            if prompts:
                break
            await asyncio.sleep(0)
        self.assertEqual(prompts[0]["kind"], "file_change")
        self.assertNotIn("reason", prompts[0]["summary"])

        bridge.resolve_approval(prompts[0]["prompt_id"], "decline")
        self.assertEqual(await request, {"decision": "decline"})

        await bridge.close()

    async def test_records_approval_waiting_and_resolution_as_activity(self) -> None:
        bridge, _, observations, prompts = self.make_bridge()
        await bridge.start()
        await bridge.start_turn(
            interaction_id="interaction-1",
            task="Apply the patch",
            workspace_ref="project",
        )
        observations.clear()
        request = asyncio.create_task(
            bridge.handle_server_request(
                {
                    "id": 99,
                    "method": "item/commandExecution/requestApproval",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "command": "pytest -q",
                    },
                }
            )
        )
        for _ in range(10):
            if prompts:
                break
            await asyncio.sleep(0)
        bridge.resolve_approval(prompts[0]["prompt_id"], "accept")
        assert await request == {"decision": "accept"}
        assert [entry["value"]["event_kind"] for entry in observations] == [
            "approval_waiting",
            "approval_resolved",
        ]
        await bridge.close()


if __name__ == "__main__":
    unittest.main()
