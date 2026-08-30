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

Every accepted Observation is eligible for generic Runtime context admission.
An Observation may include `context_disposition` as `full`, `structural`,
`unavailable`, or `withheld` (default `full`). Runtime materializes a
device-scoped latest `ContextFact` without an Observation-name-specific
reducer. Sensitive, redacted, and `health_only` values become structural state
before reaching model context. An Edge may register `context.evidence.read`
and answer its ordinary correlated action with a bounded, redacted evidence
window; raw media is never returned through this contract.

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

## Proxy Interaction Edge

A Proxy Interaction Edge lets Runtime observe and operate an unmodified target
through external capture and input hardware. The proxy is a separately paired
Edge device; it does not inherit the target's identity and it does not connect
to Runtime through an adapter-specific shortcut.

The first public capability bundle is vendor-neutral:

- `proxy.interaction.observe` provides `proxy.target_attachment.v1` and
  `proxy.screen_frame.v1` observations.
- `proxy.keyboard.input` accepts bounded text or USB-HID key chords.
- `proxy.pointer.input` accepts normalized `x`/`y` coordinates in `[0, 1]` and
  bounded move or click operations.

Every registration and action payload names both `target_id` and `surface_id`.
The target identifies the unmodified device, while the surface identifies the
specific display/input relationship controlled by this proxy. The Edge rejects
device, target, or surface mismatches before an adapter is invoked. Runtime still
owns normal registration, permission, Presence, action routing, correlation, and
audit decisions.

`proxy.target_attachment.v1` reports one of `detached`, `attached`, `degraded`,
or `incompatible` and explicitly lists the state of `screen`, `audio`,
`keyboard`, `pointer`, `virtual_media`, and `power`. A target class unsupported
by the adapter is `incompatible`; missing video or USB is an unavailable or
degraded capability, not evidence that the target supports an empty screen or
ignored input.

`proxy.screen_frame.v1` represents human-visible pixels, not structured target
OS state. Its ordinary Observation contains resolution, media type, digest,
capture timing, and a body-free Edge-local `evidence_id` (the legacy
`evidence_ref` field may be mirrored during migration). Raw JPEG bodies remain
in a bounded Edge-local frame store and are not copied into ordinary Runtime
context. When a native Edge exists for the same surface, the attachment may name
`native_device_id` so Runtime can bind provenance while preferring the native
structured capabilities during normal operation.

### Proxy screen Profile and evidence loop

The proxy additionally advertises `proxy.screen.features`,
`proxy.screen.profile.configure`, and (when capture is available)
`proxy.screen.read`. Runtime confirms a target/surface-bound Screen Profile by
sending the configuration action with a profile ID/revision, allowlisted feature
names, RFC3339 expiry, a short `valid_for_seconds` lease for clockless board
enforcement, bounded evidence-byte limit, and visual action policy. The first
supported Features are `proxy.screen.capture_health.v1`,
`proxy.screen.change.v1`, and `proxy.screen.action_effect.v1`. They are compact
structural Observations: a change detector may say that pixels changed, but it
must report `unknown`/request evidence rather than claim arbitrary GUI meaning.

An active Profile can require a current `visual_authorization` for keyboard or
pointer input. The authorization refers to a short-lived Runtime
`understanding_id`; the Edge refuses blind or expired visual actions. The normal
screen action is one ordinary request/result pair:

```json
{
  "capability": "proxy.screen.read",
  "payload": {
    "target_id": "desktop-1",
    "surface_id": "main",
    "freshness": "latest",
    "max_bytes": 98304
  }
}
```

The `latest` result includes an Edge-generated `evidence_id`. A later `cached`
request must include that exact ID. The Edge validates its device/boot scope,
300-second TTL, slot presence, byte bound, and SHA-256 before returning the same
JPEG; an evicted, expired, reboot-invalid, foreign, or tampered ID returns
`evidence_unavailable` or an integrity error and never falls back to another
frame. Gateway feeds the bounded bytes only to the configured transient vision
evaluator, persists the ID/time/digest and textual Understanding rather than the
JPEG, and returns any normal follow-up through Hermes. The older
`proxy.screen.evidence.read`/`evidence_transfer` sequence remains a compatibility
experiment and is not used by normal screen reads.

## Hosted Coding Agent Bridge

The Terminal Edge may advertise a Codex-first coding capability bundle while
keeping the same device identity and Edge Session Link. The first delivery
starts `codex app-server --listen stdio://` as a child of `openhalo-edge`; it
does not attach to an externally managed Codex process.

