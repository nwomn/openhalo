# Goal 2 Presence And Context Design Baseline

Date: 2026-06-18
Status: Working design baseline

## Purpose

This document captures the current design baseline for Goal 2, especially the part of the project that turns edge-side signals into runtime context and then into agent-driven intervention decisions.

It is intended to make six things explicit:

- how `Device` and `Capability` should be represented at the contract level
- what counts as a runtime `observation`
- how `observation` differs from `context snapshot`
- how broad agent responsibilities are split between the explicit `Presence Router` submodule and the rest of `Agent Runtime`
- how the shared observation vocabulary should grow
- how heuristic-learning style improvement should refine the system over time without entering the hot path directly

This is a design baseline, not a final implementation spec.

## Core Design Summary

The project should keep one explicit runtime semantic layer between edge-specific raw signals and agent-driven intervention decisions.

The runtime should support two proactive entry paths that converge on the same explicit presence module inside the broader agent system.

The working paths are:

- `sense-first path: edge raw signal -> normalized runtime observation -> compact context snapshot -> Agent Runtime proposal formation -> presence decision -> Agent Runtime execution planning -> action`
- `agent-initiative path: memory / goals / schedule / anomalies / unfinished work -> context refresh or observation check -> compact context snapshot -> Agent Runtime proposal formation -> presence decision -> Agent Runtime execution planning -> action`

Important boundary decisions:

- raw edge signals remain on the edge in v1
- runtime stores normalized observations plus provenance, not raw device-private evidence
- the broader agent system consumes compact context plus supporting evidence when needed
- `Presence Router` remains an explicit, inspectable governance submodule inside `Agent Runtime`
- both proactive entry paths must flow through that explicit presence module before user-facing intervention
- heuristic-learning style improvement should happen in one outer maintenance loop that refines vocabulary, mappers, reducers, and presence policy through review-gated updates

## Layer Responsibilities

### Device Edge

Responsibilities:

- collect raw local signals
- maintain device-local capability knowledge
- map raw local signals into normalized runtime observations
- retain raw local evidence on the edge for local debugging when needed
- retain device-local recent history when finer-grained evidence may later be needed by agent reasoning, debugging, or operator review

This layer owns hardware and platform differences.

The same model also applies to host-class edges that run on the runtime's own server. Those edges should expose telemetry and operational capabilities through the normal device/capability contracts instead of bypassing the edge model as backend-internal monitoring.

For the first host-edge slice, that means host-wide telemetry may enter the observation pipeline, while executable actions should stay limited to runtime-scoped lifecycle controls so the action boundary remains inspectable.

Those lifecycle controls should remain contract-stable even if the runtime deployment model changes. The first implementation may target the current plain Python process, but later deployments should be able to swap in a different execution adapter such as `systemd` without changing the capability contract seen by the rest of the runtime.

The same contract discipline should apply to diagnostics. For example, `runtime.collect_logs` should prefer a structured result shape that agents and UIs can inspect directly, while still allowing raw tail text to be included for debugging and operator readability.

The same pattern should apply to finer-grained edge history access. When the backend agent needs more detail than the compact snapshot and normalized runtime observations provide, it should not rely on the runtime continuously duplicating all raw edge evidence into core state. Instead, the edge should remain the default owner of raw local evidence and short-window detailed history, while the runtime requests an explicit structured history or diagnostics view only when needed.

The first host edge should also remain process-separate from the backend runtime it observes and controls. In that shape, a restart action can be initiated by the host edge, while recovery confirmation arrives later through fresh `runtime_health` observations instead of relying on the restarting process to confirm its own return.

### Gateway

Responsibilities:

- authenticate and accept edge traffic
- validate and route observation/event envelopes
- deliver those envelopes into runtime state

This layer is a transport and control-plane boundary, not a semantic interpreter.

### State / Context

Responsibilities:

- store runtime observations
- preserve observation provenance
- maintain a recent observation window
- synthesize compact context snapshot fields from that window
- expose supporting observation evidence for deeper reasoning and debugging

### Agent Runtime

Responsibilities:

- consume compact context snapshot plus supporting observation evidence when needed
- generate intervention proposals before presence gating
- hold an explicit `Presence Router` governance submodule for intervention decisions
- generate content, plans, and action requests after presence allows intervention
- proactively request context checks or observation refreshes when memory, goals, schedules, anomalies, or unfinished work suggest the runtime should reconsider whether to surface itself

