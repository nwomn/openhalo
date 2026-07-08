"""Runtime-neutral diagnostic event helpers for module boundary records."""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from datetime import UTC
from datetime import datetime


SCHEMA_VERSION = "diagnostic.v1"


@dataclass(slots=True)
class DiagnosticCorrelation:
    trace_id: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    event_id: str | None = None
    request_id: str | None = None
    interaction_id: str | None = None
    parent_event_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class DiagnosticEvent:
    timestamp: str
    side: str
    module: str
    operation: str
    phase: str
    correlation: DiagnosticCorrelation
    input: dict | None
    output: dict | None
    summary: str
    device: dict | None = None
    runtime_instance_id: str | None = None
    severity: str = "info"
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "side": self.side,
            "device": self.device,
            "runtime_instance_id": self.runtime_instance_id,
            "module": self.module,
            "operation": self.operation,
            "phase": self.phase,
            "correlation": self.correlation.to_dict(),
            "input": self.input,
            "output": self.output,
            "summary": self.summary,
            "severity": self.severity,
        }


class JsonlDiagnosticWriter:
    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, event: DiagnosticEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=True))
            handle.write("\n")


class JsonlDiagnosticRecorder:
    def __init__(self, path: Path, timestamp_provider=None) -> None:
        self.writer = JsonlDiagnosticWriter(path)
        self.timestamp_provider = timestamp_provider or _utc_timestamp

    def record(self, event: DiagnosticEvent) -> None:
        self.writer.record(event)

    def record_boundary(
        self,
        side: str,
        module: str,
        operation: str,
        phase: str,
        correlation: dict | DiagnosticCorrelation | None,
        input_payload: dict | None,
        output_payload: dict | None,
        summary: str,
        device: dict | None = None,
        runtime_instance_id: str | None = None,
        severity: str = "info",
        timestamp: str | None = None,
    ) -> DiagnosticEvent:
        event = _build_diagnostic_event(
            timestamp=timestamp or self.timestamp_provider(),
            side=side,
            device=device,
            runtime_instance_id=runtime_instance_id,
            module=module,
            operation=operation,
            phase=phase,
            correlation=correlation,
            input_payload=input_payload,
            output_payload=output_payload,
            summary=summary,
            severity=severity,
        )
        self.record(event)
        return event


class InMemoryDiagnosticRecorder:
    def __init__(self, timestamp_provider=None) -> None:
        self.events: list[DiagnosticEvent] = []
        self.timestamp_provider = timestamp_provider or _utc_timestamp

    def record(self, event: DiagnosticEvent) -> None:
        self.events.append(event)

    def record_boundary(
        self,
        side: str,
        module: str,
        operation: str,
        phase: str,
        correlation: dict | DiagnosticCorrelation | None,
        input_payload: dict | None,
        output_payload: dict | None,
        summary: str,
        device: dict | None = None,
        runtime_instance_id: str | None = None,
        severity: str = "info",
        timestamp: str | None = None,
    ) -> DiagnosticEvent:
        event = _build_diagnostic_event(
            timestamp=timestamp or self.timestamp_provider(),
            side=side,
            device=device,
            runtime_instance_id=runtime_instance_id,
            module=module,
            operation=operation,
            phase=phase,
            correlation=correlation,
            input_payload=input_payload,
            output_payload=output_payload,
            summary=summary,
            severity=severity,
        )
        self.record(event)
        return event


class DiagnosticBoundary(AbstractContextManager):
    def __init__(
        self,
        recorder,
        side: str,
        module: str,
        operation: str,
        correlation: dict | DiagnosticCorrelation | None,
        input_payload: dict | None,
        summary: str,
        device: dict | None = None,
        runtime_instance_id: str | None = None,
    ) -> None:
        self.recorder = recorder
        self.side = side
        self.module = module
        self.operation = operation
        self.correlation = correlation
        self.input_payload = input_payload
        self.summary = summary
        self.device = device
        self.runtime_instance_id = runtime_instance_id
        self._recorded = False

    def __enter__(self) -> "DiagnosticBoundary":
        return self

    def output(self, output_payload: dict | None, summary: str | None = None) -> None:
        self._record(
            phase="output",
            output_payload=output_payload,
            summary=summary or self.summary,
            severity="info",
        )

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if exc_value is not None and not self._recorded:
            self._record(
                phase="error",
                output_payload={
                    "error_type": exc_type.__name__ if exc_type is not None else "Error",
                    "message": str(exc_value),
                },
                summary=self.summary,
                severity="error",
            )
        return False

    def _record(
        self,
        phase: str,
        output_payload: dict | None,
        summary: str,
        severity: str,
    ) -> None:
        if self.recorder is None:
            return
        self.recorder.record_boundary(
            side=self.side,
            device=self.device,
            runtime_instance_id=self.runtime_instance_id,
            module=self.module,
            operation=self.operation,
            phase=phase,
            correlation=self.correlation,
            input_payload=self.input_payload,
            output_payload=output_payload,
            summary=summary,
            severity=severity,
        )
        self._recorded = True


