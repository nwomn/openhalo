# Personal Runtime Agent Project

## Project Summary

This project aims to build a new personal agent system oriented around `device -> context -> presence -> action`, rather than the traditional `channel -> session -> agent` product shape.

The intended product is not "another chat agent entry point". It is a personal runtime that can exist across multiple devices, maintain continuity across contexts, and decide how to surface itself through the most appropriate device or interaction surface.

At the current stage, the project has moved from pure architecture-definition into an implemented and testable v0 single-edge loop. The architecture baseline and early milestone framing are in place, and the first end-to-end desktop/CLI closed loop can now be executed and verified locally.

## Background

The project started from dissatisfaction with OpenClaw's default architecture and product feel.

Current concern:

- OpenClaw feels like an agent system that the user must actively go to.
- Its default center of gravity is still closer to channels, sessions, and entry points.
- That shape does not naturally support a low-presence, multi-device, continuous personal assistant experience.

What we want instead:

- A multi-device personal assistant runtime
- Fast response paths, especially on local devices
- Low-presence behavior, meaning the assistant should be available without always being foregrounded
- Strong continuity across devices and contexts
- A system where `channel` is downgraded to a connector, rather than being the primary abstraction

## Current Working Architecture Direction

The project is currently aligned around a two-part system:

### 1. Frontend / Device Edge

Runs on user devices such as desktops, phones, earbuds, home nodes, and background monitors.

Responsibilities:

- Local sensing
- Local interaction
- Local permission handling
- Local low-latency actions

### 2. Backend / Personal Runtime

Acts as the assistant runtime core rather than a traditional SaaS backend.

Responsibilities:

- Gateway / control-plane responsibilities
- Unified task and context state
- Presence routing
- Agent execution
- External action orchestration

The current architecture baseline is documented in:

- `docs/plans/2026-06-16-runtime-architecture-design.md`

Current boundary rules:

- `Frontend / Device Edge` is a device-resident edge runtime rather than a thin UI client
- `Backend / Personal Runtime` is a long-lived cross-device runtime rather than a traditional request-response backend
- All physical cross-boundary traffic must flow through `Edge Session Link <-> Gateway`
- Cross-boundary relationships between frontend and backend internal modules are logical only unless they pass through that transport choke point
- `Gateway` is a boundary and control-plane layer, not the primary reasoning layer

## Edge Representation Model

For edge integration, the working direction is a layered model rather than a flat "all hardware is the same kind of node" model.

- `Device` is the system-level identity and constraint layer
- `Capability` is the runtime-facing contract layer

In this model:

- Every edge participant is represented as a device with identity, connectivity, trust, placement, power, and resource constraints
- Each device may expose one or more capabilities such as sensing or actuation functions
- Runtime task selection and routing should prefer capability-level reasoning
- Safety, availability, permissions, and performance constraints remain anchored at the device layer

This direction is meant to support a wide range of edge classes, from full computing surfaces such as phones, desktops, and Raspberry Pi nodes to constrained controllers such as ESP32-class devices, without forcing the whole system to collapse to the lowest common denominator

The current preference is to support graded edge roles through device profiles rather than forcing one uniform execution shape for every device class. The design constraint is that profile modeling must stay small and legible rather than becoming a large matrix of ad hoc per-device exceptions

The current preference for profile modeling is:

- Primary classification by system role
- Secondary description by device type
- Resource scheduling detail can remain intentionally lightweight until it becomes a real product bottleneck

This means profile shape should likely answer "what role does this node play in the runtime" before answering "what hardware family is it"

For role modeling, the current preference is to keep the role set intentionally small. When onboarding new device classes, the default should be to reuse an existing role whenever possible and only introduce a new role when reuse clearly breaks down

## Core Goals

### Goal 1: Define the system architecture clearly

We need a stable high-level architecture before deep implementation begins.

Sub-goals:

- 1.1. Define the overall system boundary
- 1.2. Define the backend module boundaries
- 1.3. Define the frontend/backend contract
- 1.4. Decide whether OpenClaw gateway can be reused as an isolated control-plane component

Acceptance criteria:

- A written architecture description exists
- The role of `Device Edge` and `Personal Runtime` is explicitly separated
- The meaning of `Gateway`, `State`, `Presence Router`, `Agent Executor`, and `Action Layer` is documented
- A clear reuse-vs-rebuild decision frame exists for OpenClaw gateway

Status:

- In progress

Implementation note:

- The implementation path is no longer only conceptual; the first v0 batch has been started and the scaffold/protocol/state foundations are now in place

### Goal 2: Define the project's primary abstractions

We need to prevent the project from falling back into `channel/session/agent` as the top-level worldview.

Sub-goals:

- 2.1. Confirm first-class abstractions for the new system
- 2.2. Downgrade legacy abstractions to implementation details where appropriate
- 2.3. Define the minimum state model needed for continuity

