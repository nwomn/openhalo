# Personal Runtime Agent Project

## Project Summary

This project aims to build a new personal agent system oriented around `device -> context -> presence -> action`, rather than the traditional `channel -> session -> agent` product shape.

The intended product is not "another chat agent entry point". It is a personal runtime that can exist across multiple devices, maintain continuity across contexts, and decide how to surface itself through the most appropriate device or interaction surface. The current product direction is increasingly `presence-first`: the runtime should proactively infer user situation across input channels, decide whether to intervene, and learn intervention policy over time rather than waiting only for explicit user requests.

At the current stage, the project has moved from pure architecture-definition into an implemented and testable runtime baseline that now spans both the completed v0 single-edge WebSocket loop and the first same-template multi-edge routing slice. The architecture baseline and early milestone framing are in place, the first end-to-end desktop/CLI closed loop can be executed both in-process and across two real local processes, and the runtime can now route a normal action from one connected edge instance to another while preserving core state across restarts.

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
- Agent-driven intervention, planning, and action generation
- Explicit presence-policy and intervention-governance inside the broader agent runtime
- External action orchestration

The current architecture baseline is documented in:

- `docs/plans/2026-06-16-runtime-architecture-design.md`
- `docs/plans/2026-06-18-goal2-presence-context-design.md`
- `docs/dev-env.md` for repository-level development environment workflow

Current boundary rules:

- `Frontend / Device Edge` is a device-resident edge runtime rather than a thin UI client
- `Backend / Personal Runtime` is a long-lived cross-device runtime rather than a traditional request-response backend
- `device`, `capability`, `context`, `agent`, and `action` are the primary runtime abstractions for this project
- `channel` and `session` are secondary implementation concepts and must not become the top-level product worldview
- `Presence` should remain an explicit, inspectable governance module inside the broader agent runtime rather than disappearing into opaque agent behavior
- All physical cross-boundary traffic must flow through `Edge Session Link <-> Gateway`
- Cross-boundary relationships between frontend and backend internal modules are logical only unless they pass through that transport choke point
- `Gateway` is a boundary and control-plane layer, not the primary reasoning layer
- `Presence` is a first-class governance layer inside the broader agent runtime, not just a device-routing helper; routing is only one sub-problem inside presence
- The working direction for proactive behavior is agent-centered but presence-governed: the runtime should allow the agent to form intervention proposals while requiring explicit presence decisions before user-facing intervention
- The runtime should support both a sense-first proactive path and an agent-initiative proactive path, and both paths must pass through `Presence Router` before user-facing intervention
- Presence policy should remain explicit and inspectable even when model-generated or model-repaired; models are not the only durable representation of proactive behavior
- The runtime should support both a normal deliberative path and an explicit edge-requested fast path for direct actions
- A direct action fast path may bypass `Presence Router` and `Agent Executor`, but it must still pass through `Gateway`, update runtime state/context, and record action results
- Runtime feedback interpretation should treat `ignore != negative`; explicit rejection or repeated similar-context dismissal should carry more weight than one-off non-response
- Presence policy updates should optimize for both immediate user experience and likely future user experience, rather than greedily maximizing the current interaction outcome
- For the first same-template multi-edge slice, ordinary routed actions should prefer a different online edge instance with the required capability before falling back to the source device
- Ordinary development work in worktrees should reuse the repository root `.venv` by default, while dependency or packaging experiments should use an explicitly created worktree-local `.venv`

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
- 1.4. Decide whether OpenClaw gateway should be reused as an isolated control-plane component or kept only as reference material

Acceptance criteria:

- A written architecture description exists
- The role of `Device Edge` and `Personal Runtime` is explicitly separated
- The meaning of `Gateway`, `State`, `Presence Router`, `Agent Executor`, and `Action Layer` is documented
- A clear decision exists on whether OpenClaw gateway code is reused directly, selectively referenced, or replaced

Status:

- Completed

Implementation note:

- The implementation path is no longer only conceptual; the first v0 batch has been started and the scaffold/protocol/state foundations are now in place

### Goal 2: Establish the project's primary abstractions

We need a stable and explicit abstraction baseline for the project so later implementation work does not drift back toward a `channel -> session -> agent` product shape.

Sub-goals:

