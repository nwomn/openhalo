"""Provider/model/profile configuration for the first M9 runtime slice."""

from __future__ import annotations

import json
import os
import time
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from personal_runtime.prompt_context import build_prompt_context_package


DEFAULT_CONFIG_PATH = Path("config/llm-config.toml")
PROPOSAL_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["proposal_type", "response_text", "action", "rationale"],
    "properties": {
        "proposal_type": {
            "type": "string",
            "enum": ["reply", "action", "clarification", "no_intervention"],
        },
        "response_text": {"type": "string"},
        "action": {
            "anyOf": [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["capability", "payload"],
                    "properties": {
                        "capability": {"type": "string"},
                        "payload": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {},
                            "required": [],
                        },
                    },
                },
                {"type": "null"},
            ]
        },
        "rationale": {
            "type": "object",
            "additionalProperties": False,
            "required": ["summary", "intent_signals", "grounding_signals"],
            "properties": {
                "summary": {"type": "string"},
                "intent_signals": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "grounding_signals": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
    },
}


@dataclass(slots=True)
class ProviderConfig:
    name: str
    adapter_type: str
    base_url: str
    wire_api: str
    auth_env: str
    timeout_seconds: int = 30
    default_headers: dict[str, str] | None = None


@dataclass(slots=True)
class ModelConfig:
    name: str
    provider: str
    model_id: str
    supports_structured_output: bool = False
    supports_tools: bool = False


@dataclass(slots=True)
class ProfileConfig:
    name: str
    model_ref: str
    reasoning_effort: str = "medium"
    verbosity: str = "low"
    provider_failure_behavior: str = "deterministic"


@dataclass(slots=True)
class RuntimeModelConfig:
    providers: dict[str, ProviderConfig]
    models: dict[str, ModelConfig]
    profiles: dict[str, ProfileConfig]


@dataclass(slots=True)
class DeterministicReplyPlan:
    message: str
    metadata: dict


@dataclass(slots=True)
class ProposalPlan:
    proposal_type: str
    response_text: str
    action_capability: str | None
    action_payload: dict
    metadata: dict


class ProviderResponseShapeError(ValueError):
    def __init__(self, message: str, shape: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.shape = shape
        self.retryable = retryable


def load_runtime_model_config(path: Path | None = None) -> RuntimeModelConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    llm_payload = payload["llm"]

    providers = {
        name: ProviderConfig(
            name=name,
            adapter_type=provider_payload["adapter_type"],
            base_url=provider_payload["base_url"],
            wire_api=provider_payload["wire_api"],
            auth_env=provider_payload["auth_env"],
            timeout_seconds=provider_payload.get("timeout_seconds", 30),
            default_headers=provider_payload.get("default_headers"),
        )
        for name, provider_payload in llm_payload.get("providers", {}).items()
    }
    models = {
        name: ModelConfig(
            name=name,
            provider=model_payload["provider"],
            model_id=model_payload["model_id"],
            supports_structured_output=model_payload.get(
                "supports_structured_output", False
            ),
            supports_tools=model_payload.get("supports_tools", False),
        )
        for name, model_payload in llm_payload.get("models", {}).items()
    }
    profiles = {
        name: ProfileConfig(
            name=name,
            model_ref=profile_payload["model_ref"],
            reasoning_effort=profile_payload.get("reasoning_effort", "medium"),
            verbosity=profile_payload.get("verbosity", "low"),
            provider_failure_behavior=profile_payload.get(
                "provider_failure_behavior",
                "deterministic",
            ),
        )
        for name, profile_payload in llm_payload.get("profiles", {}).items()
    }
    return RuntimeModelConfig(
        providers=providers,
        models=models,
        profiles=profiles,
    )


def resolve_profile_config(
    config: RuntimeModelConfig,
    profile_name: str,
) -> ProfileConfig:
    return config.profiles[profile_name]


def build_openai_compatible_request(
    model_id: str,
    user_text: str,
    snapshot: dict | None,
    grounding: dict | None,
    reasoning_effort: str,
    verbosity: str,
    supports_structured_output: bool = False,
) -> dict:
    prompt_context_package = build_prompt_context_package(
        user_text=user_text,
        snapshot=snapshot,
        grounding_bundle=grounding,
    )
    return {
        "model": model_id,
        "reasoning": {"effort": reasoning_effort},
        "text": {"verbosity": verbosity},
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You are the reply generator for a personal runtime. "
                            "Generate one concise user-facing reply."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            f"User text: {user_text}\n"
                            f"Prompt context version: {prompt_context_package['version']}\n"
                            f"Prompt context package: {json.dumps(prompt_context_package, sort_keys=True)}\n"
                            f"Grounding bundle: {json.dumps(grounding or {}, sort_keys=True)}"
                        ),
                    }
                ],
            },
        ],
    }


