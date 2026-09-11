"""Local-only semantic interpretation of Isaac ROS temporal features.

The module sends a compact feature window to an Ollama text endpoint. It never
attaches image data, publishes Runtime observations, or executes actions.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time
from typing import Any, Mapping
import urllib.request


INPUT_SCHEMA_VERSION = "camera.temporal_feature_window.v1"
OUTPUT_SCHEMA_VERSION = "camera.semantic_state_candidate.v1"
STATE_LABELS = (
    "present",
    "absent",
    "stationary",
    "moving",
    "likely_busy",
    "likely_available",
    "possible_object_interaction",
    "possible_posture_change",
    "unknown",
)
INTERRUPTIBILITY_LABELS = (
    "likely_busy",
    "likely_available",
    "uncertain",
    "unknown",
)

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "state_candidates": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "state": {"type": "string", "enum": list(STATE_LABELS)},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence_refs": {
                        "type": "array",
                        "maxItems": 5,
                        "items": {"type": "string", "maxLength": 80},
                    },
                    "uncertainties": {
                        "type": "array",
                        "maxItems": 4,
                        "items": {"type": "string", "maxLength": 120},
                    },
                    "valid_for_ms": {"type": "integer", "minimum": 0, "maximum": 30000},
                },
                "required": [
                    "state",
                    "confidence",
                    "evidence_refs",
                    "uncertainties",
                    "valid_for_ms",
                ],
            },
        },
        "interruptibility": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "label": {"type": "string", "enum": list(INTERRUPTIBILITY_LABELS)},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "evidence_refs": {
                    "type": "array",
                    "maxItems": 5,
                    "items": {"type": "string", "maxLength": 80},
                },
                "uncertainties": {
                    "type": "array",
                    "maxItems": 4,
                    "items": {"type": "string", "maxLength": 120},
                },
                "valid_for_ms": {"type": "integer", "minimum": 0, "maximum": 30000},
            },
            "required": [
                "label",
                "confidence",
                "evidence_refs",
                "uncertainties",
                "valid_for_ms",
            ],
        },
        "summary": {"type": "string", "maxLength": 240},
        "missing_evidence": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string", "maxLength": 120},
        },
    },
    "required": [
        "state_candidates",
        "interruptibility",
        "summary",
        "missing_evidence",
    ],
}


class StructuredSemanticsError(ValueError):
    """Raised when a semantic result is outside the bounded experiment shape."""


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StructuredSemanticsError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise StructuredSemanticsError(f"{name} must be finite")
    return result


def _bounded_text_list(value: Any, name: str, max_items: int, max_chars: int) -> list[str]:
    if not isinstance(value, list) or len(value) > max_items:
        raise StructuredSemanticsError(f"{name} must be a list with at most {max_items} items")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > max_chars:
            raise StructuredSemanticsError(f"{name} contains invalid text")
        result.append(item.strip())
    return result


def _pick(mapping: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    return {key: mapping[key] for key in keys if key in mapping}


def _result_from_snapshot(snapshot: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    result = snapshot.get("result", snapshot)
    if not isinstance(result, Mapping):
        raise StructuredSemanticsError("snapshot has no completed feature result")
    temporal = result.get("temporal")
    if not isinstance(temporal, Mapping):
        raise StructuredSemanticsError("snapshot has no temporal feature state")
    return result, temporal


def compact_feature_window(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Remove raw geometry and retain only semantic-level numeric evidence."""
    result, temporal = _result_from_snapshot(snapshot)
    raw_tracks = temporal.get("tracks", [])
    if not isinstance(raw_tracks, list):
        raise StructuredSemanticsError("temporal tracks must be a list")

    references: list[str] = []
    for raw_track in raw_tracks:
        if not isinstance(raw_track, Mapping):
            continue
        references.append(f"{raw_track.get('label', 'unknown')}:{raw_track.get('track_id', '?')}")

    tracks: list[dict[str, Any]] = []
    for raw_track in raw_tracks:
        if not isinstance(raw_track, Mapping):
            continue
        label = str(raw_track.get("label", "unknown"))
        track_ref = f"{label}:{raw_track.get('track_id', '?')}"
        item: dict[str, Any] = {
            "ref": track_ref,
            "label": label,
            "status": str(raw_track.get("status", "unknown")),
            "confidence": round(_finite_number(raw_track.get("confidence", 0.0), "confidence"), 4),
            "dwell_s": round(_finite_number(raw_track.get("dwell_s", 0.0), "dwell_s"), 3),
            "continuity": round(_finite_number(raw_track.get("continuity", 0.0), "continuity"), 4),
            "misses": int(raw_track.get("misses", 0)),
            "reacquired": int(raw_track.get("reacquired", 0)),
            "motion": _pick(
                raw_track.get("motion", {}),
                "state",
                "direction",
                "window_s",
                "sample_count",
                "displacement",
                "mean_speed",
                "jitter_rms",
            ),
            "region": _pick(
                raw_track.get("region", {}),
                "current",
                "dwell_s",
                "transitions",
                "window_mode",
                "window_stability",
            ),
        }
        if label == "person":
            item["pose"] = _pick(
                raw_track.get("pose", {}),
                "posture",
                "change_state",
                "delta",
                "visible_keypoints",
                "change_count",
                "posture_transitions",
                "window_mode",
                "window_stability",
            )
            relationships: list[dict[str, Any]] = []
            for relation in raw_track.get("relationships", []):
                if not isinstance(relation, Mapping):
                    continue
                relationships.append(
                    _pick(relation, "track_id", "label", "relation", "distance", "iou")
                )
            item["relationships"] = relationships
        tracks.append(item)

    observed_at = snapshot.get("server_time", result.get("processed_at_epoch_s", time.time()))
    return {
        "schema_version": INPUT_SCHEMA_VERSION,
        "source": {
            "kind": "isaac_ros_temporal_features",
            "raw_media_included": False,
        },
        "observed_at_epoch_s": round(_finite_number(observed_at, "observed_at_epoch_s"), 3),
        "source_sequence": result.get("sequence"),
        "frame_age_ms": result.get("frame_age_ms"),
        "low_level_latency_ms": result.get("latency_ms", {}),
        "feature_rate_hz": snapshot.get("inference_fps"),
        "window": temporal.get("window", {}),
        "active_person_count": temporal.get("active_person_count", 0),
        "tracks": tracks,
        "available_evidence_refs": ["window", "feature_quality", *references],
    }


