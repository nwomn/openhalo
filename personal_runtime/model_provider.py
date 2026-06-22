"""Provider/model/profile configuration for the first M9 runtime slice."""

from __future__ import annotations

import json
import os
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG_PATH = Path("config/llm-config.toml")
LOCAL_OVERRIDE_CONFIG_PATH = Path(".runtime/llm-config.toml")


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


@dataclass(slots=True)
class RuntimeModelConfig:
    providers: dict[str, ProviderConfig]
    models: dict[str, ModelConfig]
    profiles: dict[str, ProfileConfig]


@dataclass(slots=True)
class DeterministicReplyPlan:
    message: str
    metadata: dict


def load_runtime_model_config(path: Path | None = None) -> RuntimeModelConfig:
    config_path = path
    if config_path is None:
        if LOCAL_OVERRIDE_CONFIG_PATH.exists():
            config_path = LOCAL_OVERRIDE_CONFIG_PATH
        else:
            config_path = DEFAULT_CONFIG_PATH
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
) -> dict:
    compact_snapshot = snapshot or {}
    grounding_bundle = grounding or {}
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
                            f"Compact snapshot: {json.dumps(compact_snapshot, sort_keys=True)}\n"
                            f"Grounding bundle: {json.dumps(grounding_bundle, sort_keys=True)}"
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
    except (KeyError, OSError, ValueError, urllib.error.URLError):
        return build_deterministic_reply_plan(
            user_text=user_text,
            profile_name=profile_name,
            fallback_reason="provider_unavailable",
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
    transport=None,
) -> dict:
    request_payload = build_openai_compatible_request(
        model_id=model.model_id,
        user_text=user_text,
        snapshot=snapshot,
        grounding=grounding,
        reasoning_effort=profile.reasoning_effort,
        verbosity=profile.verbosity,
    )

    api_key = os.environ.get(provider.auth_env)
    if not api_key:
        raise OSError(f"missing auth env: {provider.auth_env}")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # Some OpenAI-compatible gateways reject library-default requests unless
        # the client sends an explicit user agent.
        "User-Agent": "personal-runtime-agent/0.1",
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


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "DeterministicReplyPlan",
    "LOCAL_OVERRIDE_CONFIG_PATH",
    "ModelConfig",
    "ProfileConfig",
    "ProviderConfig",
    "RuntimeModelConfig",
    "build_deterministic_reply_plan",
    "build_openai_compatible_request",
    "execute_openai_compatible_request",
    "generate_text_reply_plan",
    "load_runtime_model_config",
    "parse_openai_compatible_response",
    "resolve_profile_config",
]
