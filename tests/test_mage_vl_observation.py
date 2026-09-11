import pytest

from device_edge.camera.mage_vl_observation import MageVLOutputError
from device_edge.camera.mage_vl_observation import parse_mage_vl_output


def test_parses_cli_logs_into_bounded_understanding_and_local_annotation() -> None:
    understanding = parse_mage_vl_output(
        "warmup log\n"
        '{"people_count":1,"scene":"a person in a room","readable_text":[],"confidence":0.8}\n'
        "completion log"
    )

    assert understanding.to_value() == {
        "people_count": 1,
        "scene": "a person in a room",
        "readable_text": [],
        "confidence": 0.8,
    }
    annotation = understanding.to_local_annotation(
        observed_at="2026-09-10T10:00:00Z",
        source_device_id="jetson-camera-edge-1",
        source_event_id="frame-1",
        model_revision="q4_k_m-q8_0",
    )
    assert annotation["kind"] == "camera.semantic_understanding_annotation"
    assert annotation["privacy"] == {"raw_media_included": False, "retention": "local_only"}
    assert "raw_output" not in annotation
    assert "frame" not in annotation


@pytest.mark.parametrize(
    "raw_output",
    [
        '{"people_count":-1,"scene":"room","readable_text":[],"confidence":0.8}'
        '{"people_count":1,"scene":"","readable_text":[],"confidence":0.8}'
        '{"people_count":1,"scene":"room","readable_text":["x"],"confidence":1.1}'
        '{"people_count":1,"scene":"room","readable_text":[],"confidence":0.8,"extra":true}'
    ],
)
def test_rejects_out_of_contract_output(raw_output: str) -> None:
    with pytest.raises(MageVLOutputError):
        parse_mage_vl_output(raw_output)


def test_rejects_ambiguous_multiple_valid_objects() -> None:
    raw_output = (
        '{"people_count":1,"scene":"room","readable_text":[],"confidence":0.8}\n'
        '{"people_count":0,"scene":"empty","readable_text":[],"confidence":0.7}'
    )
    with pytest.raises(MageVLOutputError):
        parse_mage_vl_output(raw_output)


def test_local_annotation_requires_provenance_strings() -> None:
    understanding = parse_mage_vl_output(
        '{"people_count":null,"scene":"unknown","readable_text":[],"confidence":0.0}'
    )
    with pytest.raises(MageVLOutputError):
        understanding.to_local_annotation(
            observed_at="",
            source_device_id="jetson-camera-edge-1",
            source_event_id="frame-1",
        )