This should remain one coherent backend module rather than being split into separate top-level proposal and execution boxes.

#### Presence Router

Responsibilities:

- consume the compact context snapshot together with agent-originated intervention proposals
- decide whether to intervene
- decide where and how strongly to intervene
- suppress or defer intervention when cooldown or ambiguity rules require it

This submodule should be treated as an explicit, inspectable governance layer inside `Agent Runtime` rather than as a separate top-level product identity.

## Contract Layers

### Device Schema V1

`Device` should stay intentionally small in v1.

It should represent:

- `device_id`
- `device_type`
- `role`
- `profile`
- `capabilities`

Example:

```json
{
  "device_id": "phone-1",
  "device_type": "phone",
  "role": "personal_mobile",
  "profile": "mobile_interactive",
  "capabilities": [
    "notification",
    "location",
    "motion"
  ]
}
```

Notes:

- current device state does not belong here
- default device tendencies should remain implicit in `role` and `profile` rather than adding another explicit abstraction layer in v1
- `capabilities` should list capability names, not action names or observation names

### Capability Schema V1

Each capability should declare:

- `name`
- `observations`
- `actions`

Example:

```json
{
  "name": "notification",
  "observations": [
    "interaction.notification_result"
  ],
  "actions": [
    "notification.show"
  ]
}
```

```json
{
  "name": "location",
  "observations": [
    "user.location"
  ],
  "actions": []
}
```

This keeps the contract shape simple:

- devices say which capabilities they have
- capabilities say which normalized observations and actions they support

### Runtime Observation Schema V1

Runtime observations are not raw edge signals.

They are normalized, runtime-owned semantic records with provenance.

Each observation should carry at least:

- `name`
- `value`
- `source_device_id`
- `source_capability`
- `source_event_id`
- `observed_at`
- `confidence`

Example:

```json
{
  "name": "user.activity_mode",
  "value": "desk_work",
  "source_device_id": "host-1",
  "source_capability": "desktop_context",
  "source_event_id": "evt-123",
  "observed_at": "2026-06-18T10:30:00Z",
  "confidence": 0.82
}
```

V1 storage rule:

- raw edge signals remain on the edge
- runtime stores normalized observations and provenance only

When deeper investigation is required:

- the agent may inspect compact snapshot plus supporting normalized observation evidence by default
- if that is still insufficient, the runtime should request a bounded edge-local history or diagnostics view explicitly rather than assuming core already stores the full raw evidence stream
- returned edge history should prefer structured summaries or bounded windows first, while raw payloads remain a more exceptional debugging surface

## Shared Observation Vocabulary

The system should have one formal shared observation vocabulary at the runtime level.

This vocabulary should:

- start small
- grow incrementally
- be defined centrally at the top level
- be extended during edge development when needed
- become normal runtime vocabulary immediately once accepted and tested

This means:

- edge-private raw terms such as OS-specific field names should not become the primary runtime language directly
- the first host edge may seed the initial vocabulary, but the terms themselves should be named as cross-device semantic concepts whenever possible

### Core Observation Vocabulary V1

The first compact vocabulary should stay focused on presence-relevant meaning:

- `user.location`
- `user.motion_state`
- `user.activity_mode`
- `user.attention_state`
- `environment.shared_space`
- `environment.noise_level`
- `device.screen_state`
- `device.audio_output_available`
- `device.user_nearby`
- `interaction.text_input`
- `interaction.voice_input`
- `interaction.notification_result`
- `runtime.task_urgency`

This list is intentionally small.

New terms should be added only when a new edge capability or presence requirement cannot be expressed cleanly with the current set.

## Observation Window And Context Snapshot

### Observation Window

`State / Context` should keep a recent runtime observation window rather than immediately flattening everything into one opaque state object.

This window is the current evidence pool from which runtime derives working context.

### Context Snapshot

The compact `context snapshot` is not a log and not a permanent truth database.

It is a working decision view synthesized from the recent observation window.

It exists primarily for hot-path agent proposal and presence decision work.

Example fields for `context snapshot v1`:

- `user.current_location`
- `user.current_input_mode`
- `user.motion_state`
- `environment.shared_space_risk`
- `available_output_devices`
- `best_private_output_device`
- `best_nearby_output_device`
- `desktop_attention_surface_available`
- `recent_notification_outcomes`
- `runtime.task_urgency`

