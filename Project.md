# OpenHalo Project

## Project Summary

OpenHalo is a new personal agent runtime system oriented around `device -> context -> presence -> action`, rather than the traditional `channel -> session -> agent` product shape.

The intended product is not "another chat agent entry point". OpenHalo is a personal runtime that can exist across multiple devices, maintain continuity across contexts, and decide how to surface itself through the most appropriate device or interaction surface. The current product direction is increasingly `presence-first`: the runtime should proactively infer user situation across input channels, decide whether to intervene, and learn intervention policy over time rather than waiting only for explicit user requests.

At the current stage, the project has moved from pure architecture-definition into an implemented and testable runtime baseline that now spans both the completed v0 single-edge WebSocket loop and the first same-template multi-edge routing slice. The architecture baseline and early milestone framing are in place, the first end-to-end desktop/CLI closed loop can be executed both in-process and across two real local processes, and the runtime can now route a normal action from one connected edge instance to another while preserving core state across restarts. The desktop/CLI surface has now been promoted into the first formal long-running terminal edge, with both user-initiated and runtime-initiated interaction still expressed through the normal `device -> context -> presence -> action` architecture rather than a chat-centered exception path. The current frontend baseline now includes both bounded scripted acceptance for repeatable verification and a true foreground live terminal session that reads user input from `stdin` on the same resident edge session.

## Naming Decision

- The project name is now `OpenHalo`.
- `OpenHalo` is the public/open-source project name for the presence-first personal runtime.
- `Personal Runtime` remains the backend architecture concept for the long-lived cross-device runtime core.
- Avoid expanding the name to `Halo OS` for now; keep `OpenHalo` as the project/repository-level name while the product shape remains open and exploratory.

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

The first host-class edge may also run on the same cloud or server substrate that hosts the runtime itself, as long as it still participates through the normal edge boundary rather than becoming an implicit backend side channel.

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
- `docs/plans/2026-06-19-host-edge-v1-design.md`
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
- `Agent Runtime` is the primary intelligent runtime module; proposal formation and execution planning both belong inside that module rather than being modeled as separate top-level backend modules
- `Presence Router` should be treated as an explicit, inspectable governance submodule inside `Agent Runtime`, so intervention logic remains readable and more deterministic than a pure model-probability output
- The working direction for proactive behavior is agent-centered but presence-governed: the runtime should allow the agent to form intervention proposals while requiring explicit presence decisions before user-facing intervention
- The runtime should support both a sense-first proactive path and an agent-initiative proactive path, and both paths must pass through `Presence Router` before user-facing intervention
- Edge-delivered signals may carry either passive environment evidence or explicit user-expressed intent; both still count as edge/context input on the sense-first path, and the runtime should interpret that input through normal proposal formation on the shared agent/presence path rather than treating any one edge type as a special case
- Proposal formation must distinguish passive observation evidence from user intent: not every observation should trigger interaction, but explicit requests, explicit commands, and approved user-configured intent triggers must receive a user-perceptible response or outcome through the presence-governed interaction model
- Ambiguous physical or environmental signals, such as an unexplained gesture captured by a future camera edge, should remain evidence by default; the same signal may become actionable intent only after user agreement, policy, or context explicitly promotes it into a configured trigger
- Explicit cross-edge commands may require two semantic surfaces: the target edge performs the requested action, while the requesting edge receives acknowledgement, result reporting, or failure explanation; proposal formation should preserve both semantics instead of collapsing the whole turn into only the remote action surface
- The hot decision path should stay shallow and explicit: once an edge-driven event reaches deliberative handling, the preferred runtime-owned chain is `event -> compact snapshot -> grounding bundle -> prompt/context package -> model-backed proposal formation -> Presence Router -> execution planning/action`, and new intermediate representations on that path require a clear non-duplicative reason
- Proposal formation should be allowed to synthesize an interaction hypothesis from one high-salience signal or from multiple device observations together; a line of terminal text is only one possible trigger shape, not the only interaction origin the runtime may reason about
- Model-backed proposal formation may emit interaction-semantic candidates such as interaction type, candidate participant surfaces, visibility intent, and the current `primary action`, but those remain proposal-layer candidates until presence governance and execution planning turn them into an actual runtime outcome
- `Presence Router` should act as an explicit governance and adjudication layer, not only a passive allow/block filter: it may suppress, narrow, retime, or redirect proposed surfaces and actions based on policy, privacy, activity, capability, and availability constraints
- `InterventionProposal.source` records the Runtime interaction phase (`sense_first`, `agent_initiative`, `observation_driven`, `post_action`, or `post_observation`), never the embedded model implementation. The current stage intentionally has no global intervention-history cooldown: terminal activity, contextual ambiguity, capability, privacy, permission, and explicit policy remain active governance inputs; future rate control must return as evidence-backed scoped policy work rather than a fixed global timer.
- The runtime may keep one `primary action` per planning turn in early slices, but that bound should remain an implementation constraint rather than a long-term architecture rule; the same interaction lifecycle should later support multi-turn `action loop` re-entry after action results or new observations
- M20 action-loop remediation replaces the historical one-external-action assumption with a runtime-owned `ActionBatch`: Hermes may complete bounded internal reasoning and propose one or more distinct governed actions, Runtime validates and dispatches the complete batch, and the interaction remains `awaiting_action_results` until every exact correlated action result, timeout, or structured failure is recorded. Distinct valid actions are never silently collapsed into `no_intervention`; exact duplicates are folded idempotently and invalid or conflicting batches terminate with an explicit inspectable rejection.
- An interaction worker is a scheduling role over one `InteractionPool` record, not a second lifecycle domain. The record persists its Hermes child-session identity and pending action-batch correlation. Hermes-native child sessions perform semantic work, while Runtime remains authoritative for concurrency, context projection, Presence, executor validation, result correlation, timeout, recovery, and completion.
- Hermes-native child sessions have isolated conversation histories. Before initial work and every result-set continuation, Runtime supplies a bounded shared-context projection containing the OpenHalo identity contract, relevant durable MemoryStore facts, active goals, exact device roster, and interaction lineage/results. This is not a copy of the persistent main-agent transcript; Runtime records lifecycle/audit pointers while Hermes MemoryStore remains the semantic durable-memory authority.
- Model-native tool calls, MCP tool calls, runtime-local tools, skill/procedure invocations, and external device actions should converge into one runtime-owned action intent/result model before side effects occur; provider-native tool syntax is an adapter input, not a permission to bypass OpenHalo action governance
- `Personal Runtime` is the authoritative source of a bounded structured device roster projected from registered device identity, capability contracts, and live availability. The Agent Harness receives that roster and performs semantic target selection from it; `Runtime` validates and governs the selected exact device target but must not replace it through keyword routing or another semantic fallback.
- The executor kind for a model-native action is selected by the OpenHalo adapter or action registry, not by a model-supplied tool argument; the M20 `openhalo_action` bridge is limited to governed `Device Edge` actions, while runtime-local, MCP, and skill/procedure routes remain OpenHalo-owned registrations
- Agent behavior should be constrained by explicit prompt/context contracts, behavior contracts, capability/action registry validation, and post-generation validation or repair before any user-visible or side-effectful action is executed
- Presence policy should remain explicit and inspectable even when model-generated or model-repaired; models are not the only durable representation of proactive behavior
- A host-resident edge running on the runtime's own server is still modeled as a first-class `Device Edge`; physical co-location does not waive the `Edge Session Link <-> Gateway` boundary
- The runtime should support both a normal deliberative path and an explicit edge-requested fast path for direct actions
- A direct action fast path may bypass the normal `Agent Runtime` path, including `Presence Router`, but it must still pass through `Gateway`, validate structured input against the exact registered target capability/schema, restrict `runtime.*` actions to the explicit runtime-control allowlist, update runtime state/context, and record action results; on the normal path, a valid `runtime.* -> runtime.control` mapping remains subject to all ordinary Presence, modality, privacy, and schema filtering
- Runtime feedback interpretation should treat `ignore != negative`; explicit rejection or repeated similar-context dismissal should carry more weight than one-off non-response
- Presence policy updates should optimize for both immediate user experience and likely future user experience, rather than greedily maximizing the current interaction outcome
- For the first same-template multi-edge slice, ordinary routed actions should prefer a different online edge instance with the required capability before falling back to the source device
- Ordinary development work should be branch-first in the main workspace and should reuse the repository root `.venv` by default, while optional worktree-based dependency or packaging experiments should use an explicitly created worktree-local `.venv`
- Runtime startup should distinguish restart-heavy development acceptance from the long-running server runtime: development helpers use port `18765` by default, while stable server operation reserves port `8765` and should be owned by a process supervisor such as systemd
- Current backend hardening gap: `Gateway` should reject post-connect frames such as `capability_announce`, `observation_push`, `event_push`, or `action_result` from unknown or unauthorized `device_id` values with a structured public error instead of allowing runtime-side exceptions such as `KeyError`
- CLI device validation is acceptable for early module testing, but host-edge verification is required before documenting a module as fully implemented and operationally ready
- In this project, `manual acceptance` or `human acceptance` means testing implemented functionality in a simulated real usage scenario, rather than only checking static output, isolated unit behavior, or non-interactive script success

Initial productization target:

- The first productized OpenHalo slice should package three surfaces together rather than treating them as unrelated developer processes: phone `Device Edge`, desktop/computer `Device Edge`, and server-side `Personal Runtime` plus host-class `Device Edge`
- The Linux server runtime should support a one-command or one-script installation path that installs and configures both `Personal Runtime` and the server/host edge together, while still preserving the `Device Edge -> Edge API -> Gateway -> Personal Runtime` boundary
- The Windows desktop edge should be installable through a normal user-facing installer rather than only through a development shell; the productized desktop package may include the runtime and host edge as optional local components that are installed but disabled by default
- The Android phone edge should be deliverable as an APK suitable for real-device installation outside Android Studio
- The standard deployment scene is: one public server running `Personal Runtime + host edge`, one computer running the desktop edge, and one phone running the phone edge
- The computer-server deployment scene is: one computer running `Personal Runtime + host edge + desktop edge`, with the phone edge connecting to the computer-hosted runtime
- Product packaging is now an explicit product milestone, not only a release-engineering afterthought; UI polish, installation flow, service supervision, endpoint pairing, and deployment-mode clarity all count as part of the first productized slice

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
- The meaning of `Gateway`, `State`, `Agent Runtime`, `Presence Router`, and `Action Layer` is documented
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
- The current implementation preference is to model `Agent Runtime` as one coherent backend module whose internal flow includes proposal formation, explicit presence governance, and later execution planning, rather than splitting those responsibilities into multiple top-level architecture boxes.
- When edge-delivered signals carry user intent, the current design preference is to keep `Agent Runtime` proposal formation on a small runtime-native taxonomy: normal user-visible or side-effectful outcomes are `action`, silent suppression/closure is `no_intervention`, and model/provider failures use the internal `provider_failure` channel rather than chat-style `reply` or `clarification` top-level proposal types.
- The current implementation preference is to avoid duplicate context-carrier layers on the hot path: if `grounding bundle` feeds a `prompt/context package`, later steps should consume that package directly rather than rebuilding equivalent payloads under new names.
- Inspection-oriented surfaces such as behavior contracts, replay/eval reports, or other verification artifacts should be treated as sidecars around the hot path by default; they may validate or summarize live-chain artifacts, but should not become mandatory intermediate decision objects unless they directly change runtime behavior.
- The detailed presence-policy design remains intentionally deferred for a dedicated research and design pass. That pass should explicitly study policy representation shape, conflict avoidance and resolution, orthogonality of policy scope, short-term versus long-term policy lifecycle, how present user-experience optimization should be balanced against future user-experience impact, how policy update review cadence should lengthen as the system becomes more stable, how environment understanding should flow from raw edge signals into structured context observations and then into a presence-consumable context snapshot, and how the shared observation vocabulary should be extended safely as new edge types are added.
- Heuristic-learning style improvement should live in one unified outer maintenance loop rather than the hot decision path: feedback, replays, and tests may drive coordinated updates to edge mappers, observation reducers, vocabulary, and presence policy, but those changes remain review-gated before entering the normal runtime path.
- Short-term device-context integration should use built-in observation-to-snapshot reducers for first-product core edges such as phone, desktop/terminal, host, and runtime health surfaces, so their presence-relevant observations become stable decision inputs without waiting for a generic dynamic mapping system.
- Before expanding into broad multi-sensor edge deployments, the project should implement the heuristic-learning governance loop that can inspect observations, snapshots, decisions, action results, and feedback, then propose reviewed mapper/reducer/vocabulary/presence-policy updates for the larger observation space.
- Presence should consume the compact context snapshot directly rather than introducing an additional presence-only feature view; richer observation evidence remains available separately for agent reasoning and debugging when needed.
- The current design preference is that raw fine-grained device history remains edge-local by default: core stores normalized observations plus provenance, while deeper agent inspection of device history should use explicit bounded edge-side diagnostics or history retrieval instead of continuous raw-history duplication into backend state.
- Agent initiative should be a first-class high-salience input to presence evaluation rather than a low-priority afterthought, but it should still remain subject to suppression, privacy, and timing policy.
- Runtime interaction lifecycle should be source-neutral through one bounded `Interaction Pool` inside the `State / Context / Agent Runtime` surface: explicit user events, admitted observation-driven triggers, agent initiative, and later action-result or fresh-observation re-entry all register or resume ordinary interactions rather than using source-specific lifecycle paths. `M18` may decide whether passive evidence merits registration, but once registered its interaction has the same proposal, presence, action, result-routing, and completion semantics as a chat-originated interaction.
- The Interaction Pool should support multiple active interactions concurrently. It may deduplicate or merge only the same causal/idempotency scope, identified from triggering evidence and provenance rather than time proximity or a guessed intent; unrelated interactions may deliberate in parallel, while `Presence Router` remains the common user-facing delivery arbiter.
- The current bounded M18 Gate is a provisional fixed-signal implementation, not the final definition of observation understanding. The durable M18 direction keeps deterministic privacy, provenance, causal, deduplication, and budget safeguards at the observation boundary, but lets the Agent Harness actively modulate relevance and follow-up from its current working/semantic/episodic state, uncertainty, active interactions, and user situation. This must not collapse into a fixed catalog of profile fields or questions: the harness may decide that an observation deserves deeper attention, request bounded safe evidence, defer it, or leave it as context according to the present situation, then register any resulting work through the ordinary Interaction Pool and shared Presence governance chain.
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
- 4.5. Define milestone M4: first mature host-edge runtime that can run stably as a real edge surface with continuous observation, durable control behavior, and edge-local verification without requiring the backend maturity work to be finished
- 4.6. Define milestone M5: mature runtime ingestion and context path on top of stable host-edge input, including gateway handling, normalized observation storage, snapshot reduction, and context freshness / ambiguity handling
- 4.7. Define milestone M6: mature presence, agent, and action path on top of stable real-edge input, so the proactive runtime chain becomes reliable beyond the current validation slice
- 4.8. Define milestone M7: operational-readiness verification milestone that gates "implemented and ready to run" claims on end-to-end host-edge-path validation rather than CLI-only checks
- 4.9. Define milestone M8: first formal terminal-edge interaction surface, turning the desktop/CLI edge into a resident terminal `Device Edge` with pull-style user requests, presence-gated runtime push, and explicit terminal activity sensing on the normal runtime path rather than as a chat-special case
- 4.10. Define milestone M9: cloud-model-backed agent baseline, so the runtime can use a real cloud model for proposal and reply generation while preserving explicit `Presence Router` governance, inspectable planning surfaces, and bounded non-model fallback behavior
- 4.11. Define milestone M10: model grounding and runtime memory baseline, so model-backed proposal and reply generation are anchored in compact context snapshot, active runtime goals, bounded edge-history retrieval, and durable state instead of behaving like stateless channel chat
- 4.12. Define milestone M11: terminal/CLI interaction maturity pass, so the first terminal edge grows from a minimal resident daemon into a substantially more complete agent CLI surface with stronger interaction ergonomics, session readability, streaming/status visibility, input affordances, and human-usable command-line UX that can better stand beside tools such as Lobster, Codex, and Claude Code without changing the core presence-governed runtime architecture
- 4.13. Define milestone M12: prompt/context engineering and behavior-contract pass, so grounded model-backed proposal and reply generation advance from first runtime-memory wiring into explicit prompt/context assembly, prompt versioning, replay/eval harnesses, and inspectable behavior contracts that verify the runtime actually uses compact snapshot state, active goals, bounded memory, and edge evidence reliably
- 4.14. Define milestone M13: proposal-formation maturity pass, so the runtime advances from the current narrow reply-shaped proposal slice into a sufficiently capable proposal-formation system that can interpret edge-delivered signals and grounded runtime context into inspectable runtime-owned proposal outcomes on the normal live chain; after M17.6 hardening, the current normal taxonomy is `action` and `no_intervention`
- 4.15. Define milestone M14: model-provider connection reliability and diagnostics, so real cloud-model usage becomes stable, observable, and protocol-aware before deeper action-loop behavior depends on it
- 4.16. Define milestone M15: runtime-native credential and runtime-config baseline, so OpenHalo can authenticate real model-provider access through its own inspectable local runtime configuration flow instead of depending on ad hoc shell environment variables or external tool-specific credential stores
- 4.17. Define milestone M16: post-action deliberation and interaction action loop, so action results or fresh observations can re-enter `Agent Runtime` inside the same interaction lifecycle and yield a new inspectable runtime-owned proposal outcome instead of terminating at a fixed completion formatter
- 4.18. Define milestone M17: multi-edge interaction expansion after the first terminal/model/action-loop baseline, so additional device surfaces can join the same presence-governed interaction model without re-centering the system on any single frontend
- 4.18.1. Define milestone M17.0: public Edge API boundary and internal-runtime encapsulation baseline, so new device edges can integrate through stable external API contracts while `Personal Runtime` internals remain closed behind the `Edge Session Link <-> Gateway` boundary
- 4.18.2. Define milestone M17.1: registration-driven multi-device extension baseline, so new edges can register action capabilities and observation contracts through the public Edge API, while runtime validation, capability/provider selection, execution planning, and action dispatch remain inspectable stages before broader real-device expansion
- 4.18.3. Define milestone M17.2: native Android Presence Edge baseline, so the first phone edge becomes a stable always-available-when-permitted participant with background connection, foreground diagnostics, low-risk mobile context observations, notification execution, and bounded real-device verification before richer phone sensing or execution becomes its own later milestone
- 4.18.4. Define milestone M17.3: Android Edge daily-use hardening, so the accepted phone-edge baseline becomes a more durable and comfortable daily mobile surface with persistent configuration, reconnect/background-health handling, Android permission and battery-policy guidance, status-first UX, notification history, and direct text-command input through the normal Edge API/runtime chain
- 4.18.5. Define milestone M17.4: Mobile Edge product UI implementation, so the accepted Android phone-edge capability baseline becomes the formal three-screen foreground product surface defined by the Mobile Edge UI spec: `Connect`, `Global Chat`, and `Settings`
- 4.18.6. Define milestone M17.5: Android screen/context observation baseline, so the accepted phone edge can use Android-local sensing such as `AccessibilityService` to collect, summarize, redact, and upload screen/use context evidence as normalized observations without performing runtime intent recognition or default raw screenshot streaming
- 4.18.7. Define milestone M17.6: multi-edge interaction lineage and fail-fast runtime semantics hardening, so active cross-edge interactions carry complete source/target/participant lineage into post-action proposal formation and runtime errors are surfaced explicitly instead of being hidden behind deterministic fallback, silent completion, or under-specified `no_intervention` outcomes
- 4.18.7.1. Define milestone M17.6.1: Agent Runtime harness engineering baseline, so real prompt/context packages used by active multi-edge interactions can become the first captured, replayable, outcome-classified harness corpus for measuring and improving model-backed proposal formation reliability before M17.6 acceptance
- 4.18.8. Define milestone M17.7: mobile observation liveness and wake recovery, so phone-driven observation remains near-real-time under normal active use through Android foreground-service background observation, runtime-side liveness monitoring, Android delivery-health reporting, and bounded FCM/OEM push wake or recovery paths instead of relying on the user manually reopening the app after background interruption
- 4.18.8.1. Define milestone M17.7.1: Android Edge continuous background observation steady state, so the phone edge can keep user-enabled `mobile.screen_context` observation and WebSocket/heartbeat delivery running while the app is backgrounded through a foreground service, low-distraction persistent notification, and battery/manufacturer background-permission guidance
- 4.18.8.2. Define milestone M17.7.2: Runtime mobile observation liveness watchdog and wake recovery, so the backend can classify phone observation freshness/degradation/unavailability, expose inspectable liveness state, and trigger bounded push/reconnect recovery when the Android edge stops delivering unexpectedly
- 4.18.9. Define milestone M17.8: mobile sensitive-screen capture governance, so Android screen/context observation moves from best-effort redaction to an allowlist-first privacy model where unknown apps default to health-only evidence, user-approved low-risk apps may produce rich screen context, and sensitive apps/pages are blocked before accessibility-node text extraction where platform metadata allows; it precedes broader M18 execution in the recorded route
- 4.19. Define milestone M18: Agent Harness-controlled observation understanding, so Edge-defined attention events and bounded observation context can be interpreted in the agent's current situation rather than by a permanent centralized trigger taxonomy; broader M18 follows M20.2, M20.3, and the M17.8 privacy boundary on M20's accepted Harness foundation
- 4.19.1. Define milestone M18.1: observation-to-snapshot decision-space integration, so the first intent-sensing step brings presence-relevant observations from core edge surfaces such as phone, desktop/terminal, host, and runtime health into compact snapshot fields before broader idle intent recognition runs on top
- 4.20. Define milestone M19: bounded-growth and storage-hygiene hardening after both the M20 Harness foundation and broader M18 observation understanding are accepted, covering unbounded state growth, high-frequency persistence pressure, duplicated long-term storage, and other operational accumulation risks before product packaging work builds on the resulting runtime histories; M19 is paused with M18
- 4.21. Define milestone M20: Agent Harness and runtime action-loop architecture refactor with unified action/tool governance, so the already-running OpenHalo system replaces its real-use agent-execution implementation with a Hermes-backed harness core behind an OpenHalo adapter, while preserving the nested internal agent loop, external runtime action loop, Hermes-native persistent memory, LLMOps/eval gate, and one inspectable runtime contract for model-native tool calls, MCP/tool/skill calls, runtime-local tools, and external device actions. The multi-action regression reopened its prior configured-provider acceptance; the remediation now has governed `ActionBatch` dispatch, result-set continuation in the same scoped child session, and renewed configured-provider Terminal/Android human acceptance, so M20 is accepted.
- 4.21.1. Define milestone M20.1: governed procedural-memory and skill lifecycle, after broader M18 and M19 have stabilized observation and retention pressure, so Hermes can distill proven workflows into OpenHalo-owned skill drafts without enabling Hermes' generic skill/plugin execution surface; drafts must have provenance, bounded declarative scope, inspection, static validation, and an explicit activation path before they can affect a live harness turn
- 4.21.2. Define milestone M20.2: OpenHalo interaction-progress presentation, as the next execution milestone after M20, so an active user-visible interaction can expose a Runtime-owned, Edge-rendered progress lifecycle and polished native animation rather than leaking Hermes' terminal display. It will translate safe lifecycle states such as deliberating, researching, planning, executing, awaiting an action result, completing, and failing into OpenHalo events while withholding chain-of-thought, provider details, raw tool content, and Hermes branding; detailed visual language remains an M20.2 design decision.
- 4.21.3. Define milestone M20.3: Terminal Edge stable CLI/TUI, immediately after M20.2, so the resident desktop terminal becomes a durable, ergonomic OpenHalo interaction surface rather than a minimal verifier. It owns an application-quality terminal layout, transcript, composer, interaction/progress rendering, session and connection lifecycle, and non-TTY fallback while continuing to use the normal public Edge API; it is not a thin wrapper around Hermes CLI or a local shell/tool console. M20.3 consumes M20.2 progress events when available, but its core stability and layout work can proceed independently.
- 4.22. Define milestone M21: policy learning and review loop after the harness/action-loop refactor, so intervention feedback, ignored interactions, explicit user responses, and runtime replays can produce model-backed, review-gated policy updates on top of stable trace, replay, action/result, and memory semantics rather than the pre-refactor runtime shape
- 4.23. Define milestone M22: first packaged three-end product slice near the end of the current roadmap, so OpenHalo can be installed and tried as a coherent phone edge, desktop edge, and runtime/host-edge system after the core runtime shape has been stabilized enough for packaging to avoid freezing transitional internals
- 4.24. Define milestone M23: Home Assistant Bridge Edge and smart-home ecosystem bridge baseline as the final currently tracked milestone, so Home Assistant-managed smart-home devices can eventually be discovered through the Home Assistant API, translated into OpenHalo downstream devices, capabilities, and observations, synchronized as context evidence, and controlled through OpenHalo-governed actions without requiring Home Assistant devices to speak the OpenHalo Edge API directly

Milestone ownership clarification:

- The structural home for richer proposal formation from edge-delivered signals belongs primarily to the `M6` `Agent Runtime` proposal-formation surface; the current runtime taxonomy is intentionally small, with `action` for visible/side-effectful outcomes and `no_intervention` for silent closure or suppression.
- The accepted `M6` implementation should not be read as full semantic completion of proposal formation; before model integration it establishes the correct live-chain location and a narrow deterministic slice, but not yet sufficiently capable open-ended intent interpretation.
- `M13` is now the explicit maturity milestone for this surface: it owns turning that narrow slice into a reliable multi-type proposal-formation capability on the live chain.
- Adjacent milestones deepen that behavior from other angles without changing the ownership boundary: `M9` supplies provider-backed generation, `M10` supplies runtime grounding and memory, `M12` supplies prompt/context and behavior-contract hardening, `M14` supplies model-provider reliability and diagnostics, `M15` deepens operator trust through runtime-native credentials, `M16` supplies post-action deliberation and same-interaction action-loop re-entry, `M17.0` closes the public Edge API boundary, `M17.1` adds registration-driven capability/observation extension plus explicit capability/provider resolution before broad real-edge expansion, `M17.2` establishes the first native Android Presence Edge baseline, `M17.3` hardens that Android edge into a more durable daily-use mobile surface without turning it into a backend shortcut or chat-centered side channel, `M17.4` turns the phone edge foreground into the formal product UI defined by the Mobile Edge UI spec, `M17.5` adds Android screen/use-context observation extraction on the phone edge while still treating it as passive evidence, `M17.6` hardens active multi-edge interaction semantics so post-action deliberation sees complete lineage and runtime failures are exposed rather than silently papered over, `M17.6.1` starts Agent Runtime harness engineering from the concrete proposal-formation reliability failures exposed by M17.6, `M17.7.1` adds the Android foreground-service steady state for continuous background observation, `M17.7.2` adds runtime-managed mobile observation liveness and wake recovery so phone observation does not depend on manual app reopening after background interruption, `M17.8` hardens mobile sensitive-screen governance with allowlist-first rich capture and pre-extraction blocking where possible, broader `M17` expands real multi-edge interaction surface area, `M18.1` first brings core edge observations into the compact snapshot decision space, accepted `M20` supplies the Hermes-backed Agent Harness and runtime action loop with unified action/tool governance, curated read-only research, and Hermes-native durable memory, deferred `M20.2` owns the user-facing progress lifecycle and Edge-native presentation of active interactions, and deferred `M20.3` owns the stable application-quality Terminal Edge that renders those interactions without becoming a Hermes CLI wrapper. Broader `M18` now resumes on the M20 foundation, and paused `M19` hardens bounded growth and storage hygiene only after broader M18 is accepted. `M21` then adds model-backed review-gated policy learning after the harness gives feedback interpretation stable trace/replay/action semantics, `M22` packages the first coherent three-end product slice across phone edge, desktop edge, and runtime/host-edge deployment near the end of the current roadmap, and `M23` is intentionally deferred as the final currently tracked ecosystem bridge milestone for Home Assistant and similar smart-home platforms after the core runtime and product shape are more mature. The current M15 implementation begins with a narrow single-file local runtime-config baseline rather than an environment-variable fallback.

