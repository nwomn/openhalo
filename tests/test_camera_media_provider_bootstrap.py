import os
from pathlib import Path
import sys
import types

if os.name == "nt" and "fcntl" not in sys.modules:
    sys.modules["fcntl"] = types.SimpleNamespace(
        LOCK_EX=0, LOCK_UN=0, flock=lambda *_args, **_kwargs: None
    )

from tests.v2_test_support import build_test_edge
from tests.v2_test_support import connect_test_edge_sync
from tests.v2_test_support import create_test_gateway


def test_runtime_sends_fixed_media_provider_after_camera_capability_announce(
    tmp_path: Path,
):
    config_path = tmp_path / "runtime-config.toml"
    config_path.write_text(
        """
[llm.providers.camera_video]
adapter_type = "openai_compatible"
base_url = "https://video.example/v1"
wire_api = "chat_completions"
api_key = "test-only-secret"
edge_direct_eligible = true

[llm.models.camera_video_model]
provider = "camera_video"
model_id = "qwen3-vl-flash"
supports_video = true

[llm.edge_media.camera-edge-1]
model_ref = "camera_video_model"
""".strip(),
        encoding="utf-8",
    )
    gateway = create_test_gateway(llm_config_path=config_path)
    edge = build_test_edge(
        device_id="camera-edge-1",
        device_type="camera",
        display_name="Camera Edge",
        capabilities=["media.provider.configure"],
    )

    replies = connect_test_edge_sync(gateway, edge)

    configure = replies[-1]
    assert configure["type"] == "action_request"
    assert configure["device_id"] == "camera-edge-1"
    assert configure["action"]["capability"] == "media.provider.configure"
    assert configure["action"]["payload"]["provider"]["name"] == "camera_video"
    assert configure["action"]["payload"]["model"]["model_id"] == "qwen3-vl-flash"


def test_runtime_does_not_provision_an_edge_that_lacks_the_configure_capability(
    tmp_path: Path,
):
    config_path = tmp_path / "runtime-config.toml"
    config_path.write_text("[llm]\n", encoding="utf-8")
    gateway = create_test_gateway(llm_config_path=config_path)
    edge = build_test_edge(
        device_id="camera-edge-1",
        device_type="camera",
        display_name="Camera Edge",
        capabilities=[],
    )

    replies = connect_test_edge_sync(gateway, edge)

    assert len(replies) == 1
