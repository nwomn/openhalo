from __future__ import annotations

import numpy as np

from experiments.isaac_ros.temporal_features import TemporalTracker


def _person(x: float, y: float = 0.5, width: float = 0.2) -> dict[str, object]:
    return {
        "label": "person",
        "bbox": (x - width / 2, y - 0.3, x + width / 2, y + 0.3),
        "confidence": 0.9,
    }


def _cup(x: float, y: float = 0.55) -> dict[str, object]:
    return {
        "label": "cup",
        "bbox": (x - 0.03, y - 0.03, x + 0.03, y + 0.03),
        "confidence": 0.8,
    }


def _pose(arm_offset: float = 0.0, posture: str = "unknown") -> dict[str, object]:
    points = np.zeros((17, 3), dtype=np.float32)
    for index in range(17):
        points[index] = (100 + (index % 3) * 10, 80 + (index // 3) * 20, 0.9)
    points[9, 0] += arm_offset
    return {"keypoints": points, "posture": posture}


def test_person_track_keeps_id_and_reports_motion_and_dwell() -> None:
    tracker = TemporalTracker(window_seconds=2.0, max_lost_seconds=1.5)
    first = tracker.update([_person(0.2)], 0.0)
    second = tracker.update([_person(0.3)], 1.0)

    assert first["tracks"][0]["track_id"] == second["tracks"][0]["track_id"]
    track = second["tracks"][0]
    assert track["dwell_s"] == 1.0
    assert track["continuity"] == 1.0
    assert track["motion"]["displacement"] > 0.03
    assert track["motion"]["direction"] == "right"


def test_stationary_detection_reports_low_jitter_and_stable_window() -> None:
    tracker = TemporalTracker(
        window_seconds=2.0,
        regions={"center": (0.333, 0.0, 0.667, 1.0)},
    )
    for index, x in enumerate((0.5, 0.502, 0.498, 0.501, 0.499)):
        snapshot = tracker.update([_person(x)], index * 0.25)

    track = snapshot["tracks"][0]
    assert track["motion"]["state"] == "stationary"
    assert track["motion"]["jitter_rms"] < 0.01
    assert track["region"]["window_stability"] is not None
    assert snapshot["window"]["person_count_stability"] == 1.0


def test_short_dropout_reacquires_and_long_dropout_ends_track() -> None:
    tracker = TemporalTracker(max_lost_seconds=0.5)
    first = tracker.update([_person(0.4)], 0.0)
    track_id = first["tracks"][0]["track_id"]
    lost = tracker.update([], 0.2)
    assert lost["tracks"][0]["status"] == "lost"

    reacquired = tracker.update([_person(0.405)], 0.4)
    assert reacquired["tracks"][0]["track_id"] == track_id
    assert reacquired["tracks"][0]["reacquired"] == 1

    ended = tracker.update([], 1.1)
    assert ended["tracks"] == []
    new_track = tracker.update([_person(0.41)], 1.2)
    assert new_track["tracks"][0]["track_id"] != track_id
    assert tracker.report()["finished_tracks"] == 1


def test_pose_change_and_person_object_region_relation_are_temporal() -> None:
    tracker = TemporalTracker(
        regions={"center": (0.333, 0.0, 0.667, 1.0), "right": (0.667, 0.0, 1.0, 1.0)},
        window_seconds=2.0,
        max_distance=0.30,
        max_lost_seconds=1.5,
        smoothing_alpha=1.0,
    )
    first = tracker.update(
        [_person(0.5), _cup(0.55)],
        0.0,
        pose_items=[_pose(0.0, "sitting")],
        frame_size=(200, 200),
    )
    assert first["tracks"][0]["region"]["current"] == "center"
    assert first["tracks"][0]["relationships"][0]["relation"] in {"near", "overlapping"}

    second = tracker.update(
        [_person(0.75), _cup(0.80)],
        1.0,
        pose_items=[_pose(80.0, "standing")],
        frame_size=(200, 200),
    )
    person = next(track for track in second["tracks"] if track["label"] == "person")
    assert person["region"]["current"] == "right"
    assert person["region"]["transitions"] == 1
    assert person["pose"]["posture_transitions"] == 1
    assert person["pose"]["change_state"] == "changing"
    assert person["relationships"][0]["label"] == "cup"