Acceptance criteria for M13 proposal-formation maturity:

- The normal live chain can emit inspectable `action` and `no_intervention` proposals from edge-delivered signals without bypassing `Presence Router`
- Proposal formation consumes compact snapshot state, active goals, bounded memory, and relevant edge evidence on the actual runtime path rather than falling back to raw text-only heuristics
- Proposal records expose enough structured rationale to inspect why a given input became a visible/side-effectful action or a no-intervention decision
- The accepted live-chain implementation does not grow redundant middle layers beyond the documented `event -> compact snapshot -> grounding bundle -> prompt/context package -> proposal formation -> Presence Router -> execution planning/action` shape; inspection sidecars may exist, but they must remain secondary to the main runtime path
- Narrow deterministic fallbacks remain available when the model is unavailable, but the primary accepted path for open-ended intent interpretation is model-backed and grounded
- Automated tests cover visible user-facing actions, runtime-control actions, failure-path handling, and no-intervention suppression/closure
- Human acceptance demonstrates the feature in simulated real usage: a tester can drive representative terminal/device interactions through the live runtime and observe action and no-intervention outcomes with readable inspection output

Acceptance criteria for M14 model-provider connection reliability and diagnostics:

- The runtime has a bounded provider-probe entrypoint that can verify the configured profile, provider, model, endpoint, auth-env presence, HTTP result, latency, and top-level response shape without exposing secrets
- The `openai_compatible` adapter respects configured wire API shape rather than hard-coding one endpoint path, and can distinguish supported `responses` behavior from incompatible response envelopes
- Provider failures are classified into at least connection/auth/rate-limit/timeout, HTTP server/client, protocol-shape mismatch, and parser/structured-output errors so operators can tell whether the problem is network, credentials, route configuration, or model output
- Retry and timeout behavior is bounded and type-aware: transient network, timeout, rate-limit, or 5xx failures may retry with backoff, while missing credentials and protocol/parser mismatches fail fast with clear metadata
- Runtime model health is observable through stored metadata or status surfaces, including last success, last failure type/reason, model unavailable state, and recent latency where available
- User-facing fallback behavior stays explicit: foreground terminal interactions may surface real provider failures, while deterministic fallback remains available for tests and deliberate offline verification without pretending the model succeeded
- Automated tests cover provider probing, wire API selection, failure classification, bounded retry behavior, and visible versus deterministic fallback policy
- Human acceptance demonstrates a real configured provider path and at least one controlled failure path with readable terminal/runtime diagnostics

Acceptance criteria for M15 runtime-native credential and runtime-config baseline:

- Runtime model-provider execution reads provider route, model/profile selection, and provider API key from one OpenHalo-owned local runtime config
- The local `config/runtime-config.toml` file is ignored by git, while `config/runtime-config.example.toml` documents the expected shape
- The auth resolution path is inspectable through provider probe metadata such as auth source, reference, and presence without exposing secret values
- Missing credentials are classified as auth failures with provider-scoped diagnostic messages rather than leaking or depending on shell-only assumptions
- The first runtime config format is documented and intentionally bounded to local file-based API-key credentials, with encryption, OS keychain integration, token refresh, and login UI deferred to later hardening
- Automated tests cover direct config credentials, missing credentials, provider request execution, and probe metadata redaction

Acceptance criteria for M16 post-action deliberation and interaction action loop:

- The same interaction lifecycle can re-enter `Agent Runtime` after an `action_result` or other relevant new observation instead of terminating at a fixed completion formatter
- Post-action deliberation can emit inspectable runtime-owned proposal outcomes grounded in the prior interaction state, current compact snapshot, active goals, bounded memory, and the new result/evidence; after M17.6 hardening, normal outcomes are `action` and `no_intervention`
- Any user-visible follow-up or next-step action produced by that re-entry still passes through `Presence Router` rather than bypassing governance because it is "post-action"
- The accepted implementation may still keep one current `primary action` per deliberation turn, but one interaction may span more than one deliberation turn with traceable lineage between turns
- Automated tests cover at least one result-driven user-visible action case, one follow-up action case, and one silent-completion case on the normal live chain
- Human acceptance demonstrates a realistic terminal/device scenario where a remote action result causes either a natural-language follow-up or another planned action through the normal runtime path

Acceptance criteria for M17.0 public Edge API boundary:

- A written external Edge API contract defines device registration, authentication shape, capability announcement, event and observation push, action request delivery, action result return, interaction update delivery, error frames, versioning, and compatibility expectations
- `Personal Runtime` backend internals are treated as closed implementation details for edge authors; external edges must not import or depend on `personal_runtime` internal modules, state objects, agent/presence implementation details, or repository-private helper contracts
- The current terminal edge and host edge interact with the runtime only through the public Edge API contract or an explicitly documented official SDK/client wrapper over that contract, not through backend-internal shortcuts
- The official Python edge client, if retained, is documented and tested as a convenience SDK over the public API rather than as the only valid integration path
- Automated tests include at least one external-edge simulation that connects through the public API without importing backend internals, announces capabilities, pushes observations or user events, receives an action request, returns an action result, and preserves interaction lineage
- Existing runtime, terminal-edge, host-edge, model-provider, prompt-contract, proposal-formation, and action-loop test suites pass after the API boundary refactor
- Human acceptance demonstrates that a new edge can be added by following the documented API contract rather than modifying runtime internals or copying a built-in edge implementation

Acceptance criteria for M17.1 registration-driven multi-device extension:

- The public Edge API supports rich action-capability registration metadata, including at minimum capability name, direction, kind, affordances, modality, content capacity, privacy class, interruptiveness, side-effect class, required permissions or trust tier, and bounded input/result schema
- The public Edge API supports explicit observation registration metadata, including at minimum observation name, provider capability, schema, semantics tags, privacy class, freshness or confidence contract, and whether the observation is allowed to feed only evidence, planner scoring, or trusted compact-snapshot / presence inputs
- `RuntimeState` persists a `Device Registry`, `Capability Registry`, and `Observation Registry` rather than only device IDs and capability names, while preserving compatibility for existing terminal and host edge capability announcements during the migration
- Gateway enforces public API registration and schema validity at ingress: unregistered observations, schema-mismatched observations, undeclared action-result capabilities, direction mismatches, and device/capability mismatches are rejected with inspectable public errors instead of being silently stored or used
- New devices can add capabilities and observations through registration without adding device-type-specific runtime branches, as long as they fit existing runtime semantic dimensions and pass schema, trust, permission, privacy, and side-effect validation
- The normal live chain keeps an explicit `Execution Planning` stage after `Presence Router` and before `Action Layer`; any capability resolver is an internal planning sub-step, not a replacement for execution planning
- Capability/provider selection happens inside the existing `Execution Planning` module, consumes proposal requirements, presence governance boundaries, registered capability/provider metadata, validated observations or snapshot fields, and device availability, and produces an inspectable candidate list
- Capability selection is not implemented as a fixed `intent -> capability` table; hard rules are limited to safety, schema, permission, privacy, availability, side-effect, interruptiveness, content-capacity, direction, and trust constraints, while scoring or later model-assisted reranking may choose among valid candidates
- Proposal formation may still emit a legacy action/capability hint during the migration, but accepted execution planning treats that hint as advisory and validates it against registries, resolver rules, and the presence decision before dispatch
- Execution plans record the chosen primary action, bounded fallback candidates where supported, filtered candidates with reasons, planning rationale, and lineage back to the proposal, presence decision, interaction, registry entries, and relevant observation evidence
- Execution planning and capability resolver boundaries emit `diagnostic.v1` input/output/error events under the existing module-boundary diagnostics format
- Action Layer receives an execution plan or finalized action envelope and remains responsible for dispatch framing and result recording, not semantic capability selection
- Automated tests cover rich capability registration, observation registration, strict rejection of unregistered observations, schema mismatch rejection, legacy compatibility for existing terminal/host registrations, requirement-based candidate resolution, privacy or public-audio suppression, content-capacity rejection such as ambient lights for private text, fallback candidate recording, and preservation of interaction lineage through action results
- Human acceptance demonstrates a multi-surface scenario where a newly registered edge capability and observation contract become available to planning through the public API, and the runtime explains why one available edge capability was chosen over another without introducing device-type-specific runtime branches

Acceptance criteria for M17 multi-edge interaction expansion:

- At least one additional device-edge surface beyond the current terminal/host baseline can connect through the normal `Edge Session Link <-> Gateway` boundary with explicit device identity, capabilities, and observation/action contracts
- The runtime can reason about more than one user-facing or context-bearing edge in the same presence-governed interaction model without introducing a new chat-centered side channel
- Presence decisions can choose, suppress, or redirect between candidate edge surfaces using device availability, activity, capability, and privacy/context evidence rather than only same-device fallback rules
- Interaction and intervention records preserve participant devices, target devices, routed capability, and lineage across multi-edge handoff or follow-up action paths
- Automated tests cover cross-edge proposal routing, unavailable-edge suppression or fallback, multi-edge observation context entering proposal formation, and preservation of interaction lineage across devices
- Human acceptance demonstrates a realistic multi-edge scenario where one edge provides intent or context, another edge is chosen or suppressed as the intervention surface, and the resulting action/update remains inspectable in the normal runtime chain

Acceptance criteria for M17.2 native Android Presence Edge baseline:

- The native Android app can act as a first-class `Device Edge` over the public Edge API with stable device identity, capability registration, WebSocket connection lifecycle, reconnect diagnostics, and no backend-internal imports or phone-specific runtime shortcuts
- The Android edge provides a foreground diagnostics surface that exposes connection state, runtime URL, device ID, last sent/received public Edge API frames, recent observations, recent action requests, and action results
- The Android edge can run as a constrained phone presence surface: background availability is attempted where Android policy allows, foreground/manual operation remains supported, and any background restriction or permission limitation is represented as context evidence rather than assumed away
- The accepted initial capability surface remains intentionally low-risk: `mobile.context` observations plus `notification.show` execution, with camera, microphone, continuous screen-use interpretation, location, and richer local command surfaces recorded as later mobile Sensor/Action Edge direction rather than M17.2 blockers
- The runtime can choose the Android edge as an intervention surface for a notification action while other candidate surfaces are present, and interaction lineage preserves the source edge, Android target edge, action result, and participant devices
- Automated verification includes runtime-side simulated routing/lineage coverage and an adb-based real-device smoke verifier for Android app connection and observation behavior
- Human acceptance demonstrates the full live chain from a non-phone source edge through the runtime to the Android phone edge, with inspectable action result and lineage evidence

Acceptance criteria for M17.3 Android Edge daily-use hardening:

- The Android edge persists normal user configuration across app/process restarts, including runtime mode, runtime URL, device identity, and token configured state, without exposing secrets in tracked source, UI diagnostics, logcat, or public Edge API frame displays
- The Android edge can be started and stopped from a status-first daily home screen, and it can restore or resume its foreground-service Edge API session after ordinary app restarts without requiring the user to re-enter configuration or use Android Studio
- WebSocket lifecycle handling includes bounded automatic reconnect with backoff, visible connection health, last successful connection time, last disconnect/error reason, and enough diagnostics to distinguish runtime/network/auth failures from Android lifecycle restrictions
- Android-specific operating constraints are surfaced as first-class health evidence: notification permission, full-screen alert capability, foreground-service state, battery optimization/background restriction risk, and any required user setting should be visible with direct system-settings affordances where Android permits them
- The first screen is a daily-use mobile surface rather than a diagnostics wall: it shows simple connected/disconnected/restricted/needs-setup state, one clear start/stop control, recent phone-edge/runtime activity, recent notification history, and a path into detailed diagnostics as a secondary view
- Runtime-delivered phone notifications remain effective alerts on Android: `notification.show` continues to use the urgent alert presenter by default, notification history/detail views preserve recently delivered content, and tapping an alert opens the relevant message/detail state rather than only a generic diagnostics screen
- The Android edge exposes a direct text-command input box for explicit user instructions from the phone, modeled as phone-originated edge input through the public Edge API and normal `Gateway -> Agent Runtime -> Presence Router -> Action Layer` chain rather than as a local-only command handler or chat-specific backend shortcut
- Local persistence covers enough recent edge state to survive process recreation gracefully, including recent notifications/events and the latest diagnostics snapshot, while keeping high-volume logs bounded
- Automated verification covers persisted configuration restore, reconnect/backoff behavior where feasible, UI state for connected/restricted/needs-setup conditions, direct text-command frame emission, and notification history/detail behavior
- Human acceptance demonstrates a realistic daily-use phone scenario: open the app, see health at a glance, start or resume the edge, send a text command from the phone, receive a runtime response or routed action through the normal chain, inspect recent notification/activity history, and recover from at least one disconnect or app restart without manual reconfiguration

Acceptance criteria for M17.4 Mobile Edge product UI implementation:

- The Android phone edge foreground UI implements the three primary tabs defined in `docs/design/mobile-edge-ui/mobile-edge-ui-spec.md`: `Connect`, `Global Chat`, and `Settings`
- The Connect page is the launch/default product surface and uses one large stateful connection control as the main visual and interaction element
- The Connect page renders the accepted connection states, including `needs_setup`, `disconnected`, `connecting`, `connected`, `reconnecting`, `restricted`, and `error`, with only one relevant primary action visible for the active state
- The Global Chat page is implemented as a global conversation projection across terminal, phone, desktop, and future edges rather than a phone-local chat session or backend shortcut
- Phone-originated messages on the Global Chat page continue to enter the runtime through the public Edge API and normal `Gateway -> Agent Runtime -> Presence Router -> Action Layer` path
- Until a durable runtime conversation-projection API exists, the Global Chat page may use a bounded local projection model, but it must keep source labels, delivery state, and interaction lineage fields compatible with later cross-edge synchronization
- The Settings page exposes normal user-facing configuration such as runtime URL, device name, notification/permission state, local network permission, reset connection, and clear local cache
- Developer-only diagnostics, raw WebSocket frames, model provider config, runtime profiles, test fixtures, and protocol traces are hidden from the normal product foreground and remain secondary diagnostics if still needed for engineering
- Compose UI tests cover primary navigation, connection-state rendering, the connection action, chat composer send state, and the main settings rows through stable semantics or test tags
- Visual QA compares the implementation against the preserved Pixso/PDF assets, checks Chinese text fitting, and verifies the UI on at least one small phone viewport and one modern large Android viewport

Acceptance criteria for M17.5 Android screen/context observation baseline:

- The Android edge exposes an explicit user-controlled screen-context observation mode based on Android-local sensing, with `AccessibilityService` as the preferred default path
- The phone edge can produce normalized `mobile.screen_context` observations from accessibility events and node-tree snapshots without requiring raw screenshot upload by default
- The design distinguishes OpenHalo app visibility from capture availability: the app Activity may be backgrounded while the foreground service and user-approved `AccessibilityService` still allow event-triggered observation of the current foreground app
- The Android screen/context observer is expected to support near-real-time foreground-use observation while permitted and while the phone is awake/unlocked; local-only buffering is a degradation path for transient delivery failure, not the accepted steady-state behavior for M18-ready mobile observation
- Locked or screen-off states pause rich screen-context extraction and produce only availability/capture-health evidence where useful
- Accessibility callbacks remain lightweight: capture, OCR, redaction, summarization, and upload run asynchronously behind bounded queues with coalescing, throttling, and stale-capture dropping so dense foreground user activity cannot block the phone edge
- Observations describe evidence only, including trigger metadata, interaction state, coarse screen kind, bounded visible text summary, UI affordances, indexed interactive elements, sensitivity flags, confidence, and provenance; they must not include runtime intent decisions such as `user_need`, `intent`, or `should_intervene`
- Event-triggered upload is primary and must be engineered as the normal low-latency path for active foreground use: UI events are debounced/coalesced, typing is not uploaded per character, unchanged screens avoid repeated full payloads, and screen-off/locked states pause rich extraction by default
- M17.5 may expose local delivery-health evidence and normal reconnect behavior, but dedicated background liveness monitoring, FCM/OEM push wake, and runtime-managed recovery are owned by M17.7 rather than being required for the first screen/context extraction baseline
- M17.5 includes only best-effort local redaction/blocking for obvious password-like fields and must not upload raw screenshots by default; comprehensive sensitive app/page governance, including unknown-app default-deny rich capture, app allowlists, and banking/payment/login pre-extraction blocking, is owned by M17.8 rather than blocking the first observation transport baseline
- Optional screenshot/OCR support, if added, is a local fallback for poor accessibility-node coverage and must record whether raw screenshots were uploaded; raw screenshots are disabled by default and require explicit user approval
- Runtime ingestion treats `mobile.screen_context` as passive context evidence for later snapshot/grounding, not as a direct command; however, fresh phone screen/context observations are expected to be one of the primary evidence sources consumed by M18 observation-driven intent sensing
- Automated tests cover accessibility node-tree extraction, interactive element indexing, redaction, bounded payload size, event debounce/coalescing, queue backpressure, stale-capture dropping, and runtime passive handling or rejection of malformed screen-context observations
- Human acceptance demonstrates that a real phone can enable the feature, interact with several normal apps, and produce useful bounded screen-context observations without raw screenshot upload or runtime intervention, including a foreground-app usage period where observations arrive at the runtime in near real time rather than only after the user reopens the OpenHalo app

Acceptance criteria for M17.6 multi-edge interaction lineage and fail-fast runtime semantics hardening:

- Post-action and post-observation proposal formation receive the complete active interaction lineage needed for cross-edge semantics, including `source_device_id`, `participant_device_ids`, previous intervention target device, current `primary_action.target_device_id`, prior proposal/action metadata, and the new action result or observation evidence
- Cross-edge commands preserve two semantic surfaces when needed: the target edge performs the requested action, while the source edge receives a visible acknowledgement, result summary, or failure explanation unless policy explicitly suppresses it with an inspectable reason
- Deterministic fallback is no longer allowed to silently convert provider, parser, protocol, lineage, or routing failures into successful-looking behavior on real runtime paths; provider and runtime failures must surface as user-visible errors, diagnostic errors, or failed interaction updates according to the path's contract
- `no_intervention` and `silent` completions require auditable preconditions proving that the user-facing obligation has already been satisfied or intentionally suppressed; in particular, `notification.show -> ok` may only silently complete when the delivered visible surface is semantically the source-facing completion surface
- Action-result re-entry with unknown interaction lineage, missing prior intervention, missing target connection, or inconsistent source/target capability evidence produces explicit diagnostic and/or public error evidence rather than returning an empty reply list with no visible failure signal
- Context viewer and chain-inspection surfaces distinguish model-backed, user-visible-error, deterministic-test-only, silent-completion, target-missing, stale-context, and lineage-missing outcomes clearly enough that operator review can locate the failing module without inferring from absence of output
- Automated tests cover terminal-to-phone command acknowledgement, same-device notification silent completion, missing interaction action-result failure, provider failure fail-fast behavior, target-missing cross-edge action failure reporting, and inspection output for each class of surfaced error
- Human acceptance demonstrates that a terminal-originated command such as "send hello to my phone" both delivers the phone action and returns an acknowledgement or failure explanation to the terminal through the normal `Gateway -> Agent Runtime -> Presence Router -> Action Layer` chain

Acceptance criteria for M17.6.1 Agent Runtime harness engineering baseline:

- The runtime can preserve and replay real Agent Runtime proposal-formation prompt/context packages from active multi-edge interactions, including initial `text.input` proposal formation and post-action/post-observation re-entry, without exposing provider secrets
- Proposal-formation outcomes are classified separately for provider/protocol failures, parser/shape failures, validation failures, semantically incomplete proposals, incorrect target/source-surface proposals, and correct proposals
- A bounded replay or harness workflow can measure proposal-formation success rate over captured M17.6 scenarios and compare prompt/context/provider changes against the same corpus, establishing the first reusable harness-engineering pattern for later Agent Runtime behavior work
- The investigation identifies which prompt/context ingredients correlate with low success, such as oversized grounding memory, previous provider-failure action results, ambiguous source/target obligations, language mismatch, structured-output request format, or provider route instability
- Any proposed improvement keeps the architecture boundary intact: model-backed proposal formation remains responsible for deciding continue/complete, but prompt contracts, validation, repair, provider retry, and failure containment may be strengthened around it
- Automated tests or replay checks cover at least the observed failure classes from M17.6 manual acceptance: missing terminal source acknowledgement after successful phone action, exhausted `codex_agent_envelope_empty_output` retries, and provider error content being routed as a normal notification action
- Human acceptance for returning to M17.6 is gated on a measured improvement in proposal-formation reliability on the captured terminal-to-phone corpus, not only on one lucky live run

Acceptance criteria for M17.7 mobile observation liveness and wake recovery:

- M17.7 is split into `M17.7.1` Android Edge continuous background observation steady state and `M17.7.2` Runtime mobile observation liveness watchdog and wake recovery, because the first half is primarily phone-edge execution durability while the second half is backend state classification and recovery governance

Acceptance criteria for M17.7.1 Android Edge continuous background observation steady state:

- M17.7 treats user-enabled continuous background observation as the intended steady-state experience for the phone edge: when the user backgrounds the app without manually stopping, swiping away, force-stopping, revoking permissions, or disabling required background allowances, the Android edge should keep observation delivery alive rather than relying on later recovery as the normal path
- The accepted Android implementation path for continuous background observation is a foreground service with a low-distraction persistent notification, WebSocket/heartbeat delivery, and explicit in-app guidance for battery-optimization exemption plus manufacturer-specific autostart/background-running permissions where needed; fully hidden indefinite background execution is not a supported OpenHalo architecture promise
- FCM/OEM push wake and reconnect are recovery mechanisms for degraded, suspended, or killed delivery states, not the primary steady-state substitute for a user-enabled background monitoring session
- The Android edge reports lifecycle and delivery-risk evidence where the platform allows it, including graceful stop, connection teardown, permission loss, battery restriction changes, foreground-service health, accessibility-service health, last local observation time, last successful upload time, and local queue/backpressure state
- Automated tests cover foreground-service lifecycle, notification state, heartbeat/upload continuation while backgrounded, permission/battery-guidance state, lifecycle and delivery-health reporting, and local queue/backpressure behavior
- Human acceptance demonstrates a real phone observation session where foreground-app observations continue to arrive near real time after the OpenHalo app is backgrounded, without requiring the user to reopen the app, while the persistent notification and required Android permissions remain visible and inspectable

Acceptance criteria for M17.7.2 Runtime mobile observation liveness watchdog and wake recovery:

- Background delivery survival is treated as a first-class mobile observation problem rather than a documentation caveat: the phone edge and runtime together distinguish real-time observation, temporarily degraded delivery, wake-requested recovery, stale evidence, and unavailable mobile observation states
- The runtime maintains a mobile observation liveness watchdog over registered phone edges, using heartbeats, observation freshness, last successful upload, expected active-observation state, gateway/server health, and known network failures to classify unexpected `mobile.screen_context` silence
- If a phone edge that recently reported active observation stops delivering evidence unexpectedly and server-side/network-wide causes are not the likely explanation, the runtime can trigger a bounded mobile wake/recovery path such as FCM or OEM push when configured
- Wake/recovery attempts are rate-limited, TTL-bound, auditable, and privacy-preserving: push payloads do not contain raw screen context, sensitive summaries, or user-visible intent decisions, and repeated failures move the phone into a degraded or unavailable liveness state rather than looping indefinitely
- When the phone edge wakes or reconnects, it reports recovery provenance, current observation availability, and fresh health evidence before or alongside any buffered observations, so the runtime can distinguish newly fresh context from stale replay
- Runtime state and inspection surfaces expose mobile liveness fields such as `fresh`, `degraded`, `wake_requested`, `stale`, and `unavailable`, with timestamps and last recovery attempt metadata suitable for M18 snapshot consumption
- Automated tests cover liveness timeout classification, no-wake behavior during server/network failures, bounded FCM/OEM wake request emission, recovery after reconnect, stale buffered observation handling, push rate limiting, and inspection output for each liveness state
- Human acceptance demonstrates a real phone observation session where the phone edge is interrupted or background-restricted, the runtime detects the gap, triggers the configured wake/recovery path, and either restores fresh observation delivery or marks the phone observation surface degraded/unavailable with inspectable evidence

Acceptance criteria for M17.8 mobile sensitive-screen capture governance:

- Rich `mobile.screen_context` capture uses an allowlist-first privacy model: unknown foreground apps default to health-only evidence until the user explicitly allows rich capture for that app or app category on the phone
- Sensitive contexts are blocked before accessibility-node text extraction where platform metadata allows it, using sources such as package/class metadata, system/window security signals where available, focused password fields, input/auth/payment surface hints, and user-configured denylist entries
- Known sensitive app/page categories such as banking, payment, wallet, password managers, login/authentication, verification-code entry, government/insurance/medical finance, and private account-management screens never upload visible text summaries or interactive-element labels by default
- Content-level detection remains only a second safety net after extraction, not the primary privacy boundary; any content-triggered block must emit health-only or redacted evidence and must not persist sensitive text in diagnostics or local history
- The Android settings surface lets the user inspect and control which apps or app categories are allowed to produce rich screen context, with a clear reset path and conservative defaults for new devices
- Runtime/context-viewer inspection surfaces make sensitive-governance outcomes visible without exposing sensitive text, including `allowed_rich_capture`, `health_only_unknown_app`, `blocked_sensitive_app`, `blocked_sensitive_page`, and relevant provenance such as user allowlist versus built-in policy
- Automated tests cover unknown-app default health-only behavior, user-allowed rich capture, denylisted app blocking, password/input/auth blocking, content-level fallback blocking without persisted text, and observation frames that prove no raw screenshots or sensitive labels are uploaded
- Human acceptance demonstrates a new phone or newly installed banking/payment app where rich capture is blocked by default without knowing the package name in advance, while a user-allowed low-risk app can still produce bounded screen-context observations

Acceptance criteria for M22 first packaged three-end product slice:

- The runtime/host-edge server package supports Linux installation with one primary install command or script, producing a supervised `Personal Runtime` service plus a co-installed host edge that connects through the normal public Edge API boundary
- The Linux installer documents and verifies the standard public-server deployment scene, including runtime endpoint, host-edge pairing, provider runtime config, service start/stop/status, logs, and uninstall or cleanup expectations
- The Windows desktop edge is deliverable as a normal installer package for end users rather than only as a Python development command, and it can connect to a configured runtime endpoint after installation
- The Windows desktop package may include `Personal Runtime + host edge` components for the computer-server deployment scene, but those local runtime components are disabled by default and can be explicitly enabled by the user
- The Android phone edge is deliverable as an APK that can be installed on a real phone outside Android Studio, preserving persistent runtime endpoint/device configuration and the accepted M17.3 daily-use surface
- Product UI packaging covers first-run setup, connection/health state, runtime endpoint pairing, recent activity, and diagnostics escape hatches on phone and desktop without turning either edge into a backend shortcut
- Both accepted deployment scenes are documented and manually verified: standard public-server deployment with server runtime/host edge plus separate computer and phone edges, and computer-server deployment with runtime/host edge/desktop edge on one computer plus phone edge connected to that computer-hosted runtime
- Packaged-mode verification includes smoke tests for service startup, endpoint connectivity, capability registration, terminal or desktop-originated input, phone notification delivery, host runtime-status action, and clean restart behavior
- The milestone explicitly does not require app-store distribution, auto-update, polished account login, encrypted local secret storage, or broad OS/ROM compatibility matrices; those remain later product hardening