Acceptance criteria:

- First-class abstractions are documented
- `channel`, `session`, and `agent` are explicitly classified as either primary or secondary concepts
- The minimum state model includes tasks, context, device state, and handoff state

Status:

- In progress

Implementation note:

- Milestone M1 is now partially implemented with a working single-edge closed loop, though the runtime is still intentionally minimal and remains in-memory only

### Goal 3: Define the initial implementation path

We need an implementation starting point that is focused enough to produce progress quickly.

Sub-goals:

- 3.1. Select the first project folder and documentation baseline
- 3.2. Define the first implementation milestone
- 3.3. Identify the minimum backend modules for v0
- 3.4. Identify the minimum device surfaces for v0

Acceptance criteria:

- The project has a dedicated folder
- Project baseline documentation exists
- The first milestone is small enough to implement without solving the whole system
- The v0 scope names which modules and device surfaces are first-class

Status:

- In progress

### Goal 4: Build the project incrementally from architecture to runtime

We need a milestone ladder from concept to working system.

Sub-goals:

- 4.1. Define milestone M0: architecture and state model validation
- 4.2. Define milestone M1: minimal runtime core
- 4.3. Define milestone M2: first multi-device continuity path
- 4.4. Define milestone M3: first presence-aware routing path

Acceptance criteria:

- Each milestone has a clear scope
- Each milestone can be accepted independently
- Later milestones depend on earlier ones in a clean way

Status:

- In progress

## Completed Sub-goals

### Completed: Project-level AGENTS enforcement baseline

Result:

- Project-level Codex hooks have been added in `.codex/hooks.json`
- Shared enforcement logic has been added in `agent_guard/codex_hooks.py`
- `AGENTS.md` now documents the internal per-turn audit and the conditional `Project.md Check` exception path
- A minimal automated test suite validates audit parsing and enforcement rules

Acceptance criteria:

- The repository has project-level Codex hooks for session start and turn-end enforcement
- The enforced workflow validates that `Project.md` was read at session start
- The enforced workflow validates that every meaningful interaction performs a `Project.md` progress check
- The enforced workflow blocks inconsistent `Project.md` update claims while keeping normal responses free of mandatory visible audit output

Status:

- Completed

### Completed: 3.1. Select the first project folder and documentation baseline

Result:

- A dedicated project folder has been created
- `Project.md` has been created as the project baseline document
- `AGENTS.md` has been created to guide future collaboration

Acceptance criteria:

- A dedicated root folder exists for the new project
- The project has a central document describing background, goals, and progress
- The collaboration contract for future Codex sessions is documented

Status:

- Completed

### Completed: Architecture orientation agreement

Result:

- The current direction is to split the system into `Device Edge` and `Personal Runtime`
- The backend is understood as a runtime core, not a generic web backend
- The system likely requires a `Gateway` or control-plane layer

Acceptance criteria:

- There is an explicit statement that the project is organized into frontend and backend halves
- There is an explicit statement that a central runtime/gateway layer is required

Status:

- Completed

### Completed: Initial v0 runtime slice definition

Result:

- The first usable product slice is now defined as a single-edge closed loop
- The first-class v0 device surface is a desktop/CLI edge client
- The minimum v0 backend module set is `Gateway`, in-memory `State / Context / Task`, a same-device `Presence Router` rule, a minimal `Agent Executor`, and an `Action Layer`
- The minimum v0 capability loop is `text.input -> event -> response -> notification.show`
- A concrete implementation plan has been written in `docs/plans/2026-06-16-v0-single-edge-loop-plan.md`

Acceptance criteria:

- The first milestone is small enough to implement without solving the whole system
- The v0 scope names which backend modules are first-class
- The v0 scope names which device surface is first-class
- The v0 path forms a complete user-visible roundtrip

Status:

- Completed

### Completed: First v0 implementation foundation batch

Result:

- The repository has been initialized as a git project with a safe `.worktrees/` workflow
- The Python project scaffold has been added with `pyproject.toml`
- The `personal_runtime` and `device_edge` package roots have been created
- Shared protocol helpers now validate supported v0 frame types and build `connect` frames
- In-memory runtime state and the same-device presence routing stub have been implemented
- Automated tests now cover scaffold imports, protocol helpers, and runtime state basics

Acceptance criteria:

- The repository can support branch and worktree based iteration safely
- The v0 scaffold can be imported as Python packages
- The shared protocol has a tested minimal contract for `connect` and frame validation
- The runtime has a tested minimal in-memory device/capability registry and same-device response rule

Status:

- Completed

### Completed: First v0 single-edge closed loop implementation

Result:

