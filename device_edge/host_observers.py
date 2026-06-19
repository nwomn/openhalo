"""Host-edge observation helpers for host metrics and runtime health."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def build_host_metric_observations(snapshot: dict, observed_at: str) -> list[dict]:
    return [
        _build_observation(
            "host.cpu_load_ratio", snapshot["cpu_load_ratio"], observed_at
        ),
        _build_observation(
            "host.memory_used_bytes", snapshot["memory_used_bytes"], observed_at
        ),
        _build_observation(
            "host.memory_available_bytes",
            snapshot["memory_available_bytes"],
            observed_at,
        ),
        _build_observation(
            "host.memory_pressure", snapshot["memory_pressure"], observed_at
        ),
        _build_observation("host.net_rx_bytes", snapshot["net_rx_bytes"], observed_at),
        _build_observation("host.net_tx_bytes", snapshot["net_tx_bytes"], observed_at),
    ]


def build_runtime_health_observations(snapshot: dict, observed_at: str) -> list[dict]:
    return [
        _build_observation(
            "runtime.health_state", snapshot["health_state"], observed_at
        ),
        _build_observation("runtime.process_pid", snapshot["process_pid"], observed_at),
        _build_observation(
            "runtime.process_present", snapshot["process_present"], observed_at
        ),
        _build_observation(
            "runtime.process_started_at",
            snapshot["process_started_at"],
            observed_at,
        ),
        _build_observation(
            "runtime.process_memory_rss_bytes",
            snapshot["process_memory_rss_bytes"],
            observed_at,
        ),
    ]


def read_host_metric_snapshot(
    loadavg_path: Path = Path("/proc/loadavg"),
    meminfo_path: Path = Path("/proc/meminfo"),
    netdev_path: Path = Path("/proc/net/dev"),
) -> dict:
    loadavg_parts = loadavg_path.read_text(encoding="utf-8").split()
    cpu_load_ratio = float(loadavg_parts[0])

    meminfo = {}
    for line in meminfo_path.read_text(encoding="utf-8").splitlines():
        key, raw_value = line.split(":", 1)
        meminfo[key] = int(raw_value.strip().split()[0]) * 1024

    total = meminfo["MemTotal"]
    available = meminfo["MemAvailable"]
    used = max(total - available, 0)
    usage_ratio = used / total if total else 0.0
    if usage_ratio >= 0.9:
        memory_pressure = "high"
    elif usage_ratio >= 0.75:
        memory_pressure = "elevated"
    else:
        memory_pressure = "normal"

    rx_bytes = 0
    tx_bytes = 0
    for line in netdev_path.read_text(encoding="utf-8").splitlines()[2:]:
        if ":" not in line:
            continue
        _, raw_stats = line.split(":", 1)
        fields = raw_stats.split()
        rx_bytes += int(fields[0])
        tx_bytes += int(fields[8])

    return {
        "cpu_load_ratio": cpu_load_ratio,
        "memory_used_bytes": used,
        "memory_available_bytes": available,
        "memory_pressure": memory_pressure,
        "net_rx_bytes": rx_bytes,
        "net_tx_bytes": tx_bytes,
    }


def read_runtime_health_snapshot(
    pid: int | None,
    process_started_at: str | None = None,
    statm_path: Path | None = None,
) -> dict:
    process_present = pid is not None
    rss_bytes = 0
    if process_present and statm_path is not None and statm_path.exists():
        rss_pages = int(statm_path.read_text(encoding="utf-8").split()[1])
        rss_bytes = rss_pages * 4096

    return {
        "health_state": "healthy" if process_present else "offline",
        "process_pid": pid,
        "process_present": process_present,
        "process_started_at": process_started_at
        or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "process_memory_rss_bytes": rss_bytes,
    }


def _build_observation(name: str, value, observed_at: str) -> dict:
    return {
        "name": name,
        "value": value,
        "observed_at": observed_at,
        "confidence": 1.0,
    }