Acceptance criteria for M18 observation-driven intent sensing:

- M18.1 is accepted first as the observation-to-snapshot decision-space integration slice: presence-relevant observations from core product edges are mapped into explicit compact snapshot fields with freshness/evidence contracts before idle intent sensing attempts to infer proactive needs
- The M18.1 core edge field set includes, at minimum, mobile app visibility, mobile notification permission, mobile connection/liveness state, terminal or desktop activity state, host health/resource signals, and runtime health/process signals where the corresponding observations are available
- M18.1 preserves the existing rule that raw observations remain passive evidence by default; adding a snapshot field makes the evidence visible to Agent Runtime and `Presence Router`, but does not by itself turn the evidence into a command or proactive intervention
- M18.1 context-viewer and chain-inspection output show which normalized observations contributed to the new snapshot fields, including fresh/stale/missing status and bounded evidence, so operators can verify that phone and desktop observations are no longer only stored in logs
- When an observation-driven trigger passes the M18 salience/relevance gate, the runtime can build a current observation/context picture across connected or actively reporting edge devices and register an ordinary interaction in the shared Interaction Pool to evaluate whether the combined evidence suggests a user need, environmental change, or runtime condition worth proposing on; unrelated active interactions or in-flight actions must not globally block this work
- M18 depends on at least one real active observation surface being able to deliver fresh evidence during normal use; for the Android path, delayed batch upload from a manually reopened app is insufficient as the primary acceptance path for phone-driven intent sensing
- M18 should consume explicit mobile observation liveness state, including fresh, degraded, wake-requested, stale, and unavailable, so proposal formation and `Presence Router` can tell the difference between "no relevant user need observed" and "the primary mobile observation surface is currently blind"
- Observation-driven intent sensing consumes normalized observations, compact snapshot fields, freshness/ambiguity contracts, active goals, and bounded recent memory rather than treating raw device events as direct user commands
- Observation-driven intent sensing distinguishes passive evidence from actionable intent, including support for approved user-configured triggers where an otherwise passive signal has an explicit agreed meaning
- The sensing stage has an explicit salience/relevance gate so weak passive observations are recorded as context only, while high-salience or goal-relevant observation patterns may trigger model-backed proposal formation
- Beyond non-negotiable boundary safeguards, M18 relevance is agent-adjustable rather than a permanent hand-authored trigger taxonomy: the Agent Harness may use its current bounded memory, uncertainty, active interactions, and situation understanding to change which safe normalized observations merit deeper deliberation or additional bounded evidence. It must record the resulting rationale and still let `Presence Router` decide whether any user-facing interaction occurs.
- Any proposal produced from idle observation sensing still uses the normal proposal taxonomy (`action` or `no_intervention`, with `provider_failure` reserved for internal model/provider failure handling) and must pass through `Presence Router` before surfacing to a user or dispatching an action
- M18 has no privileged candidate-interaction lifecycle: after its gate admits an observation-driven trigger, it registers a normal Interaction Pool record with observation provenance and follows the same proposal, presence, action, action-result, and completion chain as any other interaction; action requests and results carry the relevant interaction and turn/action correlation so results re-enter their source interaction
- The design distinguishes idle/standby observation sensing from M16 only at the trigger boundary: M16 routes evidence causally linked to an existing interaction back into that interaction, while M18 admits broader observation context as a new ordinary interaction when its causal scope is not already active
- Interaction-pool concurrency is scope-aware: exact duplicate causal evidence may coalesce, but simultaneous observations with distinct trigger reasons remain separate interactions and may enter bounded parallel deliberation; user-facing delivery conflicts are resolved later by `Presence Router`, not by globally suppressing interaction registration
- Automated tests cover no-op passive observation batches, high-salience observation-triggered proposal formation, presence suppression of an inappropriate proactive intervention, and multi-edge observation context being included in the prompt/context package
- A deterministic Runtime integration test simulates `runtime.health_state=degraded` observation admission, an active notification surface, an allowed observation-driven notification action, its exact correlated `action_result`, and completion of the originating Interaction Pool record without calling a real model
- Offline replay acceptance runs only the deterministic M18 trigger gate and ordinary Interaction Pool registration path against representative persisted runtime state/event histories in chronological order, without contacting a provider or dispatching real actions. The report must make each admitted, deferred, and skipped candidate inspectable with safe evidence references, causal scope, and interaction-registration outcome; proposal, Presence, and action outcomes remain live-chain or in-process acceptance evidence rather than replay output.
- Human acceptance demonstrates a realistic multi-edge scenario where the runtime is idle, observes a meaningful cross-device context change, forms an inspectable proposal, and either intervenes or suppresses itself through `Presence Router`

Acceptance criteria for M19 bounded-growth and storage-hygiene hardening:

- Runtime state, intervention history, observation history, action results, diagnostics, replay artifacts, and model/provider health records have explicit retention, compaction, or archival policies rather than unbounded default growth
- High-frequency observation and liveness paths have bounded persistence behavior, including rate-aware writes, deduplication or coalescing where appropriate, and preservation of enough recent evidence for M18/M20 reasoning without storing every transient detail indefinitely
- Long-running runtime state can be inspected for storage pressure, record counts, recent write volume, and old-data eligibility so operators can tell whether growth is expected, stale, or risky
- Cleanup or compaction preserves the evidence needed for accepted milestone verification, replay/eval, policy review, auditability, and debugging, while discarding or summarizing data that is no longer useful at full fidelity
- The storage model avoids duplicated long-term ownership of the same data across raw observations, compact snapshot fields, prompts, replays, and diagnostics unless the duplicate has a clearly documented purpose and retention policy
- Automated tests cover retention/compaction of observations, intervention/action histories, diagnostic logs or inspection artifacts, and replay/eval evidence preservation
- Human acceptance demonstrates that a long-running or simulated high-volume runtime can report storage posture, compact or clean eligible data, and continue normal terminal, Android, host, and multi-edge flows afterward

Acceptance criteria for M20 Agent Harness and runtime action-loop architecture refactor with unified action/tool governance:

- The architecture refactor starts from the documented target in `docs/plans/2026-07-10-agent-harness-action-loop-architecture.md` rather than reopening the whole project worldview from scratch
- The existing `Device Edge -> Gateway -> Personal Runtime -> Presence Router -> Execution Planning -> Action Layer` boundary remains intact while the agent execution core is clarified as an explicit harness layer
- The runtime distinguishes the external action loop from the internal agent loop: observations, events, and action results enter through `Gateway`; the harness emits action or terminal intent; governed execution produces new results or observations that re-enter through `Gateway`
- The harness layer has explicit contracts for context assembly, working memory, procedural memory, semantic memory, episodic or temporal memory, memory consolidation, action-result re-entry, and terminal outcomes such as `no_intervention`, `complete`, `suppressed`, or `failed`
- The runtime has an explicit behavior contract for model-backed proposal formation and post-action deliberation that defines allowed proposal types, required grounding inputs, allowed action/tool targets, and when no-intervention is required
- M20 must begin from a pinned Hermes agent-core dependency or vendored Hermes agent-core subset behind an `OpenHalo` adapter; it must not introduce a parallel greenfield agent loop, prompt builder, memory/session loop, provider loop, or general tool runner merely for implementation convenience
- New M20 code is limited to the adapter and OpenHalo-owned semantics: converting runtime observations/events/action results into harness input, converting Hermes outputs into OpenHalo proposals or action intents, enforcing the internal-tool versus governed-action split, and preserving OpenHalo diagnostics, lineage, and state contracts
- A native replacement for an individual Hermes capability is permitted only after a written reuse audit shows a concrete incompatibility, security boundary conflict, or maintenance blocker; the exception must name the Hermes component, explain why adapter-level integration cannot solve it, and retain equivalent regression coverage
- Any reused Hermes capability must still obey OpenHalo's action-governance boundaries, especially the split between agent-private tools and runtime-governed actions
- Device-edge actions, runtime-local tools, model-native tool calls, MCP/tool calls, and skill/procedure calls are represented through one runtime-owned action intent/result envelope with explicit executor kind, capability, side-effect class, visibility, permission/governance requirements, and provenance
- Provider-native tool-call syntax is normalized into the runtime action intent model before execution; model-native tool calls cannot directly bypass `Presence Router`, capability validation, action permissions, or result recording
- The canonical `notification.show` payload is `{title?: string, body: string}` for every notification-capable Edge. It is one unified user-visible delivery action across terminal and mobile surfaces; pull reply versus proactive delivery remains interaction and Presence metadata, not a separate capability. `title` is OpenHalo/target-Edge presentation metadata and must not expose Hermes branding by default.
- Before a Harness makes a semantic cross-device decision, the Runtime must supply a bounded structured device roster containing exact device IDs, device type/role, live availability, and registered action capabilities. The model chooses `target_device_hint` only from that roster according to user intent; the Runtime validates capability, availability, Presence, permission, payload, and risk without keyword-based semantic target rewriting. A prior Android acceptance failure where the model defaulted to the Terminal despite a connected Android phone is the negative case for this rule.
- OpenHalo owns the user-facing identity and system persona. Hermes is an embedded agent-core implementation only: its default identity must be replaced in the runtime-scoped Hermes identity slot, and neither model output nor durable system persona may present Hermes, Hermes Agent, or Nous Research as the user-facing assistant identity or creator attribution.
- Side-effectful or user-visible actions require validation against the behavior contract and capability/action registry before `Action Layer` execution, while bounded read-only internal tools may remain inside proposal formation when explicitly marked as non-user-visible and non-side-effectful
- Hermes must expose a curated agent-private capability set rather than its default tool surface: native persistent `memory` is the sole M20 data-mutation exception, while shell/process execution, file mutation, code execution, skills/plugins, delegation, cron, arbitrary MCP dispatch, and all browser interaction/console/CDP paths are unavailable to the OpenHalo harness
- Hermes-native web search and bounded HTTPS page extraction may run only as agent-private, read-only research helpers behind an OpenHalo policy that enforces public-network/host restrictions, request and result budgets, timeouts, audit records, and explicit treatment of remote content as untrusted prompt-injection input; research is a provenance marker rather than a global action/memory kill switch, so a later action must bind to the authenticated normal user request and pass runtime capability/risk validation before `Presence Router`, while elevated research-derived actions are confirmation-required and fail closed until confirmation exists; browser-backed rendering is explicitly deferred beyond M20 and is not enabled by the current runtime configuration or acceptance ladder
- Hermes-native persistent memory is enabled in a runtime-scoped `HERMES_HOME` and is the primary M20 durable-memory engine: the native `memory` tool may autonomously add, consolidate, replace, or remove bounded user/profile and agent-operational entries under the OpenHalo behavior contract, while writes remain scoped to the current Personal Runtime, pass Hermes' native memory safeguards, and emit OpenHalo provenance/audit metadata without a second content store; memory writes do not pass through `Presence Router` because they are not user-visible device actions, and untrusted research can inform reasoning but must never persist remote instructions or gain authority over a user-visible action
- OpenHalo must retain only inspectable memory provenance, integrity hashes, scope/session references, and replay links for the Hermes-memory path; it must not build a competing copy of Hermes durable semantic, episodic, or preference content in runtime state
- M20 live recall accepts Hermes' autonomous normalization of a user-provided sentinel into a concise memory entry: the post-write native file must contain the sentinel, its audited digest must match, and a fresh session must recall it, while OpenHalo records only the actual entry hash and no memory body
- M20 enables autonomous Hermes native-memory writes only in normal audited harness turns and seals `memory.nudge_interval = 0`; action-result and observation re-entry turns retain native-memory read context but omit the `memory` tool from both the model schema and low-level dispatcher allowlist. Periodic Hermes background memory/skill review remains deferred until OpenHalo owns an audited fork lifecycle, while M20.1 owns the separate skill-draft lifecycle
- Every Harness-marked external action must carry an allowed runtime action envelope with matching executor, capability, and payload at both pre-Presence validation and `Execution Planning`; an unbound or mismatched envelope fails closed without an edge dispatch
- Invalid, unsupported, or policy-disallowed model proposals are rejected, repaired, clarified, or converted to `no_intervention` with inspectable metadata rather than being executed opportunistically
- Post-action deliberation can use model-backed proposal formation over structured action results and prior interaction lineage, with metadata proving whether the outcome was model-backed or deterministic fallback
- `Presence Router`, execution planning, and `Action Layer` remain outside direct model control, so model-generated action intent cannot bypass presence governance, capability/provider selection, action validation, result recording, or edge-boundary dispatch
- Diagnostics, chain inspection, replay, and eval form an explicit LLMOps/eval loop around the harness, including trace, evaluation, diagnosis, gate, and controlled promotion of prompt/config/memory-policy changes
- The refactor preserves the user-visible behavior already accepted by earlier milestones before expanding new behavior, with regression coverage proving that terminal, Android, host, and multi-edge action paths still work through the public Edge API
- Automated tests cover harness loop contracts, external action-loop re-entry, contract validation, registry rejection, allowed device action, allowed runtime-local tool, normalized provider tool-call input, MCP/skill placeholder executor routing, post-action model-backed proposal metadata, and accepted behavior regression paths
- Human acceptance demonstrates at least one complete outer action-loop scenario where a device observation or action result re-enters through `Gateway`, the harness performs a new semantic decision, governed action/tool validation is visible, and the loop terminates for an inspectable reason rather than by fixed completion formatting
- Automated coverage proves the curated tool surface excludes direct-execution tools, permits and audits allowed read-only research calls, and records no raw remote-content body in durable OpenHalo state
- Automated coverage proves a Hermes memory write survives a fresh `HermesHarnessRunner` and is recalled on a later turn, while OpenHalo records only its provenance rather than a second durable memory body
- M20 acceptance distinguishes positive live fetch/search proof from the hostile-page behavior probe and deterministic boundary proof: the hostile probe may hash its configured fixture or safely decline the fetch with no side effects; forced unbound/elevated research actions must fail closed or require confirmation, instruction-shaped native memory writes must be rejected, and no planner may dispatch a Harness action without a matching allowed envelope
- Human acceptance demonstrates the action loop, real allowed `fetch` and `search` turns, and a cross-session Hermes-memory recall turn using the configured provider before M20 may be marked complete
- Automated coverage proves that distinct valid action intents from one Hermes deliberation become one governed `ActionBatch`, exact duplicates fold idempotently, and an invalid or conflicting batch records an explicit rejection instead of a fabricated `no_intervention`
- Automated coverage proves that an interaction with multiple dispatched actions does not re-enter the Harness after a partial result, and that its child session resumes exactly once with the ordered complete result set only after the batch settles
- Human acceptance demonstrates a real Terminal-to-Android multi-action interaction, verifies each action/result correlation and requester outcome, and confirms an unrelated interaction can complete in parallel while the first remains awaiting results

Acceptance criteria for M20.2 OpenHalo interaction-progress presentation:

- `Personal Runtime` produces a versioned, interaction-correlated progress lifecycle for active user-visible work; it represents stable product phases without exposing raw model reasoning or implementation-specific terminal display
- Progress payloads contain only safe phase/state, interaction or turn lineage, timing, and presentation-hint metadata. They must never contain chain-of-thought, provider/model configuration, tool arguments/results, remote content, memory text, or Hermes/Nous identity strings
- Progress is an update to an existing visible interaction, not a new proactive intervention: passive observations and agent initiative do not create a user-facing progress surface unless they first form an ordinary visible interaction through normal governance
- Gateway and the public Edge API deliver progress only to the requester or other visibility-authorized participants of that interaction. Unsupported, disconnected, or stale edges may miss an animation without affecting action execution, outcome reporting, or interaction completion
- Terminal and Android Edge render the lifecycle with their own native visual language, start/update/settle it predictably, and clear it on completion, failure, cancellation, or session loss; no Edge consumes Hermes stdout as its product progress source
- Runtime diagnostics record the safe lifecycle and correlation needed to inspect delivery/order without storing display text or the underlying private reasoning/tool content
- Automated tests cover phase ordering, correlation, privacy redaction, Edge capability/disconnect behavior, and absence of embedded Hermes display output; human acceptance verifies a natural user request on Terminal and Android has clear progress, final result, failure, and cleanup states without Hermes attribution

Acceptance criteria for M20.3 Terminal Edge stable CLI/TUI:

- The Terminal Edge remains one resident `Device Edge` session using the normal public Edge API; TUI startup, shutdown, reconnect, and failure handling must not create a local agent loop, direct runtime shortcut, shell executor, or Hermes identity surface
- A stable terminal layout provides a persistent status/header region, scrollable structured transcript, visible active interaction/progress area, and a fixed command composer. It remains coherent under narrow and wide terminals, common resize sequences, long messages, rapid updates, and terminal scrollback use
- The transcript distinguishes user input, OpenHalo responses, system connection state, governed cross-device outcomes, and M20.2 progress without exposing raw provider errors, tool internals, private reasoning, or Hermes/Nous branding
- The composer supports the existing useful local affordances and grows into predictable keyboard navigation, slash-command discovery/completion, history, draft preservation, cancellation, and help behavior without requiring mouse input or breaking ordinary stdin/non-interactive use
- Connection loss, reconnect, slow model turns, action-result re-entry, and edge disconnects produce clear recoverable UI state. The Edge preserves safe local continuity where possible, settles stale progress, and never corrupts transcript ordering or emits terminal-library stack traces to the user
- A plain non-TTY or redirected-stdio mode remains available as a readable, protocol-compatible fallback; visual enhancement cannot become a requirement for terminal participation
- M20.3 consumes the M20.2 versioned interaction-progress contract when present, but safely degrades when a Runtime or peer does not provide it; Hermes stdout is not a progress source in either mode
- Automated tests cover layout/state reduction, key local commands, resize and shutdown boundaries, reconnect, transcript ordering, progress lifecycle, and non-TTY fallback. Human acceptance verifies a realistic long-running Terminal session with a normal request, slow/progress-visible turn, cross-device action/result, reconnection, resize, slash-command use, and clean exit

Acceptance criteria for M20.1 governed procedural-memory and skill lifecycle:

- Hermes-derived skills are represented first as OpenHalo-owned, non-executable skill drafts with source/provenance references, bounded declarative scope, and no direct shell, plugin, browser, delegation, MCP, or arbitrary file-execution authority
- Draft creation, inspection, static validation, promotion, disablement, rollback, and retention are inspectable runtime operations rather than raw writes into Hermes' global skill directory
- A draft may affect a live Hermes harness turn only after an explicit OpenHalo activation decision; the active capability set remains independently constrained by the M20 tool allowlist
- Automated and human acceptance demonstrate that a useful procedural-memory draft can be reviewed and activated without exposing Hermes' generic skill/plugin manager or changing the `Device Edge -> Gateway -> Personal Runtime` action-governance boundary

Acceptance criteria for M21 policy learning and review loop:

- Intervention feedback, ignored interactions, explicit user responses, and runtime replay evidence can produce inspectable policy-update candidates rather than only one-off heuristic notes
- Model-backed feedback interpretation consumes the relevant interaction/intervention history, user feedback text, proposal metadata, compact context snapshot, and existing approved policies to draft policy candidates or explicitly return `no_policy_change`
- Policy-update candidates include scope, trigger evidence, proposed behavior change, expected user-experience impact, rollback metadata, confidence or uncertainty notes, and model/prompt provenance when model-backed interpretation was used
- Policy updates remain review-gated by default: the runtime may prepare, explain, and stage a candidate, but durable policy changes require explicit approval in the first accepted slice
- Presence-policy evaluation can consume approved policy changes without bypassing the existing compact snapshot, proposal formation, and `Presence Router` chain
- Automated tests cover positive feedback, explicit rejection, ignored intervention evidence, replay-derived candidate generation, model-backed candidate drafting, review approval, rejected/deferred candidate handling, and schema/validator rejection of overbroad policy suggestions
- Human acceptance demonstrates a realistic terminal/runtime scenario where user feedback generates a readable model-backed candidate and an approved policy change affects a later presence decision

Acceptance criteria for M23 Home Assistant Bridge Edge and smart-home ecosystem bridge:

- A Home Assistant Bridge Edge can connect to a configured Home Assistant instance through its public API without requiring individual Home Assistant-managed devices to implement the OpenHalo Edge API
- The bridge discovers Home Assistant entities, devices, areas, states, services, and relevant events, then maps supported entities into OpenHalo downstream device records, action capability registrations, and observation registrations
- The bridge uses synthetic registration with provenance metadata, including the external platform, Home Assistant entity ID, Home Assistant device or area identity where available, derived registration source, and confidence or mapping notes
- Periodic polling and Home Assistant event subscriptions can synchronize supported entity state into OpenHalo observations while preserving freshness, ambiguity, and source metadata
- OpenHalo action requests targeting bridge-registered smart-home capabilities are executed by the bridge through Home Assistant service calls and return action results that distinguish accepted service calls from confirmed physical state changes where confirmation is possible
- Home Assistant-originated smart-home capabilities remain subject to OpenHalo `Presence Router`, execution planning, capability validation, action policy, and result recording rather than bypassing runtime governance as direct Home Assistant automations
- The bridge design remains reusable for later openHAB, MQTT, Matter, or other smart-home ecosystem adapters by keeping platform-specific protocol handling inside the bridge and OpenHalo-facing behavior inside the public Edge API / registry model
- Automated tests cover entity discovery mapping, synthetic registration, state synchronization, action execution through a mocked Home Assistant API, result confirmation or failure-to-confirm behavior, and preservation of platform provenance
- Human acceptance demonstrates at least one realistic smart-home scenario, such as a Home Assistant-managed light or climate device becoming available to OpenHalo as a registered capability, receiving an OpenHalo-governed action, and reflecting the resulting state back as observation evidence

Post-M13 extension direction:

- The accepted first `M13` slice validates multi-type proposal formation on the live chain, but it should not be treated as the end state for interaction semantics
- The next design direction is for proposal formation to synthesize inspectable interaction hypotheses such as `pull`, `push`, `background`, or `silent`, potentially from multiple edge observations rather than only one visible source surface
- Model-backed proposal formation may suggest candidate participant surfaces, visibility intent, and the current `primary action` for that interaction, while `Presence Router` remains the final governance authority for actual user-visible surface delivery
- The current one-`primary action`-per-planning-turn execution shape is acceptable for early implementation, but the interaction model should remain compatible with future multi-turn `action loop` behavior where action results or fresh observations trigger reproposal inside the same interaction lifecycle
- Temporary completion-formatting patches should not be treated as substitutes for `M16`: interaction completion may carry structural status and edge delivery updates, but semantic post-action deliberation belongs to the explicit action-loop milestone

Accepted execution breakdown for M5:

- M5.1 `Gateway -> Runtime Observation Ingest`: observation batches arrive through the normal edge/gateway path, persist correctly, normalize into runtime-owned observations, and retain provenance cleanly enough for later reasoning and replay
- M5.2 `State / Context -> Compact Snapshot Field Pack`: the runtime builds an initial compact snapshot surface from those normalized observations one field at a time, with explicit contracts for field names, types, and fallback shape
- M5.3 `State / Context -> Freshness / Ambiguity / Evidence Rules`: snapshot reducers stop behaving as timeless latest-value lookups and instead apply explicit freshness aging plus bounded ambiguity / uncertainty handling where the field semantics require it
- M5.4 `Gateway -> State / Context -> Presence Input Verification`: the live runtime path demonstrably consumes the intended decision-time snapshot contract end to end, so M5 is accepted as a real runtime-ingestion/context milestone rather than only a pile of local reducer slices

Acceptance criteria:

- Each milestone has a clear scope
- Each milestone can be accepted independently
- Later milestones depend on earlier ones in a clean way

Status:

- In progress (M7, M8, M9, M10, M11, M12, M13, M14, M15, M16, M17.0, M17.1, M17.2, M17.3, M17.4, M17.5, M17.6, M17.7.1, M17.7.2, M18.1, the module-boundary diagnostics v1 baseline, and M20 completed and accepted; M20 acceptance includes renewed configured-provider Terminal/Android verification of ActionBatch dispatch, complete-result continuation, and requester outcomes; the next execution milestone is M20.2)

### Goal 5: Productize OpenHalo into an installable three-end system

We need OpenHalo to become a coherent product that can be installed, configured, connected, and tried without requiring the user to manually run unrelated developer processes.

Sub-goals:

- 5.1. Define the first productized deployment shape across phone edge, desktop/computer edge, and server/runtime host edge
- 5.2. Provide a Linux server installation path that installs and supervises `Personal Runtime + host edge` together
- 5.3. Provide a Windows desktop edge installer that can connect to a remote runtime and can optionally include disabled-by-default local runtime/host-edge components
- 5.4. Provide an Android APK delivery path for the phone edge outside Android Studio
- 5.5. Define first-run setup, endpoint pairing, connection health, diagnostics, and recent-activity UI expectations across phone and desktop surfaces
- 5.6. Verify the two accepted deployment scenes: standard public-server deployment and computer-server deployment

Acceptance criteria:

- A written productization baseline exists for the first installable OpenHalo slice
- The accepted deployment scenes are documented clearly enough that a user can tell what machines and packages are required
- Linux runtime/host-edge installation can be performed through one primary command or script and results in supervised services with status/log visibility
- Windows desktop edge installation produces a user-facing installed app, not only a development-shell entrypoint
- Android phone edge delivery produces an installable APK preserving the accepted daily-use phone-edge behavior
- Phone, desktop, runtime, and host edge all continue to communicate through the public Edge API boundary; packaging must not introduce hidden backend shortcuts
- Manual acceptance demonstrates both standard public-server deployment and computer-server deployment using packaged or packaging-equivalent artifacts

Status:

- In progress (`M22` is the first concrete implementation milestone for this goal; broader product polish, auto-update, app-store distribution, account/login UX, and encrypted local secret storage remain later hardening)

M17 preparation note:

