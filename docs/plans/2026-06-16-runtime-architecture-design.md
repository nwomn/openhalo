# Personal Runtime Architecture Baseline

Date: 2026-06-16
Status: Working design baseline

## Purpose

This document captures the current high-level architecture for the personal runtime project.

It is intended to make three boundaries explicit:

- What belongs to `Frontend / Device Edge`
- What belongs to `Backend / Personal Runtime`
- What `Gateway` should and should not own

This is a design baseline, not a final implementation spec.

## Canonical Architecture Diagram

This diagram is the current reference diagram for the agreed frontend/backend split, internal component layout, and cross-boundary communication rule.

If later discussions produce alternative sketches, this diagram should remain the baseline until it is intentionally replaced by a newer accepted version.

```mermaid
flowchart LR
    subgraph FE["Frontend / Device Edge"]
        FE1["Interaction Surface<br/>voice / chat / UI / background trigger"]
        FE2["Sensor and Device Adapter<br/>mic / camera / gps / gpio / files / notifications"]
        FE3["Local Capability Runtime<br/>capability registry<br/>event normalization<br/>lightweight local rules"]
        FE4["Local Action Executor<br/>local permissions<br/>low-latency actions<br/>device control"]
        FE5["Edge Session Link<br/>auth<br/>pairing<br/>duplex transport<br/>sync / ack / retry"]

        FE1 <--> FE3
        FE2 <--> FE3
        FE3 <--> FE4
        FE3 <--> FE5
        FE4 <--> FE5
    end

    subgraph BE["Backend / Personal Runtime"]
        BE1["Gateway<br/>device access<br/>auth<br/>pairing<br/>transport termination<br/>protocol adaptation<br/>ingress / egress routing"]
        BE2["State / Context / Task<br/>device state<br/>event log<br/>task state<br/>context memory<br/>handoff state"]
        BE3["Presence Router<br/>whether to intervene<br/>where to surface<br/>intensity / timing"]
        BE4["Agent Executor<br/>planning<br/>reasoning<br/>tool selection<br/>response generation"]
        BE5["Action Layer<br/>device actions<br/>remote commands<br/>external API calls<br/>notifications"]
        BE6["Model / Tool / Skill Runtime"]

        BE1 <--> BE2
        BE2 <--> BE3
        BE3 <--> BE4
        BE4 <--> BE5
        BE4 <--> BE6
        BE5 <--> BE2
        BE5 <--> BE1
    end

    FE5 <--> BE1

    FE3 -. "logical: events / capability state / local context updates" .-> BE2
    BE2 -. "logical: state sync / task sync / handoff sync" .-> FE3
    BE5 -. "logical: action commands / prompts / notifications" .-> FE4
    FE4 -. "logical: action result / local execution status" .-> BE5
```

## Core Interpretation

The frontend is not a thin UI client. It is a device-resident edge runtime.

The backend is not a traditional request-response application server. It is the long-lived personal runtime that maintains continuity across devices, tasks, and contexts.

The gateway is part of the backend, but it is not the system brain. It is the controlled boundary through which edge nodes connect to the runtime.

## Frontend / Device Edge

### Interaction Surface

This is where the user or environment actually touches the system.

Examples:

- voice interaction
- chat or text input
- visible UI
- notifications
- wake-word or background triggers

### Sensor and Device Adapter

This layer talks to hardware or platform APIs directly.

Examples:

- microphone
- camera
- GPS
- local file system access
- GPIO or relay control
- OS notifications

### Local Capability Runtime

This is the key frontend unification layer.

Responsibilities:

- expose device capabilities in a normalized form
- convert raw local signals into normalized events
- maintain the local capability registry
- apply lightweight local rules when needed
- shield the rest of the system from device-specific API differences

This is where the `Device` plus `Capability` abstraction starts to become concrete.

### Local Action Executor

This layer performs actions that should happen on the device itself.

Examples:

- display a local notification
- start local recording
- toggle a relay
- perform a low-latency UI or device action

### Edge Session Link

This is the frontend's only network-facing cross-boundary channel to the backend.

Responsibilities:

- pairing
- authentication
- long-lived duplex transport
- delivery acknowledgements
- retry and reconnect behavior
- synchronization envelopes