def build_openai_compatible_proposal_request(
    model_id: str,
    user_text: str,
    snapshot: dict | None,
    grounding: dict | None,
    reasoning_effort: str,
    verbosity: str,
    supports_structured_output: bool = False,
) -> dict:
    prompt_context_package = build_prompt_context_package(
        user_text=user_text,
        snapshot=snapshot,
        grounding_bundle=grounding,
    )
    text_config = {"verbosity": verbosity}
    if supports_structured_output:
        text_config["format"] = {
            "type": "json_schema",
            "name": "runtime_proposal",
            "strict": True,
            "schema": PROPOSAL_OUTPUT_SCHEMA,
        }
    return {
        "model": model_id,
        "reasoning": {"effort": reasoning_effort},
        "text": text_config,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You are the proposal formation planner for a personal runtime. "
                            "Return exactly one JSON object and no surrounding prose. "
                            "The object must include proposal_type, response_text, action, and rationale. "
                            "proposal_type must be one of: reply, action, clarification, no_intervention. "
                            "Use action when the user explicitly asks the runtime to do something, "
                            "including runtime control such as runtime.status. "
                            "Use reply for conversational responses, clarification when the request is underspecified, "
                            "and no_intervention for acknowledgements or closures that should stay silent."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            f"User text: {user_text}\n"
                            f"Prompt context version: {prompt_context_package['version']}\n"
                            f"Prompt context package: {json.dumps(prompt_context_package, sort_keys=True)}\n"
                            f"Grounding bundle: {json.dumps(grounding or {}, sort_keys=True)}\n"
                            "Return exactly one JSON object in this shape:\n"
                            '{'
                            '"proposal_type":"reply|action|clarification|no_intervention",'
                            '"response_text":"...",'
                            '"action":{"capability":"notification.show|runtime.status|...","payload":{}}'
                            ' or null,'
                            '"rationale":{"summary":"...",'
                            '"intent_signals":["..."],'
                            '"grounding_signals":["..."]}'
                            '}\n'
                            "If the request is to check runtime status, prefer "
                            '{"proposal_type":"action","action":{"capability":"runtime.status","payload":{}}}.'
                        ),
                    }
                ],
            },
        ],
    }


def parse_openai_compatible_response(
    response_payload: dict,
    profile_name: str,
    provider_name: str,
    model_id: str,
) -> DeterministicReplyPlan:
    response_shape = classify_openai_compatible_response_shape(response_payload)
    if response_shape in {
        "codex_agent_envelope_empty_output",
        "completed_empty_output",
    }:
        raise ProviderResponseShapeError(
            _provider_response_shape_error_message(
                response_shape,
                parser_name="plain runtime reply parsing",
            ),
            shape=response_shape,
        )
    for item in response_payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content_item in item.get("content", []):
            if content_item.get("type") == "output_text":
                text = content_item.get("text", "").strip()
                if text:
                    return DeterministicReplyPlan(
                        message=text,
                        metadata={
                            "llm_profile": profile_name,
                            "llm_provider": provider_name,
                            "llm_model": model_id,
                            "used_deterministic_fallback": False,
                        },
                    )
    raise ValueError("openai_compatible response did not contain output_text")


