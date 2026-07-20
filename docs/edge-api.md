# OpenHalo Edge API

Status: accepted M17.1 registration-driven extension baseline

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

## Session Lifecycle

Every edge session has an ordered handshake. New edge implementations must use
this order:

```text
connect + auth token
-> connect_ok
-> capability_announce
-> observation_push / event_push / action_result
```

`connect` is the device-registration step. `capability_announce` extends an
already registered device; it does not create a device by itself. Edges must not
send capabilities, observations, user events, or action results until they have
received `connect_ok` for the same `device_id`.

Gateway binds a successful `connect` to one WebSocket and one `device_id`.
Every post-connect frame on that socket must carry that exact `device_id`.
An unauthenticated post-connect frame receives `not_connected`; a frame for a
different device receives `device_mismatch`; and a second live socket claiming
the same device receives `device_already_connected`. Repeating `connect` on an
already authenticated socket receives `already_connected`. An edge must close or
wait for its earlier socket to close before reconnecting that device identity.

If `connect` returns `error`, the edge should stop the session, surface the
failure in local diagnostics, and retry only after configuration changes such as
fixing the token or runtime URL.

## Device Pairing

New public edges use Runtime device pairing instead of sharing
`OPENHALO_EDGE_TOKEN`. An administrator creates a short-lived one-time code on
the Runtime host. The first connection presents that code with `auth.kind` set
to `pairing`:

```json
{
  "api_version": "edge.runtime.v1",
  "type": "connect",
  "device": {
    "device_id": "android-edge-7f31c2a8",
    "device_type": "android-phone"
  },
  "auth": {
    "kind": "pairing",
    "token": "one-time-pairing-code"
  }
}
```

On success, the Runtime returns one device-specific credential. The Edge must
persist both its Runtime URL and this credential locally, and must never log or
display the credential after this response:

```json
{
  "api_version": "edge.runtime.v1",
  "type": "connect_ok",
  "auth": {
    "kind": "device",
    "token": "device-specific-credential"
  }
}
```

Later connections use the same `device_id` and `auth.kind = "device"`. A
successful device reconnect returns the normal `connect_ok` without an `auth`
field. Used or expired pairing codes return a structured error such as
`pairing_code_consumed` or `pairing_code_expired`; a revoked device credential
returns `unauthorized`.

Pairing and device credentials must cross a public network only through
`wss://`. The Runtime process may still use loopback `ws://` behind a TLS
terminating reverse proxy. Untagged shared-token auth remains a temporary local
development and managed-edge compatibility path; it is not the contract for new
public edges.

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

Authentication failure response:

```json
{
  "api_version": "edge.runtime.v1",
  "type": "error",
  "message": "unauthorized"
}
```

For temporary local development and managed-edge compatibility, the shared
Runtime token remains private in the owner's `~/.openhalo/config.json` and is
passed only to the locally managed Runtime process. New edges must use the
device-pairing contract above rather than assuming that token works.

## Capability Announcement

Edges announce capabilities after connecting. Capabilities may be simple strings
for migration compatibility or public capability objects for new integrations.
The `device_id` must match a prior successful `connect` on the same WebSocket
session.

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

Rich action capabilities should include enough metadata for runtime planning to
choose a compatible provider without device-type-specific branches:

```json
{
  "name": "notification.show",
  "direction": "runtime_to_edge",
  "kind": "action",
  "affordances": ["notify_user", "deliver_private_text"],
  "modality": "visual_text",
  "content_capacity": "short_text",
  "privacy": "personal",
  "interruptiveness": "medium",
  "side_effect": "user_visible",
  "input_schema": {
    "type": "object",
    "required": ["body"],
    "additionalProperties": false,
    "properties": {
      "title": {"type": "string"},
      "body": {"type": "string", "minLength": 1}
    }
  }
}
```

Observation-provider capabilities register the observation names and schemas
they may later push:

```json
{
  "name": "mobile.context",
  "direction": "edge_to_runtime",
  "kind": "observation_provider",
  "observations": [
    {
      "name": "mobile.screen_state",
      "schema": {
        "type": "string",
        "enum": ["locked", "unlocked", "unknown"]
      },
      "semantics": ["device_activity"],
      "privacy": "personal_device_state",
      "freshness_seconds": 120,
      "confidence": {"type": "edge_reported"}
    }
  ]
}
```