class DiagnosticBoundaryRecorder:
    def __init__(
        self,
        recorder=None,
        side: str = "runtime",
        device: dict | None = None,
        runtime_instance_id: str | None = None,
    ) -> None:
        self.recorder = recorder
        self.side = side
        self.device = device
        self.runtime_instance_id = runtime_instance_id

    def boundary(
        self,
        module: str,
        operation: str,
        correlation: dict | DiagnosticCorrelation | None,
        input_payload: dict | None,
        summary: str,
    ) -> DiagnosticBoundary:
        return DiagnosticBoundary(
            recorder=self.recorder,
            side=self.side,
            device=self.device,
            runtime_instance_id=self.runtime_instance_id,
            module=module,
            operation=operation,
            correlation=correlation,
            input_payload=input_payload,
            summary=summary,
        )


class TraceRecorder:
    def __init__(
        self,
        emitters: list[Callable[[str], None]] | None = None,
        retain_entries: bool = True,
    ) -> None:
        self.entries: list[tuple[str, str, dict]] = []
        self.emitters = emitters or []
        self.retain_entries = retain_entries

    def record(self, component: str, message: str, **fields: str) -> None:
        entry = (component, message, fields)
        if self.retain_entries:
            self.entries.append(entry)

        line = self._format_entry(entry)
        for emitter in self.emitters:
            emitter(line)

    def format_lines(self) -> list[str]:
        return [self._format_entry(entry) for entry in self.entries]

    def _format_entry(self, entry: tuple[str, str, dict]) -> str:
        component, message, fields = entry
        line = f"{component} {message}"
        if fields:
            details = ", ".join(f"{key}={value}" for key, value in fields.items())
            line = f"{line} [{details}]"
        return line


def build_trace_id(device_id: str, sequence: int) -> str:
    return f"trace-{device_id}-{sequence}"


def build_session_id(device_id: str) -> str:
    return f"session-{device_id}"


def build_turn_id(device_id: str, sequence: int) -> str:
    return f"turn-{device_id}-{sequence}"


def correlation_from_frame(frame: dict) -> dict:
    return {
        "trace_id": frame.get("trace_id"),
        "session_id": frame.get("session_id"),
        "turn_id": frame.get("turn_id"),
        "event_id": frame.get("event_id"),
        "request_id": frame.get("request_id"),
        "interaction_id": frame.get("interaction_id"),
        "parent_event_id": frame.get("parent_event_id"),
    }


def add_correlation_to_frame(frame: dict, correlation: dict) -> dict:
    return {
        **{
            key: value
            for key, value in correlation.items()
            if value is not None
        },
        **frame,
    }


def _build_diagnostic_event(
    timestamp: str,
    side: str,
    device: dict | None,
    runtime_instance_id: str | None,
    module: str,
    operation: str,
    phase: str,
    correlation: dict | DiagnosticCorrelation | None,
    input_payload: dict | None,
    output_payload: dict | None,
    summary: str,
    severity: str,
) -> DiagnosticEvent:
    if isinstance(correlation, DiagnosticCorrelation):
        diagnostic_correlation = correlation
    else:
        correlation = correlation or {}
        diagnostic_correlation = DiagnosticCorrelation(
            trace_id=correlation.get("trace_id"),
            session_id=correlation.get("session_id"),
            turn_id=correlation.get("turn_id"),
            event_id=correlation.get("event_id"),
            request_id=correlation.get("request_id"),
            interaction_id=correlation.get("interaction_id"),
            parent_event_id=correlation.get("parent_event_id"),
        )
    return DiagnosticEvent(
        timestamp=timestamp,
        side=side,
        device=device,
        runtime_instance_id=runtime_instance_id,
        module=module,
        operation=operation,
        phase=phase,
        correlation=diagnostic_correlation,
        input=input_payload,
        output=output_payload,
        summary=summary,
        severity=severity,
    )


def _utc_timestamp() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
