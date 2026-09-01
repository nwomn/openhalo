"""Build an Edge provisioning action from an existing Runtime provider profile."""

from __future__ import annotations

from personal_runtime.action_layer import build_action_request
from personal_runtime.model_provider import RuntimeModelConfig


def build_media_provider_configure_request(
    *,
    target_device_id: str,
    request_id: str,
    config: RuntimeModelConfig,
    model_ref: str,
) -> dict:
    """Project one configured Runtime provider/model to a paired media Edge.

    The returned frame contains credential material and must be delivered
    directly to the selected Edge; callers must not persist or log it.
    """

    model = config.models.get(model_ref)
    if model is None:
        raise ValueError("unknown_media_provider_model")
    provider = config.providers.get(model.provider)
    if provider is None:
        raise ValueError("unknown_media_provider")
    if not model.supports_video:
        raise ValueError("media_provider_model_lacks_video")
    if not provider.api_key:
        raise ValueError("media_provider_key_unavailable")
    if not provider.edge_direct_eligible:
        raise ValueError("media_provider_not_edge_direct_eligible")
    return build_action_request(
        target_device_id,
        {
            "capability": "media.provider.configure",
            "payload": {
                "provider": {
                    "name": provider.name,
                    "adapter_type": provider.adapter_type,
                    "base_url": provider.base_url,
                    "wire_api": provider.wire_api,
                    "api_key": provider.api_key,
                    "timeout_seconds": provider.timeout_seconds,
                    "default_headers": dict(provider.default_headers or {}),
                },
                "model": {
                    "name": model.name,
                    "model_id": model.model_id,
                    "supports_vision": model.supports_vision,
                    "supports_video": model.supports_video,
                },
            },
        },
        request_id=request_id,
    )


def build_configured_camera_media_provider_request(
    *, target_device_id: str, request_id: str, config: RuntimeModelConfig
) -> dict:
    """Build the fixed, explicitly configured provider action for one Camera Edge."""

    model_ref = config.edge_media_profiles.get(target_device_id)
    if model_ref is None:
        raise ValueError("camera_media_provider_not_configured")
    return build_media_provider_configure_request(
        target_device_id=target_device_id,
        request_id=request_id,
        config=config,
        model_ref=model_ref,
    )