Rules:

- snapshot fields may be `unknown`
- snapshot fields may be `ambiguous`
- snapshot should remain compact
- snapshot should not try to encode every piece of evidence directly

## Reducer Model

Observation-to-snapshot compression should not be implemented as one giant rule engine.

Instead, it should use small per-observation or per-field reducers.

Examples:

- a reducer for `user.location`
- a reducer for `device.audio_output_available`
- a reducer for `environment.shared_space`

V1 reducer principles:

1. filter expired observations using TTL or freshness windows
2. prefer newer evidence
3. use `confidence` as a secondary ordering signal
4. prefer direct evidence over distant derived evidence when appropriate
5. return `unknown` or `ambiguous` rather than forcing a fake certainty

This keeps hot-path logic small and testable while still allowing later refinement.

## Agent And Presence Split

The current design baseline is:

1. `State / Context` builds the compact snapshot
2. either edge/context activity or agent initiative may trigger agent evaluation
3. the broader agent forms an intervention proposal from compact context, memory, goals, schedules, and other relevant state
4. `Presence Router` evaluates that proposal as an explicit governance submodule inside `Agent Runtime`
5. if intervention or further work is appropriate, the agent continues into execution planning and action generation
6. the agent may inspect the compact snapshot plus supporting observation evidence when deeper reasoning is required

This means `Agent Runtime` is the primary intelligent actor, while `Presence Router` is a specialized internal governance submodule that controls whether and how that actor is allowed to surface itself.

The agent is not merely a passive responder in this model.

It is the first-class source of proactive initiative:

- it may notice goals, schedules, unresolved work, or anomalies
- it may request that the runtime reconsider whether to surface itself
- its initiative should be treated as a strong signal inside presence evaluation
- but it must still pass through presence cooldown, suppression, privacy, and timing policy rather than bypassing them

The project should not add an extra `presence feature view` between snapshot and presence in v1.

The hot path should remain:

`runtime observations -> compact context snapshot -> Agent Runtime proposal formation -> Presence Router -> Agent Runtime execution planning -> action`

## Presence Policy V1

Presence policy should be split by decision axis instead of being one giant combined table.

The current preferred axes are:

- `whether_to_intervene`
- `where_to_surface`
- `intensity`
- `cooldown_or_suppression`

Interpretation:

- `whether_to_intervene` decides if it is worth surfacing the runtime at all
- `where_to_surface` should select a surface intent or target style, not bind directly to a concrete `device_id` too early
- `intensity` decides how strongly the runtime should surface itself
- `cooldown_or_suppression` prevents repeated or badly timed intervention

This structure keeps policy review, testing, and later compression work tractable.

Agent-initiated requests should receive meaningful weight inside this policy system.

That means:

- an agent-initiative request should normally outrank a weak passive signal
- an agent-initiative request may justify a context refresh before final presence evaluation
- an agent-initiative request still does not bypass suppression or privacy constraints

## Heuristic Learning Outer Loop

The project should use one unified heuristic-learning style outer loop rather than independent learning loops per layer and rather than a single end-to-end opaque learner.

The inspiration for this direction is:

- [Learning Beyond Gradients](https://trinkle23897.github.io/learning-beyond-gradients/#zh)

The outer loop may update:

- shared observation vocabulary
- edge mappers
- observation reducers
- snapshot fields
- presence policy

But it should do so through:

- feedback capture
- replays
- tests
- review-gated updates

This loop should not directly replace the runtime hot path.

Instead:

- the hot path stays explicit and inspectable
- the outer loop improves the artifacts that define the hot path

## Non-Goals For V1

This design does not yet commit to:

- a complete final observation vocabulary for all future edge types
- raw edge signal persistence inside runtime
- a model-generated hot-path snapshot builder
- a presence-only extra feature abstraction layer
- fully automated policy mutation without review
- a final cross-device surface intent taxonomy

## Open Questions

The following areas still need follow-up work:

- exact `context snapshot v1` field definitions and types
- per-field reducer details and test cases
- first concrete `where_to_surface` output vocabulary
- the first review package format for the heuristic-learning maintenance loop
- how much observation evidence should be shown to agent execution by default
- which first non-CLI edge should drive the next vocabulary expansion