The registration contains one observation provider and three Runtime-to-Edge
actions:

```json
[
  {
    "name": "coding.activity",
    "direction": "edge_to_runtime",
    "kind": "observation_provider",
    "observations": [{"name": "coding.activity.v1", "schema": {"type": "object"}}]
  },
  {"name": "coding.turn.start", "direction": "runtime_to_edge", "kind": "action"},
  {"name": "coding.suggestion.offer", "direction": "runtime_to_edge", "kind": "action"},
  {"name": "coding.turn.steer", "direction": "runtime_to_edge", "kind": "action"}
]
```

`coding.turn.start` creates one independent Codex thread and turn for the
OpenHalo interaction. Its payload includes the task, the registered
`workspace_ref`, and the OpenHalo `interaction_id`; the Edge returns the exact
Codex `agent_session_id` (thread id) and `agent_turn_id` (turn id). Multiple
interactions may run in parallel, but a turn is never addressed by a keyword or
most-recent-session fallback.

`coding.activity.v1` is a bounded normalized ordinary observation. It carries
the Codex agent name, OpenHalo interaction id, exact thread/turn ids, event
kind, phase, timestamp, confidence, causal parent, workspace reference,
bounded summary, and a body-free local `evidence_ref`. It covers reasoning
summaries, plan updates, agent messages, command/file/test activity, approvals,
corrections, and turn lifecycle. High-frequency deltas are coalesced on the
Edge. Runtime receives it through the same registered observation path as any
other Edge observation; the name does not grant special priority or bypass
generic relevance and governance. Runtime never receives raw reasoning, an
unbounded transcript, complete diffs, or complete command output. Historical
`coding.attention.v1` records remain readable during migration, but new events
are not dual-written.

The Edge keeps a durable paged journal per Coding task. Active task history is
not truncated by event count; the default limit of 32 applies only to
simultaneously active tasks. A configurable local capacity policy reclaims
only completed-task history.

`coding.suggestion.offer` is a local interactive action. The Edge does not
mutate Codex while rendering it and returns the exact correlated
`action_result` only after the user chooses `accept`, `ignore`, or
`suppress_task`. Only an accepted suggestion produces a short-lived local
confirmation reference. `coding.turn.steer` must include that reference plus
the exact thread id and `expectedTurnId`; stale, mismatched, duplicate, or
unconfirmed requests fail closed.

Codex command, file-change, and extra-permission approval decisions stay local
to the Terminal Edge. The user answers them in the existing TUI or line mode,
and the Bridge sends the corresponding App Server response. Separate normalized
activity observations may contain bounded command labels, file paths, statuses,
and test results for ordinary Runtime context; approval prompts still do not
forward their sensitive command, diff, or permission detail.

## Action Requests

## Continuous Interaction Process Contracts

An action capability may advertise a bounded `process_contract` when its result
starts a process that continues after the action result. The contract is
source-neutral and is validated by Runtime; it is not a provider- or Coding-
specific lifecycle shortcut.

```json
{
  "name": "agent.run",
  "direction": "runtime_to_edge",
  "kind": "action",
  "process_contract": {
    "continuation_policy": "until_settled",
    "watches": [
      {
        "watch_id": "completion",
        "observation_names": ["process.activity.v1"],
        "resolve_when": {"state": ["completed", "failed"]}
      }
    ]
  }
}
```

An Edge may send ordinary observations containing `process_id`, `coverage`,
and an `evidence_ref`. A missing candidate event is not evidence that the
underlying event did not happen; Runtime may request bounded evidence after an
uncertain hypothesis or a coverage violation. Raw video, audio, full command
output, and full transcripts are not uploaded by default.

Long-lived process observations should report health and progress facts such as
`healthy`, `stale`, `degraded`, `unreachable`, or `inactive`. Runtime checks
both Edge connection liveness and process progress. When a process becomes
inactive, Runtime records the health change against the same Interaction and
may resume its Hermes child session for retry, escalation, user reporting, or
terminal failure.

Inside Personal Runtime, `RuntimeOrchestrator` dispatches these ordinary
observations, action results, and maintenance timeouts to the `InteractionPool`.
The pool correlates the source-neutral lifecycle and transitions persistent
watches, obligations, process state, and health; no Edge-specific continuation
router or process lifecycle exists.

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
