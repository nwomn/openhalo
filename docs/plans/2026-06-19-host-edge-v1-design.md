# Host Edge V1 Design Baseline

Date: 2026-06-19
Status: Working design baseline

## Purpose

This document captures the first concrete design baseline for a real host-class `Device Edge`.

It is intended to make five things explicit:

- how the first host edge stays frontend-side even when it lives on the same server as the runtime
- which capability surface is in scope for v1
- how host observations and runtime control actions move through the existing runtime architecture
- how runtime restart can be initiated safely without requiring the runtime to confirm its own recovery
- how the first deployment-specific control implementation should remain replaceable later

This is a design baseline, not a final implementation spec.

## Core Design Summary

The first host edge should run on the same server substrate as the personal runtime, but it must remain an explicit frontend-side daemon rather than collapsing into backend-internal monitoring code.

The v1 scope is:

- `host-wide observation`
- `runtime-scoped control`
- `independent host-edge daemon lifecycle`

The v1 scope is not:

- whole-host operational control
- arbitrary shell execution
- same-process backend instrumentation pretending to be an edge

The first host edge should expose three capability surfaces:

- `host.metrics`
- `runtime.health`
- `runtime.control`

The control contract should stay deployment-agnostic. The first concrete adapter may target the current plain Python-process deployment, while later adapters may target `systemd` or another supervisor without changing the edge contract seen by the rest of the runtime.

## Host Edge Boundary

The first host edge is still part of `Frontend / Device Edge`.

That remains true even when:

- the edge daemon and backend runtime run on the same machine
- the transport path is loopback or private-network only
- the control actions affect the backend runtime process directly

Important boundary rule:

- all cross-boundary traffic still flows through `Edge Session Link <-> Gateway`

This means the host edge daemon:

- keeps its own process lifetime
- establishes its own edge session
- announces capabilities like any other edge device
- sends observations through the normal gateway ingress path
- receives `action_request` frames through the normal gateway egress path

This separation is what makes disruptive actions such as `runtime.restart` coherent. The runtime cannot safely restart itself and also remain the observer that confirms its own return. The independent host edge daemon can.

## Device Shape V1

The first host edge should use a normal device contract, not a backend-only special case.

Example:

```json
{
  "device_id": "host-edge-1",
  "device_type": "server",
  "role": "host_runtime_companion",
  "profile": "host_daemon",
  "capabilities": [
    "host.metrics",
    "runtime.health",
    "runtime.control"
  ]
}
```

This device identity should represent the daemon itself, not the runtime backend process.

## Capability Surface V1

### `host.metrics`

Responsibilities:

- observe coarse host resource state
- provide presence-relevant host pressure signals
- avoid backend-private shortcuts

Initial normalized observation vocabulary:

- `host.cpu_load_ratio`
- `host.memory_used_bytes`
- `host.memory_available_bytes`
- `host.memory_pressure`
- `host.net_rx_bytes`
- `host.net_tx_bytes`

V1 notes:

- raw OS counters remain local implementation details
- the runtime stores normalized observations only
- Linux-first collection is acceptable for v1 because the target deployment is a cloud server

### `runtime.health`

Responsibilities:

- observe whether the backend runtime process appears healthy
- provide the authoritative post-restart recovery signal
- expose compact runtime-process state without requiring whole-host control

Initial normalized observation vocabulary:

- `runtime.health_state`
- `runtime.process_pid`
- `runtime.process_present`
- `runtime.process_started_at`
- `runtime.process_memory_rss_bytes`

Suggested `runtime.health_state` values:

- `healthy`
- `degraded`
- `offline`
- `ambiguous`

### `runtime.control`

Responsibilities:

- provide a narrow execution surface for runtime-scoped operational actions
- remain deployment-agnostic at the contract layer
- keep diagnostic outputs structured enough for agent reasoning and UI inspection

Initial actions:

- `runtime.status`
- `runtime.restart`
- `runtime.reload`
- `runtime.collect_logs`

Initial exclusions:

- `runtime.start`
- `runtime.stop`
- arbitrary shell or subprocess execution
- whole-host service or network control

## Observation Transport Shape