- The first broader `M17` real-device edge direction is a native Android `Device Edge` developed locally with Android Studio under `device_edge/android_edge/`, while the Alibaba Cloud server continues to run the OpenHalo `Personal Runtime`; local install requirements are documented in `docs/android-edge-install.md`, and the Android edge design baseline is documented in `docs/plans/2026-06-30-m17-android-edge-design.md`.
- The first native Android implementation target is now explicitly tracked as `M17.2` rather than an unbounded mobile feature set: `M17.2` should deliver a Presence Edge baseline with stable background/foreground connection behavior where Android permits it, low-risk `mobile.context` observations, `notification.show` execution, foreground diagnostics, runtime-side routing/lineage verification, adb real-device smoke verification, and manual live-chain acceptance. Richer phone sensing and execution capabilities remain part of the M17 Android direction, but will be converted into later concrete milestones only after the Presence Edge baseline is accepted.
- The local Android Studio scaffold for that first native Android edge now exists under `device_edge/android_edge/` as a Kotlin/Jetpack Compose Gradle project with package `dev.openhalo.android.edge`, giving `M17` a concrete mobile-app baseline for foreground diagnostics UI, later background service wiring, and eventual Edge API session integration without changing the `Device Edge -> Edge API v1 WebSocket -> Gateway -> Personal Runtime` boundary.
- The first local real-device bootstrap acceptance for that Android edge has now been exercised end to end: Gradle sync completed successfully after removing one duplicate Kotlin Android plugin addition from the generated scaffold, a USB-connected Android phone was recognized through `adb`, and the debug app installed and launched on a real device, confirming that the current `device_edge/android_edge/` baseline is not only scaffolded but deployable on local hardware.
- The first live Android Edge API session slice has now been exercised against the Alibaba Cloud runtime at `ws://8.153.37.167:8765`: the Android app connected as `android-edge-695b32cf`, sent registered `mobile.context` observations, and the foreground diagnostics UI recorded a successful `notification.show -> ok` action result, proving the first runtime-to-phone action dispatch path over `Android Device Edge -> Edge API v1 WebSocket -> Gateway -> Personal Runtime`. Broader `M17` remains in progress until this evidence is covered by a bounded verifier and multi-edge lineage inspection.
- The runtime-side bounded verifier for the first M17 mobile edge slice now exists as `bin/verify_m17_mobile_edge.py`, with `bin/verify-m17-mobile-edge` retained as a Unix-style wrapper. It exercises the public Edge API in-process with a terminal source edge, an Android-like target edge, and competing speaker/light surfaces; verifies `mobile.context` observation ingestion, `notification.show` routing to the Android edge, filtered candidate reasons for nonchosen surfaces, `action_result` handling, and interaction lineage from `terminal-edge-1` to `android-edge-1`; and is backed by the focused gateway regression `test_m17_mobile_edge_routes_terminal_interaction_and_preserves_lineage`. Broader `M17` remains in progress until the same evidence is extended to a repeatable real-device verifier and broader multi-edge acceptance.
- The first real-device Android verifier now exists as `bin/verify_m17_android_device.py`. It uses `adb` to detect the attached phone, launch the Android edge app, optionally tap Connect and Send Observations, read foreground diagnostics through UI automation, and inspect structured `OPENHALO_EDGE_EVENT` logcat events after the newly instrumented app is installed. The current local run verified a real phone connection to `ws://8.153.37.167:8765` plus `mobile.context` observation delivery automatically; full `--require-action` verification is available once another live edge or server-side scenario triggers a fresh runtime-to-phone `notification.show` action during the verifier window.
- The M17 Android edge testing workflow is now documented in `docs/m17-android-edge-acceptance.md` as the current layered practice: unit tests, Compose UI tests, instrumentation/UI Automator, adb installed-build smoke, and manual live-chain acceptance. Normal phone-edge development should put pure behavior and Compose flows below the adb layer; the Python adb verifier remains a small installed-build smoke check rather than the primary UI automation path.
- The M17.2 Android edge implementation has begun shifting from an Activity-owned demo connection toward a Presence Edge shape: the native app now starts a foreground `AndroidEdgeService` to own the Edge API session, connection lifecycle, low-risk `mobile.context` observation sending, and `notification.show` action execution, while the foreground Compose UI reads shared diagnostics and controls the service. The adb real-device verifier now requires foreground service evidence in addition to connection and observation evidence, keeping M17.2 acceptance aligned with "always available when Android permits it" rather than only "screen is open and connected."
- A same-day Android Studio sync and Run smoke check on a real phone confirmed the foreground-service slice can build and run locally: the diagnostic UI showed `Service: foreground`, `Connection: connected`, and successful `mobile.context` observation sending after `Send Observations`. This strengthened the M17.2 real-device baseline ahead of the later adb verifier and live terminal-to-runtime-to-phone `notification.show` acceptance that are now recorded below.
- The Android edge now tracks the runtime startup split introduced on `master`: development acceptance defaults to the restart-heavy runtime port `18765`, and the phone edge carries a configurable Edge API auth token that can match either the development `dev-token` or the long-running server's `OPENHALO_EDGE_TOKEN` without rendering the secret in foreground diagnostics.
- The Android foreground diagnostics now model that split directly with a runtime-mode switch: off selects development runtime settings, on selects persistent runtime settings, and persistent URL/token values are intended to be injected from ignored Android `local.properties` so real server secrets do not enter tracked source.
- The current persistent Android edge endpoint is `ws://8.153.37.167/openhalo/edge`, which fronts the long-running server runtime rather than requiring the phone edge to connect directly to the server-local `8765` runtime port.
- Android `notification.show` execution now uses the shared `RuntimeNotificationPresenter` path and the Android diagnostics UI exposes both a local `Test Notification` button for ordinary notification comparison and a local `Test Urgent Alert` button for pop-up verification during M17.2 real-device acceptance.
- Real-device testing on the Xiaomi/HyperOS phone showed that both local `Test Notification` and terminal-edge-triggered ordinary notification delivery reach Android's notification service as high-importance/interruption-capable notifications but still do not reliably render as a top banner on that device; the urgent-alert path, using an `OpenHalo urgent alerts` channel, full-screen intent permission, and a lightweight `RuntimeAlertActivity`, has now passed real-device manual verification and can display a pop-up notification/alert on the phone.
- The M17.2 Android phone-alert product decision is now explicit: a phone notification that requires the user to manually open the notification shade is not considered an effective OpenHalo alert. Therefore Android `notification.show` now executes through the urgent alert presenter by default, and `notification.alert` remains as an explicit high-interruption capability alias for future runtime policies that want to name the stronger behavior directly.
- The terminal-to-runtime-to-phone live-chain notification path has now passed real-device manual acceptance after the urgent-alert change: from terminal edge, the user sent the Chinese instruction `给手机发送一个hello`, and the Android phone received a pop-up OpenHalo notification showing the delivered `hello` content. This satisfies the practical M17.2 requirement that phone-targeted runtime notifications are visible without the user manually opening the notification shade.
- The adb-based M17.2 Android real-device smoke verifier has now passed against the installed phone edge on device `65L7MBE6L7WSZ9ZD`: the verifier reported `ok: true`, `connected: true`, `service_foreground: true`, `sent_observation: true`, and registered capability evidence including `notification.show`, `notification.alert`, and `mobile.context`. The verifier was also updated to locate Compose buttons by UI text and scroll diagnostics before collecting evidence, so it remains aligned with the current Android diagnostics layout.
- M17.2 completion should not be read as Android phone-edge product readiness. The current phone edge is an accepted architecture and real-device baseline for public Edge API connection, foreground-service session ownership, diagnostics, low-risk context observation, and visible notification execution. It is still closer to a validation/diagnostic edge than a daily-use mobile assistant surface: durable background survival, boot/startup behavior, battery-policy handling, reconnection/backoff hardening, richer permission UX, notification policy controls, local persistence, and non-diagnostic user-facing mobile workflows remain later Android edge hardening work.
- `M17.3` is now the named Android Edge daily-use hardening milestone. It should turn the phone edge from a diagnostics-first verifier into a daily-use mobile surface while preserving the `Device Edge -> Edge API -> Gateway -> Personal Runtime` boundary. The expected shape is a simple status-first home screen with start/stop control, connection/permission health, recent notifications/runtime events, notification history/detail views, diagnostics moved to a secondary screen, and a direct text command box for explicit user instructions. That text box should be modeled as phone-originated edge input through the normal runtime chain rather than as a chat-specific backend shortcut.
- The first M17.5 implementation slice is now in place for human acceptance: the Android edge declares a `mobile.screen_context` observation provider, exposes a user-controlled `屏幕上下文` settings toggle plus accessibility-settings entry, runs an `OpenHaloAccessibilityService` with bounded/debounced event coalescing on a worker thread, summarizes accessibility node trees into redacted `mobile.screen_context` observations, blocks sensitive/password-like contexts into health-only evidence, pauses rich capture when locked or screen-off, and sends observations through the existing foreground-service Edge API session without raw screenshot upload. Runtime-side coverage confirms `mobile.screen_context` is stored as passive evidence and does not trigger intervention in M17.5. A new read-only `personal_runtime.context_viewer` / `bin/runtime-context-viewer` inspection surface can watch a long-running runtime's persisted state and optional diagnostic JSONL to show latest ingress events, normalized observations, compact snapshot evidence, and the latest agent prompt/context package during manual acceptance.
- M17.5 human acceptance exposed that package-name denylisting and post-extraction redaction are not a sufficient privacy boundary for banking/payment-style screens: a live China Bank app run on the phone produced normal `mobile.screen_context` text despite best-effort sensitive detection. The project now deliberately splits comprehensive sensitive-screen capture governance into `M17.8`, where rich capture will become allowlist-first and unknown apps default to health-only evidence. M17.5 remains the screen/context observation transport and passive-evidence baseline, while sensitive app/page governance is no longer treated as a quick denylist patch.
- M17.5 is now accepted complete under the re-scoped observation-transport baseline: live phone testing confirmed `android-edge-782d0247` can upload `mobile.screen_context` and `mobile.screen_capture_health` through the long-running server runtime, the context viewer shows latest accepted ingress events and normalized observations in near real time, ordinary app usage produces bounded accessibility-tree summaries without raw screenshot upload, locked/screen-off states degrade to health-only evidence, high-frequency activity emits throttling/health observations, and runtime snapshot/prompt evidence keeps `mobile.screen_context` passive rather than treating it as intent. Sensitive banking/payment governance is explicitly deferred to M17.8 and is not a blocker for the completed M17.5 baseline.
- The runtime context viewer is now documented as the standard human-acceptance surface for long-running observation features: `docs/dev-env.md` records the server-side viewer command and operator loop for comparing `generated_at`, latest ingress events, normalized observations, snapshot evidence, and prompt context; `docs/m17-android-edge-acceptance.md` applies that flow directly to M17.5 Android screen-context acceptance.
- The first M17.3 implementation slice has started on the Android edge: runtime mode, endpoint, device identity, and token now persist locally through Android shared preferences; the foreground UI is reorganized around a status-first daily home surface with start/stop, notification permission health, latest runtime reply, and bounded recent mobile history before the lower diagnostic details; runtime-delivered replies/actions, observation sends, connection attempts, and phone-originated submissions append to a bounded local event history; and the phone text box now submits explicit user instructions as public Edge API `event_push` frames with capability `mobile.input`. If the phone edge is not connected when the user submits text, the client queues the text, starts the persisted Edge API session, and sends the command after WebSocket connection, preserving the normal `Device Edge -> Edge API -> Gateway -> Personal Runtime` path rather than introducing a phone-local chat shortcut.
- The M17.3 Android daily-use hardening slice now also covers bounded WebSocket reconnect/backoff, connection-health timestamps, Android permission/battery-policy affordances, notification/reply history detail views, and a diagnostics secondary view. The Android client records last successful connection time, last disconnect time/reason, retry attempt, reconnect status, and Android notification/full-screen-alert/battery health; non-manual failures schedule bounded reconnect attempts over the persisted Edge API configuration. The foreground UI now separates `Home`, `Notifications`, and `Diagnostics`, exposes direct notification/full-screen-alert/battery settings actions where Android permits them, and lets notification clicks or urgent-alert detail actions return to the app's notification-detail view. The adb real-device verifier now recognizes the new status-first UI, can use `--tap-start`, can require the daily-use UI with `--require-daily-ui`, and can submit a phone-originated text command with `--submit-text-command` while checking for a public `mobile.input` event frame.
- A real-device M17.3 smoke check passed after the manually installed Android build on device `65L7MBE6L7WSZ9ZD`: `python -B bin\verify_m17_android_device.py --serial 65L7MBE6L7WSZ9ZD --tap-start --require-daily-ui --timeout-seconds 30` reported `ok: true`, `connected: true`, `service_foreground: true`, `sent_capability_announce: true`, `sent_observation: true`, and `daily_ui_ready: true` against `ws://8.153.37.167/openhalo/edge`. The UI history also showed repeated phone-originated `Submitted mobile.input - hello runtime` entries followed by runtime-delivered `notification.show -> ok - Hello! Runtime is here. How can I help?`, confirming the installed app can exercise the phone text-command path through the normal public Edge API/runtime chain, while the verifier's fresh text-entry automation remains a follow-up robustness improvement rather than a runtime-chain blocker.
- The Android edge testing principle and workflow are now explicit and replace the older adb/UI-text-scraping optimization flow: future phone-edge development should use unit tests for pure behavior, Compose UI tests with stable `testTag` or accessibility semantics for app-internal UI flows, instrumentation/UI Automator for real device/system behavior, and `bin/verify_m17_android_device.py` only as a black-box installed-build smoke verifier over app launch, foreground service, connection, structured logcat evidence, and a small set of visible health markers.
- The new Android edge testing workflow now has a working emulator-first implementation path. The Android app exposes stable Compose `testTag` surfaces for the M17.3 home, notification, diagnostics, status, and phone-command controls; template Android tests have been replaced with M17.3-specific JVM protocol/backoff tests plus a Compose instrumentation class covering daily home status, command entry enablement, top-level navigation, and Android health helper availability. The helper `bin/test_m17_android_emulator.ps1` reuses an existing Android Studio AVD such as `OpenHalo_M17`, builds unit/debug/test APK artifacts, installs only to the selected `emulator-*` serial, runs the Compose instrumentation class directly, and treats instrumentation-reported failures as script failures even if `adb shell am instrument` exits successfully. A local run against `emulator-5554` passed with `OK (4 tests)` after `:app:testDebugUnitTest` and APK assembly, confirming that normal M17.3 UI automation no longer needs the user's daily phone or adb UI-text scraping as its primary path.
- The M17.3 emulator-first Android test coverage has been expanded beyond the initial smoke-level Compose checks. The emulator suite now covers nine instrumentation scenarios: daily home status and command surfaces, text-entry enabling, Home/Notifications/Diagnostics navigation, Android health helper availability, runtime configuration persistence, bounded newest-first history retention, AndroidEdgeService intent action/extra contracts, notification history/detail rendering from persisted events, and diagnostics display of updated connection/service/error/recent observation/recent action state. A follow-up local run of `bin/test_m17_android_emulator.ps1 -AvdName OpenHalo_M17` passed against `emulator-5554` with `OK (9 tests)` after the JVM protocol/backoff tests and APK assembly, making the emulator path the primary app-surface regression check while still leaving Android system-bound behavior and real phone pop-up/background acceptance to instrumentation/UI Automator, installed-build smoke, and manual live-chain verification.
- The local Python verifier environment is now standardized through a repository `.venv` created with Python 3.14 and `pip install -e .`; `.\.venv\Scripts\python.exe -B bin\verify_m17_mobile_edge.py` now passes and reports `ok: true`. After USB install permissions were adjusted, `.\gradlew.bat :app:connectedDebugAndroidTest` also completed successfully with 1 instrumentation test on device `65L7MBE6L7WSZ9ZD`, but the connected-test/install cycle still leaves the manually installed app absent from the phone, and a follow-up `.\gradlew.bat :app:installDebug` was again blocked by `INSTALL_FAILED_USER_RESTRICTED: Install canceled by user`. Until the phone-side install confirmation/restriction is fully resolved, avoid running connected instrumentation on the daily-use phone when preserving the installed app matters; prefer unit/runtime verifier and manually reinstall the app from Android Studio when needed.
- M17.3 Android Edge daily-use hardening has now passed human real-device acceptance on the user's HyperOS/Xiaomi-class phone. The accepted scenario covered the local app home/status flow, phone-originated `mobile.input` submission through the normal Edge API/runtime chain, terminal/runtime-to-phone notification delivery with action-result closure, and background/lock-screen/battery-setting/reconnect behavior. This accepts the bottom-layer daily phone-edge capability set for M17.3; further notification polish, long-horizon background survival tuning, broader OEM ROM matrices, and richer mobile product UX remain follow-up hardening rather than blockers for M17.3 completion.
- The first product-facing Mobile Edge UI design baseline is now recorded under `docs/design/mobile-edge-ui/`: the Pixso and PDF design assets are preserved, and `mobile-edge-ui-spec.md` defines the three-screen product shape of `Connect`, `Global Chat`, and `Settings`. This keeps the formal phone foreground UX aligned with the `Device Edge -> Edge API -> Gateway -> Personal Runtime` boundary while clarifying that the chat page is a global conversation projection across terminal, phone, desktop, and future edges rather than a phone-local chat shortcut.
- The first M17.4 Mobile Edge product UI implementation slice is now in place on the Android edge: the foreground app launches into `Connect`, exposes `Global Chat` and `Settings` as the other two primary tabs, moves phone-originated text input into Global Chat while preserving the existing public Edge API `mobile.input` service path, keeps normal runtime URL/device/permission/reset/cache controls in Settings, and hides developer diagnostics behind a session-local 7-tap gesture on the Settings version/build affordance. The adb verifier has been updated for `Connect / Global Chat / Settings` and can unlock developer diagnostics before checking raw Edge API evidence. `.\gradlew.bat :app:testDebugUnitTest` passed, and `.\bin\test_m17_android_emulator.ps1 -AvdName OpenHalo_M17` passed on `emulator-5554` with `OK (11 tests)` after building and installing the debug/test APKs.
- M17.4 visual QA was completed for the first product UI slice against rendered design pages from `docs/design/mobile-edge-ui/openhalo-mobile-edge-ui.pdf` and emulator screenshots saved under `tmp/m17_4_visual_qa/`. The emulator comparison exposed product-surface issues that were fixed in the Android UI: Global Chat now filters raw connection/context events such as runtime URL and `mobile.context` sends out of the user-facing conversation projection, Settings row values are constrained with ellipsis so long device IDs cannot overlap labels, and the Settings vertical density/bottom padding has been adjusted so the operation section is not hidden by the bottom navigation on the emulator viewport. `.\gradlew.bat :app:testDebugUnitTest :app:assembleDebugAndroidTest` passed after the visual fixes.
- M17.4 Settings interaction semantics have been corrected and added to emulator coverage. Runtime URL and device name rows now open visible edit dialogs and persist changes through `AndroidEdgePreferences`; connection protocol and local network permission are explicit read-only status rows rather than fake tappable controls; push notification opens the notification-permission path; background keepalive is a local Edge preference toggle instead of a mislabeled battery-policy shortcut; battery policy is exposed as its own system-settings row. The Compose instrumentation suite now covers these Settings user paths and action semantics, and `.\bin\test_m17_android_emulator.ps1 -AvdName OpenHalo_M17` passed on `emulator-5554` with `OK (13 tests)`.
- M17.4 follow-up fixed a daily-use Android foreground-service notification regression: phone-originated `mobile.input` submissions no longer re-promote an already foregrounded `AndroidEdgeService` or recreate the persistent "Presence edge session is running" notification on every chat send. The foreground service notification is now only established once per service foreground lifecycle, uses `setOnlyAlertOnce(true)` and `setSilent(true)`, and Global Chat text submission uses the normal service intent path instead of repeatedly requesting foreground-service startup. `.\bin\test_m17_android_emulator.ps1 -AvdName OpenHalo_M17` still passes with `OK (13 tests)` after the fix.
- M17.4 Global Chat daily-use polish now keeps the conversation anchored on the newest message as local phone/runtime history changes, applies IME-aware padding so the composer and latest visible message stay above the Android keyboard, and renders history meta timestamps from the recorded ISO `observed_at` value as real local `HH:mm` clock time instead of substring artifacts such as fractional seconds. A Compose regression test now covers newest-message visibility and clock-time labels for phone-originated `mobile.input` history, emulator screenshots under `tmp/m17_4_visual_qa/` visually confirmed the sent-message and keyboard states, and `.\bin\test_m17_android_emulator.ps1 -AvdName OpenHalo_M17` passed on `emulator-5554` with `OK (14 tests)`.
- M17.4 Global Chat IME positioning was refined after visual review found that the first keyboard-avoidance pass stacked the bottom-navigation reserve with keyboard avoidance and lifted the composer too far above the Android keyboard. The chat screen now uses a dynamic bottom reserve: the normal bottom-nav height when the keyboard is closed, and the measured IME bottom inset when the keyboard is open, so the composer sits directly above the keyboard while preserving the non-keyboard bottom navigation clearance. The corrected emulator screenshot is saved at `tmp/m17_4_visual_qa/global_chat_keyboard_gap_fix_3.png`, and `.\bin\test_m17_android_emulator.ps1 -AvdName OpenHalo_M17` passed on `emulator-5554` with `OK (14 tests)`.
- M17.4 Mobile Edge product UI implementation is now completed and accepted for the first phone-edge product UI slice. Human acceptance confirmed that the first-version phone Edge UI is now good enough to close M17.4; further design polish, broader OEM viewport checks, durable runtime-backed conversation sync, richer mobile observation depth, and packaging-level delivery are follow-up hardening or later milestones rather than blockers for M17.4.
- The repository README files now present the accepted first-version Android phone Edge UI as part of the current baseline and point users to a GitHub Release preview APK at `v0.17.4-mobile-edge-preview`. The APK is treated as a debug-signed preview artifact for early installation/testing rather than a tracked repository binary or formal release-signed distribution; full signing, updater/distribution polish, and packaged three-end delivery remain later productization work.
- The repository README files now also lead with the intended user-facing deployment scenes and use the gap between those scenes and the current implementation to frame the maintained progress table. The front-page deployment scenes are the standard personal deployment with server runtime/host edge plus separate computer and phone edges, and the computer-hosted deployment where one computer hosts runtime/host/desktop edges while the phone connects to it; the local development loop is kept under Quick Start/development context instead of being presented as a user deployment scene. The README progress table should be updated whenever a milestone is completed, accepted, or re-scoped so the repository front page stays aligned with `Project.md`.
- The README deployment-scene framing now also names a future ambient deployment direction: phones, computers, smart-home devices, sensors, and small edge-AI nodes can eventually participate as a low-presence personal environment. This is explicitly a long-term deployment vision requiring bridge integrations, device profiles, safety policy, and ambient interaction design; it should not be read as part of the completed M17.4 phone UI or near-term M22 packaged three-end slice.

## Completed Sub-goals

### Completed: M17.4 Mobile Edge product UI implementation

Result:

- The Android phone edge foreground is now a product UI rather than a developer diagnostics console: the top-level tabs are `Connect`, `Global Chat`, and `Settings`, with `Connect` as the launch/default product surface.
- `Connect` exposes the accepted product connection states through one large stateful control and keeps the relevant primary action visible for the current state.
- `Global Chat` provides a bounded local global-conversation projection with source labels and real local `HH:mm` timestamps, filters raw protocol/context noise out of the product conversation, anchors to the newest message, and keeps the composer correctly positioned above the Android keyboard.
- Phone-originated messages still submit through the existing `mobile.input` Edge API service path, preserving the normal `Device Edge -> Edge API -> Gateway -> Agent Runtime -> Presence Router -> Action Layer` boundary rather than introducing a phone-local chat shortcut.
- `Settings` now exposes normal user-facing controls for runtime URL, device name, notification/battery/background semantics, reset, clear cache, and build/version, while raw protocol controls, frame traces, token visibility, test notifications, and diagnostics cards are hidden behind a session-local 7-tap developer gesture.
- The repeated foreground-service notification regression from chat sends is fixed: phone-originated `mobile.input` submissions no longer recreate or re-alert the persistent "Presence edge session is running" notification on every send.

Acceptance evidence:

- `.\bin\test_m17_android_emulator.ps1 -AvdName OpenHalo_M17` passed on `emulator-5554` with `OK (14 tests)`, covering the M17.4 product navigation, Global Chat, Settings semantics, and hidden diagnostics path.
- Visual QA compared the Android implementation with `docs/design/mobile-edge-ui/openhalo-mobile-edge-ui.pdf` and captured emulator screenshots under `tmp/m17_4_visual_qa/`, including the corrected keyboard-positioning screenshot `global_chat_keyboard_gap_fix_3.png`.
- Human acceptance on 2026-07-05 confirmed the first-version phone Edge UI is "像模像样" and good enough to close the first M17.4 product UI slice.

Status:

- Completed and accepted

### Completed: M17.3 Android Edge daily-use hardening

Result:

- The Android edge now provides a status-first daily home surface with foreground-service start/stop control, connection health, reconnect state, Android notification/full-screen-alert/battery health evidence, recent activity, notification/reply history, and a secondary diagnostics view
- Runtime mode, endpoint, device identity, and token configured state persist locally through Android shared preferences, while public diagnostics and frame displays avoid rendering secrets
- The foreground-service client owns the Edge API session, sends `mobile.context`, announces low-risk mobile capabilities, executes `notification.show`/`notification.alert`/`mobile.reply.render`, records bounded local history, and performs bounded reconnect/backoff with visible timestamps and disconnect reasons
- Phone-originated text commands are represented as public Edge API `event_push` frames with capability `mobile.input`, preserving the normal `Device Edge -> Edge API -> Gateway -> Agent Runtime -> Presence Router -> Action Layer` chain instead of introducing a phone-local chat shortcut
- Runtime-delivered notifications use the urgent alert presenter by default, and notification clicks or alert detail actions return to the app's notification/detail surface
- The Android testing workflow now uses an emulator-first path for normal app-surface regression, backed by JVM protocol/backoff tests, Compose instrumentation tests over stable tags, runtime-side mobile-edge routing verification, real-device installed-build smoke, and manual live-chain acceptance

Acceptance evidence:

- `bin/test_m17_android_emulator.ps1 -AvdName OpenHalo_M17` passed on `emulator-5554` with `OK (9 tests)`, after JVM protocol/backoff tests and APK assembly
- `.\.venv\Scripts\python.exe -B bin\verify_m17_mobile_edge.py` passed and reported `ok: true`, covering runtime-side phone-edge routing and lineage
- A real-device M17.3 installed-build smoke check passed on device `65L7MBE6L7WSZ9ZD` with connection, foreground service, capability announcement, observation, and daily UI evidence
- Human acceptance on the user's phone confirmed that the app home/status flow, phone-originated input, terminal/runtime-to-phone notification path, action-result closure, background/lock-screen behavior, battery-setting handling, and reconnect behavior are good enough for the M17.3 bottom-layer capability baseline

### Completed: M17.2 native Android Presence Edge baseline

Result:

- The native Android app now acts as a first-class `Device Edge` over the public Edge API through a foreground `AndroidEdgeService`, with configurable development/persistent runtime selection, configurable Edge API token support, stable device identity, capability registration, WebSocket connection lifecycle handling, and no backend-internal imports or phone-specific runtime shortcuts
- The foreground Compose diagnostics surface exposes runtime mode, runtime URL, device ID, token configured/missing state without rendering the secret, connection state, service state, registered capabilities, recent observations, recent actions, in-app replies, last error, and last public Edge API frames
- The accepted low-risk Android capability surface includes `mobile.context` observations and runtime-to-phone `notification.show` execution; `notification.alert` is also registered as an explicit high-interruption alias, while camera, microphone, continuous screen interpretation, location, and richer local commands remain later mobile Sensor/Action Edge directions
- The Android phone-alert product decision is now explicit: phone-targeted runtime notifications must visibly pop up to count as effective alerts, so Android `notification.show` executes through the urgent alert presenter by default rather than relying on notification-shade-only delivery
- Runtime-side simulated verification covers Android-like routing and lineage with terminal source edge, Android target edge, competing candidate surfaces, `mobile.context` ingestion, `notification.show` dispatch, `action_result` handling, and interaction lineage preservation
- The adb-based real-device smoke verifier passed on device `65L7MBE6L7WSZ9ZD`, reporting `ok: true`, `connected: true`, `service_foreground: true`, `sent_observation: true`, and registered capability evidence including `notification.show`, `notification.alert`, and `mobile.context`
- Manual live-chain acceptance passed on the persistent runtime path: from terminal edge, the user sent `给手机发送一个hello`, and the Android phone received a pop-up OpenHalo notification showing the delivered `hello` content
- The Android install and M17 Android acceptance docs now describe the runtime mode split, persistent endpoint `ws://8.153.37.167/openhalo/edge`, token handling, urgent `notification.show` behavior, and the adb/manual verification ladder
- The completion scope is explicitly a baseline/acceptance milestone rather than a daily-use mobile product milestone; long-term usability hardening remains future Android edge work

