"""Compact context snapshot reducers for hot-path presence work."""

from personal_runtime.context_contracts import RuntimeObservation


LOCATION_FRESHNESS_MINUTES = 5
RUNTIME_HEALTH_FRESHNESS_MINUTES = 5
RUNTIME_PROCESS_PID_FRESHNESS_MINUTES = 5
RUNTIME_PROCESS_PRESENT_FRESHNESS_MINUTES = 5
RUNTIME_PROCESS_MEMORY_RSS_FRESHNESS_MINUTES = 5
RUNTIME_PROCESS_STARTED_AT_FRESHNESS_MINUTES = 5
HOST_CPU_LOAD_FRESHNESS_MINUTES = 5
HOST_MEMORY_AVAILABLE_FRESHNESS_MINUTES = 5
HOST_MEMORY_USED_FRESHNESS_MINUTES = 5
HOST_MEMORY_PRESSURE_FRESHNESS_MINUTES = 5
EVIDENCE_LIMIT = 2


def build_context_snapshot(
    observations: list[RuntimeObservation],
    snapshot_time: str | None = None,
) -> dict:
    contract = build_context_snapshot_contract(
        observations,
        snapshot_time=snapshot_time,
    )
    return {
        field_name: field_contract["value"]
        for field_name, field_contract in contract["fields"].items()
    }


def build_context_snapshot_contract(
    observations: list[RuntimeObservation],
    snapshot_time: str | None = None,
) -> dict:
    return {
        "snapshot_time": snapshot_time,
        "fields": {
            field_name: _build_field_contract(
                observations,
                observation_name=observation_name,
                reducer=reducer,
                freshness_minutes=freshness_minutes,
                snapshot_time=snapshot_time,
            )
            for field_name, observation_name, reducer, freshness_minutes in _snapshot_field_specs()
        },
    }