def parse_openai_compatible_proposal_response(
    response_payload: dict,
    profile_name: str,
    provider_name: str,
    model_id: str,
) -> ProposalPlan:
    response_shape = classify_openai_compatible_response_shape(response_payload)
    if response_shape in {
        "codex_agent_envelope_empty_output",
        "completed_empty_output",
    }:
        raise ProviderResponseShapeError(
            _provider_response_shape_error_message(
                response_shape,
                parser_name="plain runtime proposal parsing",
            ),
            shape=response_shape,
        )
    for item in response_payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content_item in item.get("content", []):
            if content_item.get("type") != "output_text":
                continue
            text = content_item.get("text", "").strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                return ProposalPlan(
                    proposal_type="reply",
                    response_text=text,
                    action_capability="notification.show",
                    action_payload={},
                    metadata={
                        "llm_profile": profile_name,
                        "llm_provider": provider_name,
                        "llm_model": model_id,
                        "used_deterministic_fallback": False,
                        "provider_proposal_type": "plain_output_text",
                        "proposal_rationale": {
                            "summary": (
                                "Provider returned plain reply text instead of a "
                                "structured proposal object."
                            )
                        },
                    },
                )
            provider_proposal_type = payload["proposal_type"]
            proposal_type = _normalize_proposal_type(provider_proposal_type)
            response_text = _extract_provider_response_text(payload)
            action_capability, action_payload = _normalize_provider_action(
                proposal_type=proposal_type,
                action=payload.get("action"),
                response_text=response_text,
            )
            return ProposalPlan(
                proposal_type=proposal_type,
                response_text=response_text,
                action_capability=action_capability,
                action_payload=action_payload,
                metadata={
                    "llm_profile": profile_name,
                    "llm_provider": provider_name,
                    "llm_model": model_id,
                    "used_deterministic_fallback": False,
                    "provider_proposal_type": provider_proposal_type,
                    "proposal_rationale": _normalize_provider_rationale(
                        payload.get("rationale", {})
                    ),
                },
            )
    raise ValueError(
        "openai_compatible response did not contain structured proposal output_text"
    )


def classify_openai_compatible_response_shape(response_payload: dict) -> str:
    if _looks_like_codex_agent_envelope(response_payload):
        return "codex_agent_envelope_empty_output"
    for item in response_payload.get("output", []) or []:
        if item.get("type") != "message":
            continue
        for content_item in item.get("content", []) or []:
            if content_item.get("type") == "output_text" and content_item.get(
                "text", ""
            ).strip():
                return "message_output_text"
    if response_payload.get("status") == "completed" and not response_payload.get(
        "output"
    ):
        return "completed_empty_output"
    return "unknown"


def _provider_response_shape_error_message(shape: str, parser_name: str) -> str:
    if shape == "codex_agent_envelope_empty_output":
        return (
            "Codex agent envelope with empty output; configured responses route "
            f"is incompatible with {parser_name}"
        )
    if shape == "completed_empty_output":
        return (
            "Completed response with empty output; configured responses route "
            f"returned no content for {parser_name}"
        )
    return f"Unsupported provider response shape: {shape}"


def _looks_like_codex_agent_envelope(response_payload: dict) -> bool:
    if response_payload.get("output"):
        return False
    if response_payload.get("status") != "completed":
        return False
    instructions = response_payload.get("instructions")
    if not isinstance(instructions, str):
        return False
    return "coding agent running in the Codex CLI" in instructions


def _normalize_proposal_type(raw_value: str) -> str:
    if not isinstance(raw_value, str):
        raise ValueError("provider proposal_type must be a string")
    normalized = raw_value.strip().lower()
    if normalized in {
        "reply",
        "response",
        "message",
        "notify",
        "direct_response",
        "assistant_message",
    }:
        return "reply"
    if normalized in {"action", "runtime_control", "control"}:
        return "action"
    if normalized in {"clarification", "clarify", "question"}:
        return "clarification"
    if normalized in {"no_intervention", "none", "ignore", "no_action"}:
        return "no_intervention"
    return "reply"


