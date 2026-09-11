"""Bounded tracking and temporal feature extraction for Camera Edge experiments.

The module accepts normalized detector geometry and optional pose keypoints. It
keeps short numeric histories only; it does not retain image data or emit
Runtime observations.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Sequence

import numpy as np


Point = tuple[float, float]
BBox = tuple[float, float, float, float]


def _bbox(value: Mapping[str, Any]) -> BBox:
    raw = value.get("bbox")
    if raw is None:
        raise ValueError("detection requires a normalized bbox")
    if len(raw) != 4:
        raise ValueError("detection bbox requires four values")
    x1, y1, x2, y2 = (float(item) for item in raw)
    if x2 < x1 or y2 < y1:
        raise ValueError("detection bbox must be ordered")
    return (x1, y1, x2, y2)


def _center(box: BBox) -> Point:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _distance(first: Point, second: Point) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _iou(first: BBox, second: BBox) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union > 0.0 else 0.0


def _mode_ratio(values: Sequence[Any]) -> tuple[Any | None, float | None]:
    if not values:
        return None, None
    value, count = Counter(values).most_common(1)[0]
    return value, count / len(values)


def _round_point(point: Point) -> list[float]:
    return [round(float(point[0]), 5), round(float(point[1]), 5)]


def _pose_signature(keypoints: np.ndarray) -> tuple[np.ndarray | None, int]:
    points = np.asarray(keypoints, dtype=np.float32)
    if points.ndim != 2 or points.shape[1] < 3:
        return None, 0
    visible = points[:, 2] >= 0.35
    visible_count = int(np.count_nonzero(visible))
    if visible_count == 0:
        return None, 0
    coords = points[:, :2]
    selected = coords[visible]
    minimum = np.min(selected, axis=0)
    maximum = np.max(selected, axis=0)
    scale = max(float(np.max(maximum - minimum)), 1.0)
    signature = np.full((points.shape[0], 2), np.nan, dtype=np.float32)
    signature[visible] = (coords[visible] - minimum) / scale
    return signature, visible_count


@dataclass
class _Track:
    track_id: int
    label: str
    bbox: BBox
    center: Point
    smoothed_center: Point
    confidence: float
    first_seen_s: float
    last_seen_s: float
    status: str = "active"
    hits: int = 1
    matched_updates: int = 1
    total_updates: int = 1
    missed_updates: int = 0
    max_gap_s: float = 0.0
    reacquired_count: int = 0
    history: deque[tuple[float, Point, Point, str | None]] = field(
        default_factory=lambda: deque(maxlen=240)
    )
    pose_history: deque[tuple[float, str, float | None, int]] = field(
        default_factory=lambda: deque(maxlen=120)
    )
    pose_signature: np.ndarray | None = None
    last_posture: str = "unknown"
    last_pose_delta: float | None = None
    pose_change_count: int = 0
    posture_transition_count: int = 0
    region: str | None = None
    region_since_s: float | None = None
    region_durations_s: dict[str, float] = field(default_factory=dict)
    region_transitions: int = 0
    relationship_key: tuple[str, ...] | None = None
    relationship_since_s: float | None = None
    relationship_transitions: int = 0
    relationships: list[dict[str, Any]] = field(default_factory=list)


class TemporalTracker:
    """Associate detections and derive bounded motion, pose, and relation state."""

    def __init__(
        self,
        *,
        regions: Mapping[str, Sequence[float]] | None = None,
        window_seconds: float = 5.0,
        max_distance: float = 0.18,
        min_iou: float = 0.05,
        max_lost_seconds: float = 0.8,
        smoothing_alpha: float = 0.45,
        object_near_distance: float = 0.30,
    ) -> None:
        if window_seconds <= 0.0 or max_distance <= 0.0 or max_lost_seconds <= 0.0:
            raise ValueError("window_seconds, max_distance, and max_lost_seconds must be positive")
        if not 0.0 < smoothing_alpha <= 1.0:
            raise ValueError("smoothing_alpha must be in (0, 1]")
        self.regions = {
            name: tuple(float(value) for value in bounds)
            for name, bounds in (regions or {}).items()
        }
        for name, bounds in self.regions.items():
            if len(bounds) != 4:
                raise ValueError(f"region {name!r} requires four values")
        self.window_seconds = float(window_seconds)
        self.max_distance = float(max_distance)
        self.min_iou = float(min_iou)
        self.max_lost_seconds = float(max_lost_seconds)
        self.smoothing_alpha = float(smoothing_alpha)
        self.object_near_distance = float(object_near_distance)
        self._tracks: dict[int, _Track] = {}
        self._finished: list[_Track] = []
        self._next_track_id = 1
        self._last_timestamp_s: float | None = None
        self._observation_history: deque[dict[str, Any]] = deque(maxlen=720)

    def _timestamp(self, timestamp_s: float) -> float:
        timestamp = float(timestamp_s)
        if self._last_timestamp_s is not None:
            timestamp = max(timestamp, self._last_timestamp_s)
        self._last_timestamp_s = timestamp
        return timestamp

    def _region_for(self, point: Point) -> str | None:
        for name, bounds in self.regions.items():
            x1, y1, x2, y2 = bounds
            if x1 <= point[0] <= x2 and y1 <= point[1] <= y2:
                return name
        return None

    def _match_cost(self, track: _Track, detection: Mapping[str, Any]) -> float | None:
        if track.label != str(detection.get("label", "")):
            return None
        box = _bbox(detection)
        center = _center(box)
        distance = _distance(track.smoothed_center, center)
        overlap = _iou(track.bbox, box)
        if distance > self.max_distance and overlap < self.min_iou:
            return None
        return distance + (1.0 - overlap) * 0.15

    def _append_history(self, track: _Track, timestamp_s: float) -> None:
        track.history.append(
            (timestamp_s, track.center, track.smoothed_center, track.region)
        )
        cutoff = timestamp_s - max(self.window_seconds * 4.0, 10.0)
        while track.history and track.history[0][0] < cutoff:
            track.history.popleft()
        while track.pose_history and track.pose_history[0][0] < cutoff:
            track.pose_history.popleft()

    def _set_region(self, track: _Track, timestamp_s: float) -> None:
        region = self._region_for(track.smoothed_center)
        if region == track.region:
            return
        if track.region is not None and track.region_since_s is not None:
            track.region_durations_s[track.region] = track.region_durations_s.get(track.region, 0.0) + max(
                0.0, timestamp_s - track.region_since_s
            )
        if track.region is not None or region is not None:
            track.region_transitions += 1
        track.region = region
        track.region_since_s = timestamp_s if region is not None else None

    def _new_track(
        self, detection: Mapping[str, Any], timestamp_s: float
    ) -> _Track:
        box = _bbox(detection)
        center = _center(box)
        track = _Track(
            track_id=self._next_track_id,
            label=str(detection.get("label", "unknown")),
            bbox=box,
            center=center,
            smoothed_center=center,
            confidence=float(detection.get("confidence", 0.0)),
            first_seen_s=timestamp_s,
            last_seen_s=timestamp_s,
        )
        self._next_track_id += 1
        track.region = self._region_for(track.smoothed_center)
        track.region_since_s = timestamp_s if track.region is not None else None
        self._append_history(track, timestamp_s)
        return track

    def _apply_detection(
        self, track: _Track, detection: Mapping[str, Any], timestamp_s: float
    ) -> None:
        box = _bbox(detection)
        center = _center(box)
        if track.status == "lost":
            track.reacquired_count += 1
            track.max_gap_s = max(track.max_gap_s, timestamp_s - track.last_seen_s)
        alpha = self.smoothing_alpha
        track.center = center
        track.smoothed_center = (
            alpha * center[0] + (1.0 - alpha) * track.smoothed_center[0],
            alpha * center[1] + (1.0 - alpha) * track.smoothed_center[1],
        )
        track.bbox = box
        track.confidence = float(detection.get("confidence", track.confidence))
        track.last_seen_s = timestamp_s
        track.status = "active"
        track.hits += 1
        track.matched_updates += 1
        track.total_updates += 1
        track.missed_updates = 0
        self._set_region(track, timestamp_s)
        self._append_history(track, timestamp_s)

    def _mark_missed(self, track: _Track, timestamp_s: float) -> None:
        track.total_updates += 1
        track.missed_updates += 1
        gap = max(0.0, timestamp_s - track.last_seen_s)
        track.max_gap_s = max(track.max_gap_s, gap)
        if gap <= self.max_lost_seconds:
            track.status = "lost"
            if track.label == "person":
                track.relationships = []
        else:
            track.status = "ended"

    def _assign_pose(
        self,
        pose_items: Sequence[Mapping[str, Any]],
        timestamp_s: float,
        frame_size: tuple[int, int] | None,
    ) -> None:
        if not pose_items or frame_size is None:
            return
        width, height = frame_size
        if width <= 0 or height <= 0:
            return
        persons = [
            track
            for track in self._tracks.values()
            if track.label == "person" and track.status == "active" and track.last_seen_s == timestamp_s
        ]
        used: set[int] = set()
        for item in pose_items:
            keypoints = np.asarray(item.get("keypoints"), dtype=np.float32)
            signature, visible_count = _pose_signature(keypoints)
            if signature is None:
                continue
            visible = keypoints[:, 2] >= 0.35
            point = np.mean(keypoints[visible, :2], axis=0)
            normalized_center = (float(point[0]) / width, float(point[1]) / height)
            choices = [
                (
                    _distance(track.smoothed_center, normalized_center),
                    track,
                )
                for track in persons
                if track.track_id not in used
            ]
            choices.sort(key=lambda value: value[0])
            if not choices or choices[0][0] > 0.30:
                continue
            track = choices[0][1]
            used.add(track.track_id)
            posture = str(item.get("posture", "unknown"))
            delta: float | None = None
            if track.pose_signature is not None:
                common = np.isfinite(track.pose_signature[:, 0]) & np.isfinite(signature[:, 0])
                if np.any(common):
                    delta = float(
                        np.mean(
                            np.linalg.norm(
                                signature[common] - track.pose_signature[common], axis=1
                            )
                        )
                    )
            if (
                track.last_posture != "unknown"
                and posture != "unknown"
                and posture != track.last_posture
            ):
                track.posture_transition_count += 1
            if delta is not None and delta >= 0.10:
                track.pose_change_count += 1
            track.pose_signature = signature
            track.last_posture = posture
            track.last_pose_delta = delta
            track.pose_history.append((timestamp_s, posture, delta, visible_count))

    def _assign_relationships(
        self,
        records: Sequence[Mapping[str, Any]],
        timestamp_s: float,
    ) -> None:
        people = [record for record in records if record.get("label") == "person"]
        objects = [record for record in records if record.get("label") != "person"]
        for person in people:
            track = self._tracks.get(int(person["track_id"]))
            if track is None:
                continue
            person_box = _bbox(person)
            relationships: list[dict[str, Any]] = []
            for item in objects:
                item_box = _bbox(item)
                overlap = _iou(person_box, item_box)
                distance = _distance(_center(person_box), _center(item_box))
                if overlap >= 0.03:
                    relation = "overlapping"
                elif distance <= self.object_near_distance:
                    relation = "near"
                else:
                    continue
                relationships.append(
                    {
                        "track_id": int(item["track_id"]),
                        "label": str(item["label"]),
                        "relation": relation,
                        "distance": round(distance, 5),
                        "iou": round(overlap, 5),
                    }
                )
            relationships.sort(key=lambda value: (value["label"], value["track_id"]))
            relation_key = tuple(
                f"{item['label']}:{item['relation']}" for item in relationships
            )
            if relation_key != track.relationship_key:
                if track.relationship_key is not None:
                    track.relationship_transitions += 1
                track.relationship_key = relation_key
                track.relationship_since_s = timestamp_s
            track.relationships = relationships

    def update(
        self,
        detections: Sequence[Mapping[str, Any]],
        timestamp_s: float,
        *,
        pose_items: Sequence[Mapping[str, Any]] = (),
        frame_size: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        timestamp = self._timestamp(timestamp_s)
        normalized_detections = [
            {**detection, "label": str(detection.get("label", "unknown"))}
            for detection in detections
        ]
        candidates = [
            track
            for track in self._tracks.values()
            if timestamp - track.last_seen_s <= self.max_lost_seconds
        ]
        proposals: list[tuple[float, int, int]] = []
        for detection_index, detection in enumerate(normalized_detections):
            for track in candidates:
                cost = self._match_cost(track, detection)
                if cost is not None:
                    proposals.append((cost, detection_index, track.track_id))
        proposals.sort()
        matched_detections: set[int] = set()
        matched_tracks: set[int] = set()
        assignments: dict[int, int] = {}
        for _, detection_index, track_id in proposals:
            if detection_index in matched_detections or track_id in matched_tracks:
                continue
            matched_detections.add(detection_index)
            matched_tracks.add(track_id)
            assignments[detection_index] = track_id

        records: list[dict[str, Any]] = []
        for detection_index, detection in enumerate(normalized_detections):
            track_id = assignments.get(detection_index)
            if track_id is None:
                track = self._new_track(detection, timestamp)
                self._tracks[track.track_id] = track
                track_id = track.track_id
            else:
                track = self._tracks[track_id]
                self._apply_detection(track, detection, timestamp)
            records.append({**detection, "track_id": track_id})

        for track_id, track in list(self._tracks.items()):
            if track_id not in matched_tracks and not any(
                record["track_id"] == track_id for record in records
            ):
                self._mark_missed(track, timestamp)
                if track.status == "ended":
                    self._finished.append(track)
                    del self._tracks[track_id]

        self._assign_relationships(records, timestamp)
        self._assign_pose(pose_items, timestamp, frame_size)
        region_counts = {name: 0 for name in self.regions}
        for record in records:
            if record["label"] != "person":
                continue
            region = self._region_for(_center(_bbox(record)))
            if region is not None:
                region_counts[region] += 1
        self._observation_history.append(
            {
                "timestamp_s": timestamp,
                "person_count": sum(record["label"] == "person" for record in records),
                "region_counts": region_counts,
            }
        )
        return self.snapshot(timestamp)

    def _motion(self, track: _Track, timestamp_s: float) -> dict[str, Any]:
        cutoff = timestamp_s - self.window_seconds
        entries = [entry for entry in track.history if entry[0] >= cutoff]
        points = [entry[2] for entry in entries]
        raw_points = [entry[1] for entry in entries]
        path_length = sum(
            _distance(first, second) for first, second in zip(points, points[1:])
        )
        displacement = _distance(points[0], points[-1]) if len(points) >= 2 else 0.0
        duration = max(0.0, entries[-1][0] - entries[0][0]) if len(entries) >= 2 else 0.0
        mean_speed = path_length / duration if duration > 0.0 else 0.0
        if mean_speed < 0.025:
            state = "stationary"
        elif mean_speed >= 0.08:
            state = "moving"
        else:
            state = "transitioning"
        direction = "none"
        if len(points) >= 2 and displacement >= 0.025:
            dx = points[-1][0] - points[0][0]
            dy = points[-1][1] - points[0][1]
            if abs(dx) >= abs(dy):
                direction = "right" if dx > 0 else "left"
            else:
                direction = "down" if dy > 0 else "up"
        residuals = [
            _distance(raw, smooth) for raw, smooth in zip(raw_points, points)
        ]
        jitter = math.sqrt(float(np.mean(np.square(residuals)))) if residuals else 0.0
        return {
            "state": state,
            "direction": direction,
            "window_s": round(self.window_seconds, 3),
            "sample_count": len(entries),
            "path_length": round(path_length, 5),
            "displacement": round(displacement, 5),
            "mean_speed": round(mean_speed, 5),
            "jitter_rms": round(jitter, 5),
        }

    def _region_summary(self, track: _Track, timestamp_s: float) -> dict[str, Any]:
        cutoff = timestamp_s - self.window_seconds
        values = [entry[3] for entry in track.history if entry[0] >= cutoff and entry[3] is not None]
        mode, stability = _mode_ratio(values)
        durations = dict(track.region_durations_s)
        if track.region is not None and track.region_since_s is not None:
            durations[track.region] = durations.get(track.region, 0.0) + max(
                0.0, timestamp_s - track.region_since_s
            )
        current_dwell = (
            max(0.0, timestamp_s - track.region_since_s)
            if track.region is not None and track.region_since_s is not None
            else 0.0
        )
        return {
            "current": track.region,
            "dwell_s": round(current_dwell, 3),
            "durations_s": {name: round(value, 3) for name, value in durations.items()},
            "transitions": track.region_transitions,
            "window_mode": mode,
            "window_stability": round(stability, 4) if stability is not None else None,
        }

    def _pose_summary(self, track: _Track, timestamp_s: float) -> dict[str, Any]:
        cutoff = timestamp_s - self.window_seconds
        values = [entry for entry in track.pose_history if entry[0] >= cutoff]
        postures = [entry[1] for entry in values if entry[1] != "unknown"]
        mode, stability = _mode_ratio(postures)
        change = track.last_pose_delta
        if change is None:
            change_state = "unknown"
        elif track.posture_transition_count > 0 or change >= 0.10:
            change_state = "changing"
        elif change >= 0.04:
            change_state = "minor_change"
        else:
            change_state = "stable"
        return {
            "posture": track.last_posture,
            "change_state": change_state,
            "delta": round(change, 5) if change is not None else None,
            "visible_keypoints": values[-1][3] if values else 0,
            "change_count": track.pose_change_count,
            "posture_transitions": track.posture_transition_count,
            "window_mode": mode,
            "window_stability": round(stability, 4) if stability is not None else None,
        }

    def _track_view(self, track: _Track, timestamp_s: float, *, path: bool = True) -> dict[str, Any]:
        motion = self._motion(track, timestamp_s)
        continuity = track.matched_updates / max(1, track.total_updates)
        dwell = max(0.0, min(timestamp_s, track.last_seen_s) - track.first_seen_s)
        relationships = list(track.relationships)
        relation_stable = (
            max(0.0, timestamp_s - track.relationship_since_s)
            if track.relationship_key is not None and track.relationship_since_s is not None
            else 0.0
        )
        view = {
            "track_id": track.track_id,
            "label": track.label,
            "status": track.status,
            "confidence": round(track.confidence, 5),
            "bbox": [round(value, 5) for value in track.bbox],
            "center": _round_point(track.smoothed_center),
            "dwell_s": round(dwell, 3),
            "hits": track.hits,
            "misses": track.missed_updates,
            "continuity": round(continuity, 4),
            "max_gap_s": round(track.max_gap_s, 3),
            "reacquired": track.reacquired_count,
            "motion": motion,
            "region": self._region_summary(track, timestamp_s),
            "pose": self._pose_summary(track, timestamp_s)
            if track.label == "person"
            else None,
            "relationships": relationships if track.label == "person" else [],
            "relationship_stable_s": round(relation_stable, 3),
            "relationship_transitions": track.relationship_transitions,
        }
        if path:
            cutoff = timestamp_s - self.window_seconds
            view["trajectory"] = [
                _round_point(entry[2]) for entry in track.history if entry[0] >= cutoff
            ][-32:]
        return view

    def _window_summary(self, timestamp_s: float) -> dict[str, Any]:
        cutoff = timestamp_s - self.window_seconds
        values = [entry for entry in self._observation_history if entry["timestamp_s"] >= cutoff]
        person_counts = [int(entry["person_count"]) for entry in values]
        person_mode, person_stability = _mode_ratio(person_counts)
        region_summary: dict[str, Any] = {}
        for name in self.regions:
            occupied = [int(entry["region_counts"].get(name, 0) > 0) for entry in values]
            mode, stability = _mode_ratio(occupied)
            region_summary[name] = {
                "mode_occupied": bool(mode) if mode is not None else None,
                "stability": round(stability, 4) if stability is not None else None,
            }
        return {
            "seconds": round(self.window_seconds, 3),
            "sample_count": len(values),
            "person_count_mode": person_mode,
            "person_count_stability": round(person_stability, 4)
            if person_stability is not None
            else None,
            "regions": region_summary,
        }

    def snapshot(self, timestamp_s: float | None = None) -> dict[str, Any]:
        timestamp = self._last_timestamp_s if timestamp_s is None else float(timestamp_s)
        if timestamp is None:
            timestamp = 0.0
        tracks = [self._track_view(track, timestamp) for track in self._tracks.values()]
        tracks.sort(key=lambda value: value["track_id"])
        return {
            "window": self._window_summary(timestamp),
            "tracks": tracks,
            "active_track_count": len(tracks),
            "active_person_count": sum(track["label"] == "person" for track in tracks),
        }

    def report(self, timestamp_s: float | None = None) -> dict[str, Any]:
        timestamp = self._last_timestamp_s if timestamp_s is None else float(timestamp_s)
        if timestamp is None:
            timestamp = 0.0
        tracks = self._finished + list(self._tracks.values())
        views = [self._track_view(track, timestamp, path=False) for track in tracks]
        persons = [track for track in views if track["label"] == "person"]
        continuity = [track["continuity"] for track in persons]
        jitter = [track["motion"]["jitter_rms"] for track in persons]
        return {
            "unique_tracks": len(views),
            "unique_person_tracks": len(persons),
            "active_tracks": sum(track["status"] == "active" for track in views),
            "lost_tracks": sum(track["status"] == "lost" for track in views),
            "finished_tracks": sum(track["status"] == "ended" for track in views),
            "reacquired_tracks": sum(track["reacquired"] > 0 for track in views),
            "person_continuity_mean": round(float(np.mean(continuity)), 4)
            if continuity
            else None,
            "person_jitter_rms_mean": round(float(np.mean(jitter)), 5) if jitter else None,
            "person_max_gap_s": max((track["max_gap_s"] for track in persons), default=0.0),
            "person_max_dwell_s": max((track["dwell_s"] for track in persons), default=0.0),
            "pose_change_events": sum(track["pose"]["change_count"] for track in persons),
            "region_transitions": sum(track["region"]["transitions"] for track in views),
            "relationship_transitions": sum(track["relationship_transitions"] for track in persons),
            "window": self._window_summary(timestamp),
            "tracks": views,
        }