## Backend / Personal Runtime

### Gateway

This is the backend boundary layer.

Responsibilities:

- terminate edge connections
- authenticate and pair devices
- adapt protocol differences
- validate and route ingress and egress messages
- expose a stable control-plane boundary for all edge participants

The gateway should stay transport-oriented and control-plane-oriented.

### State / Context / Task

This is the runtime truth center.

Responsibilities:

- maintain device state
- store normalized event history
- maintain task state
- maintain context memory
- maintain handoff and continuity state across devices

### Presence Router

This layer decides how the runtime should show up.

Responsibilities:

- decide whether the system should intervene
- choose the target device or surface
- choose timing and intensity of intervention

This is one of the biggest differences from a channel-first agent architecture.

### Agent Executor

This is the main reasoning and execution layer.

Responsibilities:

- plan work
- select tools
- interpret context
- generate responses
- coordinate action requests

### Action Layer

This layer turns decisions into effects.

Responsibilities:

- invoke edge actions
- invoke remote commands
- call external APIs
- issue notifications
- write execution results back into runtime state

### Model / Tool / Skill Runtime

This is the execution substrate used by the agent executor.

Examples:

- model providers
- tool hosts
- skill runtimes
- safety or policy wrappers

## Cross-Boundary Rule

This is an explicit architecture rule:

- All physical cross-boundary communication must pass through `Edge Session Link <-> Gateway`

This means frontend modules do not directly network-connect to backend internal modules, and backend internal modules do not directly network-connect to frontend internal modules.

The dashed arrows in the diagram represent logical producer-consumer relationships, not direct transport links.

Examples:

- `Local Capability Runtime -> State / Context / Task` means capability events are logically consumed by state management, but they still travel physically through `Edge Session Link -> Gateway`
- `Action Layer -> Local Action Executor` means action requests are logically consumed by local executors, but they still travel physically through `Gateway -> Edge Session Link`

This rule is intended to prevent protocol sprawl and keep the architecture understandable.

## Gateway Scope

### Gateway should own

- device pairing
- authentication and trust checks
- transport lifecycle management
- protocol adaptation
- ingress and egress routing
- acknowledgement, retry, and delivery envelope mechanics
- basic validation and message normalization
- connection-level observability

### Gateway should not own

- long-term task truth
- context reasoning
- presence decisions
- agent planning
- semantic interpretation of user state
- business-level action orchestration

In short:

- `Gateway` is a boundary and control-plane layer
- `Personal Runtime` is the stateful decision and execution core

## Allowed Gateway Preprocessing

Gateway preprocessing should remain protocol-level, not semantic.

Reasonable examples:

- schema validation
- message envelope normalization
- attachment metadata handling
- auth-derived device identity enrichment
- deduplication using delivery IDs
- retry classification

Gateway preprocessing should not cross into runtime reasoning.

Not acceptable as gateway responsibilities:

- deciding whether an event is important to the user
- deciding which device should surface a response
- deciding whether a task should be created
- running agent planning logic

## Edge Representation Rules

Current agreed direction:

- Represent every edge participant as a `Device`
- Expose runtime-facing functions as `Capabilities`
- Classify profiles primarily by role
- Describe hardware family as secondary metadata
- Keep role vocabulary intentionally small
- Reuse existing roles for new device classes whenever possible
- Defer heavy resource-tier scheduling design until it becomes a real bottleneck

## OpenClaw Reuse Stance

Current agreed direction:

- Reuse OpenClaw gateway parts only if they can be isolated as product-neutral control-plane infrastructure
- If isolation fails cleanly, build a minimal replacement gateway

This avoids pulling channel/session-centered assumptions into the new runtime architecture.

## Immediate Implications For v0

The first implementation milestone should probably prove these points in the smallest possible way:

- one edge client can pair with the backend
- the edge client can register device identity and capabilities
- normalized events can reach runtime state
- the backend can issue one action command back to the edge
- the full round-trip uses only `Edge Session Link <-> Gateway` as the physical cross-boundary path

## Still Open

This document does not yet finalize:

- the first-class object for implementation sequencing
- the minimum state model fields
- the minimal role vocabulary
- the first v0 device surfaces
- whether OpenClaw code can actually be cleanly isolated