def _extract_provider_response_text(payload: dict) -> str:
    for field_name in ("response_text", "response", "message", "reply", "text"):
        value = payload.get(field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_provider_action(
    proposal_type: str,
    action,
    response_text: str,
) -> tuple[str | None, dict]:
    if action is None and proposal_type == "action":
        normalized_text = response_text.strip().lower()
        if "runtime status" in normalized_text or "checking runtime status" in normalized_text:
            return "runtime.status", {}

    if isinstance(action, dict):
        return action.get("capability"), dict(action.get("payload", {}))

    if isinstance(action, str):
        normalized = action.strip().lower()
        if normalized in {"respond", "reply", "message", "notify", "notification.show"}:
            return "notification.show", {}
        if normalized in {"runtime_status", "status"}:
            return "runtime.status", {}
        if normalized.startswith("runtime."):
            return normalized, {}
        if normalized in {"none", "no_action", "no_intervention", "ignore", ""}:
            return None, {}

    if proposal_type in {"reply", "clarification"} and response_text:
        return "notification.show", {}
    return None, {}


def _normalize_provider_rationale(rationale) -> dict:
    if isinstance(rationale, dict):
        return dict(rationale)
    if isinstance(rationale, str):
        return {"summary": rationale}
    return {}


def build_deterministic_reply_plan(
    user_text: str,
    profile_name: str,
    fallback_reason: str,
    provider_name: str | None = None,
    model_id: str | None = None,
) -> DeterministicReplyPlan:
    return DeterministicReplyPlan(
        message=f"Runtime heard: {user_text}",
        metadata={
            "llm_profile": profile_name,
            "llm_provider": provider_name or "local_deterministic",
            "llm_model": model_id or "local_deterministic",
            "used_deterministic_fallback": True,
            "fallback_reason": fallback_reason,
        },
    )


def build_deterministic_proposal_plan(
    user_text: str,
    profile_name: str,
    fallback_reason: str,
    snapshot: dict | None = None,
    grounding: dict | None = None,
    provider_name: str | None = None,
    model_id: str | None = None,
) -> ProposalPlan:
    normalized = user_text.strip().lower()
    snapshot_fields = sorted((snapshot or {}).keys())
    grounding_goals = grounding.get("active_goals", []) if grounding else []
    rationale = {
        "summary": "",
        "intent_signals": [signal for signal in normalized.split() if signal],
        "grounding_signals": snapshot_fields,
        "active_goal_count": len(grounding_goals),
    }

    if (
        normalized in {"thanks", "thank you", "ok thanks", "cool thanks"}
        or normalized.endswith("thanks")
        or normalized.endswith("thank you")
    ):
        rationale["summary"] = (
            "No intervention needed because the user message looks like a closure or acknowledgement."
        )
        return ProposalPlan(
            proposal_type="no_intervention",
            response_text="",
            action_capability=None,
            action_payload={},
            metadata={
                "llm_profile": profile_name,
                "llm_provider": provider_name or "local_deterministic",
                "llm_model": model_id or "local_deterministic",
                "used_deterministic_fallback": True,
                "fallback_reason": fallback_reason,
                "proposal_rationale": rationale,
            },
        )

    if normalized in {"help", "what can you do", "what now", "?"}:
        rationale["summary"] = (
            "Clarify the request because it is underspecified and needs disambiguation."
        )
        return ProposalPlan(
            proposal_type="clarification",
            response_text=(
                "Please clarify what you want me to do. You can ask for a reply or a runtime action such as status."
            ),
            action_capability="notification.show",
            action_payload={},
            metadata={
                "llm_profile": profile_name,
                "llm_provider": provider_name or "local_deterministic",
                "llm_model": model_id or "local_deterministic",
                "used_deterministic_fallback": True,
                "fallback_reason": fallback_reason,
                "proposal_rationale": rationale,
            },
        )

    if "runtime" in normalized and "status" in normalized:
        rationale["summary"] = (
            "Action proposal selected because the user explicitly requested runtime status."
        )
        return ProposalPlan(
            proposal_type="action",
            response_text="Checking runtime status.",
            action_capability="runtime.status",
            action_payload={},
            metadata={
                "llm_profile": profile_name,
                "llm_provider": provider_name or "local_deterministic",
                "llm_model": model_id or "local_deterministic",
                "used_deterministic_fallback": True,
                "fallback_reason": fallback_reason,
                "proposal_rationale": rationale,
            },
        )

    rationale["summary"] = (
        "Reply proposal selected because the user text looks like a normal conversational request."
    )
    return ProposalPlan(
        proposal_type="reply",
        response_text=f"Runtime heard: {user_text}",
        action_capability="notification.show",
        action_payload={},
        metadata={
            "llm_profile": profile_name,
            "llm_provider": provider_name or "local_deterministic",
            "llm_model": model_id or "local_deterministic",
            "used_deterministic_fallback": True,
            "fallback_reason": fallback_reason,
            "proposal_rationale": rationale,
        },
    )


def _summarize_provider_failure(error: Exception) -> str:
    if isinstance(error, urllib.error.URLError):
        reason = getattr(error, "reason", None)
        if reason:
            return str(reason)
    if isinstance(error, json.JSONDecodeError):
        return "provider returned invalid structured proposal JSON"
    if isinstance(error, KeyError):
        return f"missing config field: {error.args[0]}"
    message = str(error).strip()
    if message:
        return message
    return error.__class__.__name__


def classify_provider_failure(error: Exception) -> str:
    if isinstance(error, ProviderResponseShapeError):
        return "protocol_shape"
    if isinstance(error, json.JSONDecodeError):
        return "parser"
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, urllib.error.HTTPError):
        if error.code == 429:
            return "rate_limit"
        if 500 <= error.code <= 599:
            return "http_server"
        return "http_client"
    if isinstance(error, urllib.error.URLError):
        reason = getattr(error, "reason", None)
        if isinstance(reason, TimeoutError):
            return "timeout"
        return "connection"
    if isinstance(error, OSError):
        message = str(error).lower()
        if "missing auth env" in message:
            return "auth"
        if "timed out" in message or "timeout" in message:
            return "timeout"
        return "connection"
    if isinstance(error, ValueError):
        message = str(error).lower()
        if "unsupported wire_api" in message or "response shape" in message:
            return "protocol_shape"
        return "parser"
    return "unknown"


