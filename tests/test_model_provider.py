import unittest
from pathlib import Path

from personal_runtime.model_provider import (
    DeterministicReplyPlan,
    ModelConfig,
    ProfileConfig,
    ProposalPlan,
    ProviderConfig,
    build_deterministic_reply_plan,
    classify_provider_failure,
    build_openai_compatible_proposal_request,
    build_openai_compatible_request,
    build_deterministic_proposal_plan,
    execute_openai_compatible_request,
    generate_text_proposal_plan,
    parse_openai_compatible_response,
    parse_openai_compatible_proposal_response,
    probe_model_provider,
    classify_openai_compatible_response_shape,
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

    def test_load_runtime_model_config_uses_tracked_default_when_no_path_is_provided(
        self,
    ) -> None:
        config = load_runtime_model_config()
        profile = resolve_profile_config(config, "interactive_reply")

        self.assertEqual(config.providers["crs_main"].base_url, "https://api-cf.cubence.com/v1")
        self.assertEqual(config.providers["crs_main"].auth_env, "CRS_OAI_KEY")
        self.assertEqual(config.models["crs_gpt54"].provider, "crs_main")
        self.assertEqual(profile.model_ref, "crs_gpt54")
        self.assertEqual(profile.provider_failure_behavior, "user_visible_error")

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

    def test_build_openai_compatible_proposal_request_uses_structured_proposal_contract(
        self,
    ) -> None:
        request_payload = build_openai_compatible_proposal_request(
            model_id="gpt-5.5",
            user_text="check runtime status",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={
                "bundle_version": "m10.v1",
                "active_goals": [{"goal_id": "goal-1", "title": "Keep runtime healthy"}],
                "recent_memory": {"user_inputs": [], "interventions": [], "action_results": []},
                "edge_history": {"returned_entries": 1},
            },
            reasoning_effort="medium",
            verbosity="low",
        )

        rendered = str(request_payload["input"])
        self.assertEqual(request_payload["model"], "gpt-5.5")
        self.assertIn("proposal formation planner", rendered)
        self.assertIn("proposal_type", rendered)
        self.assertIn("reply", rendered)
        self.assertIn("action", rendered)
        self.assertIn("clarification", rendered)
        self.assertIn("no_intervention", rendered)
        self.assertIn("check runtime status", rendered)
        self.assertIn("runtime.status", rendered)
        self.assertIn(PROMPT_CONTEXT_VERSION, rendered)

    def test_execute_openai_compatible_proposal_request_uses_json_schema_format_when_supported(
        self,
    ) -> None:
        observed = {}

        def transport(provider, request_payload, api_key, headers):
            observed["request_payload"] = request_payload
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"proposal_type":"action",'
                                    '"response_text":"Checking runtime status.",'
                                    '"action":{"capability":"runtime.status","payload":{}},'
                                    '"rationale":{"summary":"User asked for runtime status.",'
                                    '"intent_signals":["runtime"],'
                                    '"grounding_signals":["runtime.current_health_state"]}}'
                                ),
                            }
                        ],
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
            supports_structured_output=True,
        )
        profile = ProfileConfig(
            name="proposal_formation",
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
            user_text="check runtime status",
            snapshot={"runtime.current_health_state": "healthy"},
            request_builder=build_openai_compatible_proposal_request,
            transport=transport,
        )

        text_config = observed["request_payload"]["text"]
        self.assertEqual(text_config["verbosity"], "low")
        self.assertEqual(text_config["format"]["type"], "json_schema")
        self.assertEqual(text_config["format"]["name"], "runtime_proposal")
        self.assertTrue(text_config["format"]["strict"])
        schema = text_config["format"]["schema"]
        self.assertEqual(
            schema["properties"]["proposal_type"]["enum"],
            ["reply", "action", "clarification", "no_intervention"],
        )
        self.assertIn("action", schema["required"])

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

    def test_parse_openai_compatible_response_surfaces_codex_agent_envelope_error(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "Codex agent envelope with empty output",
        ):
            parse_openai_compatible_response(
                {
                    "status": "completed",
                    "output": [],
                    "output_text": None,
                    "instructions": (
                        "You are a coding agent running in the Codex CLI, "
                        "a terminal-based coding assistant."
                    ),
                },
                profile_name="interactive_reply",
                provider_name="crs_main",
                model_id="gpt-5.4",
            )

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

    def test_parse_openai_compatible_proposal_response_returns_structured_action_plan(
        self,
    ) -> None:
        plan = parse_openai_compatible_proposal_response(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"proposal_type":"action",'
                                    '"response_text":"Checking runtime status.",'
                                    '"action":{"capability":"runtime.status","payload":{}},'
                                    '"rationale":{"summary":"User explicitly asked for runtime status.","intent_signals":["runtime","status"],"grounding_signals":["runtime.current_health_state"]}}'
                                ),
                            }
                        ],
                    }
                ]
            },
            profile_name="interactive_reply",
            provider_name="openai_main",
            model_id="gpt-5.5",
        )

        self.assertIsInstance(plan, ProposalPlan)
        self.assertEqual(plan.proposal_type, "action")
        self.assertEqual(plan.action_capability, "runtime.status")
        self.assertEqual(plan.action_payload, {})
        self.assertEqual(plan.response_text, "Checking runtime status.")
        self.assertEqual(
            plan.metadata["proposal_rationale"]["summary"],
            "User explicitly asked for runtime status.",
        )
        self.assertFalse(plan.metadata["used_deterministic_fallback"])

    def test_parse_openai_compatible_proposal_response_maps_string_reply_action_to_notification_show(
        self,
    ) -> None:
        plan = parse_openai_compatible_proposal_response(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"proposal_type":"reply",'
                                    '"response_text":"Hello!",'
                                    '"action":"respond",'
                                    '"rationale":"The user greeted the runtime."}'
                                ),
                            }
                        ],
                    }
                ]
            },
            profile_name="interactive_reply",
            provider_name="openai_main",
            model_id="gpt-5.5",
        )

        self.assertEqual(plan.proposal_type, "reply")
        self.assertEqual(plan.action_capability, "notification.show")
        self.assertEqual(plan.response_text, "Hello!")
        self.assertEqual(
            plan.metadata["proposal_rationale"]["summary"],
            "The user greeted the runtime.",
        )

    def test_parse_openai_compatible_proposal_response_defaults_reply_to_notification_show_when_action_missing(
        self,
    ) -> None:
        plan = parse_openai_compatible_proposal_response(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"proposal_type":"clarification",'
                                    '"response_text":"Please clarify.",'
                                    '"rationale":{"summary":"Need clarification."}}'
                                ),
                            }
                        ],
                    }
                ]
            },
            profile_name="interactive_reply",
            provider_name="openai_main",
            model_id="gpt-5.5",
        )

        self.assertEqual(plan.proposal_type, "clarification")
        self.assertEqual(plan.action_capability, "notification.show")
        self.assertEqual(plan.response_text, "Please clarify.")

    def test_parse_openai_compatible_proposal_response_maps_string_runtime_action_capability(
        self,
    ) -> None:
        plan = parse_openai_compatible_proposal_response(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"proposal_type":"action",'
                                    '"response_text":"Checking runtime status.",'
                                    '"action":"runtime.status",'
                                    '"rationale":{"summary":"User asked for runtime status."}}'
                                ),
                            }
                        ],
                    }
                ]
            },
            profile_name="interactive_reply",
            provider_name="openai_main",
            model_id="gpt-5.5",
        )

        self.assertEqual(plan.proposal_type, "action")
        self.assertEqual(plan.action_capability, "runtime.status")
        self.assertEqual(plan.response_text, "Checking runtime status.")

    def test_parse_openai_compatible_proposal_response_uses_response_field_for_reply_text(
        self,
    ) -> None:
        plan = parse_openai_compatible_proposal_response(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"proposal_type":"response",'
                                    '"response":"Hello! How can I help?",'
                                    '"rationale":"The user greeted the runtime."}'
                                ),
                            }
                        ],
                    }
                ]
            },
            profile_name="proposal_formation",
            provider_name="openai_main",
            model_id="gpt-5.5",
        )

        self.assertEqual(plan.proposal_type, "reply")
        self.assertEqual(plan.response_text, "Hello! How can I help?")
        self.assertEqual(plan.action_capability, "notification.show")

    def test_parse_openai_compatible_proposal_response_treats_plain_output_text_as_reply(
        self,
    ) -> None:
        plan = parse_openai_compatible_proposal_response(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "你好！我在，有什么我可以帮你的吗？",
                            }
                        ],
                    }
                ]
            },
            profile_name="proposal_formation",
            provider_name="crs_main",
            model_id="gpt-5.4",
        )

        self.assertEqual(plan.proposal_type, "reply")
        self.assertEqual(plan.response_text, "你好！我在，有什么我可以帮你的吗？")
        self.assertEqual(plan.action_capability, "notification.show")
        self.assertFalse(plan.metadata["used_deterministic_fallback"])

    def test_generate_text_proposal_plan_surfaces_malformed_structured_payload_as_provider_failure(
        self,
    ) -> None:
        self.addCleanup(
            __import__("os").environ.pop,
            "TEST_REAL_MODEL_REQUIRED_KEY_MISSING",
            None,
        )
        __import__("os").environ["TEST_REAL_MODEL_REQUIRED_KEY_MISSING"] = "test-key"

        plan = generate_text_proposal_plan(
            user_text="hello runtime",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
            profile_name="proposal_formation",
            config_path=Path("tests/fixtures/llm-config-visible-error-test.toml"),
            transport=lambda *_args: {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"proposal_type": 42, "response_text": "hello"}',
                            }
                        ],
                    }
                ]
            },
        )

        self.assertEqual(plan.proposal_type, "reply")
        self.assertEqual(plan.action_capability, "notification.show")
        self.assertIn("Real model reply unavailable", plan.response_text)
        self.assertEqual(plan.metadata["provider_failure_type"], "ValueError")
        self.assertFalse(plan.metadata["used_deterministic_fallback"])

    def test_parse_openai_compatible_proposal_response_surfaces_codex_agent_envelope_error(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "Codex agent envelope with empty output",
        ):
            parse_openai_compatible_proposal_response(
                {
                    "status": "completed",
                    "output": [],
                    "output_text": None,
                    "instructions": (
                        "You are a coding agent running in the Codex CLI, "
                        "a terminal-based coding assistant."
                    ),
                },
                profile_name="proposal_formation",
                provider_name="crs_main",
                model_id="gpt-5.4",
            )

    def test_classify_openai_compatible_response_shape_names_codex_envelope(
        self,
    ) -> None:
        shape = classify_openai_compatible_response_shape(
            {
                "status": "completed",
                "output": [],
                "output_text": None,
                "instructions": (
                    "You are a coding agent running in the Codex CLI, "
                    "a terminal-based coding assistant."
                ),
            }
        )

        self.assertEqual(shape, "codex_agent_envelope_empty_output")

    def test_classify_openai_compatible_response_shape_names_completed_empty_output(
        self,
    ) -> None:
        shape = classify_openai_compatible_response_shape(
            {
                "status": "completed",
                "output": [],
                "instructions": "Return exactly one JSON object.",
            }
        )

        self.assertEqual(shape, "completed_empty_output")

    def test_generate_text_proposal_plan_retries_transient_bad_response_shape(
        self,
    ) -> None:
        self.addCleanup(
            __import__("os").environ.pop,
            "TEST_REAL_MODEL_REQUIRED_KEY_MISSING",
            None,
        )
        __import__("os").environ["TEST_REAL_MODEL_REQUIRED_KEY_MISSING"] = "test-key"
        calls = []

        def transport(provider, request_payload, api_key, headers):
            calls.append(request_payload)
            if len(calls) == 1:
                return {
                    "status": "completed",
                    "output": [],
                    "output_text": None,
                    "instructions": (
                        "You are a coding agent running in the Codex CLI, "
                        "a terminal-based coding assistant."
                    ),
                }
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"proposal_type":"reply",'
                                    '"response_text":"Hello after retry.",'
                                    '"action":null,'
                                    '"rationale":{"summary":"Retry recovered."}}'
                                ),
                            }
                        ],
                    }
                ]
            }

        plan = generate_text_proposal_plan(
            user_text="hello runtime",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
            profile_name="proposal_formation",
            config_path=Path("tests/fixtures/llm-config-visible-error-test.toml"),
            transport=transport,
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(plan.response_text, "Hello after retry.")
        self.assertEqual(plan.metadata["provider_attempt_count"], 2)
        self.assertEqual(plan.metadata["provider_retry_count"], 1)
        self.assertEqual(
            plan.metadata["provider_retried_shapes"],
            ["codex_agent_envelope_empty_output"],
        )

    def test_generate_text_proposal_plan_retries_completed_empty_output_shape(
        self,
    ) -> None:
        self.addCleanup(
            __import__("os").environ.pop,
            "TEST_REAL_MODEL_REQUIRED_KEY_MISSING",
            None,
        )
        __import__("os").environ["TEST_REAL_MODEL_REQUIRED_KEY_MISSING"] = "test-key"
        calls = []

        def transport(provider, request_payload, api_key, headers):
            calls.append(request_payload)
            if len(calls) == 1:
                return {
                    "status": "completed",
                    "output": [],
                    "instructions": "Return exactly one JSON object.",
                }
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"proposal_type":"reply",'
                                    '"response_text":"Recovered from empty output.",'
                                    '"action":null,'
                                    '"rationale":{"summary":"Retry recovered."}}'
                                ),
                            }
                        ],
                    }
                ]
            }

        plan = generate_text_proposal_plan(
            user_text="hello runtime",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
            profile_name="proposal_formation",
            config_path=Path("tests/fixtures/llm-config-visible-error-test.toml"),
            transport=transport,
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(plan.response_text, "Recovered from empty output.")
        self.assertEqual(
            plan.metadata["provider_retried_shapes"],
            ["completed_empty_output"],
        )

    def test_generate_text_proposal_plan_sanitizes_exhausted_bad_shape_for_user(
        self,
    ) -> None:
        self.addCleanup(
            __import__("os").environ.pop,
            "TEST_REAL_MODEL_REQUIRED_KEY_MISSING",
            None,
        )
        __import__("os").environ["TEST_REAL_MODEL_REQUIRED_KEY_MISSING"] = "test-key"
        calls = []

        def transport(provider, request_payload, api_key, headers):
            calls.append(request_payload)
            return {
                "status": "completed",
                "output": [],
                "output_text": None,
                "instructions": (
                    "You are a coding agent running in the Codex CLI, "
                    "a terminal-based coding assistant."
                ),
            }

        plan = generate_text_proposal_plan(
            user_text="hello runtime",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
            profile_name="proposal_formation",
            config_path=Path("tests/fixtures/llm-config-visible-error-test.toml"),
            transport=transport,
        )

        self.assertIn("provider returned an incompatible response shape", plan.response_text)
        self.assertNotIn("Codex agent envelope", plan.response_text)
        self.assertEqual(calls[0]["text"]["format"]["type"], "json_schema")
        self.assertEqual(plan.metadata["provider_wire_api"], "responses")
        self.assertEqual(plan.metadata["provider_request_format"], "json_schema")
        self.assertEqual(
            plan.metadata["provider_failure_shape"],
            "codex_agent_envelope_empty_output",
        )
        self.assertIn("Codex agent envelope", plan.metadata["provider_failure_reason"])
        self.assertEqual(plan.metadata["provider_attempt_count"], 2)

    def test_build_deterministic_proposal_plan_supports_all_m13_proposal_classes(self) -> None:
        clarification = build_deterministic_proposal_plan(
            user_text="help",
            profile_name="interactive_reply",
            fallback_reason="provider_unavailable",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
        )
        self.assertEqual(clarification.proposal_type, "clarification")
        self.assertEqual(clarification.action_capability, "notification.show")
        self.assertIn("clarify", clarification.metadata["proposal_rationale"]["summary"].lower())
        self.assertTrue(clarification.metadata["used_deterministic_fallback"])

        action = build_deterministic_proposal_plan(
            user_text="check runtime status",
            profile_name="interactive_reply",
            fallback_reason="provider_unavailable",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
        )
        self.assertEqual(action.proposal_type, "action")
        self.assertEqual(action.action_capability, "runtime.status")
        self.assertIn("status", action.metadata["proposal_rationale"]["summary"].lower())

        no_intervention = build_deterministic_proposal_plan(
            user_text="thanks",
            profile_name="interactive_reply",
            fallback_reason="provider_unavailable",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
        )
        self.assertEqual(no_intervention.proposal_type, "no_intervention")
        self.assertIsNone(no_intervention.action_capability)
        self.assertIn("no intervention", no_intervention.metadata["proposal_rationale"]["summary"].lower())

        reply = build_deterministic_proposal_plan(
            user_text="hello runtime",
            profile_name="interactive_reply",
            fallback_reason="provider_unavailable",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
        )
        self.assertEqual(reply.proposal_type, "reply")
        self.assertEqual(reply.action_capability, "notification.show")
        self.assertEqual(reply.response_text, "Runtime heard: hello runtime")

    def test_generate_text_proposal_plan_falls_back_to_grounded_deterministic_plan(self) -> None:
        plan = generate_text_proposal_plan(
            user_text="check runtime status",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
            profile_name="interactive_reply",
            config_path=Path("tests/fixtures/llm-config-test.toml"),
            transport=lambda *_args: (_ for _ in ()).throw(OSError("offline")),
        )

        self.assertEqual(plan.proposal_type, "action")
        self.assertEqual(plan.action_capability, "runtime.status")
        self.assertTrue(plan.metadata["used_deterministic_fallback"])
        self.assertEqual(plan.metadata["fallback_reason"], "provider_unavailable")

    def test_generate_text_proposal_plan_can_surface_provider_failure_as_visible_error_reply(
        self,
    ) -> None:
        plan = generate_text_proposal_plan(
            user_text="hello runtime",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
            profile_name="proposal_formation",
            config_path=Path("tests/fixtures/llm-config-visible-error-test.toml"),
        )

        self.assertEqual(plan.proposal_type, "reply")
        self.assertEqual(plan.action_capability, "notification.show")
        self.assertIn("Real model reply unavailable", plan.response_text)
        self.assertIn(
            "TEST_REAL_MODEL_REQUIRED_KEY_MISSING",
            plan.response_text,
        )
        self.assertEqual(
            plan.metadata["provider_failure_behavior"],
            "user_visible_error",
        )
        self.assertEqual(plan.metadata["provider_failure_type"], "OSError")
        self.assertFalse(plan.metadata["used_deterministic_fallback"])

    def test_generate_text_proposal_plan_sends_structured_proposal_request_to_transport(
        self,
    ) -> None:
        observed = {}

        def transport(provider, request_payload, api_key, headers):
            observed["request_payload"] = request_payload
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"proposal_type":"action",'
                                    '"response_text":"Checking runtime status.",'
                                    '"action":{"capability":"runtime.status","payload":{}},'
                                    '"rationale":{"summary":"User explicitly asked for runtime status."}}'
                                ),
                            }
                        ],
                    }
                ]
            }

        self.addCleanup(__import__("os").environ.pop, "OPENAI_API_KEY", None)
        __import__("os").environ["OPENAI_API_KEY"] = "test-key"

        plan = generate_text_proposal_plan(
            user_text="check runtime status",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
            profile_name="proposal_formation",
            config_path=Path("tests/fixtures/llm-config-test.toml"),
            transport=transport,
        )

        rendered = str(observed["request_payload"]["input"])
        self.assertEqual(plan.proposal_type, "action")
        self.assertEqual(plan.action_capability, "runtime.status")
        self.assertIn("proposal formation planner", rendered)
        self.assertIn("Return exactly one JSON object", rendered)
        self.assertNotIn("Generate one concise user-facing reply", rendered)

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

    def test_execute_openai_compatible_request_rejects_unsupported_wire_api(
        self,
    ) -> None:
        provider = ProviderConfig(
            name="openai_main",
            adapter_type="openai_compatible",
            base_url="https://api.openai.com/v1",
            wire_api="chat_completions",
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

        with self.assertRaisesRegex(ValueError, "unsupported wire_api"):
            execute_openai_compatible_request(
                provider=provider,
                model=model,
                profile=profile,
                user_text="hello runtime",
                transport=lambda *_args: {"output": []},
            )

    def test_classify_provider_failure_covers_auth_rate_limit_timeout_http_protocol_and_parser(
        self,
    ) -> None:
        self.assertEqual(
            classify_provider_failure(OSError("missing auth env: CRS_OAI_KEY")),
            "auth",
        )
        self.assertEqual(
            classify_provider_failure(TimeoutError("timed out")),
            "timeout",
        )
        self.assertEqual(
            classify_provider_failure(
                __import__("urllib.error").error.HTTPError(
                    url="https://example.test",
                    code=429,
                    msg="rate limited",
                    hdrs={},
                    fp=None,
                )
            ),
            "rate_limit",
        )
        self.assertEqual(
            classify_provider_failure(
                __import__("urllib.error").error.HTTPError(
                    url="https://example.test",
                    code=500,
                    msg="server error",
                    hdrs={},
                    fp=None,
                )
            ),
            "http_server",
        )
        self.assertEqual(
            classify_provider_failure(
                __import__("urllib.error").error.HTTPError(
                    url="https://example.test",
                    code=400,
                    msg="bad request",
                    hdrs={},
                    fp=None,
                )
            ),
            "http_client",
        )
        self.assertEqual(
            classify_provider_failure(ValueError("unsupported wire_api for openai_compatible: chat")),
            "protocol_shape",
        )
        self.assertEqual(
            classify_provider_failure(__import__("json").JSONDecodeError("bad", "x", 0)),
            "parser",
        )

    def test_probe_model_provider_reports_success_without_exposing_secret(self) -> None:
        self.addCleanup(__import__("os").environ.pop, "OPENAI_API_KEY", None)
        __import__("os").environ["OPENAI_API_KEY"] = "secret-test-key"

        result = probe_model_provider(
            profile_name="proposal_formation",
            config_path=Path("tests/fixtures/llm-config-test.toml"),
            transport=lambda *_args: {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"proposal_type":"reply",'
                                    '"response_text":"probe ok",'
                                    '"action":null,'
                                    '"rationale":{"summary":"probe",'
                                    '"intent_signals":["probe"],'
                                    '"grounding_signals":[]}}'
                                ),
                            }
                        ],
                    }
                ]
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["profile"], "proposal_formation")
        self.assertEqual(result["provider"], "openai_main")
        self.assertEqual(result["model"], "gpt-5.5")
        self.assertEqual(result["wire_api"], "responses")
        self.assertTrue(result["auth_env_present"])
        self.assertNotIn("secret-test-key", str(result))
        self.assertEqual(result["response_shape"], "message_output_text")
        self.assertGreaterEqual(result["latency_ms"], 0)

    def test_probe_model_provider_reports_controlled_failure_classification(
        self,
    ) -> None:
        self.addCleanup(__import__("os").environ.pop, "TEST_REAL_MODEL_REQUIRED_KEY_MISSING", None)
        __import__("os").environ["TEST_REAL_MODEL_REQUIRED_KEY_MISSING"] = "test-key"

        result = probe_model_provider(
            profile_name="proposal_formation",
            config_path=Path("tests/fixtures/llm-config-visible-error-test.toml"),
            transport=lambda *_args: {
                "status": "completed",
                "output": [],
                "instructions": (
                    "You are a coding agent running in the Codex CLI, "
                    "a terminal-based coding assistant."
                ),
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["failure_class"], "protocol_shape")
        self.assertEqual(result["response_shape"], "codex_agent_envelope_empty_output")
        self.assertIn("provider returned an incompatible response shape", result["user_visible_reason"])


if __name__ == "__main__":
    unittest.main()