- 2.1. Confirm first-class abstractions for the new system
- 2.2. Downgrade legacy abstractions to implementation details where appropriate
- 2.3. Define the minimum state model needed for continuity
- 2.4. Define the runtime dispatch-path abstraction for deliberative handling versus direct edge-requested action handling
- 2.5. Research and define the presence-policy model, including policy representation, scope boundaries, conflict handling, lifecycle management, and feedback-driven refinement

Acceptance criteria:

- Primary runtime abstractions are documented explicitly as `device`, `capability`, `context`, `agent`, and `action`
- `channel` and `session` are explicitly classified as secondary implementation concepts rather than primary product abstractions
- The project documents that `Presence` remains an explicit, inspectable governance module inside the broader agent runtime rather than disappearing into opaque agent behavior
- The minimum state model includes context, device state, handoff state, intervention history, experience feedback signals, and tasks as a derived or optional structured object rather than the mandatory primary axis
- The runtime documents which layers may be bypassed by an explicit direct-action request and which state/context recording steps remain mandatory
- The project documents that proactive behavior is agent-centered but presence-governed, with explicit or inspectable presence policy as the durable control surface for intervention decisions
- The project documents that early presence-policy refinement should use a review-gated update loop: runtime and agent tooling may prepare policy update candidates from feedback, but user-approved review remains the default before changes take effect
- The project documents that presence decisions should consume structured context observations and a synthesized context snapshot rather than raw environment signals directly
- The project documents that the shared observation vocabulary should grow incrementally at the top level: new terms are introduced during edge development, validated centrally, and then used as normal runtime vocabulary once accepted
- The project documents that proactive runtime evaluation may be initiated either by edge/context signals or by agent initiative, but both paths must converge on the same presence gate

Status:

- Completed

Implementation note:

