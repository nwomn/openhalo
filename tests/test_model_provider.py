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
    build_deterministic_post_action_proposal_plan,
    build_deterministic_proposal_plan,
    execute_openai_compatible_request,
    generate_post_observation_proposal_plan,
    generate_post_action_proposal_plan,
    generate_text_proposal_plan,
    parse_openai_compatible_response,
    parse_openai_compatible_proposal_response,
    probe_model_provider,
    classify_openai_compatible_response_shape,
    load_runtime_model_config,
    resolve_profile_config,
)
from personal_runtime.model_provider_probe import build_model_provider_probe_parser
from personal_runtime.prompt_context import PROMPT_CONTEXT_VERSION


class ModelProviderConfigTests(unittest.TestCase):
    def test_model_provider_probe_parser_accepts_runtime_config_path(self) -> None:
        parser = build_model_provider_probe_parser()

        args = parser.parse_args(
            [
                "--runtime-config-path",
                "tests/fixtures/llm-config-test.toml",
            ]
        )

        self.assertEqual(
            args.runtime_config_path,
            "tests/fixtures/llm-config-test.toml",
        )

    def test_model_provider_probe_parser_keeps_llm_config_path_compatibility(
        self,
    ) -> None:
        parser = build_model_provider_probe_parser()

        args = parser.parse_args(
            [
                "--llm-config-path",
                "tests/fixtures/llm-config-test.toml",
            ]
        )

        self.assertEqual(
            args.runtime_config_path,
            "tests/fixtures/llm-config-test.toml",
        )

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
        self.assertEqual(config.providers["openai_main"].api_key, "")
        self.assertEqual(config.models["openai_gpt55"].provider, "openai_main")
        self.assertEqual(profile.model_ref, "openai_gpt55")
        self.assertEqual(profile.reasoning_effort, "medium")
        self.assertEqual(profile.verbosity, "low")

    def test_load_runtime_model_config_uses_runtime_config_when_no_path_is_provided(
        self,
    ) -> None:
        config = load_runtime_model_config(
            Path("config/runtime-config.example.toml")
        )
        profile = resolve_profile_config(config, "interactive_reply")

        self.assertEqual(
            config.providers["openai_main"].base_url,
            "https://api-dmit.cubence.com/v1",
        )
        self.assertEqual(
            config.providers["openai_main"].api_key,
            "replace-with-provider-api-key",
        )
        self.assertEqual(
            config.providers["openai_main"].default_headers,
            {"User-Agent": "openhalo-runtime/0.1"},
        )
        self.assertEqual(config.models["openai_gpt55"].provider, "openai_main")
        self.assertEqual(profile.model_ref, "openai_gpt55")
        self.assertEqual(config.models["openai_gpt55"].model_id, "gpt-5.5")
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
        self.assertIn("target_device_hint", rendered)
        self.assertIn("action", rendered)
        self.assertIn("no_intervention", rendered)
        self.assertNotIn("reply|action|clarification", rendered)
        self.assertIn("check runtime status", rendered)
        self.assertIn("runtime.status", rendered)
        self.assertIn(PROMPT_CONTEXT_VERSION, rendered)

    def test_build_deterministic_post_action_proposal_plan_summarizes_runtime_status_result(
        self,
    ) -> None:
        plan = build_deterministic_post_action_proposal_plan(
            interaction_id="interaction-1",
            prior_proposal={
                "proposal_type": "action",
                "action_capability": "runtime.status",
            },
            result={
                "status": "ok",
                "capability": "runtime.status",
                "details": {"state": "running", "pid": 42137},
            },
            profile_name="proposal_formation",
            fallback_reason="deterministic_post_action",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
        )

        self.assertEqual(plan.proposal_type, "action")
        self.assertEqual(plan.action_capability, "notification.show")
        self.assertEqual(
            plan.action_payload["message"],
            "Runtime status: running (pid 42137).",
        )
        self.assertEqual(
            plan.metadata["proposal_rationale"]["trigger"],
            "action_result",
        )
        self.assertEqual(
            plan.metadata["proposal_rationale"]["parent_action_capability"],
            "runtime.status",
        )

    def test_build_deterministic_post_action_proposal_plan_can_request_follow_up_action(
        self,
    ) -> None:
        plan = build_deterministic_post_action_proposal_plan(
            interaction_id="interaction-1",
            prior_proposal={
                "proposal_type": "action",
                "action_capability": "runtime.status",
            },
            result={
                "status": "ok",
                "capability": "runtime.status",
                "details": {"state": "degraded", "needs_follow_up": True},
            },
            profile_name="proposal_formation",
            fallback_reason="deterministic_post_action",
        )

        self.assertEqual(plan.proposal_type, "action")
        self.assertEqual(plan.action_capability, "runtime.status")
        self.assertEqual(plan.action_payload, {})
        self.assertEqual(
            plan.metadata["proposal_rationale"]["summary"],
            "Follow-up runtime status action selected because the prior result requested another check.",
        )

    def test_build_deterministic_post_action_proposal_plan_explains_missing_target(
        self,
    ) -> None:
        plan = build_deterministic_post_action_proposal_plan(
            interaction_id="interaction-1",
            prior_proposal={
                "proposal_type": "action",
                "action_capability": "notification.show",
            },
            result={
                "status": "failed",
                "reason": "target_missing",
                "capability": "notification.show",
                "device_id": "android-edge-1",
                "details": {"target_device_id": "android-edge-1"},
            },
            profile_name="proposal_formation",
            fallback_reason="deterministic_post_action",
            interaction={
                "source_device_id": "terminal-edge-1",
                "participant_device_ids": ["terminal-edge-1", "android-edge-1"],
                "primary_action": {"target_device_id": "android-edge-1"},
            },
        )

        self.assertEqual(plan.proposal_type, "reply")
        self.assertEqual(plan.action_capability, "notification.show")
        self.assertIn("android-edge-1", plan.response_text)
        self.assertIn("not connected", plan.response_text)

    def test_build_deterministic_post_action_proposal_plan_can_finish_silently(
        self,
    ) -> None:
        plan = build_deterministic_post_action_proposal_plan(
            interaction_id="interaction-1",
            prior_proposal={
                "proposal_type": "reply",
                "action_capability": "notification.show",
            },
            result={
                "status": "ok",
                "capability": "notification.show",
                "details": {"message": "Hello! Runtime here."},
            },
            profile_name="proposal_formation",
            fallback_reason="deterministic_post_action",
        )

        self.assertEqual(plan.proposal_type, "no_intervention")
        self.assertIsNone(plan.action_capability)
        self.assertEqual(plan.action_payload, {})

    def test_generate_post_action_proposal_plan_uses_model_backed_action_result_context(
        self,
    ) -> None:
        calls = []

        def transport(_provider, request_payload, *_args):
            calls.append(request_payload)
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"proposal_type":"reply",'
                                    '"response_text":"The runtime is running and using about 27 MB RSS.",'
                                    '"action":{"capability":"notification.show","payload":{"message":"The runtime is running and using about 27 MB RSS."}},'
                                    '"rationale":{"summary":"Summarized runtime.status action_result including memory.",'
                                    '"intent_signals":["runtime.status"],'
                                    '"grounding_signals":["runtime.current_health_state"]}}'
                                ),
                            }
                        ],
                    }
                ]
            }

        plan = generate_post_action_proposal_plan(
            interaction_id="interaction-1",
            prior_proposal={
                "proposal_type": "action",
                "action_capability": "runtime.status",
            },
            result={
                "status": "ok",
                "capability": "runtime.status",
                "details": {
                    "state": "running",
                    "pid": 42137,
                    "memory_rss_bytes": 28114944,
                },
            },
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
            config_path=Path("config/runtime-config.example.toml"),
            transport=transport,
        )

        self.assertEqual(plan.proposal_type, "reply")
        self.assertEqual(plan.action_capability, "notification.show")
        self.assertEqual(
            plan.response_text,
            "The runtime is running and using about 27 MB RSS.",
        )
        self.assertFalse(plan.metadata["used_deterministic_fallback"])

        self.assertEqual(plan.metadata["post_action_trigger"], "action_result")
        rendered_request = str(calls[0]["input"])
        self.assertIn('"memory_rss_bytes": 28114944', rendered_request)
        self.assertIn('"interaction_id": "interaction-1"', rendered_request)

    def test_generate_post_action_proposal_plan_uses_decision_brief_context(
        self,
    ) -> None:
        calls = []

        def transport(_provider, request_payload, *_args):
            calls.append(request_payload)
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"proposal_type":"reply",'
                                    '"response_text":"Delivered hello to your phone.",'
                                    '"action":{"capability":"notification.show","payload":{}},'
                                    '"rationale":{"summary":"Acknowledged the source terminal.",'
                                    '"intent_signals":["source ack"],'
                                    '"grounding_signals":["decision brief"]}}'
                                ),
                            }
                        ],
                    }
                ]
            }

        generate_post_action_proposal_plan(
            interaction_id="interaction-1",
            interaction={
                "interaction_id": "interaction-1",
                "source_device_id": "terminal-edge-1",
                "participant_device_ids": ["terminal-edge-1", "android-edge-1"],
                "primary_action": {"target_device_id": "android-edge-1"},
            },
            prior_proposal={
                "proposal_type": "reply",
                "action_capability": "notification.show",
            },
            result={
                "status": "ok",
                "capability": "notification.show",
                "details": {"message": "hello"},
            },
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
            config_path=Path("config/runtime-config.example.toml"),
            transport=transport,
        )

        rendered_request = str(calls[0]["input"])
        self.assertIn("Decision task:", rendered_request)
        self.assertIn("source_device_id: terminal-edge-1", rendered_request)
        self.assertIn("target_device_id: android-edge-1", rendered_request)
        self.assertIn("source_ack_required: true", rendered_request)
        self.assertNotIn("Post-action deliberation: inspect the action_result", rendered_request)

    def test_generate_post_action_proposal_plan_recovers_after_two_bad_shapes(
        self,
    ) -> None:
        calls = []

        def transport(_provider, request_payload, *_args):
            calls.append(request_payload)
            if len(calls) <= 2:
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
                                    '{"proposal_type":"no_intervention",'
                                    '"response_text":"",'
                                    '"action":null,'
                                    '"rationale":{"summary":"Action result handled after retry.",'
                                    '"intent_signals":["action_result"],'
                                    '"grounding_signals":["runtime.current_health_state"]}}'
                                ),
                            }
                        ],
                    }
                ]
            }

        plan = generate_post_action_proposal_plan(
            interaction_id="interaction-1",
            prior_proposal={
                "proposal_type": "action",
                "action_capability": "notification.show",
            },
            result={
                "status": "ok",
                "capability": "notification.show",
                "details": {"message": "hello"},
            },
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
            config_path=Path("tests/fixtures/llm-config-visible-error-test.toml"),
            transport=transport,
        )

        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0]["text"]["format"]["type"], "json_schema")
        self.assertNotIn("format", calls[1]["text"])
        self.assertNotIn("format", calls[2]["text"])
        self.assertEqual(plan.proposal_type, "no_intervention")
        self.assertFalse(plan.metadata["used_deterministic_fallback"])
        self.assertEqual(plan.metadata["provider_attempt_count"], 3)
        self.assertEqual(plan.metadata["provider_retry_count"], 2)
        self.assertEqual(
            plan.metadata["provider_retried_shapes"],
            [
                "codex_agent_envelope_empty_output",
                "codex_agent_envelope_empty_output",
            ],
        )
        self.assertEqual(plan.metadata["provider_request_format"], "prompt_json")
        self.assertEqual(plan.metadata["post_action_trigger"], "action_result")

    def test_post_action_model_no_intervention_is_not_rewritten_to_source_ack(
        self,
    ) -> None:
        def transport(_provider, _request_payload, *_args):
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"proposal_type":"no_intervention",'
                                    '"response_text":"",'
                                    '"action":null,'
                                    '"rationale":{"summary":"Source acknowledgement was delivered; stop the loop.",'
                                    '"intent_signals":["action_result"],'
                                    '"grounding_signals":[]}}'
                                ),
                            }
                        ],
                    }
                ]
            }

        plan = generate_post_action_proposal_plan(
            interaction_id="interaction-1",
            interaction={
                "interaction_id": "interaction-1",
                "source_device_id": "terminal-edge-1",
                "participant_device_ids": ["terminal-edge-1", "android-edge-1"],
                "primary_action": {
                    "capability": "notification.show",
                    "target_device_id": "android-edge-1",
                },
            },
            prior_proposal={
                "proposal_type": "reply",
                "action_capability": "notification.show",
            },
            result={
                "status": "ok",
                "capability": "notification.show",
                "details": {
                    "message": "Sent to your phone.",
                    "delivered_via": "terminal.stdout",
                },
            },
            config_path=Path("tests/fixtures/llm-config-test.toml"),
            transport=transport,
        )

        self.assertEqual(plan.proposal_type, "no_intervention")
        self.assertIsNone(plan.action_capability)
        self.assertNotEqual(
            plan.metadata.get("post_action_semantics"),
            "source_ack",
        )

    def test_deterministic_post_action_fallback_does_not_decide_source_ack(
        self,
    ) -> None:
        plan = build_deterministic_post_action_proposal_plan(
            interaction_id="interaction-1",
            interaction={
                "interaction_id": "interaction-1",
                "source_device_id": "terminal-edge-1",
                "participant_device_ids": ["terminal-edge-1", "android-edge-1"],
                "primary_action": {
                    "capability": "notification.show",
                    "target_device_id": "android-edge-1",
                },
            },
            prior_proposal={
                "proposal_type": "reply",
                "action_capability": "notification.show",
            },
            result={
                "status": "ok",
                "capability": "notification.show",
                "details": {
                    "message": "hello",
                    "delivered_via": "android.urgent_alert",
                },
            },
            profile_name="proposal_formation",
            fallback_reason="provider_unavailable",
        )

        self.assertEqual(plan.proposal_type, "no_intervention")
        self.assertIsNone(plan.action_capability)
        self.assertEqual(
            plan.metadata["post_action_semantics"],
            "fallback_no_action_loop_decision",
        )
        self.assertNotIn("source_ack", str(plan.action_payload))

    def test_generate_post_action_proposal_plan_isolates_observed_provider_failure_before_model(
        self,
    ) -> None:
        calls = []

        plan = generate_post_action_proposal_plan(
            interaction_id="interaction-1",
            interaction={
                "interaction_id": "interaction-1",
                "source_device_id": "terminal-edge-1",
                "participant_device_ids": ["terminal-edge-1", "android-edge-1"],
                "primary_action": {"target_device_id": "android-edge-1"},
            },
            prior_proposal={
                "proposal_type": "reply",
                "action_capability": "notification.show",
                "metadata": {"provider_failure_class": "protocol_shape"},
            },
            result={
                "status": "ok",
                "capability": "notification.show",
                "details": {
                    "message": (
                        "Real model reply unavailable: provider returned an "
                        "incompatible response shape; please retry shortly"
                    )
                },
            },
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
            config_path=Path("config/runtime-config.example.toml"),
            transport=lambda *_args: calls.append(True),
        )

        self.assertEqual(calls, [])
        self.assertEqual(plan.proposal_type, "provider_failure")
        self.assertIsNone(plan.action_capability)
        self.assertEqual(plan.action_payload, {})
        self.assertEqual(plan.metadata["runtime_message_channel"], "provider_failure")
        self.assertEqual(plan.metadata["provider_failure_observed"], True)
        self.assertNotIn("Real model reply unavailable", plan.response_text)
        self.assertNotIn("incompatible response shape", plan.response_text)

    def test_generate_post_observation_proposal_plan_uses_model_backed_observation_context(
        self,
    ) -> None:
        calls = []

        def transport(_provider, request_payload, *_args):
            calls.append(request_payload)
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"proposal_type":"action",'
                                    '"response_text":"Checking runtime status after degraded health.",'
                                    '"action":{"capability":"runtime.status","payload":{}},'
                                    '"rationale":{"summary":"Fresh degraded runtime health changed the open interaction.",'
                                    '"intent_signals":["runtime.health_state"],'
                                    '"grounding_signals":["runtime.current_health_state"]}}'
                                ),
                            }
                        ],
                    }
                ]
            }

        plan = generate_post_observation_proposal_plan(
            interaction_id="interaction-1",
            prior_proposal={
                "proposal_type": "action",
                "action_capability": "runtime.status",
            },
            observations=[
                {
                    "name": "runtime.health_state",
                    "value": "degraded",
                    "observed_at": "2026-06-21T10:10:30Z",
                    "confidence": 1.0,
                }
            ],
            snapshot={"runtime.current_health_state": "degraded"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
            config_path=Path("config/runtime-config.example.toml"),
            transport=transport,
        )

        self.assertEqual(plan.proposal_type, "action")
        self.assertEqual(plan.action_capability, "runtime.status")
        self.assertFalse(plan.metadata["used_deterministic_fallback"])
        self.assertEqual(plan.metadata["post_observation_trigger"], "observation")
        rendered_request = str(calls[0]["input"])
        self.assertIn('"runtime.health_state"', rendered_request)
        self.assertIn('"value": "degraded"', rendered_request)
        self.assertIn('"interaction_id": "interaction-1"', rendered_request)

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
            api_key="test-key",
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

    def test_parse_openai_compatible_proposal_response_preserves_target_device_hint(
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
                                    '"response_text":"Sending hello to your phone.",'
                                    '"target_device_hint":"android-edge-1",'
                                    '"action":{"capability":"notification.show","payload":{"message":"hello"}},'
                                    '"rationale":{"summary":"User explicitly targeted the phone.","intent_signals":["phone"],"grounding_signals":["android-edge-1"]}}'
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

        self.assertEqual(plan.proposal_type, "action")
        self.assertEqual(plan.action_capability, "notification.show")
        self.assertEqual(plan.target_device_hint, "android-edge-1")

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

    def test_parse_openai_compatible_proposal_response_promotes_targeted_clarification_action(
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
                                    '"response_text":"你是想让我再试着给手机发送通知吗？",'
                                    '"target_device_hint":"android-edge-782d0247",'
                                    '"action":{"capability":"notification.show",'
                                    '"payload":{"message":"你是想让我再试着给手机发送通知吗？"}},'
                                    '"rationale":{"summary":"User asked to check the phone again.",'
                                    '"intent_signals":["你再看看呢"],'
                                    '"grounding_signals":["known phone target"]}}'
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
        self.assertEqual(plan.action_capability, "notification.show")
        self.assertEqual(plan.target_device_hint, "android-edge-782d0247")

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

        self.assertEqual(plan.proposal_type, "provider_failure")
        self.assertIsNone(plan.action_capability)
        self.assertEqual(plan.action_payload, {})
        self.assertIn("Real model reply unavailable", plan.response_text)
        self.assertEqual(plan.metadata["runtime_message_channel"], "provider_failure")
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
        self.assertEqual(calls[0]["text"]["format"]["type"], "json_schema")
        self.assertNotIn("format", calls[1]["text"])
        self.assertEqual(plan.response_text, "Hello after retry.")
        self.assertEqual(plan.metadata["provider_attempt_count"], 2)
        self.assertEqual(plan.metadata["provider_retry_count"], 1)
        self.assertEqual(
            plan.metadata["provider_retried_shapes"],
            ["codex_agent_envelope_empty_output"],
        )
        self.assertEqual(plan.metadata["provider_request_format"], "prompt_json")

    def test_generate_text_proposal_plan_retries_completed_empty_output_shape(
        self,
    ) -> None:
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
        self.assertEqual(plan.metadata["provider_attempt_count"], 3)

    def test_build_deterministic_proposal_plan_uses_action_for_visible_responses(self) -> None:
        help_action = build_deterministic_proposal_plan(
            user_text="help",
            profile_name="interactive_reply",
            fallback_reason="provider_unavailable",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
        )
        self.assertEqual(help_action.proposal_type, "action")
        self.assertEqual(help_action.action_capability, "notification.show")
        self.assertIn("clarify", help_action.metadata["proposal_rationale"]["summary"].lower())
        self.assertTrue(help_action.metadata["used_deterministic_fallback"])

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
        self.assertEqual(reply.proposal_type, "action")
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

    def test_generate_text_proposal_plan_isolates_provider_failure_from_normal_reply_action(
        self,
    ) -> None:
        plan = generate_text_proposal_plan(
            user_text="hello runtime",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
            profile_name="proposal_formation",
            config_path=Path("tests/fixtures/llm-config-missing-key-test.toml"),
        )

        self.assertEqual(plan.proposal_type, "provider_failure")
        self.assertIsNone(plan.action_capability)
        self.assertEqual(plan.action_payload, {})
        self.assertIn("Real model reply unavailable", plan.response_text)
        self.assertIn(
            "missing provider credential: openai_main",
            plan.response_text,
        )
        self.assertEqual(plan.metadata["runtime_message_channel"], "provider_failure")
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

        plan = generate_text_proposal_plan(
            user_text="check runtime status",
            snapshot={"runtime.current_health_state": "healthy"},
            grounding={"active_goals": [{"goal_id": "goal-1"}]},
            profile_name="proposal_formation",
            config_path=Path("tests/fixtures/llm-config-visible-error-test.toml"),
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
            api_key="test-key",
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

    def test_execute_openai_compatible_request_uses_runtime_config_api_key(
        self,
    ) -> None:
        observed = {}

        def transport(provider, request_payload, api_key, headers):
            observed["api_key"] = api_key
            observed["authorization"] = headers["Authorization"]
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
            api_key="config-test-key",
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

        execute_openai_compatible_request(
            provider=provider,
            model=model,
            profile=profile,
            user_text="hello runtime",
            transport=transport,
        )

        self.assertEqual(observed["api_key"], "config-test-key")
        self.assertEqual(observed["authorization"], "Bearer config-test-key")

    def test_execute_openai_compatible_request_rejects_unsupported_wire_api(
        self,
    ) -> None:
        provider = ProviderConfig(
            name="openai_main",
            adapter_type="openai_compatible",
            base_url="https://api.openai.com/v1",
            wire_api="chat_completions",
            api_key="test-key",
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
            classify_provider_failure(
                OSError("missing provider credential: openai_main")
            ),
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
        result = probe_model_provider(
            profile_name="proposal_formation",
            config_path=Path("tests/fixtures/llm-config-visible-error-test.toml"),
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
        self.assertEqual(result["auth_source"], "runtime_config")
        self.assertEqual(
            result["auth_reference"],
            "llm.providers.openai_main.api_key",
        )
        self.assertTrue(result["auth_present"])
        self.assertNotIn("test-key", str(result))
        self.assertEqual(result["response_shape"], "message_output_text")
        self.assertGreaterEqual(result["latency_ms"], 0)

    def test_probe_model_provider_reports_controlled_failure_classification(
        self,
    ) -> None:
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

    def test_probe_model_provider_retries_transient_bad_response_shape(
        self,
    ) -> None:
        calls = []

        def transport(_provider, request_payload, *_args):
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
                                    '"response_text":"probe recovered",'
                                    '"action":null,'
                                    '"rationale":{"summary":"probe retry",'
                                    '"intent_signals":["probe"],'
                                    '"grounding_signals":[]}}'
                                ),
                            }
                        ],
                    }
                ]
            }

        result = probe_model_provider(
            profile_name="proposal_formation",
            config_path=Path("tests/fixtures/llm-config-visible-error-test.toml"),
            transport=transport,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["text"]["format"]["type"], "json_schema")
        self.assertNotIn("format", calls[1]["text"])
        self.assertEqual(result["attempt_count"], 2)
        self.assertEqual(result["retry_count"], 1)
        self.assertEqual(
            result["retried_shapes"],
            ["codex_agent_envelope_empty_output"],
        )
        self.assertEqual(result["request_format"], "prompt_json")
        self.assertEqual(result["response_shape"], "message_output_text")


if __name__ == "__main__":
    unittest.main()