def _validate_candidate(candidate: Any, *, interruptibility: bool = False) -> dict[str, Any]:
    if not isinstance(candidate, Mapping):
        raise StructuredSemanticsError("candidate must be an object")
    required = {
        "label" if interruptibility else "state",
        "confidence",
        "evidence_refs",
        "uncertainties",
        "valid_for_ms",
    }
    if set(candidate) != required:
        raise StructuredSemanticsError("candidate has unexpected or missing fields")
    label_key = "label" if interruptibility else "state"
    label = candidate[label_key]
    allowed = INTERRUPTIBILITY_LABELS if interruptibility else STATE_LABELS
    if label not in allowed:
        raise StructuredSemanticsError(f"unsupported {label_key}: {label!r}")
    confidence = _finite_number(candidate["confidence"], "confidence")
    if not 0.0 <= confidence <= 1.0:
        raise StructuredSemanticsError("confidence must be in [0, 1]")
    valid_for_ms = candidate["valid_for_ms"]
    if isinstance(valid_for_ms, bool) or not isinstance(valid_for_ms, int):
        raise StructuredSemanticsError("valid_for_ms must be an integer")
    if not 0 <= valid_for_ms <= 30000:
        raise StructuredSemanticsError("valid_for_ms is outside the bounded range")
    return {
        label_key: label,
        "confidence": round(confidence, 4),
        "evidence_refs": _bounded_text_list(candidate["evidence_refs"], "evidence_refs", 5, 80),
        "uncertainties": _bounded_text_list(candidate["uncertainties"], "uncertainties", 4, 120),
        "valid_for_ms": valid_for_ms,
    }


def parse_semantic_output(raw_output: str) -> dict[str, Any]:
    """Validate one model JSON object and fail closed on extra prose/fields."""
    if not isinstance(raw_output, str) or not raw_output.strip():
        raise StructuredSemanticsError("model output must be non-empty")
    try:
        value = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise StructuredSemanticsError("model output is not JSON") from exc
    if not isinstance(value, Mapping):
        raise StructuredSemanticsError("model output must be an object")
    expected = {"state_candidates", "interruptibility", "summary", "missing_evidence"}
    if set(value) != expected:
        raise StructuredSemanticsError("model output has unexpected or missing fields")
    candidates = value["state_candidates"]
    if not isinstance(candidates, list) or len(candidates) > 3:
        raise StructuredSemanticsError("state_candidates is outside the bounded range")
    summary = value["summary"]
    if not isinstance(summary, str) or not summary.strip() or len(summary.strip()) > 240:
        raise StructuredSemanticsError("summary is outside the bounded range")
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "state_candidates": [_validate_candidate(item) for item in candidates],
        "interruptibility": _validate_candidate(value["interruptibility"], interruptibility=True),
        "summary": summary.strip(),
        "missing_evidence": _bounded_text_list(value["missing_evidence"], "missing_evidence", 5, 120),
    }