The current protocol already has a generic `event_push` envelope, so the first host-edge slice should reuse that instead of adding a new transport primitive immediately.

Recommended shape:

```json
{
  "type": "event_push",
  "device_id": "host-edge-1",
  "capability": "host.metrics",
  "event_id": "evt-host-001",
  "payload": {
    "observations": [
      {
        "name": "host.memory_pressure",
        "value": "normal",
        "observed_at": "2026-06-19T09:30:00Z",
        "confidence": 0.93
      }
    ]
  }
}
```

The gateway should:

- keep the raw event in `state.events`
- record each normalized observation in `state.observations`
- attach provenance from the enclosing frame such as `source_device_id`, `source_capability`, and `source_event_id`

## Runtime Control Result Shape

`runtime.control` actions should continue using the normal `action_request -> action_result` path.

The result surface should prefer structured payloads:

```json
{
  "type": "action_result",
  "device_id": "host-edge-1",
  "result": {
    "status": "ok",
    "capability": "runtime.status",
    "details": {
      "state": "running",
      "pid": 42137,
      "uptime_s": 183,
      "memory_rss_bytes": 28114944
    }
  }
}
```

For `runtime.collect_logs`, the result should include both structured entries and raw tail text:

```json
{
  "status": "ok",
  "capability": "runtime.collect_logs",
  "details": {
    "entries": [
      {
        "line": "Runtime ready",
        "line_number": 198
      }
    ],
    "tail_text": "Runtime ready\n...",
    "captured_at": "2026-06-19T09:31:10Z"
  }
}
```

`runtime.reload` may return `unsupported` in the first Python-process adapter if no safe reload command exists yet.

## Adapter Model

The control contract must not leak deployment mechanics upward.

The adapter layer is where deployment-specific execution lives.

Recommended adapter interface responsibilities:

- inspect runtime status
- request runtime restart
- request runtime reload
- collect runtime diagnostics

The first concrete adapter should be a `PythonProcessAdapter`.

Its local configuration should be explicit rather than magical:

- `process_match_substring`
- `start_command`
- optional `reload_command`
- optional `log_path`

V1 constraint:

- the adapter should not try to control arbitrary processes
- if no configured runtime process can be identified, `runtime.restart` should return a clear error rather than silently acting on an inferred target

Later adapters may replace this implementation with a `SystemdAdapter` or container-oriented controller without changing capability names or action semantics.

## Restart And Recovery Flow

`runtime.restart` must be treated as a disruptive handoff rather than a synchronous success guarantee.

Recommended flow:

1. The host edge receives an `action_request` for `runtime.restart`.
2. The host edge adapter validates that a configured runtime target exists.
3. The host edge returns a best-effort `action_result` with `status=accepted` and `handoff_expected=true`.
4. The host edge initiates the local restart.
5. The backend runtime disconnects and later returns.
6. The host edge continues observing runtime health locally while reconnecting through the normal edge session path.
7. Fresh `runtime.health` observations provide the authoritative recovery signal.

Important consequence:

- restart success is confirmed by later health observations, not by the restarting process itself

Useful recovery indicators include:

- a newly observed PID
- a new process start time
- `runtime.health_state=healthy`

## Local Daemon Behavior

The first host edge daemon should:

- establish a long-lived websocket session to the runtime gateway
- announce the three host-edge capabilities once connected
- publish initial observations immediately after connect
- continue publishing periodic `host.metrics` and `runtime.health` samples
- receive `action_request` frames and dispatch `runtime.control` actions locally
- reconnect after backend outages without pretending the outage is an edge failure

V1 can keep local persistence intentionally small.

A minimal acceptable behavior is:

- best-effort immediate `action_result`
- later health re-observation after reconnect

If action-result delivery proves too fragile during disruptive operations, a small local pending-operation journal can be added later without changing the contract.

## Non-Goals For V1

The first host edge slice should not attempt to solve:

- full supervisor abstraction across every host platform
- whole-host process or service inventory management
- automated remediation policy
- host-level network reconfiguration
- opaque backend-internal monitoring that bypasses the edge model

The point of v1 is to make the first real host edge concrete, inspectable, and testable while preserving room for a later `systemd` or container-backed execution adapter.