Acceptance criteria:

- The native Android app can act as a first-class `Device Edge` over the public Edge API with stable device identity, capability registration, WebSocket connection lifecycle, reconnect diagnostics, and no backend-internal imports or phone-specific runtime shortcuts
- The Android edge provides a foreground diagnostics surface that exposes connection state, runtime URL, device ID, last sent/received public Edge API frames, recent observations, recent action requests, and action results
- The Android edge can run as a constrained phone presence surface: background availability is attempted where Android policy allows, foreground/manual operation remains supported, and any background restriction or permission limitation is represented as context evidence rather than assumed away
- The accepted initial capability surface remains intentionally low-risk: `mobile.context` observations plus `notification.show` execution, with camera, microphone, continuous screen-use interpretation, location, and richer local command surfaces recorded as later mobile Sensor/Action Edge direction rather than M17.2 blockers
- The runtime can choose the Android edge as an intervention surface for a notification action while other candidate surfaces are present, and interaction lineage preserves the source edge, Android target edge, action result, and participant devices
- Automated verification includes runtime-side simulated routing/lineage coverage and an adb-based real-device smoke verifier for Android app connection and observation behavior
- Human acceptance demonstrates the full live chain from a non-phone source edge through the runtime to the Android phone edge, with inspectable action result and lineage evidence

Status:

- Completed and accepted

### Completed: M17.0 public Edge API boundary and internal-runtime encapsulation baseline

Result:

- The public Edge API boundary is documented in `docs/edge-api.md`, covering device registration, authentication shape, capability announcement, user events, observations, action requests, action results, interaction updates, errors, versioning, and compatibility expectations
- The runtime architecture baseline now includes an `M17.0` Edge API interaction flow diagram that shows terminal, host, and external edges using `Edge API v1` before traffic reaches `Gateway`
- A public `edge_api` package defines dependency-free `edge.runtime.v1` frame helpers so external edge authors do not need to import `personal_runtime` internals
- The official Python edge client now builds connect, capability, user-event, observation, and action-result frames through the public API wrapper
- The current terminal edge and host edge preserve their normal runtime behavior while using the public API envelope for edge/runtime traffic
- `Gateway` accepts versioned public frames, normalizes `observation_push` into the existing runtime observation path, supports capability object announcements, and emits versioned `connect_ok`, `event_ack`, `action_request`, `interaction_update`, and `error` frames
- `action_request` frames now carry a public `request_id`, while `interaction_id` continues to preserve interaction lineage through action results and post-action re-entry
- Automated tests include a raw external-edge simulation that connects through public API frames, announces capabilities, pushes an observation and user event, receives an action request, returns an action result, and preserves interaction lineage without importing runtime internals
- Fresh full verification passed with `.venv/bin/python -m unittest discover -s tests -v`, reporting 294 tests OK
- Human acceptance is recorded from real-use feedback that the actual M17.0 API path is stable enough for this milestone

Acceptance criteria:

- A written external Edge API contract exists
- Runtime internals are closed to edge authors behind `Edge API v1 -> Gateway`
- Terminal edge and host edge use the public API contract or official SDK wrapper
- The Python edge client is documented and tested as a convenience wrapper rather than the only integration path
- External-edge raw-frame automated coverage exists
- Existing runtime, terminal-edge, host-edge, model-provider, prompt-contract, proposal-formation, and action-loop tests pass after the API boundary refactor
- Human acceptance confirms the new edge API path is stable enough for the milestone

Status:

- Completed and accepted

### Completed: M17.1 registration-driven multi-device extension baseline

Result:

- The public Edge API now preserves and validates rich capability registration objects, including action metadata and observation-provider contracts, while keeping simple string capability announcements compatible for existing terminal and host edges
- `RuntimeState` now persists a device registry, capability registry, and observation registry, and restores older state payloads without registry fields
- `Gateway` now records rich capability metadata and nested observation schemas at public API ingress, rejects unregistered or schema-mismatched observations with public `error` frames, and keeps bounded compatibility defaults for current terminal and host observation providers
- `Execution Planning` now includes a registry-driven capability resolver sub-step after `Presence Router`, consumes registered provider metadata and online device state, filters invalid candidates, deterministically scores valid candidates, and emits an inspectable planning record
- Action dispatch now uses the finalized execution outcome from `Execution Planning`, while `Action Layer` remains responsible for building action frames rather than choosing semantic providers
- Chain inspection now includes an `Execution Plan` section with candidate, filtered-candidate, chosen-candidate, fallback, and rationale data for replay and later policy-learning work
- Automated coverage now includes rich mobile-style registration, strict observation rejection, schema mismatch rejection, registry persistence, planner candidate resolution, multi-surface phone/speaker/light routing, and dev-env verifier coverage
- Bounded manual acceptance is available through `bin/verify-m17-1-registration-extension --dry-run` and `bin/verify-m17-1-registration-extension`
- Fresh targeted verification passed with `.venv/bin/python -B -m unittest tests.test_protocol_v0 tests.test_edge_client_v0 tests.test_runtime_state_v0 tests.test_runtime_persistence_v0 tests.test_gateway_v0 tests.test_roundtrip_v0 tests.test_execution_planning tests.test_chain_inspection tests.test_dev_env_scripts -v`, reporting 145 tests OK
- Fresh full regression passed with `.venv/bin/python -m unittest discover -s tests -v`, reporting 342 tests OK
- Human acceptance evidence from the bounded verifier shows registered devices, registered capabilities, registered observations, accepted registered observation ingest, strict unregistered-observation rejection, phone notification selected as the primary action, and public speaker / ambient light candidates rejected with planner reasons

Acceptance criteria:

- Rich action-capability registration metadata is supported through the public Edge API
- Explicit observation registration metadata is supported through the public Edge API
- Device, capability, and observation registries are persisted while preserving existing terminal/host compatibility
- Gateway rejects unregistered and schema-mismatched observations with inspectable public errors
- New registered capabilities can participate in planning without device-type-specific runtime branches
- Execution Planning owns capability/provider selection after Presence Router and before Action Layer
- Capability selection uses registered metadata rather than a fixed `intent -> capability` table
- Planning records preserve chosen, fallback, filtered, rationale, and registry-reference data
- Diagnostics and chain inspection expose the Execution Planning / capability resolver boundary
- Automated and bounded manual acceptance cover the multi-surface registration-driven path

Status:

- Completed and accepted

### Completed: Module-boundary diagnostics v1 and runtime orchestration boundary baseline

Result:

- A neutral `openhalo_common` package now owns shared diagnostic primitives, including the structured `diagnostic.v1` event schema, in-memory diagnostic recorder, JSONL writer, correlation helpers, and backward-compatible lightweight trace recorder
- Device-edge runtime paths now use runtime-neutral diagnostics instead of importing `personal_runtime` tracing internals; dependency-boundary coverage verifies ordinary shared, terminal, and host edge runtime paths do not depend on backend internals
- Edge API frames now carry lightweight correlation fields such as `trace_id`, `session_id`, `turn_id`, and `event_id`, while runtime-generated `action_request`, edge-returned `action_result`, and runtime `interaction_update` frames preserve those identifiers and add `request_id` / `interaction_id` where applicable
- `RuntimeOrchestrator` now owns backend runtime-chain coordination for normal turns, direct actions, observation re-entry, and post-action re-entry, while `RuntimeGateway` remains focused on authentication, public frame validation/normalization, connection state, ingress persistence, event acknowledgements, and outbound WebSocket dispatch
- A real `Execution Planning` module now owns the proposal / presence-decision to action-or-completion outcome boundary on the normal runtime path
- Module-boundary diagnostics now record structured input/output events for the normal runtime chain across `Gateway`, `State / Context`, `Grounding / Runtime Memory`, `Proposal Formation`, `Presence Router`, `Execution Planning`, and `Action Layer`
- Edge-side diagnostics now record representative `Local Capability Runtime` and `Edge Session Link` boundary events for both text input normalization and observation frame preparation, so host-edge observation traffic also creates local JSONL diagnostics when `--diagnostic-log-path` is enabled
- Diagnostic recording is now starting to move inside module classes rather than being owned by the outer orchestration path: `Local Capability Runtime`, `Edge Session Link`, `Local Action Executor`, `Proposal Formation`, `Presence Router`, and `Execution Planning` each own their public input/output diagnostic boundaries, while lightweight coordinators such as `SessionClient` avoid writing downstream module logs
- Runtime, terminal-edge, and host-edge entrypoints now accept `--diagnostic-log-path` so manual multi-process acceptance runs can write physically separate local JSONL diagnostic logs without assuming shared frontend/backend storage
- Resident terminal live input now builds its `text.input` frames through the shared `SessionClient`, so manual terminal sessions carry `trace_id`, `session_id`, `turn_id`, and `event_id` like scripted/API edge traffic
- Gateway WebSocket dispatch now emits non-invasive `diagnostic.v1` records for cross-device reply delivery, including target connection presence and send status, and host-edge / terminal-edge local action execution now records its own `Local Action Executor` boundary without importing backend internals
- Host-edge startup observation handling now tolerates runtime observation errors without trapping later `action_request` frames behind an `event_ack` wait, and the compatibility runtime-health contract accepts unknown/null process start time while preserving strict observation validation elsewhere
- Chain inspection now includes `Diagnostic Events` alongside the previous trace, observation, snapshot, grounding, prompt, proposal, presence, intervention, replay, and action-result sections, so local acceptance can inspect architecture-module input/output records directly
- Automated coverage now includes diagnostic schema/JSONL behavior, correlation propagation, edge/backend dependency boundaries, runtime orchestrator delegation, execution planning outcomes, and chain-inspection diagnostic display

Acceptance criteria:

- Frontend and backend diagnostics use the same structured event shape while remaining locally recorded and physically separate
- Cross-boundary frames carry correlation identifiers that allow Edge and Runtime logs to be aligned without shared storage
- Manual runtime, host-edge, and terminal-edge processes can opt into local JSONL diagnostic logs through startup arguments
- Device-edge runtime code no longer depends on backend tracing internals for ordinary operation
- Gateway-to-runtime orchestration and execution planning are represented by explicit tested modules, with regression coverage ensuring `RuntimeOrchestrator` does not fall back to Gateway private runtime-chain implementations
- Inspect-chain output exposes module-boundary diagnostic events in the architecture chain

Status:

- Completed and accepted

### Completed: Project-level AGENTS enforcement baseline

Result:

- Project-level Codex hooks have been added in `.codex/hooks.json`
- Shared enforcement logic has been added in `agent_guard/codex_hooks.py`
- `AGENTS.md` now documents the internal per-turn audit and the conditional `Project.md Check` exception path
- Project progress updates are now also hook-enforced: when the user asks for a progress report, the response must include separate `Goal 1` through `Goal 5` sections with explicit architecture-aware labels for `状态`, `架构位置`, `本批完成`, `对整体链路的作用`, and `还缺什么`
- Edited turns are now also hook-enforced: when a turn uses `apply_patch`, the final response must include a `架构实现小结` block with explicit `架构位置`, `本步完成`, and `影响链路` labels
- A minimal automated test suite validates audit parsing and enforcement rules
- The hook entrypoint is now path-portable through `.codex/run_hook.py`, so `.codex/hooks.json` no longer hard-codes the repository checkout path

Acceptance criteria:

- The repository has project-level Codex hooks for session start and turn-end enforcement
- The enforced workflow validates that `Project.md` was read at session start
- The enforced workflow validates that every meaningful interaction performs a `Project.md` progress check
- The enforced workflow validates the required `Goal 1` through `Goal 5` architecture-aware structure for project progress updates
- The enforced workflow validates the required `架构实现小结` structure for edited turns
- The enforced workflow blocks inconsistent `Project.md` update claims while keeping normal responses free of mandatory visible audit output
- The hook configuration can survive repository folder renames by deriving the repository root from the checked-out project path

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
- The minimum v0 backend module set is `Gateway`, in-memory `State / Context / Task`, a same-device presence rule inside a minimal `Agent Runtime`, and an `Action Layer`
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
- A minimal `Agent Runtime` slice now generates text replies and the `Action Layer` converts them into `notification.show` requests
- A minimal `SessionClient` now builds connect, capability, and text-event frames and returns `action_result` payloads after local execution
- A minimal CLI edge runner can execute the whole loop locally from typed text input to printed notification output
- End-to-end tests now verify the single-edge roundtrip through gateway, edge session client, and local action execution
- Manual command-line verification now demonstrates the closed loop with `python3 -m device_edge.cli.cli_edge`

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
- The gateway can bypass the normal `Agent Runtime` path for that request, including `Presence Router`, and emit the requested action directly
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
- The repository-level development workflow now also documents the local Android edge path, including opening `device_edge/android_edge/` in Android Studio, verifying devices with `adb devices -l`, and using Android Studio as the normal debug install/run surface for the first M17 phone edge
- `bin/test` now provides a small helper that always uses the repository root `.venv`
- `bin/bootstrap-worktree-venv` now provides an explicit opt-in path for isolated worktree environments during dependency or packaging experiments
- Automated tests now verify the helper scripts and the documented shared-versus-isolated environment rules
- The default day-to-day repository workflow is now explicitly branch-first in the main workspace, with worktrees kept as an advanced optional path rather than the normal baseline
- The repository now documents a verification ladder: CLI device tests are acceptable for early validation, while host-edge verification is required before calling a module implemented and operationally ready

Acceptance criteria:

- The default development workflow for ordinary branch work in the main workspace is explicitly documented
- The isolated worktree environment exception path is explicitly documented
- The repository includes helper commands for both modes
- The environment workflow is covered by automated tests
- The project-level documentation explicitly distinguishes early CLI validation from host-edge operational verification

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

### Completed: First snapshot-driven presence decision slice

Result:

- The normal runtime path now builds a compact context snapshot from stored normalized observations before user-facing notification routing
- `Presence Router` now returns an explicit inspectable decision object rather than only a target device id
- The first live suppression rules now work on the hot path: ambiguous location context suppresses intervention, and a recent allowed intervention can suppress repeated follow-up actions when an explicit event timestamp is available
- The runtime now records intervention history separately from raw events and action results, and that history survives state serialization
- Automated tests now cover allowed intervention recording, ambiguous-context suppression, cooldown suppression, and intervention-history roundtrips

Acceptance criteria:

- The live runtime path evaluates an explicit presence decision before emitting a normal user-facing notification action
- The first presence decision slice can suppress at least one ambiguous-context case and one repeated-intervention case
- Intervention history is persisted as first-class runtime state for later policy refinement
- The new slice is covered by automated tests without regressing the existing v0 and M2 roundtrip behavior

Status:

- Completed

### Completed: First intervention-proposal live path slice

Result:

- The normal runtime path no longer jumps directly from compact snapshot into presence gating; it now builds an explicit inspectable intervention proposal first
- The early agent layer now exposes a minimal `InterventionProposal` shape for the normal notification path
- `Presence Router` now evaluates proposal-aware notification requests instead of inferring everything only from source device and capability lookup
- Allowed intervention history now records the proposal payload together with the later presence decision and target device choice
- Trace output and automated tests now cover the `snapshot -> proposal -> presence -> action` flow on the normal path

Acceptance criteria:

- The live normal path constructs an explicit proposal before evaluating a presence decision
- Presence evaluation can consume proposal data together with compact snapshot and intervention history
- Proposal-aware routing behavior is covered by automated tests without regressing existing roundtrip or host-edge behavior

Status:

- Completed

### Completed: First M4 mature host-edge runtime milestone

Result:

- The host edge can now run as an independent long-lived daemon process through `python -m device_edge.host.host_daemon`, rather than only as an in-process or one-shot control helper
- The host-edge runtime can now sustain continuous observation behavior with periodic idle-cycle sampling, post-action runtime-health follow-up, bounded reconnect/backoff handling, and bounded local observation history
- Runtime-scoped control remains available through the normal gateway path, including structured `runtime.status`, restart/recovery confirmation flow, and explicit edge-side history retrieval
- The repository now has both bounded automated verification and bounded local operational verification for the mature host-edge path, including `tests.test_host_daemon_v1`, `tests.test_roundtrip_v0`, and `bin/verify-host-edge`
- Manual verification visibility is now materially better on both sides of the edge boundary: the host daemon can emit local trace output, and the runtime now emits neutral startup readiness plus explicit edge-connected events to stdout

Acceptance criteria:

- The host edge can run stably as a standalone real edge surface outside the backend runtime process
- The host edge can continue or resume durable observation/control behavior across idle periods and backend disconnects instead of treating them as terminal failure
- The host-edge control path remains runtime-scoped and inspectable while preserving separate post-action health confirmation
- The host edge can be verified on its own through explicit edge-local and bounded end-to-end verification paths without waiting for later backend-maturity milestones

Status:

- Completed

### Completed: First M5 observation freshness and expiry slice

Result:

- Compact context snapshot building now supports an explicit snapshot reference timestamp instead of always treating the full stored observation history as equally current
- The first reducer-level freshness policy is now live for `user.location`, so stale location evidence ages out to `unknown` instead of continuing to drive presence decisions indefinitely
- The live gateway path now builds normal-path snapshots against the triggering event's decision time, which prevents expired conflicting location evidence from causing false ambiguity suppression
- Automated tests now cover stale-versus-fresh snapshot behavior and the live runtime path that must ignore stale conflicting location evidence during notification routing

Acceptance criteria:

- Snapshot reducers can evaluate freshness against an explicit reference time
- At least one presence-relevant field uses freshness filtering before returning a compact snapshot value
- The live gateway path uses a decision-time snapshot instead of a timeless observation-history read
- The new freshness slice is covered by automated tests without regressing the existing ambiguity and cooldown presence behavior

Status:

- Completed

### Completed: First M5 freshness-aware runtime health snapshot field

Result:

- The compact snapshot now exposes `runtime.current_health_state` as a first runtime-ingestion field derived from host-edge `runtime.health_state` observations
- Runtime-health snapshot values now use the same explicit snapshot-time freshness pattern as location evidence, so stale host-edge health reports age out to `unknown`
- The runtime can now carry one freshness-aware host-edge health signal in the compact snapshot without widening this batch into broader host-metric aggregation or policy changes
- Automated tests now cover fresh and stale runtime-health snapshot behavior alongside the existing location freshness slice

Acceptance criteria:

- The compact snapshot exposes at least one freshness-aware runtime-health field
- Stale runtime-health evidence resolves to `unknown` instead of remaining indefinitely current
- The new runtime-health snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slice

Status:

- Completed

### Completed: First M5 freshness-aware host metric snapshot field

Result:

- The compact snapshot now exposes `host.current_memory_pressure` as the first host-metric field derived from normalized `host.memory_pressure` observations
- Host memory pressure now uses the same explicit snapshot-time freshness pattern as location and runtime health, so stale host metric evidence ages out to `unknown`
- The runtime can now carry one compact freshness-aware host telemetry signal beyond runtime-specific health state without widening this batch into broader metric aggregation or agent-policy changes
- Automated tests now cover fresh and stale host memory pressure snapshot behavior alongside the earlier location and runtime health freshness slices

Acceptance criteria:

- The compact snapshot exposes at least one freshness-aware host metric field
- Stale host metric evidence resolves to `unknown` instead of remaining indefinitely current
- The new host-metric snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: Second M5 freshness-aware host metric snapshot field

Result:

- The compact snapshot now exposes `host.current_cpu_load_ratio` as a freshness-aware host-metric field derived from normalized `host.cpu_load_ratio` observations
- Host CPU load now uses the same explicit snapshot-time freshness pattern as location, runtime-side snapshot fields, and host memory pressure, so stale host CPU evidence ages out to `unknown`
- The runtime can now carry a second compact freshness-aware host telemetry signal without widening this batch into threshold policy, metric aggregation, or agent-behavior changes
- Automated tests now cover fresh and stale host CPU load snapshot behavior alongside the earlier M5 freshness slices

Acceptance criteria:

- The compact snapshot exposes a second freshness-aware host metric field
- Stale host CPU load evidence resolves to `unknown` instead of remaining indefinitely current
- The new host CPU snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: Third M5 freshness-aware host metric snapshot field

Result:

- The compact snapshot now exposes `host.current_memory_available_bytes` as a freshness-aware host-metric field derived from normalized `host.memory_available_bytes` observations
- Host available memory now uses the same explicit snapshot-time freshness pattern as location, runtime-side snapshot fields, host CPU load, and host memory pressure, so stale host memory-availability evidence ages out to `unknown`
- The runtime can now carry a third compact freshness-aware host telemetry signal without widening this batch into threshold policy, metric aggregation, or agent-behavior changes
- Automated tests now cover fresh and stale host available-memory snapshot behavior alongside the earlier M5 freshness slices

Acceptance criteria:

- The compact snapshot exposes a third freshness-aware host metric field
- Stale host available-memory evidence resolves to `unknown` instead of remaining indefinitely current
- The new host available-memory snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: Fourth M5 freshness-aware host metric snapshot field

Result:

- The compact snapshot now exposes `host.current_memory_used_bytes` as a freshness-aware host-metric field derived from normalized `host.memory_used_bytes` observations
- Host used memory now uses the same explicit snapshot-time freshness pattern as location, runtime-side snapshot fields, and the other host-metric fields, so stale host memory-usage evidence ages out to `unknown`
- The runtime can now carry a fourth compact freshness-aware host telemetry signal without widening this batch into threshold policy, metric aggregation, or agent-behavior changes
- Automated tests now cover fresh and stale host used-memory snapshot behavior alongside the earlier M5 freshness slices

Acceptance criteria:

- The compact snapshot exposes a fourth freshness-aware host metric field
- Stale host used-memory evidence resolves to `unknown` instead of remaining indefinitely current
- The new host used-memory snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: First M5 freshness-aware runtime process presence snapshot field

Result:

- The compact snapshot now exposes `runtime.current_process_present` as a freshness-aware runtime-ingestion field derived from host-edge `runtime.process_present` observations
- Runtime process presence now uses the same explicit snapshot-time freshness pattern as location, runtime health, and host memory pressure, so stale process-presence evidence ages out to `unknown`
- The runtime can now carry a second compact runtime-health-adjacent host signal without widening this batch into presence decisions, agent behavior, or broader reducer refactoring
- Automated tests now cover fresh and stale runtime process presence snapshot behavior alongside the earlier M5 freshness slices

Acceptance criteria:

- The compact snapshot exposes a freshness-aware runtime process presence field
- Stale runtime process presence evidence resolves to `unknown` instead of remaining indefinitely current
- The new runtime process presence snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: First M5 freshness-aware runtime process RSS snapshot field

Result:

- The compact snapshot now exposes `runtime.current_process_memory_rss_bytes` as a freshness-aware runtime-ingestion field derived from host-edge `runtime.process_memory_rss_bytes` observations
- Runtime process RSS now uses the same explicit snapshot-time freshness pattern as location, runtime health, runtime process presence, and host memory pressure, so stale process-memory evidence ages out to `unknown`
- The runtime can now carry a third compact runtime-health-adjacent host signal without widening this batch into threshold policy, aggregation, or agent-behavior changes
- Automated tests now cover fresh and stale runtime process RSS snapshot behavior alongside the earlier M5 freshness slices

Acceptance criteria:

- The compact snapshot exposes a freshness-aware runtime process RSS field
- Stale runtime process RSS evidence resolves to `unknown` instead of remaining indefinitely current
- The new runtime process RSS snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: Second M5 freshness-aware runtime process lifecycle snapshot field

Result:

- The compact snapshot now exposes `runtime.current_process_started_at` as a freshness-aware runtime-ingestion field derived from host-edge `runtime.process_started_at` observations
- Runtime process start time now uses the same explicit snapshot-time freshness pattern as location, the other runtime-side snapshot fields, and the host-metric fields, so stale process-lifecycle evidence ages out to `unknown`
- The runtime can now carry a fourth compact runtime-health-adjacent host signal without widening this batch into restart heuristics, policy changes, or broader time-semantics work
- Automated tests now cover fresh and stale runtime process started-at snapshot behavior alongside the earlier M5 freshness slices

Acceptance criteria:

- The compact snapshot exposes a freshness-aware runtime process lifecycle field
- Stale runtime process started-at evidence resolves to `unknown` instead of remaining indefinitely current
- The new runtime process started-at snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: First M5 freshness-aware runtime process identity snapshot field

Result:

- The compact snapshot now exposes `runtime.current_process_pid` as a freshness-aware runtime-ingestion field derived from host-edge `runtime.process_pid` observations
- Runtime process pid now uses the same explicit snapshot-time freshness pattern as location, the other runtime-side snapshot fields, and the host-metric fields, so stale process-identity evidence ages out to `unknown`
- The runtime can now carry a fifth compact runtime-health-adjacent host signal without widening this batch into restart heuristics, policy changes, or broader reducer refactoring
- Automated tests now cover fresh and stale runtime process pid snapshot behavior alongside the earlier M5 freshness slices

Acceptance criteria:

- The compact snapshot exposes a freshness-aware runtime process identity field
- Stale runtime process pid evidence resolves to `unknown` instead of remaining indefinitely current
- The new runtime process pid snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: M5 decision-time snapshot contract and evidence baseline

Result:

- `State / Context` now exposes a parallel decision-time snapshot contract view in addition to the compact field dict, so each snapshot field can be inspected as `value + status + bounded supporting evidence`
- The snapshot contract now records explicit field states for `fresh`, `stale`, `missing`, and `ambiguous` outcomes instead of leaving those semantics implicit inside reducer-local behavior only
- The compact hot-path API remains unchanged for current callers, while the broader runtime now has a stable inspection surface for replay, debugging, and later agent-side deeper reasoning
- Automated tests now cover fresh, stale, missing, and ambiguous contract states without regressing the earlier compact snapshot field-pack behavior

Acceptance criteria:

- The runtime exposes a decision-time snapshot contract alongside the compact snapshot field dict
- The contract makes freshness / ambiguity / evidence status explicit per field
- Supporting evidence remains bounded and inspectable rather than widening the compact snapshot into a raw-history mirror
- The new contract behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: M5 gateway-to-presence input verification baseline

Result:

- The live gateway normal path now records the exact decision-time snapshot contract that was used when building a proposal and evaluating a presence decision
- Intervention history can now show whether runtime and host telemetry was consumed as fresh evidence or aged out as stale evidence on the real gateway path, rather than only proving that local reducers return the right value in isolation
- The runtime now has a concrete human-inspectable verification surface for M5 acceptance: recorded interventions include the compact decision input contract together with proposal, decision, reason, and target device
- Automated tests now cover live intervention recording for both fresh and stale runtime-health-adjacent telemetry without widening this batch into richer presence-policy changes

Acceptance criteria:

- The gateway normal path records the decision-time snapshot contract used for intervention evaluation
- Recorded interventions can distinguish fresh versus stale runtime/host telemetry on the live path
- The end-to-end verification surface is inspectable enough for human acceptance of M5 as a runtime-ingestion/context milestone
- The new live-path verification behavior is covered by automated tests without regressing existing gateway routing behavior

Status:

- Completed

### Completed: M5 runtime-ingestion and context-maturity milestone acceptance

Result:

- `M5` has now been accepted as complete using real host-edge input instead of relying only on inspection-injected sample observations
- The normal `Gateway -> State / Context -> Presence` path now has human-inspectable acceptance evidence across raw edge events, normalized observations, compact snapshot fields, explicit snapshot contract state, and recorded interventions
- Human acceptance can now inspect both runtime-side persisted evidence and edge-side daemon trace output for the same live decision-time chain
- The live-path acceptance pass also closed two real verification gaps: `python -m device_edge.cli.cli_edge --inspect-chain` now executes through the module entrypoint, and snapshot freshness reduction now accepts fractional-second observation timestamps emitted by the real host daemon

Acceptance criteria:

- `M5` is accepted through the normal gateway path using real host-edge telemetry
- Decision-time snapshot input remains inspectable in recorded intervention history rather than only through isolated reducer tests
- Human verification can inspect both runtime-side and edge-side evidence for the same live chain
- Real host-daemon timestamp shape does not break snapshot freshness evaluation on the live path

Status:

- Completed

### Completed: M6 dual-entry proactive runtime milestone acceptance

Result:

- The live runtime now supports both sense-first and agent-initiative proposal entry paths on top of the accepted M5 observation and snapshot surface
- The backend can now trigger an explicit `agent_initiative` proposal from runtime-owned state rather than relying only on an edge-originated text event to start the normal path
- Both entry paths now rebuild a decision-time compact snapshot and snapshot contract, form an inspectable intervention proposal, and converge on the same explicit `Presence Router` before action planning
- The accepted `M6` proposal-formation slice remains intentionally narrow: ordinary sense-first text input still collapses into a reply-shaped `notification.show` proposal rather than a fully generalized proposal-typing system
- The normal allowed path now supports both user-facing `notification.show` actions and narrow host-control actions such as `runtime.status` without falling back to the direct-action bypass
- Initiative proposals can now carry action payload, proposal source, bounded metadata, and a target-device hint while still remaining subject to cooldown and ambiguity suppression on the shared presence path
- The repository now has a dedicated M6 local inspection entrypoint: `python -m device_edge.cli.cli_edge --inspect-agent-initiative`, which prints trace, observations, snapshot, snapshot contract, proposal, presence decision, recorded intervention, and action result for one initiative-triggered run
- Automated tests now cover runtime-triggered initiative entry, cooldown suppression on the initiative path, CLI initiative triggering, initiative chain inspection, and a real websocket host-edge `runtime.status` roundtrip driven by runtime-side initiative dispatch

Acceptance criteria:

- The live runtime supports both sense-first and agent-initiative proposal entry on top of stable real-edge input
- Both proactive entry paths converge on the same explicit `Presence Router`
- Allowed actions can continue into at least one user-facing notification path and one narrow host-control path without using the direct-action bypass
- M6 behavior is covered by automated tests and a human-readable inspection path for manual acceptance

Status:

- Completed

### Completed: M9 cloud-model-backed agent baseline acceptance

Result:

- The runtime now has a formal provider boundary inside `Agent Runtime`, with runtime model configuration split into provider, model, and profile layers instead of hard-coded provider/model selection inside proposal-generation call sites
- The first accepted adapter path is a narrow but mature `openai_compatible` slice, preserving explicit `Presence Router` governance, inspectable proposal metadata, and bounded deterministic fallback behavior on the normal runtime chain
- Normal text replies now carry inspectable `llm_profile`, `llm_provider`, `llm_model`, and `used_deterministic_fallback` metadata through proposal recording and chain-inspection surfaces, so human acceptance can distinguish real model execution from local fallback behavior
- The repository originally accepted a tracked default `config/llm-config.toml`, explicit provider-level header configuration for future multi-provider compatibility hardening, and a runtime startup path that only used non-default LLM config when an explicit config path was provided; M15 has now moved real provider setup to ignored local `config/runtime-config.toml` plus tracked `config/runtime-config.example.toml`, keeping provider route, model/profile selection, and API key together in one runtime-owned config file
- The previously tracked CRS provider path passed the original Cloudflare `1010` gateway block after adding an explicit runtime `User-Agent`, but a fresh real-runtime recheck on 2026-06-25 still showed mixed behavior on the same `https://api-cf.cubence.com/v1` `/responses` route: at least one `crs_main` / `gpt-5.4` proposal call returned a valid structured `reply`, while later calls the same day returned completed payloads with empty `output` plus a Codex-agent instruction envelope instead of plain runtime response content, so that route should now be treated as a non-default comparative provider path rather than the tracked manual-acceptance baseline
- Runtime provider handling now treats that 2026-06-25 CRS response shape as an explicit incompatibility signal and surfaces the real failure reason to the user, rather than fabricating a conversational fallback or hiding the issue behind a generic parse miss
- A same-machine manual comparison on 2026-06-25 also showed that `master` could still complete ordinary natural-language terminal dialogue under the same resident terminal startup path, so the currently observed dialogue regression should no longer be treated as proven provider-wide outage by default; the stronger working hypothesis is now that the feat-branch runtime/provider changes introduced a branch-local regression on top of a still-usable upstream route
- Local runtime and CLI regression tests are now isolated from ambient machine-local config through explicit test config injection, so automated verification stays deterministic while non-default manual acceptance must opt in deliberately

Acceptance criteria:

- The runtime can use a real cloud model for proposal and reply generation through a formal provider/configuration boundary rather than a one-off hard-coded call path
- Real model-backed replies remain subject to the existing normal `Gateway -> State / Context -> Presence -> Action` chain instead of bypassing `Presence Router` governance
- Human inspection can distinguish real provider execution from deterministic fallback through recorded proposal metadata and existing local inspection entrypoints
- The first accepted implementation is covered by automated tests and verified end to end against at least one real `openai_compatible` provider path

Status:

- Completed

### Completed: M10 model grounding and runtime memory baseline acceptance

Result:

- The runtime now builds an explicit runtime-native grounding bundle for model-backed reply and proposal generation instead of passing only raw user text plus compact snapshot into the provider layer
- The first accepted grounding bundle is intentionally small and inspectable: it includes compact snapshot state, active runtime goals, bounded recent runtime memory for user inputs/interventions/action results, and a bounded edge-history window
- Durable runtime goals now live inside persisted `RuntimeState`, so active goal context survives restart and can shape later grounded model calls without inventing a separate side store
- Proposal metadata now records grounding provenance such as bundle version, active-goal count, recent-memory counts, and whether bounded edge history was attached, so inspection and replay can distinguish grounded runtime-native calls from thinner prompt shapes
- The local inspection chain now performs an explicit bounded `runtime.edge_history` retrieval through the host-edge control surface and prints the resulting `Grounding Bundle` alongside the compact snapshot, proposal, presence decision, and recorded intervention for human acceptance
- The repository now has targeted automated coverage for grounding-bundle construction, bounded recent-memory shaping, goal persistence shape, provider-request grounding injection, and inspection visibility for the first `M10` slice
- The resident terminal edge exit path has now been tightened so live `stdin` handling no longer relies only on a background-thread `readline()` path in normal TTY use; the daemon now prefers event-loop reader integration for real terminal input and explicitly cancels pending live-input tasks on session exit, reducing the previous need for repeated `Ctrl+C` to terminate the CLI device cleanly

Acceptance criteria:

- Model-backed proposal and reply generation are grounded in compact snapshot state, active runtime goals, bounded recent runtime memory, and explicit bounded edge-history retrieval rather than behaving like stateless channel chat
- Grounding remains runtime-native and inspectable instead of silently collapsing into opaque chat transcript prompting
- The first accepted implementation keeps edge-history retrieval explicit and bounded rather than continuously mirroring fine-grained device history into backend state
- Human inspection can verify the grounded bundle and proposal grounding metadata through an existing local acceptance entrypoint

Status:

- Completed

### Completed: M11 terminal/CLI interaction maturity acceptance

Result:

- The first resident terminal edge now has a thin but human-usable edge-local UX layer on top of the unchanged normal runtime chain, including readable `[system]`, `[user]`, and `[runtime]` session rendering instead of raw undifferentiated stdout output
- The preferred foreground terminal surface now also includes a first full-screen Textual `--tui` mode with a fixed status bar, scrollable transcript pane, and dedicated input box, while keeping the earlier line-oriented daemon path as a compatibility fallback on the same terminal-edge/runtime session chain
- The terminal daemon now keeps a bounded readable local transcript plus explicit session counters and visibility state, so a foreground terminal user can inspect recent interaction flow and current edge state without digging into backend state files
- The first local command affordances are now implemented directly on the terminal edge as edge-local ergonomics rather than backend special cases: `/help`, `/status`, `/history`, and `/quit` stay local to the edge and do not become normal `text.input` runtime traffic
- Resident terminal behavior remains compatible with the accepted presence-governed runtime architecture: normal user text still flows through the usual `Gateway -> State / Context -> Agent Runtime -> Presence Router -> Action Layer` path, while runtime push still depends on terminal activity evidence and explicit terminal target locking
- The bounded acceptance path now covers both the earlier M8 terminal behaviors and the new M11 CLI maturity affordances: `bin/verify-terminal-edge --dry-run` exposes the local command verification intent, and the real `bin/verify-terminal-edge` run now verifies one pull interaction, one active terminal push allow, one idle terminal push suppress, and persisted terminal-delivery evidence without depending on a provider-specific reply string
- The repository now has targeted automated coverage for local terminal command handling, readable session status/history output, runtime message rendering, resident-session behavior after live stdin EOF, and the updated terminal-edge verification/documentation surface

Acceptance criteria:

- The resident terminal edge exposes materially better session readability and human-usable local CLI affordances without introducing a backend-side chat exception path
- Local terminal commands stay edge-local and do not silently mutate the normal runtime protocol path
- Runtime-delivered terminal output remains presence-governed and verifiable on the real runtime chain rather than being faked through local-only shortcuts
- The milestone is covered by targeted automated tests plus a bounded real `bin/verify-terminal-edge` acceptance run

Status:

- Completed

### Completed: M12 prompt/context engineering and behavior-contract acceptance

Result:

- The runtime now has an explicit prompt/context assembly layer inside `Agent Runtime`, so grounded model-backed reply generation no longer formats compact snapshot and grounding state as ad hoc provider strings only
- The first accepted prompt/context package is versioned as `m12.v1` and keeps its inspectable sections intentionally small: `compact_snapshot`, `active_goals`, `recent_memory`, and bounded `edge_evidence`
- Proposal metadata now records explicit prompt/context provenance such as prompt version, section names, bounded section counts, and behavior-contract check results, so recorded interventions can show whether the normal runtime path actually carried the intended grounded state into the model-facing layer
- The local chain-inspection report now exposes `Prompt Context`, `Behavior Contract`, and `Replay Eval` sections as first-class inspection surfaces on the same live runtime chain that already prints observations, compact snapshot, grounding bundle, proposal, presence decision, and recorded intervention
- The repository now has a bounded local M12 acceptance entrypoint: `bin/verify-prompt-contract` prints one grounded inspection report, verifies the explicit prompt/context and behavior-contract surfaces, and confirms a replay/eval pass on the recorded prompt package without requiring a second provider call
- The repository now has targeted automated coverage for explicit prompt/context assembly, behavior-contract checks, provider-request prompt injection, prompt-contract inspection output, and the new verification/documentation surface

Acceptance criteria:

- Grounded model-backed proposal and reply generation use an explicit prompt/context assembly surface rather than only thin prompt wiring
- Prompt/context versioning is inspectable through recorded proposal metadata and local inspection output
- The runtime exposes a behavior-contract surface that verifies compact snapshot state, active goals, bounded recent memory, and bounded edge evidence are present and internally consistent with the grounding bundle
- A bounded replay/eval acceptance path can re-check the recorded prompt package locally without depending on a fresh provider response

Status:

- Completed

### Completed: M13 proposal-formation maturity acceptance

Result:

- The normal sense-first live chain can now emit inspectable runtime-owned proposal outcomes from ordinary edge-delivered text without bypassing `Presence Router`; after M17.6 hardening, normal outcomes are `action` and `no_intervention`
- Proposal formation now consumes compact snapshot state, active goals, bounded memory, and bounded edge evidence on the actual runtime path, while recorded interventions and inspection output expose structured proposal rationale together with provider/fallback metadata
- The provider boundary now supports structured proposal-plan parsing, provider proposal-type normalization, and deterministic grounded fallback when the model is unavailable, without adding a redundant middle interpretation layer beyond the documented hot path
- The live provider compatibility layer is now more tolerant of real structured-proposal response variants as well: string-valued actions such as `respond`, reply-text aliases such as `response`, and string rationale summaries are normalized onto the accepted `notification.show` / structured-rationale runtime shape instead of silently suppressing delivery after a successful model call
- The local inspection and acceptance ladder includes bounded M13 tooling: `python -m device_edge.cli.cli_edge --inspect-chain` prints proposal type and rationale on the live chain, and `bin/verify-proposal-formation` now exercises visible action, runtime-control action, and `no_intervention` scenarios end to end
- Fresh targeted automated verification and bounded human acceptance prove the runtime-owned proposal taxonomy on representative live terminal/runtime interactions, including the `no_intervention` path recording a proposal and ending with a suppressed action result instead of dispatch
- The accepted first `M13` slice still executes at most one current `primary action` per planning turn; that is an intentional implementation bound for the slice, not a claim that future interaction handling should remain permanently single-step
- The accepted `M13` boundary stops at first-turn proposal typing plus primary-action dispatch; post-action semantic handling remains intentionally out of scope here and is now promoted into explicit `M16` action-loop work rather than being represented by a completion-summary patch

Acceptance criteria:

- The normal live chain can emit inspectable `action` and `no_intervention` proposals from edge-delivered signals without bypassing `Presence Router`
- Proposal formation consumes compact snapshot state, active goals, bounded memory, and relevant edge evidence on the actual runtime path rather than falling back to raw text-only heuristics
- Proposal records expose enough structured rationale to inspect why a given input became a visible/side-effectful action or a no-intervention decision
- The accepted live-chain implementation does not grow redundant middle layers beyond the documented `event -> compact snapshot -> grounding bundle -> prompt/context package -> proposal formation -> Presence Router -> execution planning/action` shape
- Narrow deterministic fallbacks remain available when the model is unavailable, while the provider boundary stays ready for model-backed structured proposal output
- Automated tests cover visible user-facing actions, runtime-control actions, and ambiguity/suppression handling
- Human acceptance demonstrates action and no-intervention outcomes with readable inspection output on the live runtime path

Status:

- Completed

## Open Questions

- Which device surfaces should be the first non-CLI surfaces for presence-first experiments?
- What is the smallest reliable terminal-presence signal set that is good enough for runtime push decisions without overfitting to one shell or multiplexer?
- Which concrete `openai_compatible` providers and model families should be implemented first after the shared provider boundary lands?
- What is the minimum grounding bundle every model call should receive from runtime state, snapshot, and goal context?
- When should explicit profile-selected model calls grow into automatic provider/model fallback and broader strategy routing?
- What is the smallest safe operational-control surface for the first host edge, and how should that surface be constrained so it stays inspectable?
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
- Treat the runtime's own hosting server as the first host-class `Device Edge` candidate for early non-CLI presence and operations work
- Model that host edge as a first-class device/capability participant rather than hiding it inside backend-only monitoring code
- Keep operational control in scope for that first host edge, but constrain it to an explicit capability surface rather than arbitrary shell access
- For the first host-edge control slice, prefer host-wide observation together with runtime-scoped control rather than immediate whole-server operational control
- Keep host-edge capability contracts stable while allowing the runtime-control execution backend to vary by deployment model
- For v1, implement runtime-scoped control against the current plain Python process shape first, while preserving a later adapter path for `systemd`-managed deployment
- For `runtime_control`, prefer deployment-agnostic action names such as `status`, `restart`, `reload`, and `collect_logs` over backend-specific verbs
- For `runtime.collect_logs`, prefer a structured result surface first while still carrying raw tail text for debugging compatibility
- Keep the first host edge as an independent frontend-side daemon rather than a module inside the backend runtime process
- The desktop/CLI edge should now be treated as the preferred first formal long-running interaction surface rather than only as a validation harness
- Treat terminal conversation as one capability surface inside that edge, not as a special top-level product abstraction
- The first terminal edge should support both pull-style user requests and push-style runtime interventions, but push should depend on terminal presence or activity instead of blindly printing into unattended terminals
- Model terminal-side user input, activity or idle evidence, runtime-originated message delivery, reply, and ignore or non-response as ordinary edge events and actions on the normal runtime path instead of inventing a chat-only side protocol
- Keep terminal-edge intelligence thin: local UX control may exist on the edge, but proposal formation, intervention policy, and routing authority should remain in the backend runtime
- Prefer the post-M7 milestone sequence to stay narrow and layered: M8 formal terminal edge first, M9 cloud-model agent baseline second, M10 grounding and memory third, M11 terminal/CLI interaction maturity fourth, M12 prompt/context engineering fifth, M13 proposal-formation maturity sixth, M14 model-provider connection reliability and diagnostics seventh, M15 runtime-native credential/runtime-config baseline eighth, M16 post-action deliberation/action loop ninth, M17 multi-edge interaction expansion tenth, accepted M20 Agent Harness and runtime action-loop refactor eleventh, M20.2 interaction-progress presentation twelfth, M20.3 stable Terminal Edge thirteenth, M17.8 sensitive-screen governance fourteenth, broader M18 Agent Harness-controlled observation understanding fifteenth, M19 bounded-growth/storage-hygiene hardening sixteenth, M20.1 governed skill lifecycle seventeenth, M21 policy learning/review eighteenth, M22 first packaged three-end product slice nineteenth, and M23 Home Assistant / smart-home ecosystem bridge last
- Prefer cloud-model proposal and reply generation to stay behind a provider boundary inside `Agent Runtime`, with explicit presence governance and normal edge routing still deciding whether and where anything surfaces
- Prefer a hybrid model-provider architecture for `M9`: keep a shared provider registry, model catalog, and runtime-facing profile-selection layer, while implementing only the `openai_compatible` adapter branch in the first accepted slice
- Prefer runtime call sites to select named model profiles rather than hard-coding provider/model pairs directly in business logic, so later provider swaps and model-routing changes stay configuration-driven
- Prefer OpenClaw-style separation between explicit selection, provider/auth failover, model fallback, and later strategy routing; the runtime should not silently treat those as one undifferentiated mechanism
- Defer automatic provider/model strategy routing until after the first grounded model stage, rather than hiding routing policy inside the initial `M9` provider-integration batch
- Prefer model grounding to be runtime-native: model calls should consume compact snapshot, active goals, bounded retrieved edge evidence, and durable runtime state rather than raw channel transcripts alone
- Prefer feedback-driven policy evolution to remain review-gated even after model-backed behavior arrives, so the runtime does not silently rewrite durable intervention policy from weak evidence

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
- Use the runtime's own hosting server as the first host-class edge candidate so M3 can learn from real host telemetry rather than only typed CLI input
- Treat that host edge as both an observation source and a future operational-control surface, with a small inspectable capability boundary
- Lock the first host-edge control boundary to `host-wide observation + runtime-scoped control` so the first operational loop stays auditable and easy to test
- Keep the `runtime_control` contract deployment-agnostic and treat Python-process control as the first concrete adapter rather than the permanent execution model
- Keep `runtime_control` responses structured enough for agent reasoning and UI inspection, while allowing raw diagnostic payloads to ride alongside when helpful
- Let `runtime_control.restart` initiate restart from the independent host edge, and let post-restart confirmation arrive later through separate `runtime_health` observations rather than synchronous self-confirmation
- Capture the first host-edge daemon shape and implementation ladder explicitly in `docs/plans/2026-06-19-host-edge-v1-design.md` and `docs/plans/2026-06-19-host-edge-v1-implementation-plan.md`
- Treat the current host-edge batch as a foundation rather than a finished endpoint; keep that completion work out of M3 and carry it in later milestones instead: M4 for a mature standalone host edge, M5 for backend ingestion/context maturity on top of that input, M6 for presence/agent/action maturity on real edge input, and M7 for end-to-end operational-readiness verification

## Current Project Progress

Current phase:

- Post-M16 architecture expansion has completed and accepted `M17.0` public Edge API boundary/internal-runtime encapsulation, `M17.1` registration-driven multi-device extension, `M17.2` native Android Presence Edge, `M17.3` Android daily-use hardening, `M17.4` Mobile Edge product UI implementation, `M17.5` Android screen/context observation baseline, `M17.6` multi-edge lineage/fail-fast semantics, `M17.7.1` Android Edge continuous background observation steady state, `M17.7.2` Runtime mobile observation liveness watchdog and wake recovery, `M18.1` observation-to-snapshot decision-space integration, the module-boundary diagnostics v1 baseline, and `M20` Hermes Agent Harness/runtime action-loop implementation. The renewed configured-provider Terminal/Android run accepts the governed `ActionBatch`, full result-set continuation, scoped child-session shared context, semantic roster targeting, and requester outcomes. The recorded execution route is M20.2, M20.3, M17.8, broader M18, M19, M20.1, M21, M22, and M23.

## Next Execution Route

1. `M20.2` OpenHalo interaction-progress presentation: define and deliver the safe Runtime-to-Edge progress lifecycle that replaces embedded Hermes terminal display.
2. `M20.3` Terminal Edge stable CLI/TUI: turn that lifecycle and the existing terminal session into a resilient, application-quality OpenHalo CLI surface.
3. `M17.8` mobile sensitive-screen capture governance: close the allowlist-first privacy boundary before expanding what the agent can learn from phone observation.
4. Broader `M18` Agent Harness-controlled observation understanding: build the edge-led attention and safe-evidence loop on top of the accepted Harness, progress-capable interaction surfaces, and M17.8 boundary.
5. `M19` bounded growth and storage hygiene: set retention, compaction, and operational pressure controls after the final observation flow is known.
6. `M20.1` governed procedural-memory and skill lifecycle: introduce inspectable, OpenHalo-owned skill drafts only after the relevant evidence, retention, and audit shape has stabilized.
7. `M21` policy learning and review: turn feedback and replay evidence into review-gated policy candidates.
8. `M22` productization: package the server/runtime, desktop, and phone as one installable three-end system.
9. `M23` Home Assistant and smart-home bridge: add the ecosystem bridge after the core product surface is stable.