def _provider_failure_is_retryable(error: Exception) -> bool:
    return classify_provider_failure(error) in {
        "connection",
        "timeout",
        "rate_limit",
        "http_server",
        "protocol_shape",
    }


def _user_visible_provider_failure_reason(error: Exception) -> str:
    if isinstance(error, ProviderResponseShapeError):
        return "provider returned an incompatible response shape; please retry shortly"
    return _summarize_provider_failure(error)


def build_provider_failure_proposal_plan(
    user_text: str,
    profile_name: str,
    error: Exception,
    snapshot: dict | None = None,
    grounding: dict | None = None,
    provider_name: str | None = None,
    model_id: str | None = None,
    attempt_count: int = 1,
    retried_shapes: list[str] | None = None,
    provider_wire_api: str | None = None,
    provider_request_format: str | None = None,
) -> ProposalPlan:
    failure_reason = _summarize_provider_failure(error)
    user_visible_reason = _user_visible_provider_failure_reason(error)
    failure_class = classify_provider_failure(error)
    snapshot_fields = sorted((snapshot or {}).keys())
    grounding_goals = grounding.get("active_goals", []) if grounding else []
    metadata = {
        "llm_profile": profile_name,
        "llm_provider": provider_name or "local_deterministic",
        "llm_model": model_id or "local_deterministic",
        "provider_wire_api": provider_wire_api or "unknown",
        "provider_request_format": provider_request_format or "unknown",
        "used_deterministic_fallback": False,
        "provider_failure_behavior": "user_visible_error",
        "provider_failure_class": failure_class,
        "provider_failure_reason": failure_reason,
        "provider_failure_type": error.__class__.__name__,
        "provider_attempt_count": attempt_count,
        "provider_retry_count": max(attempt_count - 1, 0),
        "model_unavailable": True,
        "proposal_rationale": {
            "summary": (
                "The configured model provider was unavailable, so the runtime "
                "surfaced the real provider failure instead of fabricating a deterministic reply."
            ),
            "intent_signals": [signal for signal in user_text.strip().lower().split() if signal],
            "grounding_signals": snapshot_fields,
            "active_goal_count": len(grounding_goals),
        },
    }
    if isinstance(error, ProviderResponseShapeError):
        metadata["provider_failure_shape"] = error.shape
    if retried_shapes:
        metadata["provider_retried_shapes"] = list(retried_shapes)
    return ProposalPlan(
        proposal_type="reply",
        response_text=f"Real model reply unavailable: {user_visible_reason}",
        action_capability="notification.show",
        action_payload={},
        metadata=metadata,
    )