- A minimal `RuntimeGateway` now handles `connect`, `capability_announce`, and `event_push` frames
- A minimal `Agent Executor` now generates text replies and the `Action Layer` converts them into `notification.show` requests
- A minimal `SessionClient` now builds connect, capability, and text-event frames and returns `action_result` payloads after local execution
- A minimal CLI edge runner can execute the whole loop locally from typed text input to printed notification output
- End-to-end tests now verify the single-edge roundtrip through gateway, edge session client, and local action execution
- Manual command-line verification now demonstrates the closed loop with `python3 -m device_edge.cli_edge`

Acceptance criteria:

- The backend can accept the minimal v0 frame sequence and emit an action request
- The edge can execute the returned `notification.show` action and produce an `action_result`
- The single-edge roundtrip is covered by automated tests
- The loop can be exercised manually from the command line in the worktree

Status:

- Completed

## Open Questions

- Can OpenClaw gateway be isolated as a reusable control-plane component?
- If it cannot, what minimum replacement gateway must be implemented first?
- What should be the first-class object for implementation sequencing: task, device, or presence?
- Which device surfaces should be v0 first-class surfaces?

Current preference:

- Try to reuse only the OpenClaw gateway parts that can be isolated as product-neutral control-plane infrastructure
- If that isolation does not stay clean, prefer building a minimal replacement gateway rather than carrying forward channel/session-centered assumptions
- A preliminary source audit suggests `packages/gateway-protocol` and `packages/gateway-client` are the strongest reuse candidates, while `src/gateway/server-methods` is too tightly coupled to OpenClaw runtime semantics to treat as a clean control-plane layer

Current v0 milestone direction:

- Start with one desktop/CLI `Device Edge`
- Use one long-lived `Edge Session Link <-> Gateway` path
- Keep auth, presence, and state intentionally minimal
- Prove one full loop from `text.input` to `notification.show`

Immediate post-v0 direction:

- Add minimal persistence for device registration and recent event history
- Add a second surface or second device to prove cross-surface routing
- Add one non-text capability so the runtime demonstrates more than a text loop

## Current Project Progress

Current phase:

- V0 single-edge loop implemented and testable

Current progress summary:

- The project problem statement is clear enough to start structuring implementation work
- We have agreed on a top-level split between `Device Edge` and `Personal Runtime`
- We have agreed that a central gateway/midplane concept is required
- We now have a written architecture baseline covering frontend/backend boundaries, internal module roles, and gateway scope
- We have now scoped the first usable v0 slice as a single-edge closed-loop runtime
- We are adopting a layered edge representation model: `device identity/constraints` plus `capability contracts`
- We prefer graded device profiles for heterogeneous edge hardware, but profile sprawl is now an explicit design risk to control
- We currently prefer profile modeling that is role-first with device-type metadata, while deferring heavy resource-tier scheduling design
- We also prefer a minimal role vocabulary that expands only when new device onboarding cannot fit existing roles cleanly
- We currently prefer a "reuse only if isolatable, otherwise rebuild minimal" stance for the OpenClaw gateway question
- We now have a preliminary source audit of OpenClaw gateway code that narrows reuse candidates to protocol/client/auth transport layers rather than the full gateway server surface
- We have explicitly defined that all physical frontend/backend communication must be funneled through `Edge Session Link <-> Gateway`
- We have partially defined the frontend/backend contract around capability events, state sync, action commands, and execution results
- We have selected the first v0 device surface as a desktop/CLI edge and the first capability loop as `text.input -> notification.show`
- We have also defined the immediate follow-up slice after v0: minimal persistence, a second surface or device, and one non-text capability
- We now have project-level Codex hooks enforcing `Project.md` session-start and per-turn audit behavior
- We have now defined the minimum backend module set for the first usable v0 slice
- We have initialized the repository as a git project and established an isolated worktree-based implementation flow
- We have completed the first implementation batch for the v0 plan: Python project scaffold, `personal_runtime` and `device_edge` package roots, shared protocol helpers, in-memory runtime state, and the same-device presence routing stub
- We now have automated tests covering the v0 scaffold import contract, protocol frame helpers, and runtime state/presence basics alongside the existing project hook tests
- We have now implemented the first minimal backend gateway loop, response generator, action builder, edge session client, and CLI edge runner
- We now have an executable and testable end-to-end single-edge closed loop from `text.input` to `notification.show`
- We can manually verify the local loop with `python3 -m device_edge.cli_edge`, and automated discovery now covers the full v0 and hook test suite
- We have not yet validated whether OpenClaw gateway code can actually be reused cleanly
- We have not yet performed deeper extraction tests on the most promising OpenClaw reuse candidates

Next recommended update trigger:

- Update this document whenever a major architecture decision, milestone decision, or sub-goal status changes

## Progress Update Rules

When updating this file:

- Keep goal statuses current
- Move finished sub-goals into the completed section
- Add new milestones or sub-goals only when they become concrete enough to evaluate
- Do not mark a sub-goal complete unless its acceptance criteria are satisfied
