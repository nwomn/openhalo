import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from personal_runtime.main import build_gateway
from tests.v2_test_support import TEST_AUDIENCE
from tests.v2_test_support import build_test_edge
from tests.v2_test_support import connect_test_edge
from tests.v2_test_support import create_test_gateway

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_TEST_DIR = REPO_ROOT / ".worktrees" / "v0-single-edge-loop" / ".runtime-test"
TEST_LLM_CONFIG = REPO_ROOT / "tests" / "fixtures" / "llm-config-test.toml"


class RuntimePersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_gateway_restores_state_from_disk(self) -> None:
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "restored-state.json"
            pairing_store_path = Path(directory) / "pairing.json"
            first_gateway = create_test_gateway(
                state_path=state_path,
                pairing_store_path=pairing_store_path,
                persist_state=True,
                llm_config_path=TEST_LLM_CONFIG,
            )
            first_gateway.state.upsert_goal(
                goal_id="goal-1",
                title="Keep runtime healthy",
                status="active",
                summary="Watch runtime health signals.",
                updated_at="2026-06-22T10:00:00Z",
            )
            edge = build_test_edge(
                device_id="desktop-dev-1",
                device_type="desktop-cli",
                display_name="Test Desktop",
            )
            await connect_test_edge(first_gateway, edge)
            replies = await first_gateway.handle_test_frames(
                [edge.client.build_text_event("hello")]
            )
            action_request = next(
                reply for reply in replies if reply["type"] == "action_request"
            )
            await first_gateway.handle_test_frames(
                [edge.client.handle_action_request(action_request)]
            )

            restored_gateway = build_gateway(
                state_path=state_path,
                pairing_store_path=pairing_store_path,
                llm_config_path=TEST_LLM_CONFIG,
                audience=TEST_AUDIENCE,
            )

            self.assertIn("desktop-dev-1", restored_gateway.state.devices)
            self.assertEqual(
                restored_gateway.state.events[-1]["payload"]["text"],
                "hello",
            )
            self.assertEqual(restored_gateway.state.action_results[-1]["status"], "ok")
            self.assertEqual(restored_gateway.state.tasks[0]["goal_id"], "goal-1")
            self.assertEqual(restored_gateway.state.tasks[0]["status"], "active")


if __name__ == "__main__":
    unittest.main()