The runtime stores registration metadata in device, capability, and observation
registries. Capability names are still mirrored onto the legacy device
capability set while built-in terminal and host edges migrate. Gateway returns
structured `unknown_device`, `not_connected`, `device_mismatch`, or
`device_already_connected` errors at the public boundary rather than admitting a
post-connect frame by device ID alone.

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

During migration, `payload.observations` is retained as a compatibility mirror
for existing host and terminal code paths. New integrations should read and
write the top-level `observations` field.

New edges must register each observation under the source capability before
using `observation_push` or `event_push` with `payload.observations`.
Unregistered observations and schema-mismatched observation values are rejected
with public `error` frames and are not stored as runtime observations.

## Action Requests

Runtime-to-edge actions use `action_request`.

```json
{
  "api_version": "edge.runtime.v1",
  "type": "action_request",
  "request_id": "action-1",
  "interaction_id": "interaction-1",
  "interaction_turn_id": "interaction-turn-1",
  "device_id": "terminal-1",
  "action": {
    "capability": "notification.show",
    "payload": {
      "title": "OpenHalo",
      "body": "Runtime status: running."
    }
  }
}
```

`request_id` identifies one action request. `interaction_id` identifies the
larger interaction lifecycle, including post-action re-entry.
`interaction_turn_id` identifies the runtime deliberation turn that issued the
request; it is distinct from edge-side `turn_id` diagnostics.

## Action Results

Edges return action completion with `action_result`.

```json
{
  "api_version": "edge.runtime.v1",
  "type": "action_result",
  "request_id": "action-1",
  "interaction_id": "interaction-1",
  "interaction_turn_id": "interaction-turn-1",
  "device_id": "terminal-1",
  "result": {
    "status": "ok",
    "capability": "notification.show",
    "observed_at": "2026-06-29T10:00:02Z",
    "details": {
      "title": "OpenHalo",
      "body": "Runtime status: running."
    }
  }
}
```

When an `interaction_id` is present, the runtime records lineage and may re-enter
post-action proposal formation before deciding whether to issue another action
or complete the interaction. Edges must echo the additive
`(interaction_id, interaction_turn_id, request_id)` correlation fields from a
runtime-issued action request; the runtime uses that exact pending triple rather
than a most-recent-interaction lookup. Frames missing either correlation field
are rejected for lineage-bearing results. The reporting `device_id` must also
match the target device selected for that action request; a matching triple from
another connected edge is rejected. Action results must report a capability that
exactly matches the originating `action_request.action.capability`; a device
registered for a different compatible capability cannot resolve that request.

## Interaction Progress

`interaction_progress` is a Runtime-to-Edge display update, not an action and
not a new intervention. Runtime sends it only to an online, visibility-authorized
participant that announced the `interaction.progress` capability. A missing,
disconnected, or unsupported participant may miss the presentation without
blocking action dispatch, action-result handling, or interaction completion.

```json
{
  "api_version": "edge.runtime.v1",
  "type": "interaction_progress",
  "device_id": "android-edge-1",
  "progress": {
    "version": 1,
    "interaction_id": "interaction-1",
    "interaction_turn_id": "interaction-turn-1",
    "sequence": 3,
    "phase": "executing",
    "state": "active",
    "occurred_at": "2026-07-19T14:00:00Z",
    "presentation_hint": "working"
  }
}
```

For version `1`, `progress` contains exactly the fields shown above. The
allowed phases are `deliberating`, `researching`, `planning`, `executing`,
`awaiting_action_result`, `completing`, `completed`, `failed`, and `cancelled`.
`state` is `active` or `settled`; `presentation_hint` is one of `working`,
`waiting`, `completed`, `failed`, or `cancelled`. `interaction_turn_id` may be
`null` only when the lifecycle transition has no turn-specific lineage.

Progress must not contain model/provider identity or configuration, reasoning,
tool arguments or results, remote content, memory text, or Hermes/Nous display
content. Edges must render only their own localized mapping of the safe phase,
never a provider or agent console stream. They accept a frame only when its
`device_id` matches their own identity, version is supported, and `sequence`
strictly advances for that `interaction_id`; invalid, unauthorized, or stale
frames are ignored. Edges clear active progress on a settled or terminal phase,
the corresponding terminal `interaction_update`, or session loss. No
`event_ack` or `action_result` is returned for a progress frame.

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

Current expected error meanings:

- `unauthorized`: the `connect` token does not match the runtime token.
- unknown or missing device registration: the edge sent a post-connect frame
  before a successful `connect_ok`; current builds may expose this as a server
  diagnostic instead of a stable public error.