def gate_semantic_result(
    semantic: Mapping[str, Any], feature_window: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Apply deterministic evidence gates before a candidate leaves the Edge."""
    tracks = feature_window.get("tracks", [])
    person_tracks = [
        track for track in tracks if isinstance(track, Mapping) and track.get("label") == "person"
    ]
    has_relationship = any(
        isinstance(track.get("relationships"), list) and bool(track["relationships"])
        for track in person_tracks
    )
    has_known_pose = any(
        isinstance(track.get("pose"), Mapping)
        and track["pose"].get("posture") not in (None, "unknown")
        for track in person_tracks
    )
    has_pose_change = any(
        isinstance(track.get("pose"), Mapping)
        and track["pose"].get("change_state") in ("changing", "minor_change")
        for track in person_tracks
    )
    active_person_count = int(feature_window.get("active_person_count", 0) or 0)
    window = feature_window.get("window", {})
    window_seconds = window.get("seconds", 5.0) if isinstance(window, Mapping) else 5.0
    try:
        max_valid_for_ms = max(1000, min(5000, round(float(window_seconds) * 1000)))
    except (TypeError, ValueError):
        max_valid_for_ms = 5000

    reasons: list[str] = []
    gated_candidates: list[dict[str, Any]] = []
    for candidate in semantic["state_candidates"]:
        item = {**candidate, "uncertainties": list(candidate["uncertainties"])}
        item["valid_for_ms"] = min(item["valid_for_ms"], max_valid_for_ms)
        if item["state"] == "possible_object_interaction" and not has_relationship:
            item["state"] = "unknown"
            item["confidence"] = min(item["confidence"], 0.2)
            item["uncertainties"].append("no person-object relationship was present")
            reasons.append("blocked possible_object_interaction without relationship evidence")
        elif item["state"] == "possible_posture_change" and not has_pose_change:
            item["state"] = "unknown"
            item["confidence"] = min(item["confidence"], 0.2)
            item["uncertainties"].append("no pose change evidence was present")
            reasons.append("blocked possible_posture_change without pose-change evidence")
        elif item["state"] == "absent" and active_person_count > 0:
            item["state"] = "unknown"
            item["confidence"] = min(item["confidence"], 0.2)
            item["uncertainties"].append("an active person track was present")
            reasons.append("blocked absent while an active person track was present")
        elif item["state"] == "present" and active_person_count == 0:
            item["state"] = "unknown"
            item["confidence"] = min(item["confidence"], 0.2)
            item["uncertainties"].append("no active person track was present")
            reasons.append("blocked present without an active person track")
        if item["state"] == "likely_busy" and not (has_relationship or has_known_pose):
            item["confidence"] = min(item["confidence"], 0.65)
            item["uncertainties"].append("attention or task engagement was not directly observed")
            reasons.append("capped likely_busy without relation or known posture evidence")
        item["uncertainties"] = list(dict.fromkeys(item["uncertainties"]))[:4]
        gated_candidates.append(item)

    interruptibility = {
        **semantic["interruptibility"],
        "uncertainties": list(semantic["interruptibility"]["uncertainties"]),
    }
    interruptibility["valid_for_ms"] = min(
        interruptibility["valid_for_ms"], max_valid_for_ms
    )
    if interruptibility["label"] == "likely_busy" and not (has_relationship or has_known_pose):
        interruptibility["confidence"] = min(interruptibility["confidence"], 0.65)
        interruptibility["uncertainties"].append(
            "attention or task engagement was not directly observed"
        )
        reasons.append("capped interruptibility likely_busy without direct engagement evidence")
    interruptibility["uncertainties"] = list(dict.fromkeys(interruptibility["uncertainties"]))[:4]
    gated = {
        "schema_version": semantic["schema_version"],
        "state_candidates": gated_candidates,
        "interruptibility": interruptibility,
        "summary": semantic["summary"],
        "missing_evidence": semantic["missing_evidence"],
    }
    return gated, list(dict.fromkeys(reasons))


def _prompt(feature_window: Mapping[str, Any]) -> str:
    return (
        "你是 OpenHalo Camera Edge 的受限语义解释器。\n"
        "输入是小模型从摄像头提取的结构化时序特征，不是图像。只能根据输入证据生成候选状态，"
        "不能把候选当作事实；不能推断情绪、医疗、生理状态、身份或用户真实意图。\n"
        "姿态为 unknown、关键点很少、轨迹不连续、关系不稳定或证据缺失时，降低置信度并写入 uncertainties。"
        "只有存在明确的人与物关系证据时，才使用 possible_object_interaction。"
        "可打扰性只能输出 likely_busy、likely_available、uncertain 或 unknown。"
        "summary 用简短中文，最多输出 3 个状态候选，valid_for_ms 不要超过 5000。"
        "输出必须严格符合给定 JSON schema，不要输出 Markdown 或额外文字。\n\n"
        "STRUCTURED_FEATURE_WINDOW:\n"
        + json.dumps(feature_window, ensure_ascii=False, separators=(",", ":"))
    )


def infer_structured(
    feature_window: Mapping[str, Any],
    *,
    endpoint: str = "http://127.0.0.1:11434",
    model: str = "qwen3:1.7b",
    timeout_seconds: float = 120.0,
    context: int = 2048,
    max_tokens: int = 256,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call a resident text model without an image attachment."""
    payload = {
        "model": model,
        "stream": True,
        "think": False,
        "format": OUTPUT_SCHEMA,
        "keep_alive": "5m",
        "messages": [
            {
                "role": "user",
                "content": _prompt(feature_window),
            }
        ],
        "options": {
            "temperature": 0.0,
            "seed": 42,
            "num_ctx": context,
            "num_predict": max_tokens,
        },
    }
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    first_content: float | None = None
    text = ""
    final: Mapping[str, Any] | None = None
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        for line in response:
            if not line.strip():
                continue
            item = json.loads(line)
            if "error" in item:
                raise RuntimeError(str(item["error"]))
            content = item.get("message", {}).get("content", "")
            if content and first_content is None:
                first_content = time.perf_counter() - started
            text += content
            if item.get("done"):
                final = item
    if final is None:
        raise RuntimeError("Ollama stream ended without completion")
    try:
        result = parse_semantic_output(text)
    except StructuredSemanticsError as exc:
        preview = text[:240].replace("\n", "\\n")
        raise StructuredSemanticsError(f"{exc}; output_preview={preview!r}") from exc
    metrics: dict[str, Any] = {
        "request_s": round(time.perf_counter() - started, 6),
        "first_content_s": round(first_content, 6) if first_content is not None else None,
        "input_chars": len(payload["messages"][0]["content"]),
        "output_chars": len(text),
        "input_tokens": final.get("prompt_eval_count"),
        "output_tokens": final.get("eval_count"),
        "done_reason": final.get("done_reason"),
    }
    for key in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
        value = final.get(key)
        metrics[key.replace("_duration", "_s")] = (
            round(float(value) / 1e9, 6) if isinstance(value, (int, float)) else None
        )
    return result, metrics


def _fetch_snapshot(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10.0) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise StructuredSemanticsError("state endpoint did not return an object")
    return value


def run(args: argparse.Namespace) -> int:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    records_path = output_dir / "requests.jsonl"
    for request_number in range(1, args.requests + 1):
        started = time.time()
        try:
            if args.input_json is not None:
                snapshot = json.loads(args.input_json.read_text(encoding="utf-8"))
            else:
                snapshot = _fetch_snapshot(args.input_url)
            feature_window = compact_feature_window(snapshot)
            model_semantic, metrics = infer_structured(
                feature_window,
                endpoint=args.endpoint,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                context=args.context,
                max_tokens=args.max_tokens,
            )
            gated_semantic, gate_reasons = gate_semantic_result(model_semantic, feature_window)
            record = {
                "request": request_number,
                "started_at_epoch_s": started,
                "ok": True,
                "model": args.model,
                "feature_window": feature_window,
                "model_semantic": model_semantic,
                "gated_semantic": gated_semantic,
                "gate_reasons": gate_reasons,
                "metrics": metrics,
            }
            print(json.dumps(record, ensure_ascii=False), flush=True)
        except Exception as exc:
            record = {
                "request": request_number,
                "started_at_epoch_s": started,
                "ok": False,
                "model": args.model,
                "error": f"{type(exc).__name__}: {exc}",
            }
            print(json.dumps(record, ensure_ascii=False), flush=True)
        with records_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        if request_number < args.requests and args.interval_seconds > 0:
            time.sleep(args.interval_seconds)
    return 0


def build_parser() -> argparse.ArgumentParser:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-url", default="http://127.0.0.1:8876/api/state")
    parser.add_argument("--input-json", type=Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3:1.7b")
    parser.add_argument("--requests", type=int, default=1)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--context", type=int, default=2048)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/openhalo-isaac-ros/results-structured-semantics-v1"),
    )
    parser.add_argument("--source-root", type=Path, default=here)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
