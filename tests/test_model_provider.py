import unittest
from pathlib import Path

from personal_runtime.model_provider import (
    DeterministicReplyPlan,
    ModelConfig,
    ProfileConfig,
    ProviderConfig,
    build_deterministic_reply_plan,
    build_openai_compatible_request,
    execute_openai_compatible_request,
    parse_openai_compatible_response,
    load_runtime_model_config,
    resolve_profile_config,
)
from personal_runtime.prompt_context import PROMPT_CONTEXT_VERSION


class ModelProviderConfigTests(unittest.TestCase):
    def test_load_runtime_model_config_reads_provider_model_and_profile_layers(self) -> None:
        config = load_runtime_model_config(
            Path("tests/fixtures/llm-config-test.toml")
        )
        profile = resolve_profile_config(config, "interactive_reply")

        self.assertEqual(config.providers["openai_main"].adapter_type, "openai_compatible")
        self.assertEqual(
            config.providers["openai_main"].default_headers,
            {"User-Agent": "fixture-agent/0.1"},
        )
        self.assertEqual(config.models["openai_gpt55"].provider, "openai_main")
        self.assertEqual(profile.model_ref, "openai_gpt55")
        self.assertEqual(profile.reasoning_effort, "medium")
        self.assertEqual(profile.verbosity, "low")

    def test_build_openai_compatible_request_uses_profile_and_snapshot_context(self) -> None:
        request_payload = build_openai_compatible_request(
            model_id="gpt-5.5",
            user_text="hello runtime",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={
                "bundle_version": "m10.v1",
                "active_goals": [
                    {
                        "goal_id": "goal-1",
                        "title": "Keep runtime healthy",
                        "status": "active",
                    }
                ],
                "recent_memory": {
                    "user_inputs": [{"text": "hello runtime"}],
                    "interventions": [],
                    "action_results": [],
                },
                "edge_history": {"returned_entries": 1},
            },
            reasoning_effort="medium",
            verbosity="low",
        )

        self.assertEqual(request_payload["model"], "gpt-5.5")
        self.assertEqual(request_payload["reasoning"]["effort"], "medium")
        self.assertEqual(request_payload["text"]["verbosity"], "low")
        self.assertIn("Prompt context version", str(request_payload["input"]))
        self.assertIn(PROMPT_CONTEXT_VERSION, str(request_payload["input"]))
        self.assertIn("hello runtime", str(request_payload["input"]))
        self.assertIn("healthy", str(request_payload["input"]))
        self.assertIn("Keep runtime healthy", str(request_payload["input"]))
        self.assertIn('"bundle_version": "m10.v1"', str(request_payload["input"]))
        self.assertIn('"edge_evidence"', str(request_payload["input"]))
        self.assertIn('"recent_memory"', str(request_payload["input"]))

    def test_parse_openai_compatible_response_returns_bounded_reply_text(self) -> None:
        plan = parse_openai_compatible_response(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Model says hello.",
                            }
                        ],
                    }
                ]
            },
            profile_name="interactive_reply",
            provider_name="openai_main",
            model_id="gpt-5.5",
        )

        self.assertEqual(plan.message, "Model says hello.")
        self.assertEqual(plan.metadata["llm_profile"], "interactive_reply")
        self.assertEqual(plan.metadata["llm_provider"], "openai_main")
        self.assertEqual(plan.metadata["llm_model"], "gpt-5.5")
        self.assertFalse(plan.metadata["used_deterministic_fallback"])

    def test_build_deterministic_reply_plan_marks_local_fallback(self) -> None:
        plan = build_deterministic_reply_plan(
            user_text="hello runtime",
            profile_name="interactive_reply",
            fallback_reason="provider_unavailable",
        )

        self.assertIsInstance(plan, DeterministicReplyPlan)
        self.assertEqual(plan.message, "Runtime heard: hello runtime")
        self.assertTrue(plan.metadata["used_deterministic_fallback"])
        self.assertEqual(plan.metadata["fallback_reason"], "provider_unavailable")
        self.assertEqual(plan.metadata["llm_profile"], "interactive_reply")

    def test_execute_openai_compatible_request_passes_explicit_user_agent_header(self) -> None:
        observed = {}

        def transport(provider, request_payload, api_key, headers):
            observed["provider"] = provider
            observed["request_payload"] = request_payload
            observed["api_key"] = api_key
            observed["headers"] = headers
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "ok"}],
                    }
                ]
            }

        provider = ProviderConfig(
            name="openai_main",
            adapter_type="openai_compatible",
            base_url="https://api.openai.com/v1",
            wire_api="responses",
            auth_env="OPENAI_API_KEY",
            timeout_seconds=30,
        )
        model = ModelConfig(
            name="openai_gpt55",
            provider="openai_main",
            model_id="gpt-5.5",
        )
        profile = ProfileConfig(
            name="interactive_reply",
            model_ref="openai_gpt55",
            reasoning_effort="medium",
            verbosity="low",
        )

        self.addCleanup(__import__("os").environ.pop, "OPENAI_API_KEY", None)
        __import__("os").environ["OPENAI_API_KEY"] = "test-key"

        execute_openai_compatible_request(
            provider=provider,
            model=model,
            profile=profile,
            user_text="hello runtime",
            snapshot={"runtime.current_health_state": "healthy"},
            transport=transport,
        )

        self.assertEqual(observed["api_key"], "test-key")
        self.assertIn("User-Agent", observed["headers"])
        self.assertTrue(observed["headers"]["User-Agent"])
        self.assertEqual(observed["headers"]["Content-Type"], "application/json")


if __name__ == "__main__":
    unittest.main()
