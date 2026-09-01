from personal_runtime.media_provider_delivery import build_media_provider_configure_request
from personal_runtime.media_provider_delivery import build_configured_camera_media_provider_request
from personal_runtime.model_provider import ModelConfig
from personal_runtime.model_provider import ProviderConfig
from personal_runtime.model_provider import RuntimeModelConfig


def test_runtime_projects_its_full_provider_profile_to_one_edge():
    config = RuntimeModelConfig(
        providers={"runtime_video": ProviderConfig(name="runtime_video", adapter_type="openai_compatible", base_url="https://provider.example/v1", wire_api="responses", api_key="runtime-private-key", timeout_seconds=45, default_headers={"User-Agent": "openhalo"}, edge_direct_eligible=True)},
        models={"runtime_video_model": ModelConfig(name="runtime_video_model", provider="runtime_video", model_id="vision-model", supports_vision=True, supports_video=True)},
        profiles={}, edge_media_profiles={"camera-edge-1": "runtime_video_model"},
    )
    frame = build_media_provider_configure_request(target_device_id="camera-edge-1", request_id="provider-1", config=config, model_ref="runtime_video_model")
    payload = frame["action"]["payload"]
    assert frame["device_id"] == "camera-edge-1"
    assert payload["provider"]["adapter_type"] == "openai_compatible"
    assert payload["provider"]["api_key"] == "runtime-private-key"
    assert payload["model"] == {"name": "runtime_video_model", "model_id": "vision-model", "supports_vision": True, "supports_video": True}
    configured = build_configured_camera_media_provider_request(target_device_id="camera-edge-1", request_id="provider-2", config=config)
    assert configured["action"]["payload"]["model"]["name"] == "runtime_video_model"


def test_runtime_rejects_a_provider_not_explicitly_allowed_for_edge_direct_use():
    config = RuntimeModelConfig(
        providers={"runtime_only": ProviderConfig(name="runtime_only", adapter_type="openai_compatible", base_url="https://provider.example/v1", wire_api="responses", api_key="key")},
        models={"vision_model": ModelConfig(name="vision_model", provider="runtime_only", model_id="vision-model", supports_vision=True, supports_video=True)},
        profiles={},
    )
    try:
        build_media_provider_configure_request(target_device_id="camera-edge-1", request_id="provider-1", config=config, model_ref="vision_model")
    except ValueError as exc:
        assert str(exc) == "media_provider_not_edge_direct_eligible"
    else:
        raise AssertionError("expected direct Edge provider rejection")