def generate_text_reply_plan(
    user_text: str,
    snapshot: dict | None = None,
    grounding: dict | None = None,
    profile_name: str = "interactive_reply",
    config_path: Path | None = None,
    transport=None,
) -> DeterministicReplyPlan:
    config = load_runtime_model_config(config_path)
    profile = resolve_profile_config(config, profile_name)
    model = config.models[profile.model_ref]
    provider = config.providers[model.provider]

    if provider.adapter_type != "openai_compatible":
        failure_reason = f"unsupported adapter: {provider.adapter_type}"
        if profile.provider_failure_behavior == "user_visible_error":
            return DeterministicReplyPlan(
                message=f"Real model reply unavailable: {failure_reason}",
                metadata={
                    "llm_profile": profile_name,
                    "llm_provider": provider.name,
                    "llm_model": model.model_id,
                    "used_deterministic_fallback": False,
                    "provider_failure_behavior": "user_visible_error",
                    "provider_failure_reason": failure_reason,
                    "provider_failure_class": "protocol_shape",
                    "provider_failure_type": "UnsupportedAdapter",
                    "model_unavailable": True,
                },
            )
        return build_deterministic_reply_plan(
            user_text=user_text,
            profile_name=profile_name,
            fallback_reason="unsupported_adapter",
            provider_name=provider.name,
            model_id=model.model_id,
        )

    try:
        response_payload = execute_openai_compatible_request(
            provider=provider,
            model=model,
            profile=profile,
            user_text=user_text,
            snapshot=snapshot,
            grounding=grounding,
            transport=transport,
        )
        return parse_openai_compatible_response(
            response_payload=response_payload,
            profile_name=profile.name,
            provider_name=provider.name,
            model_id=model.model_id,
        )
    except (KeyError, OSError, ValueError, urllib.error.URLError) as exc:
        if profile.provider_failure_behavior == "user_visible_error":
            return DeterministicReplyPlan(
                message=f"Real model reply unavailable: {_summarize_provider_failure(exc)}",
                metadata={
                    "llm_profile": profile.name,
                    "llm_provider": provider.name,
                    "llm_model": model.model_id,
                    "used_deterministic_fallback": False,
                    "provider_failure_behavior": "user_visible_error",
                    "provider_failure_reason": _summarize_provider_failure(exc),
                    "provider_failure_class": classify_provider_failure(exc),
                    "provider_failure_type": exc.__class__.__name__,
                    "model_unavailable": True,
                },
            )
        return build_deterministic_reply_plan(
            user_text=user_text,
            profile_name=profile_name,
            fallback_reason="provider_unavailable",
            provider_name=provider.name,
            model_id=model.model_id,
        )


