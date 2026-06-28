# OpenHalo Edge API

Status: M17.0 implementation baseline

The Edge API is the public integration boundary between device edges and the
OpenHalo Personal Runtime. Edge authors should depend on this contract, not on
`personal_runtime` internals.

## Boundary

All physical device/runtime traffic flows through:

```text
Device Edge -> Edge API v1 -> Gateway -> Personal Runtime
```

`Gateway` owns protocol validation, authentication, device registration,
ingress normalization, and egress routing. `State / Context`, `Agent Runtime`,
`Presence Router`, and `Action Layer` remain backend implementation details.

The Python package `edge_api` contains dependency-free frame helpers for this
contract. `device_edge.shared.session_client.SessionClient` is the official
Python convenience client over the same public frame contract.

## Version

Current version:

```text
edge.runtime.v1
```

Versioned frames carry:

```json
{
  "api_version": "edge.runtime.v1",
  "type": "..."
}
```

The runtime still accepts legacy unversioned frames during the M17.0 migration
so older tests and local tools can continue to run. New edge integrations should
send `api_version`.

## Connect

Edges start a session with `connect`.

```json
{
  "api_version": "edge.runtime.v1",
  "type": "connect",
  "device": {
    "device_id": "terminal-1",
    "device_type": "desktop-cli",
    "role": "interactive_surface"
  },
  "auth": {
    "token": "dev-token"
  }
}
```

Successful response:

```json
{
  "api_version": "edge.runtime.v1",
  "type": "connect_ok"
}
```

## Capability Announcement

Edges announce capabilities after connecting. Capabilities may be simple strings
or public capability objects.

```json
{
  "api_version": "edge.runtime.v1",
  "type": "capability_announce",
  "device_id": "terminal-1",
  "capabilities": [
    {
      "name": "text.input",
      "direction": "edge_to_runtime"
    },
    {
      "name": "notification.show",
      "direction": "runtime_to_edge"
    }
  ]
}
```

The runtime currently persists capability names. Rich capability fields are part
of the public envelope and can be expanded without exposing backend internals.

## User Events

User intent and explicit edge requests use `event_push`.

```json
{
  "api_version": "edge.runtime.v1",
  "type": "event_push",
  "device_id": "terminal-1",
  "capability": "text.input",
  "payload": {
    "text": "check runtime status",
    "observed_at": "2026-06-29T10:00:00Z"
  }
}
```

The runtime acknowledges accepted events with:

```json
{
  "api_version": "edge.runtime.v1",
  "type": "event_ack"
}
```

## Observations

Context and environment evidence use `observation_push`.

```json
{
  "api_version": "edge.runtime.v1",
  "type": "observation_push",
  "device_id": "host-1",
  "capability": "runtime.health",
  "observations": [
    {
      "name": "runtime.health_state",
      "value": "healthy",
      "observed_at": "2026-06-29T10:00:00Z",
      "confidence": 1.0
    }
  ],
  "payload": {
    "observations": [
      {
        "name": "runtime.health_state",
        "value": "healthy",
        "observed_at": "2026-06-29T10:00:00Z",
        "confidence": 1.0
      }
    ]
  }
}
```

During the M17.0 migration, `payload.observations` is retained as a compatibility
mirror for existing host and terminal code paths. New integrations should read
and write the top-level `observations` field.

## Action Requests

Runtime-to-edge actions use `action_request`.

```json
{
  "api_version": "edge.runtime.v1",
  "type": "action_request",
  "request_id": "action-1",
  "interaction_id": "interaction-1",
  "device_id": "terminal-1",
  "action": {
    "capability": "notification.show",
    "payload": {
      "message": "Runtime status: running."
    }
  }
}
```

`request_id` identifies one action request. `interaction_id` identifies the
larger interaction lifecycle, including post-action re-entry.

## Action Results

Edges return action completion with `action_result`.

```json
{
  "api_version": "edge.runtime.v1",
  "type": "action_result",
  "request_id": "action-1",
  "interaction_id": "interaction-1",
  "device_id": "terminal-1",
  "result": {
    "status": "ok",
    "capability": "notification.show",
    "observed_at": "2026-06-29T10:00:02Z",
    "details": {
      "message": "Runtime status: running."
    }
  }
}
```

When an `interaction_id` is present, the runtime records lineage and may re-enter
post-action proposal formation before deciding whether to issue another action
or complete the interaction.

## Interaction Updates

Runtime-visible interaction state is delivered with `interaction_update`.

```json
{
  "api_version": "edge.runtime.v1",
  "type": "interaction_update",
  "device_id": "terminal-1",
  "interaction": {
    "interaction_id": "interaction-1",
    "status": "completed",
    "visibility": "visible",
    "summary": "Runtime status: running."
  }
}
```

Edges may use this to update local UI state, clear pending indicators, or record
session history.

## Errors

Errors use the public `error` frame type.

```json
{
  "api_version": "edge.runtime.v1",
  "type": "error",
  "message": "unauthorized"
}
```

Future hardening should add stable error codes, retryability, and request
correlation for all error frames.