- This goal is intended to finish once the abstraction vocabulary is written clearly enough that later implementation work can be checked against it, while the anti-drift rule itself remains a standing architecture constraint. The current direction is to treat `agent` as the primary intelligent actor, treat `presence` as an explicit internal governance layer for intervention decisions, treat `task` as a secondary structure that may be created when useful, and allow agents/models to grow or repair inspectable presence policy from feedback over time.
- The current implementation preference is to keep the online runtime path small and inspectable: edge mappers produce normalized runtime observations, lightweight per-observation reducers synthesize compact context snapshot fields, and `unknown` or `ambiguous` results are allowed when evidence is insufficient.
- The current implementation preference is to keep presence evaluation unified even when the trigger differs: edge/context activity and agent-initiative checks should both build or refresh compact context snapshot state and then flow through the same presence decision surface.
- The detailed presence-policy design remains intentionally deferred for a dedicated research and design pass. That pass should explicitly study policy representation shape, conflict avoidance and resolution, orthogonality of policy scope, short-term versus long-term policy lifecycle, how present user-experience optimization should be balanced against future user-experience impact, how policy update review cadence should lengthen as the system becomes more stable, how environment understanding should flow from raw edge signals into structured context observations and then into a presence-consumable context snapshot, and how the shared observation vocabulary should be extended safely as new edge types are added.
- Heuristic-learning style improvement should live in one unified outer maintenance loop rather than the hot decision path: feedback, replays, and tests may drive coordinated updates to edge mappers, observation reducers, vocabulary, and presence policy, but those changes remain review-gated before entering the normal runtime path.
- Presence should consume the compact context snapshot directly rather than introducing an additional presence-only feature view; richer observation evidence remains available separately for agent reasoning and debugging when needed.
- Agent initiative should be a first-class high-salience input to presence evaluation rather than a low-priority afterthought, but it should still remain subject to suppression, privacy, and timing policy.
- Reference inspiration for this outer-loop direction: [Learning Beyond Gradients](https://trinkle23897.github.io/learning-beyond-gradients/#zh)

### Goal 3: Define the initial implementation path

We need an implementation starting point that is focused enough to produce progress quickly.

Sub-goals:

- 3.1. Select the first project folder and documentation baseline
- 3.2. Define the first implementation milestone
- 3.3. Identify the minimum backend modules for v0
- 3.4. Identify the minimum device surfaces for v0
- 3.5. Define the first post-v0 multi-edge slice using the same edge template on more than one device instance

Acceptance criteria:

- The project has a dedicated folder
- Project baseline documentation exists
- The first milestone is small enough to implement without solving the whole system
- The v0 scope names which modules and device surfaces are first-class
- The next slice after v0 names how multiple same-template edges participate and what routing behavior it is meant to validate

Status:

- Completed

### Goal 4: Build the project incrementally from architecture to runtime

We need a milestone ladder from concept to working system.

Sub-goals:

- 4.1. Define milestone M0: architecture and state model validation
- 4.2. Define milestone M1: minimal runtime core with real transport, minimal continuity, and explicit direct-action fast-path support
- 4.3. Define milestone M2: first multi-device continuity and same-template cross-edge routing path
- 4.4. Define milestone M3: first presence-aware routing path beyond fixed fast-path and simple fallback rules

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

### Completed: OpenClaw gateway reuse decision

Result:

- The project has moved past the stage where OpenClaw gateway reuse is needed to bootstrap a working runtime baseline
- The repository now has its own tested minimal protocol helpers, edge session client, and runtime gateway covering the current v0 and early M2 transport needs
- OpenClaw gateway server code is no longer treated as a primary reuse target for implementation
- `packages/gateway-protocol` and `packages/gateway-client` remain useful as reference material and possible selective inspiration, not as planned integration dependencies
- A minimal replacement gateway is now the active project path, with OpenClaw transport and protocol pieces retained only as optional future reference

Acceptance criteria:

- The project has an explicit decision on direct reuse versus replacement for the OpenClaw gateway server surface
- The decision reflects the current implementation baseline rather than only the earlier source audit
- The remaining role of OpenClaw protocol/client code is documented clearly enough to guide future work

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

### Completed: First real WebSocket single-edge closed loop

Result:

- The backend now exposes a real WebSocket gateway server path in addition to the in-process simulation helpers
- The edge session client now supports real WebSocket client roundtrips against an explicit runtime URL
- The runtime records returned `action_result` payloads in memory after local edge execution
- The project now uses a worktree-local `.venv` for Python dependency isolation, including `websockets`
- Manual verification now proves a true two-process flow: runtime server process plus CLI edge process over `ws://127.0.0.1`
- Automated tests now cover real WebSocket handshake, event delivery, action request delivery, and action-result return flow

Acceptance criteria:

- A local runtime server can bind a WebSocket endpoint and accept the minimal v0 frame sequence
- A local edge client can connect over WebSocket, send text input, receive an action request, execute it, and return an action result
- The real WebSocket path is covered by automated tests
- The real two-process loop can be exercised manually from the command line

Status:

- Completed

### Completed: Explicit direct-action fast path baseline

Result:

- The edge session client can now build an explicit `direct_action` event payload for urgent edge-requested actions
- The gateway now detects `direct_action` requests on `event_push` frames and converts them directly into `action_request` frames without going through the normal routed reply generation path
- Direct-action events are still appended to runtime state and persisted before dispatch so continuity and auditability are preserved
- Returned `action_result` payloads continue to be recorded and persisted through the shared gateway action-result path after local edge execution
- Automated tests now verify that a direct-action event bypasses the normal routing path while still being persisted

Acceptance criteria:

- An edge can send an explicit direct-action request through the normal gateway transport
- The gateway can bypass `Presence Router` and `Agent Executor` for that request and emit the requested action directly
- The runtime still records the event and resulting action outcome in shared state on the existing persistence path
- The direct-action behavior is covered by automated tests

Status:

- Completed

### Completed: Minimal runtime continuity persistence

Result:

- Runtime state can now be serialized to and restored from a file-backed JSON snapshot
- The gateway now persists device registration, capability registration, recent events, and action results automatically after state changes
- The runtime server entrypoint now supports a configurable `--state-path` and restores state on startup
- The project ignores generated runtime snapshot directories so persistence artifacts do not pollute git state
- Automated tests now verify state serialization, state store load/save, gateway-triggered persistence, and runtime restart recovery

Acceptance criteria:

- Core runtime state survives process restarts through disk-backed snapshots
- State writes happen automatically on the main v0 state transition paths
- Runtime startup restores previously persisted state from disk
- The persistence path is covered by automated tests

Status:

- Completed

### Completed: First same-template multi-edge routing slice

Result:

- The runtime can now keep two live instances of the same edge template connected at once under different `device_id`s
- The normal routed path can now target another connected edge instance for `notification.show` instead of always replying to the source device
- The WebSocket gateway now maintains a minimal online connection registry so `action_request` frames can be delivered to a different live edge connection
- The ordinary routing path now prefers online peers and falls back to the source device when only offline residual device state is available
- Automated tests now cover capability-based target selection, sync cross-edge routing, real WebSocket cross-edge delivery, and fallback behavior when a peer is not online

Acceptance criteria:

- Two instances of the same edge template can connect to one runtime with distinct device identities
- A normal routed action can be delivered from one connected edge to another over the real WebSocket path
- The runtime still records events and action results correctly while routing across edge instances
- Offline residual device state does not hijack ordinary routed actions away from the currently active edge

Status:

- Completed

### Completed: Repository development environment workflow baseline

Result:

- The repository now documents a default shared-venv workflow in `docs/dev-env.md`
- `bin/test` now provides a small helper that always uses the repository root `.venv`
- `bin/bootstrap-worktree-venv` now provides an explicit opt-in path for isolated worktree environments during dependency or packaging experiments
- Automated tests now verify the helper scripts and the documented shared-versus-isolated environment rules

Acceptance criteria:

- The default development workflow for ordinary worktrees is explicitly documented
- The isolated worktree environment exception path is explicitly documented
- The repository includes helper commands for both modes
- The environment workflow is covered by automated tests

Status:

- Completed

### Completed: First M3 presence-context foundation batch

Result:

- The runtime now has explicit shared context contracts for `Device`, `Capability`, and normalized `RuntimeObservation` records
- Runtime state can now store normalized observations with provenance separately from raw edge event details and round-trip them through serialization
- The project now has a first compact context snapshot reducer module for hot-path presence work
- The first snapshot field, `user.current_location`, now supports concrete value selection as well as explicit `unknown` and `ambiguous` outcomes
- Automated tests now cover the shared contract shapes, normalized observation storage, and compact snapshot reducer behavior

Acceptance criteria:

- Shared runtime context contract types exist for device, capability, and normalized observation records
- Runtime state can record and restore normalized observations with provenance
- A compact snapshot reducer exists for at least one presence-relevant field and preserves `unknown` / `ambiguous` outcomes when evidence is insufficient or conflicting
- The new context and snapshot foundation is covered by automated tests

Status:

- Completed

## Open Questions

- Which device surfaces should be the first non-CLI surfaces for presence-first experiments?
- What is the smallest inspectable policy representation that can support model-authored or model-repaired intervention behavior without becoming opaque?
- Which feedback signals are strong enough to update presence policy automatically versus only being stored as weak evidence?
- How should the runtime prevent learned or generated policies from colliding with one another as the policy set grows over time?
- How should policy scope be constrained so independently learned rules stay as orthogonal as possible instead of silently overlapping?
- What lifecycle model should distinguish short-lived situational policy from durable long-term user preference or trust policy?
- Which parts of the presence-policy problem should be informed by external research before the first concrete design is locked in?
- What review cadence should govern early presence-policy updates, and what evidence should be strong enough to justify moving from daily review toward weekly, monthly, or longer review windows?

Current preference:

- Keep the project on its own minimal gateway path rather than planning around OpenClaw gateway server reuse
- Treat the earlier OpenClaw source audit as useful reference context, not as an integration roadmap
- Retain `packages/gateway-protocol` and `packages/gateway-client` only as optional reference material for future protocol organization or client transport hardening
- Treat proactive intervention as an agent-centered but presence-governed problem rather than a task-first assistant workflow
- Treat `Presence Router` as an explicit governance/policy layer inside the broader agent runtime whose scope includes whether to intervene, when, where, and with what intensity
- Prefer explicit or inspectable policy as the durable control surface for proactive behavior, while allowing agent/model loops to create, revise, and repair that policy from runtime feedback
- Prefer a review-gated policy maintenance loop in early phases: runtime and agents may prepare policy update candidates from feedback, but the user should confirm changes on a deliberate cadence before activation
- Treat intervention history and experience feedback as first-class state inputs for policy refinement
- Interpret single ignored interventions as weak evidence rather than immediate negative feedback
- Optimize policy updates against both current user experience and likely future user experience
- Treat policy review cadence itself as adaptive governance: early policy changes may be reviewed daily while the system is noisy, then gradually move toward weekly, monthly, or longer windows as behavior stabilizes
- Prefer a structured environment-understanding pipeline for early presence work: edge sensing produces normalized context observations with source metadata, confidence, and TTL; runtime context state then synthesizes those observations into the snapshot consumed by presence policy
- Prefer a centrally owned shared observation vocabulary that starts small and grows incrementally; new vocabulary should be added at the top level during edge development, validated there, and then treated as normal runtime vocabulary once accepted
- Prefer one unified heuristic-learning maintenance loop around the runtime rather than separate learning loops per layer: online behavior should use explicit mappers and lightweight reducers, while feedback-driven improvements update those components and presence policy through review-gated iterations
- Avoid adding an extra presence-only feature abstraction between context snapshot and `Presence Router`; keep the hot path shallow and let richer evidence remain available separately outside the compact snapshot
- Prefer a dual-entry proactive model: both edge/context activity and agent initiative may trigger agent proposal generation, but both should converge on the same `Presence Router`
- Prefer agent-initiative requests to carry higher salience than weak passive signals so the system feels meaningfully proactive, while still remaining constrained by presence suppression and privacy policy
- Keep the heuristic-learning reference explicit in project context so future implementation work can revisit the outer-loop design source: [Learning Beyond Gradients](https://trinkle23897.github.io/learning-beyond-gradients/#zh)
- For urgent edge-originated actions, prefer an explicit direct-action path over pretending every event should go through model-driven routing or planning
- Even when an edge requests a direct action, the runtime should still retain the event and result in shared state so continuity and auditability are preserved

Current v0 milestone direction:

- Start with one desktop/CLI `Device Edge`
- Use one long-lived `Edge Session Link <-> Gateway` path
- Keep auth, presence, and state intentionally minimal
- Prove one full loop from `text.input` to `notification.show`
- Preserve room for two runtime dispatch paths: ordinary routed/deliberative handling and explicit direct-action handling

Immediate post-v0 direction:

- Extend persistence enough to support multi-edge continuity experiments cleanly
- Run more than one instance of the same edge template to prove cross-edge routing without introducing a separate one-off edge type
- Add one non-text capability so the runtime demonstrates more than a text loop

Current M2 slice direction:

- Treat same-template edge instances as separate live devices distinguished by `device_id`
- Keep routing rules intentionally simple for now: prefer another online edge with the required capability, otherwise fall back to the source device
- Preserve the direct-action fast path alongside the new ordinary cross-edge routing path
- Use this slice to validate gateway connection tracking and cross-edge action delivery before adding richer presence logic

Current M3 slice direction:

- Build explicit shared context contracts before threading richer presence logic through the live runtime path
- Store normalized runtime observations with provenance separately from raw edge event details
- Build compact snapshot reducers one field at a time, preserving `unknown` and `ambiguous` outcomes instead of forcing certainty
- After the context foundation is stable, thread snapshot-driven routing into `Presence Router` and gateway decision flow

## Current Project Progress

Current phase:

- First M3 presence-context foundation batch implemented on top of the completed v0 and M2 routing baseline

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
- We have now decided not to plan around direct OpenClaw gateway server reuse for implementation
- The earlier OpenClaw source audit remains useful as reference, especially around protocol and client transport patterns, but no longer drives the main delivery path
- We have explicitly defined that all physical frontend/backend communication must be funneled through `Edge Session Link <-> Gateway`
- We have partially defined the frontend/backend contract around capability events, state sync, action commands, and execution results
- We now prefer an agent-centered but presence-governed product reading of the architecture: the runtime should let the agent form intervention proposals while requiring explicit presence decisions before surfacing itself
- We now treat the current `Presence Router` concept as a broader intervention-governance layer inside the agent runtime rather than a narrow routing helper
- We now prefer durable proactive behavior to live in explicit or inspectable policy that can be created and revised by agent/model loops instead of only in end-to-end opaque model behavior
- We now expect future runtime state for Goal 2 to include intervention history and experience feedback signals so the system can learn from how users react to proactive actions
- We now explicitly treat a single ignored intervention as weak evidence rather than a definitive negative outcome
- We now want policy refinement to consider both present interaction quality and likely future user-experience impact, not just the immediate result of the latest action
- We have now identified presence-policy design itself as a dedicated Goal 2 workstream that should be handled in a focused later discussion with supporting external research rather than being settled incidentally
- We now prefer early presence-policy updates to be review-gated rather than silently auto-applied, with candidate updates accumulated from runtime feedback and confirmed by the user on an explicit cadence that can lengthen over time
- We now prefer a v1 environment-understanding pipeline where raw edge signals are normalized into structured context observations and then merged into a context snapshot before any presence-policy decision is evaluated
- We now prefer observation-vocabulary governance where new shared terms are introduced and validated centrally during edge development, then immediately become normal system vocabulary once added to the top-level contract
- We now prefer to implement environment understanding with explicit online mappers and small per-observation reducers, while using a single review-gated heuristic-learning outer loop to refine vocabulary, reducers, and presence policy from feedback over time
- We now prefer `Presence Router` to consume the compact snapshot directly, without an extra presence feature layer, while `Agent Executor` may still inspect snapshot plus supporting observation evidence when deeper reasoning is needed
- We now have a written Goal 2 design baseline for device/capability contracts, runtime observations, compact context snapshots, presence-policy axes, and the unified heuristic-learning outer loop in `docs/plans/2026-06-18-goal2-presence-context-design.md`
- We now explicitly support both sense-first and agent-initiative proactive paths, with both paths converging on `Presence Router` and agent-initiative requests carrying meaningful salience without bypassing suppression policy
- We now treat `agent` as a primary runtime abstraction and `Presence Router` as an explicit governance module inside the broader agent runtime, completing the current Goal 2 abstraction baseline
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
- We now have a project-local `.venv` for dependency isolation instead of relying on global Python packages
- We now have a real WebSocket transport path for the single-edge loop, including gateway server binding, edge client connection, action dispatch, and action-result return
- We have manually verified a true two-process local flow using `python3 -m personal_runtime.main` and `python3 -m device_edge.cli_edge --url ...`
- We now have minimal file-backed continuity through runtime state snapshots and restart recovery via a configurable state path
- The gateway now persists device, capability, event, and action-result state automatically on the main v0 flow
- We now have a two-path runtime reaction model implemented: a normal routed/deliberative path and an explicit edge-requested direct-action path
- Direct-action requests can now bypass routing and agent planning while still being recorded in runtime state/context together with their execution results
- We now have the first same-template multi-edge routing slice working: two edge instances can stay connected and a normal routed notification action can be delivered from one device to another
- The gateway now tracks live edge connections for WebSocket delivery, allowing cross-edge `action_request` frames instead of only same-socket replies
- Ordinary routed actions now prefer another online peer with the required capability and safely fall back to the source edge when only offline residual device state is present
- We now have a repository-level development environment workflow: ordinary worktrees reuse the root `.venv`, while dependency and packaging experiments use an explicitly created worktree-local `.venv`
- The repository now includes helper scripts and automated tests for that shared-versus-isolated environment workflow
- We now have explicit shared runtime context contracts for device, capability, and normalized observation records
- Runtime state can now retain normalized observations with provenance as a distinct layer instead of collapsing everything into raw event history only
- We now have the first compact context snapshot reducer for hot-path presence work, including explicit `unknown` and `ambiguous` outcomes for location evidence
- Targeted automated tests now cover shared context contracts, observation storage, and the first compact snapshot reducer behavior
- We have our own tested minimal protocol, edge session client, and gateway baseline, reducing the value of deeper OpenClaw gateway extraction work
- We may still borrow ideas from OpenClaw protocol/client layers later, but that is now optional follow-on work rather than an open prerequisite

Next recommended update trigger:

- Update this document whenever a major architecture decision, milestone decision, or sub-goal status changes

## Progress Update Rules

When updating this file:

- Keep goal statuses current
- Move finished sub-goals into the completed section
- Add new milestones or sub-goals only when they become concrete enough to evaluate
- Do not mark a sub-goal complete unless its acceptance criteria are satisfied