def _reduce_current_location(
    observations: list[RuntimeObservation],
    snapshot_time: str | None = None,
) -> str:
    location_observations = [
        observation
        for observation in observations
        if observation.name == "user.location"
    ]
    if snapshot_time is not None:
        location_observations = [
            observation
            for observation in location_observations
            if _within_freshness_window(
                observed_at=observation.observed_at,
                snapshot_time=snapshot_time,
                freshness_minutes=LOCATION_FRESHNESS_MINUTES,
            )
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


def _within_freshness_window(
    observed_at: str,
    snapshot_time: str,
    freshness_minutes: int,
) -> bool:
    return (
        _to_epoch_minutes(snapshot_time) - _to_epoch_minutes(observed_at)
    ) <= freshness_minutes


def _build_field_contract(
    observations: list[RuntimeObservation],
    observation_name: str,
    reducer,
    freshness_minutes: int,
    snapshot_time: str | None = None,
) -> dict:
    matching_observations = _ordered_observations(
        observations,
        observation_name=observation_name,
    )
    fresh_observations = matching_observations
    if snapshot_time is not None:
        fresh_observations = [
            observation
            for observation in matching_observations
            if _within_freshness_window(
                observed_at=observation.observed_at,
                snapshot_time=snapshot_time,
                freshness_minutes=freshness_minutes,
            )
        ]

    value = reducer(observations, snapshot_time=snapshot_time)
    if value == "ambiguous":
        return {
            "observation_name": observation_name,
            "value": value,
            "status": "ambiguous",
            "evidence": [
                observation.to_dict()
                for observation in fresh_observations[:EVIDENCE_LIMIT]
            ],
        }
    if not matching_observations:
        return {
            "observation_name": observation_name,
            "value": "unknown",
            "status": "missing",
            "evidence": [],
        }
    if snapshot_time is not None and not fresh_observations:
        return {
            "observation_name": observation_name,
            "value": "unknown",
            "status": "stale",
            "evidence": [
                observation.to_dict()
                for observation in matching_observations[:EVIDENCE_LIMIT]
            ],
        }

    evidence_source = fresh_observations or matching_observations
    return {
        "observation_name": observation_name,
        "value": value,
        "status": "fresh",
        "evidence": [
            observation.to_dict() for observation in evidence_source[:EVIDENCE_LIMIT]
        ],
    }


def _ordered_observations(
    observations: list[RuntimeObservation],
    observation_name: str,
) -> list[RuntimeObservation]:
    matching_observations = [
        observation
        for observation in observations
        if observation.name == observation_name
    ]
    return sorted(
        matching_observations,
        key=lambda observation: (
            observation.observed_at,
            observation.confidence,
        ),
        reverse=True,
    )


def _reduce_runtime_health_state(
    observations: list[RuntimeObservation],
    snapshot_time: str | None = None,
) -> str:
    health_observations = [
        observation
        for observation in observations
        if observation.name == "runtime.health_state"
    ]
    if snapshot_time is not None:
        health_observations = [
            observation
            for observation in health_observations
            if _within_freshness_window(
                observed_at=observation.observed_at,
                snapshot_time=snapshot_time,
                freshness_minutes=RUNTIME_HEALTH_FRESHNESS_MINUTES,
            )
        ]
    if not health_observations:
        return "unknown"

    ordered = sorted(
        health_observations,
        key=lambda observation: (
            observation.observed_at,
            observation.confidence,
        ),
        reverse=True,
    )
    return ordered[0].value


def _reduce_runtime_process_pid(
    observations: list[RuntimeObservation],
    snapshot_time: str | None = None,
) -> int | str:
    process_pid_observations = [
        observation for observation in observations if observation.name == "runtime.process_pid"
    ]
    if snapshot_time is not None:
        process_pid_observations = [
            observation
            for observation in process_pid_observations
            if _within_freshness_window(
                observed_at=observation.observed_at,
                snapshot_time=snapshot_time,
                freshness_minutes=RUNTIME_PROCESS_PID_FRESHNESS_MINUTES,
            )
        ]
    if not process_pid_observations:
        return "unknown"

    ordered = sorted(
        process_pid_observations,
        key=lambda observation: (
            observation.observed_at,
            observation.confidence,
        ),
        reverse=True,
    )
    return ordered[0].value


def _reduce_host_memory_pressure(
    observations: list[RuntimeObservation],
    snapshot_time: str | None = None,
) -> str:
    pressure_observations = [
        observation
        for observation in observations
        if observation.name == "host.memory_pressure"
    ]
    if snapshot_time is not None:
        pressure_observations = [
            observation
            for observation in pressure_observations
            if _within_freshness_window(
                observed_at=observation.observed_at,
                snapshot_time=snapshot_time,
                freshness_minutes=HOST_MEMORY_PRESSURE_FRESHNESS_MINUTES,
            )
        ]
    if not pressure_observations:
        return "unknown"

    ordered = sorted(
        pressure_observations,
        key=lambda observation: (
            observation.observed_at,
            observation.confidence,
        ),
        reverse=True,
    )
    return ordered[0].value


def _reduce_host_cpu_load_ratio(
    observations: list[RuntimeObservation],
    snapshot_time: str | None = None,
) -> float | str:
    cpu_load_observations = [
        observation
        for observation in observations
        if observation.name == "host.cpu_load_ratio"
    ]
    if snapshot_time is not None:
        cpu_load_observations = [
            observation
            for observation in cpu_load_observations
            if _within_freshness_window(
                observed_at=observation.observed_at,
                snapshot_time=snapshot_time,
                freshness_minutes=HOST_CPU_LOAD_FRESHNESS_MINUTES,
            )
        ]
    if not cpu_load_observations:
        return "unknown"

    ordered = sorted(
        cpu_load_observations,
        key=lambda observation: (
            observation.observed_at,
            observation.confidence,
        ),
        reverse=True,
    )
    return ordered[0].value


def _reduce_host_memory_available_bytes(
    observations: list[RuntimeObservation],
    snapshot_time: str | None = None,
) -> int | str:
    memory_available_observations = [
        observation
        for observation in observations
        if observation.name == "host.memory_available_bytes"
    ]
    if snapshot_time is not None:
        memory_available_observations = [
            observation
            for observation in memory_available_observations
            if _within_freshness_window(
                observed_at=observation.observed_at,
                snapshot_time=snapshot_time,
                freshness_minutes=HOST_MEMORY_AVAILABLE_FRESHNESS_MINUTES,
            )
        ]
    if not memory_available_observations:
        return "unknown"

    ordered = sorted(
        memory_available_observations,
        key=lambda observation: (
            observation.observed_at,
            observation.confidence,
        ),
        reverse=True,
    )
    return ordered[0].value


def _reduce_host_memory_used_bytes(
    observations: list[RuntimeObservation],
    snapshot_time: str | None = None,
) -> int | str:
    memory_used_observations = [
        observation
        for observation in observations
        if observation.name == "host.memory_used_bytes"
    ]
    if snapshot_time is not None:
        memory_used_observations = [
            observation
            for observation in memory_used_observations
            if _within_freshness_window(
                observed_at=observation.observed_at,
                snapshot_time=snapshot_time,
                freshness_minutes=HOST_MEMORY_USED_FRESHNESS_MINUTES,
            )
        ]
    if not memory_used_observations:
        return "unknown"

    ordered = sorted(
        memory_used_observations,
        key=lambda observation: (
            observation.observed_at,
            observation.confidence,
        ),
        reverse=True,
    )
    return ordered[0].value


def _reduce_runtime_process_present(
    observations: list[RuntimeObservation],
    snapshot_time: str | None = None,
) -> bool | str:
    process_present_observations = [
        observation
        for observation in observations
        if observation.name == "runtime.process_present"
    ]
    if snapshot_time is not None:
        process_present_observations = [
            observation
            for observation in process_present_observations
            if _within_freshness_window(
                observed_at=observation.observed_at,
                snapshot_time=snapshot_time,
                freshness_minutes=RUNTIME_PROCESS_PRESENT_FRESHNESS_MINUTES,
            )
        ]
    if not process_present_observations:
        return "unknown"

    ordered = sorted(
        process_present_observations,
        key=lambda observation: (
            observation.observed_at,
            observation.confidence,
        ),
        reverse=True,
    )
    return ordered[0].value


def _reduce_runtime_process_memory_rss(
    observations: list[RuntimeObservation],
    snapshot_time: str | None = None,
) -> int | str:
    process_memory_observations = [
        observation
        for observation in observations
        if observation.name == "runtime.process_memory_rss_bytes"
    ]
    if snapshot_time is not None:
        process_memory_observations = [
            observation
            for observation in process_memory_observations
            if _within_freshness_window(
                observed_at=observation.observed_at,
                snapshot_time=snapshot_time,
                freshness_minutes=RUNTIME_PROCESS_MEMORY_RSS_FRESHNESS_MINUTES,
            )
        ]
    if not process_memory_observations:
        return "unknown"

    ordered = sorted(
        process_memory_observations,
        key=lambda observation: (
            observation.observed_at,
            observation.confidence,
        ),
        reverse=True,
    )
    return ordered[0].value


def _reduce_runtime_process_started_at(
    observations: list[RuntimeObservation],
    snapshot_time: str | None = None,
) -> str:
    process_started_at_observations = [
        observation
        for observation in observations
        if observation.name == "runtime.process_started_at"
    ]
    if snapshot_time is not None:
        process_started_at_observations = [
            observation
            for observation in process_started_at_observations
            if _within_freshness_window(
                observed_at=observation.observed_at,
                snapshot_time=snapshot_time,
                freshness_minutes=RUNTIME_PROCESS_STARTED_AT_FRESHNESS_MINUTES,
            )
        ]
    if not process_started_at_observations:
        return "unknown"

    ordered = sorted(
        process_started_at_observations,
        key=lambda observation: (
            observation.observed_at,
            observation.confidence,
        ),
        reverse=True,
    )
    return ordered[0].value


def _to_epoch_minutes(timestamp: str) -> int:
    date_part, time_part = timestamp.rstrip("Z").split("T", maxsplit=1)
    year, month, day = (int(part) for part in date_part.split("-"))
    hour_text, minute_text, second_text = time_part.split(":")
    hour = int(hour_text)
    minute = int(minute_text)
    _second = int(second_text.split(".", maxsplit=1)[0])
    return (((year * 12 + month) * 31 + day) * 24 + hour) * 60 + minute


def _snapshot_field_specs():
    return [
        (
            "user.current_location",
            "user.location",
            _reduce_current_location,
            LOCATION_FRESHNESS_MINUTES,
        ),
        (
            "runtime.current_health_state",
            "runtime.health_state",
            _reduce_runtime_health_state,
            RUNTIME_HEALTH_FRESHNESS_MINUTES,
        ),
        (
            "runtime.current_process_pid",
            "runtime.process_pid",
            _reduce_runtime_process_pid,
            RUNTIME_PROCESS_PID_FRESHNESS_MINUTES,
        ),
        (
            "runtime.current_process_present",
            "runtime.process_present",
            _reduce_runtime_process_present,
            RUNTIME_PROCESS_PRESENT_FRESHNESS_MINUTES,
        ),
        (
            "runtime.current_process_memory_rss_bytes",
            "runtime.process_memory_rss_bytes",
            _reduce_runtime_process_memory_rss,
            RUNTIME_PROCESS_MEMORY_RSS_FRESHNESS_MINUTES,
        ),
        (
            "runtime.current_process_started_at",
            "runtime.process_started_at",
            _reduce_runtime_process_started_at,
            RUNTIME_PROCESS_STARTED_AT_FRESHNESS_MINUTES,
        ),
        (
            "host.current_cpu_load_ratio",
            "host.cpu_load_ratio",
            _reduce_host_cpu_load_ratio,
            HOST_CPU_LOAD_FRESHNESS_MINUTES,
        ),
        (
            "host.current_memory_available_bytes",
            "host.memory_available_bytes",
            _reduce_host_memory_available_bytes,
            HOST_MEMORY_AVAILABLE_FRESHNESS_MINUTES,
        ),
        (
            "host.current_memory_used_bytes",
            "host.memory_used_bytes",
            _reduce_host_memory_used_bytes,
            HOST_MEMORY_USED_FRESHNESS_MINUTES,
        ),
        (
            "host.current_memory_pressure",
            "host.memory_pressure",
            _reduce_host_memory_pressure,
            HOST_MEMORY_PRESSURE_FRESHNESS_MINUTES,
        ),
    ]