def generate_text_proposal_plan(
    user_text: str,
    snapshot: dict | None = None,
    grounding: dict | None = None,
    profile_name: str = "proposal_formation",
    config_path: Path | None = None,
    transport=None,
) -> ProposalPlan:
    config = load_runtime_model_config(config_path)
    fallback_profile_name = (
        profile_name if profile_name in config.profiles else "interactive_reply"
    )
    profile = resolve_profile_config(config, fallback_profile_name)
    model = config.models[profile.model_ref]
    provider = config.providers[model.provider]
    provider_request_format = (
        "json_schema" if model.supports_structured_output else "prompt_json"
    )

    if provider.adapter_type != "openai_compatible":
        if profile.provider_failure_behavior == "user_visible_error":
            return build_provider_failure_proposal_plan(
                user_text=user_text,
                profile_name=fallback_profile_name,
                error=ValueError(f"unsupported adapter: {provider.adapter_type}"),
                snapshot=snapshot,
                grounding=grounding,
                provider_name=provider.name,
                model_id=model.model_id,
                provider_wire_api=provider.wire_api,
                provider_request_format=provider_request_format,
            )
        return build_deterministic_proposal_plan(
            user_text=user_text,
            profile_name=fallback_profile_name,
            fallback_reason="unsupported_adapter",
            snapshot=snapshot,
            grounding=grounding,
            provider_name=provider.name,
            model_id=model.model_id,
        )

    attempt_count = 0
    retried_shapes: list[str] = []
    started_at = time.monotonic()
    max_attempts = 2
    try:
        for attempt_index in range(max_attempts):
            attempt_count = attempt_index + 1
            try:
                response_payload = execute_openai_compatible_request(
                    provider=provider,
                    model=model,
                    profile=profile,
                    user_text=user_text,
                    snapshot=snapshot,
                    grounding=grounding,
                    request_builder=build_openai_compatible_proposal_request,
                    transport=transport,
                )
                plan = parse_openai_compatible_proposal_response(
                    response_payload=response_payload,
                    profile_name=profile.name,
                    provider_name=provider.name,
                    model_id=model.model_id,
                )
                if attempt_count > 1:
                    plan.metadata["provider_attempt_count"] = attempt_count
                    plan.metadata["provider_retry_count"] = attempt_count - 1
                    plan.metadata["provider_retried_shapes"] = list(retried_shapes)
                plan.metadata["provider_wire_api"] = provider.wire_api
                plan.metadata["provider_request_format"] = provider_request_format
                plan.metadata["provider_latency_ms"] = int(
                    (time.monotonic() - started_at) * 1000
                )
                return plan
            except ProviderResponseShapeError as exc:
                if exc.retryable and attempt_index + 1 < max_attempts:
                    retried_shapes.append(exc.shape)
                    continue
                raise
            except (OSError, urllib.error.URLError, TimeoutError) as exc:
                if _provider_failure_is_retryable(exc) and attempt_index + 1 < max_attempts:
                    continue
                raise
    except (
        KeyError,
        OSError,
        ValueError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ) as exc:
        if profile.provider_failure_behavior == "user_visible_error":
            plan = build_provider_failure_proposal_plan(
                user_text=user_text,
                profile_name=fallback_profile_name,
                error=exc,
                snapshot=snapshot,
                grounding=grounding,
                provider_name=provider.name,
                model_id=model.model_id,
                attempt_count=attempt_count,
                retried_shapes=retried_shapes,
                provider_wire_api=provider.wire_api,
                provider_request_format=provider_request_format,
            )
            plan.metadata["provider_latency_ms"] = int(
                (time.monotonic() - started_at) * 1000
            )
            return plan
        return build_deterministic_proposal_plan(
            user_text=user_text,
            profile_name=fallback_profile_name,
            fallback_reason="provider_unavailable",
            snapshot=snapshot,
            grounding=grounding,
            provider_name=provider.name,
            model_id=model.model_id,
        )


