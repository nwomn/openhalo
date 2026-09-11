import io
import json
from unittest.mock import patch

import pytest

from experiments.isaac_ros.structured_semantics import StructuredSemanticsError
from experiments.isaac_ros.structured_semantics import compact_feature_window
from experiments.isaac_ros.structured_semantics import gate_semantic_result
from experiments.isaac_ros.structured_semantics import infer_structured
from experiments.isaac_ros.structured_semantics import parse_semantic_output


def _snapshot() -> dict:
    return {
        "server_time": 100.0,
        "inference_fps": 9.2,
        "result": {
            "sequence": 12,
            "frame_age_ms": 22.0,
            "latency_ms": {"total": 38.0},
            "temporal": {
                "window": {"seconds": 5.0, "person_count_mode": 1},
                "active_person_count": 1,
                "tracks": [
                    {
                        "track_id": 4,
                        "label": "person",
                        "status": "active",
                        "confidence": 0.91,
                        "bbox": [0.1, 0.1, 0.5, 0.9],
                        "center": [0.3, 0.5],
                        "trajectory": [[0.2, 0.5], [0.3, 0.5]],
                        "dwell_s": 4.0,
                        "continuity": 0.99,
                        "misses": 0,
                        "reacquired": 0,
                        "motion": {"state": "stationary", "jitter_rms": 0.002},
                        "region": {"current": "center", "window_stability": 1.0},
                        "pose": {"posture": "unknown", "visible_keypoints": 6},
                        "relationships": [
                            {"track_id": 8, "label": "cup", "relation": "near", "distance": 0.2, "iou": 0.0}
                        ],
                    },
                    {
                        "track_id": 8,
                        "label": "cup",
                        "status": "active",
                        "confidence": 0.72,
                        "dwell_s": 2.0,
                        "continuity": 0.95,
                        "misses": 0,
                        "reacquired": 0,
                        "motion": {"state": "stationary"},
                        "region": {"current": "center"},
                    },
                ],
            },
        },
    }


def test_compaction_excludes_raw_geometry_and_keeps_bounded_evidence() -> None:
    value = compact_feature_window(_snapshot())

    assert value["schema_version"] == "camera.temporal_feature_window.v1"
    assert value["source"]["raw_media_included"] is False
    assert "bbox" not in value["tracks"][0]
    assert "trajectory" not in value["tracks"][0]
    assert value["tracks"][0]["relationships"][0]["relation"] == "near"
    assert "person:4" in value["available_evidence_refs"]


def _valid_output() -> dict:
    return {
        "state_candidates": [
            {
                "state": "stationary",
                "confidence": 0.8,
                "evidence_refs": ["person:4"],
                "uncertainties": ["posture unknown"],
                "valid_for_ms": 3000,
            }
        ],
        "interruptibility": {
            "label": "uncertain",
            "confidence": 0.5,
            "evidence_refs": ["window"],
            "uncertainties": ["attention not observable"],
            "valid_for_ms": 2000,
        },
        "summary": "用户在中心区域保持静止，但姿态和注意力无法确认。",
        "missing_evidence": ["更完整的姿态关键点"],
    }


def test_semantic_output_is_bounded() -> None:
    parsed = parse_semantic_output(json.dumps(_valid_output(), ensure_ascii=False))
    assert parsed["schema_version"] == "camera.semantic_state_candidate.v1"
    assert parsed["state_candidates"][0]["state"] == "stationary"


def test_semantic_output_rejects_extra_prose_or_unknown_state() -> None:
    value = _valid_output()
    value["state_candidates"][0]["state"] = "用户正在工作"
    with pytest.raises(StructuredSemanticsError):
        parse_semantic_output(json.dumps(value, ensure_ascii=False))
    with pytest.raises(StructuredSemanticsError):
        parse_semantic_output("前置说明\n" + json.dumps(_valid_output(), ensure_ascii=False))


def test_gate_blocks_relationship_claim_without_low_level_relationship() -> None:
    snapshot = _snapshot()
    snapshot["result"]["temporal"]["tracks"][0]["relationships"] = []
    feature_window = compact_feature_window(snapshot)
    semantic = _valid_output()
    semantic["state_candidates"][0]["state"] = "possible_object_interaction"
    semantic["state_candidates"][0]["confidence"] = 1.0
    semantic["state_candidates"][0]["valid_for_ms"] = 30000
    semantic["interruptibility"]["label"] = "likely_busy"
    semantic["interruptibility"]["confidence"] = 1.0
    parsed = parse_semantic_output(json.dumps(semantic, ensure_ascii=False))

    gated, reasons = gate_semantic_result(parsed, feature_window)

    assert gated["state_candidates"][0]["state"] == "unknown"
    assert gated["state_candidates"][0]["confidence"] == 0.2
    assert gated["state_candidates"][0]["valid_for_ms"] == 5000
    assert gated["interruptibility"]["confidence"] == 0.65
    assert any("without relationship evidence" in reason for reason in reasons)


def test_text_only_inference_does_not_send_images() -> None:
    chunks = [
        {"message": {"content": json.dumps(_valid_output(), ensure_ascii=False)}, "done": False},
        {"message": {"content": ""}, "done": True, "eval_count": 64, "prompt_eval_count": 240},
    ]

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    payloads = []

    def open_request(request, **_kwargs):
        payloads.append(json.loads(request.data))
        return Response(b"\n".join(json.dumps(chunk).encode() for chunk in chunks))

    with patch("urllib.request.urlopen", side_effect=open_request):
        result, metrics = infer_structured(compact_feature_window(_snapshot()))

    assert result["interruptibility"]["label"] == "uncertain"
    assert metrics["output_tokens"] == 64
    message = payloads[0]["messages"][0]
    assert "images" not in message
    assert payloads[0]["format"]["type"] == "object"
