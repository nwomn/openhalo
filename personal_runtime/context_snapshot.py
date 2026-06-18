"""Compact context snapshot reducers for hot-path presence work."""

from personal_runtime.context_contracts import RuntimeObservation


def build_context_snapshot(observations: list[RuntimeObservation]) -> dict:
    return {
        "user.current_location": _reduce_current_location(observations),
    }


def _reduce_current_location(observations: list[RuntimeObservation]) -> str:
    location_observations = [
        observation
        for observation in observations
        if observation.name == "user.location"
    ]
    if not location_observations:
        return "unknown"

    ordered = sorted(
        location_observations,
        key=lambda observation: (
            observation.observed_at,
            observation.confidence,
        ),
        reverse=True,
    )
    best = ordered[0]
    if len(ordered) == 1:
        return best.value

    runner_up = ordered[1]
    close_confidence = abs(best.confidence - runner_up.confidence) <= 0.05
    close_time = abs(
        _to_epoch_minutes(best.observed_at) - _to_epoch_minutes(runner_up.observed_at)
    ) <= 1
    if best.value != runner_up.value and close_confidence and close_time:
        return "ambiguous"
    return best.value


def _to_epoch_minutes(timestamp: str) -> int:
    date_part, time_part = timestamp.rstrip("Z").split("T", maxsplit=1)
    year, month, day = (int(part) for part in date_part.split("-"))
    hour, minute, _second = (int(part) for part in time_part.split(":"))
    return (((year * 12 + month) * 31 + day) * 24 + hour) * 60 + minute