def execute_openai_compatible_request(
    provider: ProviderConfig,
    model: ModelConfig,
    profile: ProfileConfig,
    user_text: str,
    snapshot: dict | None = None,
    grounding: dict | None = None,
    request_builder=build_openai_compatible_request,
    transport=None,
) -> dict:
    if provider.wire_api != "responses":
        raise ValueError(
            f"unsupported wire_api for openai_compatible: {provider.wire_api}"
        )

    request_payload = request_builder(
        model_id=model.model_id,
        user_text=user_text,
        snapshot=snapshot,
        grounding=grounding,
        reasoning_effort=profile.reasoning_effort,
        verbosity=profile.verbosity,
        supports_structured_output=model.supports_structured_output,
    )

    api_key = os.environ.get(provider.auth_env)
    if not api_key:
        raise OSError(f"missing auth env: {provider.auth_env}")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # Some OpenAI-compatible gateways reject library-default requests unless
        # the client sends an explicit user agent.
        "User-Agent": "openhalo/0.1",
    }
    if provider.default_headers:
        headers.update(provider.default_headers)

    if transport is not None:
        return transport(provider, request_payload, api_key, headers)

    request = urllib.request.Request(
        url=f"{provider.base_url.rstrip('/')}/responses",
        data=json.dumps(request_payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=provider.timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def probe_model_provider(
    profile_name: str = "proposal_formation",
    config_path: Path | None = None,
    transport=None,
) -> dict:
    config = load_runtime_model_config(config_path)
    profile = resolve_profile_config(config, profile_name)
    model = config.models[profile.model_ref]
    provider = config.providers[model.provider]
    endpoint = f"{provider.base_url.rstrip('/')}/{provider.wire_api}"
    auth_env_present = bool(os.environ.get(provider.auth_env))
    result = {
        "ok": False,
        "profile": profile.name,
        "provider": provider.name,
        "model": model.model_id,
        "endpoint": endpoint,
        "wire_api": provider.wire_api,
        "auth_env": provider.auth_env,
        "auth_env_present": auth_env_present,
        "adapter_type": provider.adapter_type,
        "supports_structured_output": model.supports_structured_output,
        "response_shape": "not_called",
        "failure_class": None,
        "failure_reason": None,
        "user_visible_reason": None,
        "latency_ms": 0,
    }
    started_at = time.monotonic()
    try:
        response_payload = execute_openai_compatible_request(
            provider=provider,
            model=model,
            profile=profile,
            user_text="provider readiness probe",
            snapshot={"runtime.current_health_state": "probe"},
            grounding={"active_goals": [], "recent_memory": {}, "edge_history": {}},
            request_builder=build_openai_compatible_proposal_request,
            transport=transport,
        )
        result["response_shape"] = classify_openai_compatible_response_shape(
            response_payload
        )
        parse_openai_compatible_proposal_response(
            response_payload=response_payload,
            profile_name=profile.name,
            provider_name=provider.name,
            model_id=model.model_id,
        )
        result["ok"] = True
        result["http_result"] = "ok"
    except Exception as exc:
        result["failure_class"] = classify_provider_failure(exc)
        result["failure_reason"] = _summarize_provider_failure(exc)
        result["user_visible_reason"] = _user_visible_provider_failure_reason(exc)
        if isinstance(exc, ProviderResponseShapeError):
            result["response_shape"] = exc.shape
        if isinstance(exc, urllib.error.HTTPError):
            result["http_status"] = exc.code
        result["http_result"] = "error"
    result["latency_ms"] = int((time.monotonic() - started_at) * 1000)
    return result


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "DeterministicReplyPlan",
    "ModelConfig",
    "ProposalPlan",
    "ProfileConfig",
    "PROPOSAL_OUTPUT_SCHEMA",
    "ProviderConfig",
    "RuntimeModelConfig",
    "build_deterministic_reply_plan",
    "build_deterministic_proposal_plan",
    "build_provider_failure_proposal_plan",
    "build_openai_compatible_proposal_request",
    "build_openai_compatible_request",
    "classify_openai_compatible_response_shape",
    "classify_provider_failure",
    "execute_openai_compatible_request",
    "generate_text_proposal_plan",
    "generate_text_reply_plan",
    "load_runtime_model_config",
    "parse_openai_compatible_proposal_response",
    "parse_openai_compatible_response",
    "probe_model_provider",
    "resolve_profile_config",
]
