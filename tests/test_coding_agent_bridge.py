from __future__ import annotations

import asyncio
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

    async def test_registers_start_steer_and_attention_capabilities(self) -> None:
        names = {registration["name"] for registration in CODING_CAPABILITY_REGISTRATIONS}

        self.assertEqual(
            names,
            {
                "coding.attention",
                "coding.turn.start",
                "coding.suggestion.offer",
                "coding.turn.steer",
            },
        )

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
        self.assertEqual(observations[0]["value"]["event_kind"], "tool_activity")
        self.assertTrue(observations[0]["value"]["evidence_ref"])

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


if __name__ == "__main__":
    unittest.main()