This is execution priority, not milestone-number order. Existing accepted M17/M18.1 foundations remain available for preparation and maintenance work, but they do not displace the next acceptance target.

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
- We now have a completed M5 runtime context surface: normalized host/runtime observations feed a compact snapshot field-pack, a decision-time snapshot contract with explicit evidence states, and a live gateway intervention record that preserves what the runtime actually consumed
- M18.1 is accepted: compact snapshot contracts expose passive mobile decision-space evidence for app visibility, notification permission, connection state, runtime-derived observation liveness, and bounded screen context; live test-runtime acceptance verified fresh Android background observation, snapshot evidence marking, and inclusion of those mobile fields in the Agent Runtime prompt/context package
- The durable M18 architecture direction is edge-led attention plus source-neutral interactions: Edge-defined attention events let the Harness notice local changes without a centralized semantic taxonomy; an ingress guard retains only privacy, provenance, causal, deduplication, rate, and budget control; the Harness may silently consume the event, request bounded safe evidence, defer it, or create a normal Interaction Pool record. Once created, that interaction has the same lifecycle as chat, agent-initiative, and action-result-driven work; `Presence Router` arbitrates user-facing delivery across the shared pool.
- The bounded M18 backend slice is implemented and Python-verified: a deterministic gate admits only high-salience non-parented evidence, coalesces persistent failure episodes, creates ordinary Interaction Pool records, uses an observation-specific provider contract with M18-safe screen-context projection, routes through Presence, and binds action results to both their exact turn/request lineage and selected target edge. Runtime-only replay against `android-openai-dev-state.json` processed 1432 observations with 1427 skips, 5 defers, 0 triggers, and 0 action dispatches; this is offline admission evidence, not a substitute for multi-edge human acceptance.
- This bounded implementation still uses a fixed gate and therefore does not yet realize the final Agent Harness-controlled attention model: it cannot adapt observation relevance from the agent's evolving understanding of the user or current situation, nor consume Edge-defined attention events as the primary sense-first wake signal. M20 ActionBatch revalidation is now accepted, so broader M18 may resume implementation on the restored Harness foundation.
- The M20 Harness foundation is implemented on the `codex/m20-harness-foundation` development branch. OpenHalo pins `NousResearch/hermes-agent` at `e12626b34fb1024bf00f40f4759647f9cbd3f198`; real-use config selects `HermesHarnessRunner`, while explicit legacy fixtures preserve offline regressions. The action bridge captures rather than dispatches `openhalo_action`, normalizes Hermes notification payloads to the registered OpenHalo edge contract, and passes every governed intent through behavior/capability validation, Presence, execution planning, action-result envelope recording, and post-action re-entry; multiple external Hermes action intents fail closed, unbound or mismatched Harness envelopes fail closed again in execution planning, and unimplemented runtime-local/MCP/skill executors remain inspectable placeholders rather than edge dispatches. Curated pinned-IP `fetch` plus configured `search` record untrusted, body-free provenance instead of globally forbidding action/memory after research: a research-assisted low-risk reply must bind to the authenticated normal user request and still pass runtime validation and Presence, while cross-device/runtime/unknown elevated actions become confirmation-required and fail closed. Hermes-native `MEMORY.md`/`USER.md` remain the only durable semantic-memory content store and survive a fresh runner; only normal audited turns expose the native memory write tool, while action-result and observation re-entry retains read context but excludes that tool at both schema and low-level dispatch gates. The native memory tool may autonomously add, replace, remove, or batch-consolidate compact user/profile and agent-operational entries under the behavior contract, while OpenHalo records only body-free integrity/provenance, scope, and Hermes task/tool-call references without a second memory body. M20 seals periodic Hermes background memory/skill review off (`nudge_interval = 0`) because its fresh-agent turn model cannot realize that cadence and a future review fork must first be made auditable. Research is a source marker rather than a global memory block, but remote instructions, role claims, and tool directives must not persist. Configured-provider human acceptance previously passed the governed action, public fetch, research-assisted reply, public search, hostile fixture hash with zero action/memory writes, and fresh-session native-memory recall, with only hashes retained in `.runtime/m20-harness-live-evidence.json`. The unified canonical `notification.show {title?, body}` contract is now implemented. Fresh configured-provider Terminal Edge human acceptance confirmed normal reply delivery and OpenHalo user-facing identity without Hermes/Nous attribution. The final Android cross-edge human acceptance then completed the sequence: the Runtime roster exposed exact Terminal and Android identities/capabilities, 4 explicit user interactions completed with 7 persisted `ok` action results, and each requester received its final outcome. The embedded Hermes scope is serialized inside the Personal Runtime process and does not support unrelated unconstrained Hermes co-hosting. Both research capabilities run without a browser binary or GUI; browser-backed rendering is deferred, no browser tool or configuration path is registered in M20, and it is absent from the acceptance ladder. M20.1 now owns governed procedural-memory and skill drafts; M20.2 owns the Runtime-owned, Edge-native progress presentation for active visible interactions; M20.3 owns the stable application-quality Terminal Edge that displays those interactions; broader M18 may build on this accepted Harness foundation.
- Android revalidation exposed a target-selection context gap rather than an Android notification-contract failure: Hermes was asked to choose a target without a structured online device/capability view and defaulted a phone-directed request to its Terminal source. The implemented M20 correction projects the Runtime-owned device roster into every Harness grounding/prompt context and requires Hermes to perform semantic target choice from exact roster IDs; Runtime continues to validate and govern that choice, but does not replace it through keyword routing. Fresh configured-provider Android cross-edge acceptance passed with the registered `terminal-edge-1` and `android-edge-782d0247` roster.
- The M20 post-action acceptance contract now distinguishes logical requesters from evidence sources. An explicit user event records `initiator_kind=explicit_user_intent`, its requesting device, and an outcome-delivery obligation; passive Edge observations and agent initiative record no requester obligation and therefore receive no automatic result report. After a cross-device explicit user action settles, Hermes receives a structured `action_result_context` and must acknowledge the requester. If it returns `no_intervention` or a provider failure instead, Runtime creates a narrowly authorized `runtime_outcome_fallback` notification to that exact requester and still subjects it to Presence and Execution Planning. The previous Android attempt is retained as the negative case: the phone action succeeded but the Terminal did not receive its final outcome. The final configured-provider Android acceptance verified both deliveries: 4 explicit interactions completed, with requester outcome updates sent to both Android and Terminal surfaces.
- M20 Android revalidation then found two governance defects: Hermes implementation identity had leaked into `InterventionProposal.source`, and the old fixed five-minute global Presence cooldown suppressed subsequent explicit interactions. Hermes adapter output now uses Runtime semantic sources (`sense_first`, `agent_initiative`, `post_action`, `post_observation`, or `observation_driven`) while retaining Hermes only as harness metadata; the global cooldown is removed. This restores ordinary user turns and same-interaction confirmations without weakening the remaining concrete Presence checks.
- The prior M20 configured-provider Android human run on 2026-07-17 remains valid evidence for single-action routing, requester outcomes, Hermes memory, research, and canonical notification delivery. A later retry exposed an unaccepted control-flow hole: one valid Hermes deliberation emitted two external action intents, and the adapter incorrectly converted the batch into `no_intervention`. M20 is therefore reopened for ActionBatch/result-set remediation; the residual Hermes stdout progress indicator remains a separate operational-presentation concern owned by M20.2.
- The ActionBatch/result-set remediation is implemented and automatically verified: Hermes bridge calls normalize into deduplicated batches with unique action IDs; InteractionPool persists child-session identity, batch/action/request lineage, and `awaiting_action_results`; Runtime validates every batch member, runs Presence and execution planning per member, dispatches the whole valid batch, blocks same-interaction observation re-entry while actions remain pending, and resumes the same child-session contract once with the ordered complete result set. The same batch path covers normal, observation-driven, post-observation, and post-action turns. The renewed configured-provider Terminal/Android human acceptance on 2026-07-17 passed on a clean Runtime state: registered `terminal-edge-m20` and `android-edge-782d0247` completed 6 explicit-user interactions with 12 persisted `notification.show` action results, all `ok`; the live run included one 3-action and one 2-action initial batch, each with distinct request/action lineage, before their same-child-session continuations and final requester updates. Runtime diagnostics recorded zero dispatch or planning failures, and the focused ActionBatch/runtime-state regression suite passed 138 tests (4 intentional skips). This closes the M20 completion gate and returns M20 to accepted status.
- The bounded M18 integration suite now also proves the positive action path in-process: a fresh degraded runtime-health observation creates an observation-driven interaction, receives an allowed visible notification action on an active terminal, accepts the exact correlated action result, and completes that interaction. This validates Runtime behavior but does not replace real multi-edge human acceptance.
- We have now explicitly accepted and marked `M5` complete in the project baseline after live host-edge verification of the `observation -> snapshot -> intervention` chain
- We have now decided not to plan around direct OpenClaw gateway server reuse for implementation
- The earlier OpenClaw source audit remains useful as reference, especially around protocol and client transport patterns, but no longer drives the main delivery path
- We have explicitly defined that all physical frontend/backend communication must be funneled through `Edge Session Link <-> Gateway`
- We have partially defined the frontend/backend contract around capability events, state sync, action commands, and execution results
- We have now added an `M17.0` Edge API interaction flow diagram to the runtime architecture baseline, showing how external, terminal, and host edges connect, announce capabilities, push events or observations, receive action requests, return action results, and preserve interaction updates through the public API boundary
- We have completed and accepted the `M17.0` implementation baseline: a public `edge_api` package now defines versioned Edge API frame helpers, terminal and host edges build frames through the public API wrapper, Gateway accepts versioned public frames including `observation_push`, action requests and interaction updates carry the public API envelope, and an external-edge raw-frame test validates a full connect/capability/observation/event/action-result turn without importing runtime internals
- We have completed and accepted the `M17.1` registration-driven extension baseline: rich capability and observation-provider registration now flows through the public Edge API, runtime registries persist device/capability/observation metadata, Gateway rejects unregistered or schema-mismatched observations, Execution Planning resolves registered provider candidates after Presence Router, and bounded multi-surface verifier evidence covers phone notification selection over public speaker and ambient light alternatives
- We now prefer an agent-centered but presence-governed product reading of the architecture: the runtime should let the agent form intervention proposals while requiring explicit presence decisions before surfacing itself
- We now treat the current `Presence Router` concept as a broader intervention-governance layer inside the agent runtime rather than a narrow routing helper
- We now prefer durable proactive behavior to live in explicit or inspectable policy that can be created and revised by agent/model loops instead of only in end-to-end opaque model behavior
- We now expect future runtime state for Goal 2 to include intervention history and experience feedback signals so the system can learn from how users react to proactive actions
- We now explicitly treat a single ignored intervention as weak evidence rather than a definitive negative outcome
- We now want policy refinement to consider both present interaction quality and likely future user-experience impact, not just the immediate result of the latest action
- We now want the first real non-CLI edge to be the runtime's own hosting server, represented as a first-class edge rather than hidden backend instrumentation
- We now want that first host edge to evolve beyond passive observation into an explicit operational-control surface, while still keeping the control boundary narrow and inspectable
- We now prefer the first host-edge capability envelope to observe whole-host state while limiting executable actions to the personal runtime's own process or service lifecycle
- We now prefer the host-edge interface layer to stay stable even if the runtime later moves from a plain Python process to `systemd` or another deployment supervisor
- We now prefer `runtime_control` actions to stay deployment-agnostic and `runtime.collect_logs` to return structured diagnostics plus raw tail text rather than only opaque log blobs
- We now define the first productized slice as a coherent phone edge, desktop edge, and runtime/host-edge system with two supported deployment scenes: a standard public-server deployment and a computer-server deployment where the desktop package can optionally enable local runtime/host-edge components
- We now treat Linux one-command runtime/host-edge installation, Windows desktop-edge installer packaging, Android APK delivery, endpoint pairing, health UI, and install-mode verification as explicit product work rather than incidental release engineering
- We now require the first host edge to remain a frontend-side daemon independent from the backend runtime process so restart and health-observation loops stay physically separable
- We now have a dedicated host-edge v1 design baseline covering daemon boundaries, capability contracts, adapter shape, and restart/recovery semantics in `docs/plans/2026-06-19-host-edge-v1-design.md`
- We now have a dedicated host-edge v1 implementation ladder in `docs/plans/2026-06-19-host-edge-v1-implementation-plan.md`, scoped around configurable edge capabilities, host observation collection, runtime control adapters, host-daemon lifecycle, and observation recording
- We have now identified presence-policy design itself as a dedicated Goal 2 workstream that should be handled in a focused later discussion with supporting external research rather than being settled incidentally
- We now prefer early presence-policy updates to be review-gated rather than silently auto-applied, with candidate updates accumulated from runtime feedback and confirmed by the user on an explicit cadence that can lengthen over time
- We now prefer a v1 environment-understanding pipeline where raw edge signals are normalized into structured context observations and then merged into a context snapshot before any presence-policy decision is evaluated
- We now prefer observation-vocabulary governance where new shared terms are introduced and validated centrally during edge development, then immediately become normal system vocabulary once added to the top-level contract
- We now prefer to implement environment understanding with explicit online mappers and small per-observation reducers, while using a single review-gated heuristic-learning outer loop to refine vocabulary, reducers, and presence policy from feedback over time
- We now prefer `Presence Router` to consume the compact snapshot directly, without an extra presence feature layer, while the broader `Agent Runtime` may still inspect snapshot plus supporting observation evidence when deeper reasoning is needed
- We now prefer edge-local ownership of fine-grained raw device history, with backend agents requesting bounded structured edge-history views only when deeper reasoning or debugging requires more than the compact snapshot and normalized runtime observations
- We now use `Agent Runtime` as the top-level backend module name, because that module owns both proposal formation and later execution planning around the explicit `Presence Router` submodule
- The architecture baseline now needs to show `Presence Router` as an internal governance submodule inside `Agent Runtime`, together with the dual-entry proactive flow that converges on that submodule
- We now have a written Goal 2 design baseline for device/capability contracts, runtime observations, compact context snapshots, presence-policy axes, and the unified heuristic-learning outer loop in `docs/plans/2026-06-18-goal2-presence-context-design.md`
- We now explicitly support both sense-first and agent-initiative proactive paths, with both paths converging on `Presence Router` and agent-initiative requests carrying meaningful salience without bypassing suppression policy
- We now treat `agent` as a primary runtime abstraction and `Presence Router` as an explicit governance module inside the broader agent runtime, completing the current Goal 2 abstraction baseline
- The live runtime now has an explicit interaction-lifecycle surface on the normal chain: proposal/presence outcomes are recorded under an `interaction_id`, remote action results can complete that interaction later, and user-facing edges can consume a generic `interaction_update` instead of inferring completion only from a locally executed action
- The terminal edge no longer depends on the old narrow “wait until this device receives an action_request” path for pull-style requests; remote runtime actions, `no_intervention`, and suppressed outcomes now all resolve through the same interaction-completion mechanism
- Interaction completion currently remains a structural live-chain surface only: it can mark an interaction finished and notify user-facing edges about delivery or remote action completion, but semantic post-action deliberation is now explicitly deferred to `M16` rather than hidden behind a formatter patch
- The accepted first interaction-lifecycle slice still keeps at most one `primary action` per planning turn, but the state/protocol shape now preserves a cleaner path toward later multi-turn `action loop` re-entry through the normal runtime chain
- We have selected the first v0 device surface as a desktop/CLI edge and the first capability loop as `text.input -> notification.show`
- We have also defined the immediate follow-up slice after v0: minimal persistence, a second surface or device, and one non-text capability
- We now have project-level Codex hooks enforcing `Project.md` session-start and per-turn audit behavior
- We have now defined the minimum backend module set for the first usable v0 slice
- We have initialized the repository as a git project and support both normal branch work and optional isolated worktree-based iteration
- We have completed the first implementation batch for the v0 plan: Python project scaffold, `personal_runtime` and `device_edge` package roots, shared protocol helpers, in-memory runtime state, and the same-device presence routing stub
- We now have automated tests covering the v0 scaffold import contract, protocol frame helpers, and runtime state/presence basics alongside the existing project hook tests
- We have now implemented the first minimal backend gateway loop, response generator, action builder, edge session client, and CLI edge runner
- We now have an executable and testable end-to-end single-edge closed loop from `text.input` to `notification.show`
- We can manually verify the local loop with `python3 -m device_edge.cli.cli_edge`, and automated discovery now covers the full v0 and hook test suite
- We now have a project-local `.venv` for dependency isolation instead of relying on global Python packages
- We now have a real WebSocket transport path for the single-edge loop, including gateway server binding, edge client connection, action dispatch, and action-result return
- We have manually verified a true two-process local flow using `python3 -m personal_runtime.main` and `python3 -m device_edge.cli.cli_edge --url ...`
- We now have minimal file-backed continuity through runtime state snapshots and restart recovery via a configurable state path
- The gateway now persists device, capability, event, and action-result state automatically on the main v0 flow
- We now have a two-path runtime reaction model implemented: a normal routed/deliberative path and an explicit edge-requested direct-action path
- Direct-action requests can now bypass routing and agent planning while still being recorded in runtime state/context together with their execution results
- We now have the first same-template multi-edge routing slice working: two edge instances can stay connected and a normal routed notification action can be delivered from one device to another
- The gateway now tracks live edge connections for WebSocket delivery, allowing cross-edge `action_request` frames instead of only same-socket replies
- Ordinary routed actions now prefer another online peer with the required capability and safely fall back to the source edge when only offline residual device state is present
- We now have a repository-level development environment workflow: ordinary day-to-day work stays branch-first in the main workspace and reuses the root `.venv`, while optional dependency and packaging experiments may use an explicitly created worktree-local `.venv`
- The repository now includes helper scripts and automated tests for that shared-versus-isolated environment workflow
- We now require host-edge verification before describing a module as implemented and operationally ready in project documentation, while still allowing early CLI device validation during initial development
- We now have explicit shared runtime context contracts for device, capability, and normalized observation records
- Runtime state can now retain normalized observations with provenance as a distinct layer instead of collapsing everything into raw event history only
- We now have the first compact context snapshot reducer for hot-path presence work, including explicit `unknown` and `ambiguous` outcomes for location evidence
- Targeted automated tests now cover shared context contracts, observation storage, and the first compact snapshot reducer behavior
- We now have a configurable edge-capability foundation on the frontend side, so host-class edges are no longer forced to masquerade as the original text-only CLI capability shape
- The edge session client can now emit structured observation events with stable `event_id`s, allowing host telemetry to enter the runtime through the normal `Edge Session Link <-> Gateway` path instead of only through text input
- We now have a Linux-first host observation collector for whole-host telemetry and runtime health snapshots, covering the first real non-CLI observation path for M3
- We now have a first runtime-scoped control adapter contract on the edge side, with a Python-process implementation for `status`, `restart`, `reload`, and `collect_logs` while preserving a later adapter swap for `systemd` or other supervisors
- We now have the first independent host-edge daemon foundation that can bootstrap capability frames, push initial host observations, accept runtime control requests, and confirm later recovery through separate health observations
- The host-edge daemon can now sustain a longer-lived websocket session shape instead of only a single control roundtrip: it can continue observation cycles during idle periods, handle more than one runtime-control action in one connected session, and preserve the later health-follow-up path for disruptive actions
- The host-edge slice now includes a dedicated daemon startup path with explicit runtime connection and control options, plus a reconnect loop that retries after backend outages instead of treating disconnects as terminal edge failure
- The host-edge reconnect loop now supports bounded backoff growth and injectable jitter instead of only a fixed retry delay, which makes the daemon behavior closer to a real resident edge process under repeated backend outages
- The daemon startup surface now exposes reconnect backoff, max-delay, and fixed-jitter options explicitly, so the host-edge retry behavior can be tuned operationally instead of only through internal code changes
- The host-edge daemon session and startup surface now also support bounded idle verification controls, including configurable idle timeout and max-idle-cycle exit, so local host-edge validation can stop cleanly after a small observation run instead of requiring indefinite residency
- The host-edge daemon startup surface now also exposes bounded session-count exit through `max_sessions`, so local daemon verification can be capped by reconnect/session attempts as well as by idle observation behavior
- The host-edge daemon can now continue periodic observation cycles after the initial scheduled samples are exhausted when a timestamp provider is available, which moves the slice closer to a genuinely resident edge surface instead of a finite scripted session
- The Python-process runtime-control adapter can now discover a matching runtime process from a configurable `/proc` root for default `runtime.status` inspection, rather than only returning placeholder status when no custom supplier is injected
- The host-edge daemon startup path no longer passes edge-local history configuration into the reconnect loop incorrectly, fixing a real CLI startup regression that unit tests had previously missed behind a mocked `run_forever`
- The repository now includes a dedicated `bin/verify-host-edge` bounded verification path that starts the runtime server, runs the host daemon as a real separate process, sends a targeted `runtime.status` request through the normal gateway path, and waits for a clean daemon exit
- The gateway can now ingest observation batches as first-class runtime events, persist the raw edge event, normalize host observations, and record them into shared runtime observation state with provenance
- The runtime state layer now exposes explicit observation recording so later presence and agent flows can consume host telemetry without reparsing raw event payloads
- We now prefer the host edge itself to keep a bounded local observation-history window, and to expose that history only through explicit structured retrieval requests when deeper agent reasoning or debugging needs more detail than normalized core observations provide
- The host edge now keeps a bounded in-memory local observation-history window and exposes a first explicit `runtime.edge_history` retrieval surface for recent structured edge-side history instead of assuming core continuously mirrors fine-grained device evidence
- The host-edge daemon can now emit optional live local trace output to stdout and/or a local trace file, making reconnects, observation cycles, and runtime-control handling visible during manual edge-side verification instead of forcing operators to infer everything from core state alone
- The `device_edge` package is now physically split by edge role into `device_edge/shared`, `device_edge/cli`, and `device_edge/host`, and the earlier top-level edge module shells have now been removed so repository code, scripts, and tests consistently use the new paths directly
- We now have targeted automated coverage for host observation collection, runtime control adapter behavior, host-daemon request handling, gateway observation recording, CLI trace output, and trace-recorder persistence helpers
- We now have targeted automated coverage for the longer-lived host-edge daemon session shape as well, including multiple runtime-control actions in one websocket session and idle-period observation cycles between actions
- We now have targeted automated coverage for host-daemon reconnect behavior, daemon entrypoint wiring, periodic observation extension beyond the initial schedule, and default runtime-process discovery for `runtime.status`
- We now have targeted automated coverage for bounded reconnect backoff and jitter behavior as part of the host-daemon retry path
- We now have targeted automated coverage for the daemon startup wiring of reconnect backoff, max-delay, and fixed-jitter options as part of the host-edge operational surface
- We now have targeted automated coverage for bounded idle verification behavior, including max-idle-cycle session exit and daemon startup wiring of idle-timeout controls
- We now have targeted automated coverage for daemon startup wiring of bounded session-count exit as part of the host-edge local verification surface
- We now have targeted automated coverage for host-daemon live trace wiring and for the startup-path regression where CLI wiring passed an unexpected `history_limit` argument into `run_forever`
- We now have automated coverage and a documented dry-run path for the dedicated `bin/verify-host-edge` local verification entrypoint
- We now have targeted automated coverage for bounded edge-local observation history and explicit `runtime.edge_history` retrieval on the host-edge side
- Fresh targeted verification passed for the mature host-edge slice, including the dedicated host-daemon, roundtrip, dev-environment, and edge-layout test suites together with a bounded `bin/verify-host-edge` end-to-end run
- We now explicitly keep M3 scoped as the first presence-aware routing validation slice and move host-edge and product-maturity work into later milestones instead of stretching M3 semantics
- We now consider M4 complete: the host edge can run as a stable standalone real-edge surface with continuous observation, durable runtime-scoped control behavior, reconnect handling, and dedicated local verification paths
- We now define M5 as the runtime-ingestion and context-maturity milestone: once host-edge input is stable, the backend still needs more mature gateway ingestion, normalized observation handling, reducer behavior, and freshness / ambiguity management
- We now make M5 more execution-friendly by breaking it into four acceptance-oriented sub-stages: `M5.1` gateway ingest / normalized observations, `M5.2` compact snapshot field-pack growth, `M5.3` freshness / ambiguity / evidence rules, and `M5.4` end-to-end presence-input verification
- We have now landed the first explicit M5 freshness / expiry slice: compact snapshots accept a decision-time reference, stale `user.location` evidence ages out before presence evaluation, and the live gateway path no longer lets expired conflicting location evidence suppress a normal notification action
- We now have the first freshness-aware runtime-ingestion snapshot field beyond user location as well: `runtime.current_health_state` is derived from host-edge `runtime.health_state` observations and ages out to `unknown` when the health evidence is stale
- We now have a second freshness-aware runtime-ingestion snapshot field as well: `runtime.current_process_present` is derived from host-edge `runtime.process_present` observations and ages out to `unknown` when the process-presence evidence is stale
- We now have a third freshness-aware runtime-ingestion snapshot field as well: `runtime.current_process_memory_rss_bytes` is derived from host-edge `runtime.process_memory_rss_bytes` observations and ages out to `unknown` when the process-memory evidence is stale
- We now have a fourth freshness-aware runtime-ingestion snapshot field as well: `runtime.current_process_started_at` is derived from host-edge `runtime.process_started_at` observations and ages out to `unknown` when the process-lifecycle evidence is stale
- We now have a fifth freshness-aware runtime-ingestion snapshot field as well: `runtime.current_process_pid` is derived from host-edge `runtime.process_pid` observations and ages out to `unknown` when the process-identity evidence is stale
- We now have the first freshness-aware compact host-metric snapshot field as well: `host.current_memory_pressure` is derived from normalized `host.memory_pressure` observations and ages out to `unknown` when the host metric evidence is stale
- We now have a second freshness-aware compact host-metric snapshot field as well: `host.current_cpu_load_ratio` is derived from normalized `host.cpu_load_ratio` observations and ages out to `unknown` when the host CPU evidence is stale
- We now have a third freshness-aware compact host-metric snapshot field as well: `host.current_memory_available_bytes` is derived from normalized `host.memory_available_bytes` observations and ages out to `unknown` when the host memory-availability evidence is stale
- We now have a fourth freshness-aware compact host-metric snapshot field as well: `host.current_memory_used_bytes` is derived from normalized `host.memory_used_bytes` observations and ages out to `unknown` when the host memory-usage evidence is stale
- We now expose a parallel decision-time snapshot contract with explicit `fresh`, `stale`, `missing`, and `ambiguous` field states plus bounded supporting evidence, so M5 freshness/ambiguity semantics are inspectable outside reducer internals
- The live gateway normal path now records that decision-time snapshot contract into intervention history, which makes M5 human-verifiable on the real `Gateway -> State / Context -> Presence` chain rather than only through local reducer slices
- M5 has now been accepted as complete using targeted `tests.test_context_snapshot`, `tests.test_gateway_v0`, and `tests.test_roundtrip_v0` verification together with recorded intervention inspection and real host-edge evidence review
- We now also have a dedicated local chain-inspection entrypoint for human acceptance work: `python -m device_edge.cli.cli_edge --inspect-chain --text "..."` prints trace, normalized observations, compact snapshot, snapshot contract, proposal, presence decision, and recorded intervention in one report
- The runtime now also exposes a backend-originated initiative path on the live normal chain, so proactive work no longer depends only on an edge text event to begin proposal formation
- Both sense-first and agent-initiative triggers now rebuild the same decision-time snapshot inputs, form inspectable proposals, and converge on the same `Presence Router` before any user-facing or host-control action is emitted
- The normal execution-planning path now supports both `notification.show` and narrow `runtime.control` actions such as `runtime.status`, allowing a host-edge control action to be dispatched on the mature proactive path instead of only through the direct-action bypass
- Initiative proposals now record explicit proposal source, bounded metadata, action payload, and target-device intent in intervention history, making the live proactive chain easier to inspect and replay
- We now have a dedicated M6 inspection entrypoint for manual acceptance: `python -m device_edge.cli.cli_edge --inspect-agent-initiative` prints the initiative-triggered trace, snapshot inputs, proposal, presence decision, recorded intervention, and resulting action outcome in one report
- A real websocket verification now proves that runtime-originated initiative dispatch can route `runtime.status` to a connected host edge and record the returned result through the normal action-result path
- We now consider M6 complete: the runtime has a dual-entry proactive chain, unified presence governance, and a first mature execution-planning path across both user-facing notification and narrow host-control actions
- We now hard-enforce the project progress report format at the hook layer: when the user asks for progress, the response must include separate `Goal 1` through `Goal 5` sections and each section must carry the required architecture-aware labels
- We now also hard-enforce architecture-aware final reply summaries for edited turns: when a turn uses `apply_patch`, the final response must include `架构实现小结` with `架构位置`, `本步完成`, and `影响链路`
- We now move active execution focus to M7 operational-readiness verification: end-to-end host-edge-path validation must now gate stronger “implemented and ready to run” claims on top of the newly accepted M6 runtime behavior
- We now have a dedicated M7 implementation plan in `docs/plans/2026-06-21-m7-operational-readiness-verification-plan.md`, focused on turning host-edge readiness into a concrete bounded acceptance gate instead of another feature-expansion batch
- The default `bin/verify-host-edge` readiness run is now defined to cover both host-edge control entry modes we rely on operationally: the explicit direct-action fast path and the runtime-originated initiative path that still flows through snapshot rebuild, proposal formation, `Presence Router`, and normal action planning before hitting the host edge
- The host-edge daemon verification surface now includes an explicit bounded `max_action_requests` control so local readiness runs can exit after handling the intended number of action requests rather than relying only on idle-time timing
- Refreshed M7 verification evidence now passed across both targeted automated suites and a bounded real `bin/verify-host-edge` run: the repository can now gate stronger “implemented and ready to run” claims on both the direct-action host-control path and the normal runtime-initiative host-control path, each validated against a separate real host-edge daemon
- We now consider M7 complete: host-edge-path operational-readiness verification is no longer only a documentation rule, but a concrete bounded acceptance gate with real runtime, host-daemon, websocket, persisted-state, and dual-path action evidence
- We completed and accepted M20 after a configured-provider Gateway/Terminal/Android human-acceptance ladder proved the governed outer action loop, real public fetch/search, research-assisted reply, hostile fixture provenance with no action or memory side effect, fresh-session Hermes native-memory recall with body-free evidence, canonical `notification.show {title?, body}` delivery, roster-guided Android target selection, and requester outcome reporting in both directions. M20.1 remains the owner of governed procedural-memory and skill lifecycle work; M20.2 owns OpenHalo interaction-progress presentation; M20.3 owns the stable Terminal Edge CLI/TUI; and M19 follows broader M18 before M21 policy learning, M22 product packaging, and M23 ecosystem bridging
- We now intentionally schedule bounded-growth and storage-hygiene hardening after both M20 and broader M18, because the final Harness-controlled attention/event flow determines the histories, attention traces, and retention pressure M19 must govern
- We now prefer the desktop/CLI edge to evolve from a verification harness into the first formal long-running terminal `Device Edge` for product-facing interaction
- We now explicitly treat terminal interaction as ordinary environment sensing plus runtime action on a `Device Edge`, not as a special chat-centered system mode
- We now want the first formal terminal edge to support both user-initiated pull requests and presence-gated runtime-initiated push interactions on the same normal runtime chain
- We now consider M8 complete: the desktop/CLI surface has been promoted into a resident terminal edge with explicit `terminal.activity_state` observations on the normal runtime path, bounded resident daemon controls, pull-style user requests, presence-gated runtime push, a true foreground live terminal session that reads `stdin` on the same resident websocket session, and a dedicated `bin/verify-terminal-edge` acceptance run that records delivered terminal actions plus active/idle push decisions in persisted runtime state
- Terminal push targeting is now explicitly terminal-locked: when a runtime-initiated `notification.show` targets a terminal edge, idle or unavailable terminal state suppresses the push instead of silently falling back to another online device
- Repeated explicit terminal `text.input` requests are now treated as user-driven interaction rather than proactive interruption: the shared cooldown still constrains repeated runtime-initiated user-facing push, but it no longer suppresses back-to-back live terminal requests in the same resident session
- Compact snapshot freshness now rejects future-dated observation evidence, which keeps decision-time terminal presence evaluation aligned with the actual runtime timestamp used for intervention decisions
- We now want real model integration to enter behind an explicit provider boundary inside `Agent Runtime`, so proposal and reply generation can become model-backed without collapsing the architecture back into chat-session product assumptions
- We now have a dedicated `M9` provider-configuration design baseline in `docs/plans/2026-06-22-m9-provider-configuration-design.md`, defining a hybrid provider architecture with separate provider, model, profile, and selection-policy layers
- We now prefer `M9` runtime call sites to select named model profiles instead of hard-coded provider/model pairs, while the first accepted implementation remains limited to the `openai_compatible` adapter path
- We now explicitly defer broad provider/model strategy routing until after the first grounded model stage, so `M9` can focus on a mature configuration boundary without prematurely mixing in `M10` grounding or later policy work
- We now want the first model-backed stage after that to focus on grounding rather than only provider wiring, so runtime memory, snapshot context, goals, and bounded edge evidence meaningfully shape model behavior
- We now want prompt/context engineering to become its own explicit milestone after terminal/CLI maturity, so grounded runtime-native state can be turned into a durable and inspectable agent behavior contract instead of remaining as thin prompt wiring
- We now want proposal-formation maturity to become its own explicit milestone after prompt/context engineering, so the runtime can reliably distinguish action and no-intervention outcomes on the live chain before post-action deliberation, multi-edge expansion, idle observation sensing, and later policy learning build on that behavior
- We now want model-provider connection reliability and diagnostics to become the immediate milestone after proposal-formation maturity, because deeper action-loop behavior should not depend on a model path that still hides protocol mismatches, timeouts, fallback policy, or health status
- We now want runtime-native credential/runtime-config work to become the immediate milestone after model-provider reliability, so real provider access can become a product-owned capability before deeper post-action behavior depends on it
- We now want post-action deliberation and same-interaction action-loop handling to remain its own explicit milestone after runtime-native credentialing, rather than being approximated by a completion-summary patch on the gateway path
- We now want multi-edge interaction expansion to become the immediate milestone after post-action behavior, because the system needs more real device surfaces before deeper idle sensing, bounded-growth hardening, harness refactor, or policy learning can be validated against representative behavior
- We now intentionally fold standalone behavior-contract/action-tool governance into M20 Agent Harness and runtime action-loop architecture refactor, because implementing it earlier would likely create a transitional governance layer that the harness refactor would later replace
- We now intentionally defer policy learning and review to M21, after the M20 harness refactor gives model-backed feedback interpretation stable trace, replay, memory, action/result, and governance semantics rather than the pre-refactor runtime shape
- We now have the first working `M9` provider/configuration implementation slice: runtime model config is split into provider, model, and profile layers; the first accepted adapter path is `openai_compatible`; normal text replies now carry inspectable provider/profile/fallback metadata through the existing proposal and chain-inspection surfaces
- The repository now includes an ignored local `config/runtime-config.toml` runtime configuration path, a tracked `config/runtime-config.example.toml` template, targeted provider-unit coverage, gateway coverage, human-readable local inspection guidance for the first `M9` profile-driven text-reply path, and an explicit `--runtime-config-path` runtime escape hatch for intentional non-default provider runs, with `--llm-config-path` retained only as a compatibility alias
- The real-use provider baseline now lives in local `config/runtime-config.toml`, so ordinary startup expects provider credentials in the runtime config itself rather than in a configured shell auth environment variable
- The current accepted runtime-config model baseline for the `https://api-dmit.cubence.com/v1` OpenAI-compatible relay is `gpt-5.5`; `gpt-5.4` can pass a narrow provider probe but has been observed to return a Codex-agent envelope with empty output on the terminal live proposal path once compact snapshot fields are present
- A host-plus-terminal real-use acceptance run showed that ordinary Chinese dialogue and `runtime.status` can succeed through the live runtime on `gpt-5.5`; the follow-up WebSocket `1011` keepalive timeout exposed by a slower grounded provider call is now addressed by moving WebSocket frame handling off the event loop with serialized background-thread execution, with regression coverage proving ping responsiveness during slow proposal generation
- The current real-use acceptance posture is "mostly stable with explicit residual provider/relay errors": occasional surfaced provider failures are still possible and should be captured as provider stability evidence when the terminal edge remains connected and `bin/verify-model-provider` continues to report `ok: true`
- We now have a more precise real-provider `M9` status for the tracked CRS default: the runtime's `openai_compatible` adapter sends an explicit `User-Agent`, which avoids the CRS gateway's earlier Cloudflare `1010` block, but a renewed real-runtime check on 2026-06-25 also showed that the same CRS `/responses` route can later return a completed payload with empty `output` and a Codex-agent instruction envelope instead of plain runtime reply/proposal text
- Local runtime and CLI regression tests are now isolated from ambient machine-local config through explicit test config injection, so automated suites stay deterministic while non-default manual acceptance must opt in deliberately
- Real-use model profiles now default to explicit provider-failure surfacing instead of fake conversational fallback: when the configured proposal/reply model cannot be reached, the user-facing runtime response now reports the real failure reason directly, while bounded development fixtures can still opt into deterministic fallback for offline chain verification
- Runtime config precedence is now intentionally local and single-source: ordinary startup uses ignored `config/runtime-config.toml` unless an operator explicitly passes `--runtime-config-path`, while `config/runtime-config.example.toml` remains the tracked template for the expected provider/model/profile/API-key shape
- The current local development default is the OpenAI-aligned ignored `config/runtime-config.toml`: `bin/run-runtime-dev` and the current real-provider helpers use that file by default, while an ignored `config/runtime-config.openai-local.toml` is optional local backup material rather than a path a worktree may assume exists
- The current live diagnosis for 2026-06-25 is therefore no longer "CRS is simply healthy again", but it is also no longer "the provider must be globally broken": the project baseline now records both mixed CRS response shapes on this feat branch and a same-machine `master` manual acceptance that still produced normal natural-language terminal dialogue, so the next follow-up should treat feat-branch regression analysis as the primary path while still keeping the provider contract mismatch in scope
- We now consider M11 complete: the resident terminal edge has moved beyond the minimal M8 daemon baseline into a more human-usable CLI surface with readable session rendering, bounded local transcript/history, explicit `/help` `/status` `/history` `/quit` edge-local affordances, and a refreshed `bin/verify-terminal-edge` acceptance path that still validates the real presence-governed runtime chain
- The M11 terminal acceptance script no longer assumes a deterministic provider reply string for its pull-stage readiness check; it now waits on persisted terminal delivery evidence, which keeps the acceptance path valid across both local fallback and real model-backed reply variants
- We now consider M12 complete: the runtime has an explicit versioned prompt/context package, proposal-level prompt provenance metadata, a first inspectable behavior-contract surface, and a bounded `bin/verify-prompt-contract` acceptance path that re-checks the recorded grounded prompt package locally
- The local inspection ladder now extends beyond M10 grounding metadata into explicit prompt/context engineering: one `--inspect-prompt-contract` run now prints prompt sections, behavior-contract checks, and replay/eval results on the same grounded runtime chain
- We now consider M13 complete: the normal sense-first live chain can emit inspectable proposal outcomes from grounded edge-delivered text without bypassing `Presence Router`; after M17.6 hardening, the current normal proposal taxonomy is `action` and `no_intervention`
- Proposal formation now records structured rationale together with provider/fallback metadata on the live chain, while keeping the documented `event -> compact snapshot -> grounding bundle -> prompt/context package -> proposal formation -> Presence Router -> execution planning/action` shape intact
- The provider boundary now supports structured proposal-plan parsing plus proposal-type normalization, and the runtime retains deterministic grounded fallback when the model is unavailable
- The proposal-formation provider parser now also tolerates plain `output_text` replies from an OpenAI-compatible `/responses` route, mapping them back into normal user-visible `action` proposals instead of surfacing parser/provider errors as user-facing dialogue
- Host-edge daemon receive handling now preserves action requests that arrive while the daemon is waiting for observation acknowledgements, so continuous host observation traffic no longer swallows `runtime.status` requests planned by the normal terminal-to-runtime-to-host chain
- The repository now has a bounded M13 acceptance ladder: `bin/verify-proposal-formation --dry-run` lists the accepted scenario checks, and the real `bin/verify-proposal-formation` run exercises user-visible action, runtime-control action, and `no_intervention` outcomes with readable rationale on the live chain
- Fresh targeted automated verification and bounded human acceptance now pass for M13, and the project has now completed and accepted `M14` model-provider connection reliability and diagnostics against its provider-probe, health/status, failure-classification, and controlled-failure criteria
- The first M14 provider-stability hardening slice now classifies OpenAI-compatible response shapes, retries transient empty-output response shapes such as Codex-agent envelopes or completed responses with no output before surfacing failure, and keeps terminal-facing errors product-safe while preserving the raw provider shape and reason in proposal metadata for diagnostics
- The provider-backed proposal path now uses a Responses `json_schema` structured-output request format when the selected model declares structured-output support, so the current `action` / `no_intervention` proposal taxonomy is constrained at the provider protocol layer rather than by action-specific local fallback rules
- Follow-up M14 hardening now treats repeated `codex_agent_envelope_empty_output` results from the `json_schema` request shape as a request-contract compatibility problem rather than only provider randomness: the proposal path and provider probe retry once with the same prompt-JSON proposal contract without the Responses `json_schema` envelope, record the final request format plus retried shapes, and still surface a protocol-shape failure if that fallback also returns an incompatible response
- The OpenAI-compatible adapter now fails fast on unsupported `wire_api` values instead of silently sending every provider through `/responses`, and proposal metadata records the provider wire API plus request format so future bad-shape recurrences can distinguish route/config issues from model-output issues
- The runtime now has a bounded provider-probe entrypoint and `bin/verify-model-provider` acceptance path; the probe reports profile, provider, model, endpoint, auth-env presence, wire API, response shape, latency, and failure class without exposing provider secrets
- Provider failures now carry a normalized `provider_failure_class` that distinguishes auth, connection, timeout, rate-limit, HTTP client/server, protocol-shape, parser, and unknown failures across probe and runtime metadata
- Runtime state now persists `model_health` by profile, including provider/model identity, availability status, last failure class/reason/type, wire API, request format, latency where available, and last success timestamp where applicable
- Human acceptance after the structured-output change showed the normal terminal/model/action path is broadly stable again: Chinese dialogue returned natural replies, `check runtime status` and a later Chinese runtime-status request both formed model-backed `runtime.status` actions, host-edge action results reached the terminal, and follow-up dialogue continued normally
- The real-use acceptance documentation now requires a provider probe plus a three-process runtime, host-edge, and terminal-edge scenario, with explicit pass criteria for Chinese model-backed dialogue, host-routed `runtime.status`, context follow-up stability, and visible `json_schema -> prompt_json` recovery metadata when the provider returns a Codex-agent empty-output shape
- One acceptance prompt still produced a single `codex_agent_envelope_empty_output` bad-shape failure even under `provider_wire_api=responses` and `provider_request_format=json_schema`; later turns recovered, so the current status is "overall usable with occasional provider bad-shape failure" rather than persistent state pollution
- Current M14 diagnostic status: after clearing `.runtime`, the terminal/model path returned stable natural-language replies; a minimal reconstructed pollution state containing recent provider-failure action results did not reproduce the bad response shape, and later structured-output host-edge acceptance showed overall stable dialogue/action behavior with one nonpersistent provider bad-shape failure, so persistent state pollution is no longer treated as the active blocker
- The M14 follow-up documentation now includes a dedicated implementation plan in `docs/plans/2026-06-26-m14-model-provider-reliability-implementation-plan.md` and a dev-environment recurrence workflow that preserves `.runtime` bad-state evidence before any cleanup or clean-state comparison
- M14 is now accepted complete; any further provider dashboards, broader live-provider matrices, or deeper operational telemetry are follow-up hardening rather than blockers for `M15` runtime-config baseline or `M16` action-loop semantics
- The M15 runtime-config surface now uses `Runtime config` wording in the runtime startup message, accepts `--runtime-config-path` on both the runtime server and provider-probe CLI, preserves `--llm-config-path` as a compatibility alias, and documents the new spelling in the development workflow while keeping local provider API keys inside ignored `config/runtime-config.toml`
- M15 is now accepted complete: `bin/verify-model-provider` passed against the local runtime-owned config with `auth_source=runtime_config`, `auth_present=true`, no secret exposure, `openai_main/gpt-5.5`, and visible `json_schema -> prompt_json` recovery metadata; terminal live-path verification produced a model-backed `openai_main/gpt-5.5` reply with `used_deterministic_fallback=False`; host-edge verification produced `runtime.status` action results and host observations through the normal runtime/edge path
- A follow-up real-use comparison with an ignored official OpenAI local config showed faster and more stable `gpt-5.5` responses than the current relay baseline, supporting the conclusion that the earlier intermittent `codex_agent_envelope_empty_output` behavior is a provider/relay compatibility issue rather than an M15 runtime-config or credential-resolution blocker
- Post-acceptance hardening now also covers the resident terminal TUI lifecycle edge case: status/transcript refresh timers tolerate shutdown/unmount boundaries without raising Textual query errors, and the terminal/TUI manual acceptance docs now use explicit `.venv/bin/python` commands plus a user-scenario sequence centered on `hello runtime`, `check runtime status`, local slash commands, and clean exit
- Terminal TUI quit-path hardening now also treats `quit_requested + connection_state=disconnected` as sufficient to leave the full-screen UI, so `/quit` no longer leaves the final rendered frame stuck on screen while a lingering session thread finishes unwinding
- Terminal TUI environment hardening now detects `TERM=dumb` and falls back to the line-oriented resident terminal mode instead of forcing a Textual full-screen session into an unsupported shell surface that can leave inline render residue after exit
- Terminal TUI input sensing now records draft-empty versus draft-nonempty changes and sends them through the normal `terminal.context` observation path as `terminal.input_state` and `terminal.input_draft_length`; nonempty draft observations now wake the daemon's idle wait so active foreground typing is observed before a fresh `terminal.activity_state=idle` report, while still avoiding a claim of full IME composition semantics
- M16 is now accepted complete for active interaction re-entry: `action_result` frames with a known `interaction_id` can rebuild decision-time snapshot and grounding context, re-enter `Agent Runtime` as `post_action` proposals, pass through `Presence Router`, and either dispatch a governed follow-up reply/action or complete silently inside the same interaction lifecycle
- M16 post-action proposal formation now has a provider-backed path over structured action-result evidence and prior interaction lineage: `generate_post_action_proposal_plan` sends the action result into the configured `proposal_formation` model profile, records whether deterministic fallback was used, and preserves a deterministic post-action fallback only for provider-unavailable or unsupported-adapter cases
- M16 fresh-observation re-entry is now implemented for active interactions: when a relevant high-salience observation such as degraded runtime health arrives from a participant device during an open interaction, the runtime can rebuild snapshot/grounding context, form a `post_observation` proposal, pass it through `Presence Router`, and dispatch a same-interaction follow-up action while idle/standby global observation intent sensing remains deferred to M18
- M16 interaction lineage is now inspectable through multiple intervention records sharing the same `interaction_id`, with post-action and post-observation metadata such as trigger, turn index, parent proposal/action capability, result or observation evidence, snapshot fields, and grounding counts
- The action loop still keeps one current `primary_action` per deliberation turn, but a single interaction can now span more than one turn; the old fixed completion formatter remains only as fallback for missing or unknown interaction lineage
- The repository now has a bounded M16 acceptance helper: `bin/verify-action-loop --dry-run` lists the action-loop checks, `bin/verify-action-loop` exercises runtime-status action-result reentry, fresh-observation same-interaction reentry, follow-up action planning, silent completion after delivered notification, and post-action/post-observation lineage in an in-process runtime scenario, and `bin/verify-action-loop --runtime-config-path config/runtime-config.toml --require-model-backed` requires model-backed post-action metadata before accepting the real-provider path
- M16 real-use acceptance has been exercised in a terminal/host/runtime scenario with the official OpenAI local runtime config; the active-interaction action-loop baseline is accepted complete, while broader idle/standby observation intent sensing is explicitly tracked as later M18 work after multi-edge expansion
- Terminal-to-phone real-use inspection exposed an M17/M16 boundary gap now tracked as `M17.6`: post-action proposal formation currently consumes action result, prior proposal, compact snapshot, and grounding context, but not the full active interaction lineage such as source device, target device, and participant devices; deterministic fallback and permissive silent/no-intervention completion can therefore hide missing cross-edge source acknowledgement or routing/provider failures instead of surfacing them as actionable errors
- The first M17.6.1 Agent Runtime harness engineering slice has started from a clean runtime baseline: `personal_runtime.proposal_harness` can build scrubbed proposal replay cases, classify proposal outcomes, compare prompt variants, and run a bounded terminal-to-phone fixture through `bin/verify-proposal-harness`. The initial fixture keeps the live model request chain unchanged while contrasting the current raw JSON post-action prompt shape against a candidate decision-brief prompt shape, so later real-provider replay can measure whether clearer source/target obligation framing improves proposal-formation reliability before returning to M17.6 acceptance.
- M17.6.1 can now derive an offline replay corpus from persisted runtime state: `bin/verify-proposal-harness --state .runtime/m17_6_acceptance_state.json` loads post-action interventions from the M17.6 acceptance state and classifies observed proposal outcomes without calling the provider. The current state-derived report covers six post-action samples with three correct outcomes, two provider/protocol failures, and one semantically incomplete source-acknowledgement failure, giving the harness a real failure baseline before live provider A/B replay.
- The first M17.6.1 real-provider A/B replay has run against the six state-derived M17.6 post-action samples using the relay-backed `config/runtime-config.toml`; that historical relay run showed raw JSON producing three correct outcomes and three semantically incomplete `source_ack_missing` outcomes, while the candidate decision-brief prompt variant produced six correct outcomes. The M17.6.1 harness now resolves real-provider replay through the OpenAI-aligned local `config/runtime-config.toml`; when run with the same local proxy environment as the deployed runtime, the official OpenAI replay completes on `openai_main/gpt-5.5`: raw JSON now produces four correct outcomes and two semantically incomplete source-acknowledgement failures, while decision brief produces six correct outcomes. The remaining provider-error samples are now counted as correct containment because provider failures stay on a dedicated `provider_failure` channel instead of being routed as normal `notification.show` actions.
- M17.6.1 is accepted complete as the Agent Runtime harness engineering baseline: `decision_brief` is now the live post-action prompt shape, provider/model failures are isolated onto a dedicated `provider_failure` channel rather than normal `notification.show`, focused regression coverage protects source acknowledgement, empty-output provider-shape handling, and provider-error containment, and the official OpenAI replay over the captured M17.6 corpus reaches six correct outcomes out of six for the decision-brief path. The return to M17.6 human acceptance has now completed on the real terminal-to-phone path rather than being inferred only from the harness result.
- M17.6 fail-fast acceptance hardening has resumed after M17.6.1: `PresenceRouter` now preserves an explicit proposal `target_device_hint` for a known capable target even when that target is offline, instead of defaulting cross-edge actions back to the source edge; when `Gateway` attempts to dispatch an `action_request` to a missing target connection, it emits a failed `action_result` with `reason: target_missing`, records it in runtime state, and re-enters the normal post-action proposal chain so the source edge can receive a model/runtime-formed failure explanation rather than a successful-looking local fallback.
- M17.6 terminal-edge acceptance then exposed a deeper normal-proposal gap: after the phone edge had been disconnected, terminal-visible replies such as `已发送到手机。`, `再给手机发送一个 hello。`, and `发了，刚才已经又给手机发送了一个 hello。` were delivered through `terminal.stdout`, proving that the user-visible conversation still looked successful even though the requested phone target was unavailable. The fix now extends proposal formation so structured model plans may carry `target_device_hint`, infers a unique known phone/android device when the user explicitly says `phone` or `手机`, and lets execution planning preserve an explicitly targeted offline device as an action outcome for `Gateway` fail-fast dispatch instead of converting the turn into a local terminal completion.
- M17.6 is accepted complete after real-device terminal-to-phone acceptance on the development runtime port `18765`: terminal-originated phone sends route to the Android edge and return source acknowledgements; phone-offline sends and contextual retries preserve the known Android target, produce failed `action_result` records with `reason=target_missing`, and return explicit terminal failure explanations; reconnecting the phone restores successful delivery. The same acceptance run confirms the cleaned proposal taxonomy: normal user-visible, retry, acknowledgement, and failure-explanation turns are `proposal_type=action`, silent loop completions are `proposal_type=no_intervention`, and normal runtime paths no longer emit `reply` or `clarification` as top-level proposal types.
- After resetting the long-running runtime state for a clean M17.7 start, an empty-state reconnect exposed that `Gateway` still allowed a `capability_announce` from an unknown device to raise a runtime `KeyError`. The gateway now returns a structured `unknown_device` public error for that case instead of crashing the websocket handler; broader unknown-device handling for other post-connect frame types remains a hardening concern.
- M17.7.1 is accepted complete for the Android edge continuous background observation steady-state slice: the foreground `AndroidEdgeService` schedules a background observation heartbeat while user-enabled background keepalive is active, periodic `mobile.context` uploads continue through the normal WebSocket edge session, diagnostics record background observation state, last local observation time, last successful upload time, and delivery queue depth, and the settings/diagnostics surface exposes battery/background-running guidance including manufacturer-specific restriction hints. The M17 Android acceptance document includes a dedicated M17.7.1 background observation steady-state checklist.
- M17.7.1 acceptance is based on short-duration real-phone background steady-state evidence on the Alibaba Cloud runtime: while the phone edge was kept in the background, `android-edge-782d0247` continued sending `mobile.screen_context` and `mobile.screen_capture_health` for roughly 35 minutes, with recent evidence normally seconds old and a latest observed gap under one minute. This accepts half-hour-class background survival for the current milestone slice, while longer overnight/OEM-restriction survival, server-side liveness classification, wake/reconnect recovery, and the observed stale/closed WebSocket ack-path degradation remain outside M17.7.1 and belong to M17.7.2 or later hardening.
- Follow-up M17.7.1 screen-context schema hardening now records the Android app identity fields already captured by the AccessibilityService: `mobile.screen_context` values include `package_name` and `root_class_name`, and the Android capability announcement schema declares both fields as required strings. This fixes the previous mismatch where screen text and UI affordances were persisted but the structured app identity was only used locally for `package_category`.
- Follow-up M17.7.1 Android settings hardening is accepted complete: the Android edge persists the user-enabled screen-context observation switch synchronously, drives Compose switches from explicit target states, refreshes the system accessibility-service state on Activity resume, and checks enabled accessibility services through `AccessibilityManager` plus compatible Settings-list parsing. Real-phone logcat diagnosis on MIUI then showed a separate system-level caveat: swiping the app away as `SwipeUpClean` force-stops `dev.openhalo.android.edge`, clears `enabled_accessibility_services`, and disables the system AccessibilityService, so this path is treated as OEM/system force-stop behavior rather than an app preference persistence failure. The Android edge now records when accessibility observation was previously enabled and, if screen-context observation is still desired but the next launch finds the system service disabled, shows an accepted restart-time notice that manual background cleanup may have disabled observation and offers to reopen Android Accessibility settings.
- Follow-up M17.7 Android chat-surface hardening fixed a local history retention bug exposed during test-port real-phone acceptance: high-frequency `mobile.context` / `mobile.screen_context` event history no longer evicts visible conversation messages from the global chat surface, because Android now keeps conversation history separate from diagnostics event history and the chat UI reads that dedicated conversation stream. Regression coverage verifies that a user message and runtime reply remain visible after many screen-context history writes.
- M17.7.2 Gateway connection-lifecycle hardening has started from the stale/closed WebSocket ack-path evidence seen on the Alibaba Cloud runtime: source-device replies now resolve through the current `live_connections[source_device_id]` mapping before falling back to the handler socket, and replaced websocket handlers only clear online/connection state if the registry still points at that exact socket. Focused Gateway regression tests cover ack dispatch after same-device reconnect and old-session close cleanup that must not remove the newer active connection.
- M17.7.2 runtime-side mobile observation liveness hardening is accepted complete for the current milestone scope: `personal_runtime.mobile_liveness` classifies registered phone edges as `fresh`, `degraded`, `wake_requested`, `stale`, or `unavailable` from screen-context freshness, health evidence, online state, expected-active observation state, runtime health suppression, and recovery-attempt metadata. Gateway connect/disconnect and mobile observation ingress update persisted `state.mobile_liveness`, the context viewer exposes online-aware `mobile_liveness` inspection output, and the watchdog entry point can issue bounded, TTL-bound, rate-limited, privacy-preserving wake recovery attempts through a configured transport hook. Automated coverage includes fresh/degraded/stale/unavailable-style classification, wake audit privacy, rate limiting, server/network-failure suppression, stale buffered replay handling, reconnect recovery provenance, Gateway state updates, and viewer output.
- M17.7.2 manual acceptance passed on the Alibaba Cloud development runtime test path `18765` after resetting the test state: with Android edge `android-edge-782d0247` in the background, the runtime observed `mobile_liveness.state=fresh` with seconds-old `mobile.screen_context` / `mobile.screen_capture_health`; after a longer network interruption with no established websocket, current liveness computation reported `state=stale`, `online=false`, `expected_active_observation=true`, and `wake_recovery_eligible=true` at roughly 142 seconds of silence; after restoring network without manually restarting OpenHalo, the phone reconnected in the background and returned to fresh observation with an established websocket, `last_session.connected` around `2026-07-10T17:15:23Z`, `mobile_liveness.state=fresh`, seconds-old `mobile.screen_context` / `mobile.screen_capture_health`, and no `connection_closed` events in the latest 3-minute recovery window. This accepts the fresh background live-chain, stale/wake-eligible degradation, and reconnect recovery evidence for M17.7.2. The short `degraded` window, real configured wake transport, stale buffered replay on a live phone, periodic no-ingress watchdog persistence, and formal `8765` deployment acceptance are no longer blockers for M17.7.2 and are tracked as follow-up hardening to address opportunistically during longer-term use or deployment work if they surface as practical issues.
- Long-running runtime updates should now default to a clean state reset unless a verified migration exists: stop `openhalo-runtime`, remove `/var/lib/openhalo/runtime-state.json`, sync code while preserving `.venv` and `/etc/openhalo`, restart the service, and verify provider access through the service user's proxy environment. Proxy verification must check the selected upstream node against `api.openai.com`, not only the presence of `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`.
- Observation-driven intent sensing now has a bounded M18 backend implementation after multi-edge expansion: M16 continues to own causally linked re-entry inside an active interaction lifecycle, while the M18 Gate admits only unrelated high-salience evidence into ordinary interactions. The backend slice is covered only by Personal Runtime Python regression and offline admission replay; Android Edge builds/tests and real-phone acceptance remain separate local edge-development work. M18 action-result re-entry now requires the original interaction/turn/request triple, target device, and requested capability to match exactly; realistic multi-edge human acceptance remains required before broader M18 is accepted.
- Full regression verification should now watch formal `coverage.py` line coverage alongside pass/fail results. The current baseline is 87% line coverage over `personal_runtime`, `device_edge`, and `agent_guard` after 291 passing unittest cases; future full-test summaries should call out meaningful coverage drops or low-coverage risk areas, especially on the runtime/action/presence/model and edge paths
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
