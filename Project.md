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
- The hot decision path should stay shallow and explicit: once an edge-driven event reaches deliberative handling, the preferred runtime-owned chain is `event -> compact snapshot -> grounding bundle -> prompt/context package -> model-backed proposal formation -> Presence Router -> execution planning/action`, and new intermediate representations on that path require a clear non-duplicative reason
- Proposal formation should be allowed to synthesize an interaction hypothesis from one high-salience signal or from multiple device observations together; a line of terminal text is only one possible trigger shape, not the only interaction origin the runtime may reason about
- Model-backed proposal formation may emit interaction-semantic candidates such as interaction type, candidate participant surfaces, visibility intent, and the current `primary action`, but those remain proposal-layer candidates until presence governance and execution planning turn them into an actual runtime outcome
- `Presence Router` should act as an explicit governance and adjudication layer, not only a passive allow/block filter: it may suppress, narrow, retime, or redirect proposed surfaces and actions based on policy, privacy, activity, capability, and availability constraints
- The runtime may keep one `primary action` per planning turn in early slices, but that bound should remain an implementation constraint rather than a long-term architecture rule; the same interaction lifecycle should later support multi-turn `action loop` re-entry after action results or new observations
- Model-native tool calls, MCP tool calls, runtime-local tools, skill/procedure invocations, and external device actions should converge into one runtime-owned action intent/result model before side effects occur; provider-native tool syntax is an adapter input, not a permission to bypass OpenHalo action governance
- Agent behavior should be constrained by explicit prompt/context contracts, behavior contracts, capability/action registry validation, and post-generation validation or repair before any user-visible or side-effectful action is executed
- Presence policy should remain explicit and inspectable even when model-generated or model-repaired; models are not the only durable representation of proactive behavior
- A host-resident edge running on the runtime's own server is still modeled as a first-class `Device Edge`; physical co-location does not waive the `Edge Session Link <-> Gateway` boundary
- The runtime should support both a normal deliberative path and an explicit edge-requested fast path for direct actions
- A direct action fast path may bypass the normal `Agent Runtime` path, including `Presence Router`, but it must still pass through `Gateway`, update runtime state/context, and record action results
- Runtime feedback interpretation should treat `ignore != negative`; explicit rejection or repeated similar-context dismissal should carry more weight than one-off non-response
- Presence policy updates should optimize for both immediate user experience and likely future user experience, rather than greedily maximizing the current interaction outcome
- For the first same-template multi-edge slice, ordinary routed actions should prefer a different online edge instance with the required capability before falling back to the source device
- Ordinary development work should be branch-first in the main workspace and should reuse the repository root `.venv` by default, while optional worktree-based dependency or packaging experiments should use an explicitly created worktree-local `.venv`
- CLI device validation is acceptable for early module testing, but host-edge verification is required before documenting a module as fully implemented and operationally ready
- In this project, `manual acceptance` or `human acceptance` means testing implemented functionality in a simulated real usage scenario, rather than only checking static output, isolated unit behavior, or non-interactive script success

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
- When edge-delivered signals carry user intent, the current design preference is to extend `Agent Runtime` proposal formation so it can yield multiple proposal classes such as `reply`, `action`, `clarification`, and `no_intervention`, rather than introducing a separate top-level `Intent Interpretation` module.
- The current implementation preference is to avoid duplicate context-carrier layers on the hot path: if `grounding bundle` feeds a `prompt/context package`, later steps should consume that package directly rather than rebuilding equivalent payloads under new names.
- Inspection-oriented surfaces such as behavior contracts, replay/eval reports, or other verification artifacts should be treated as sidecars around the hot path by default; they may validate or summarize live-chain artifacts, but should not become mandatory intermediate decision objects unless they directly change runtime behavior.
- The detailed presence-policy design remains intentionally deferred for a dedicated research and design pass. That pass should explicitly study policy representation shape, conflict avoidance and resolution, orthogonality of policy scope, short-term versus long-term policy lifecycle, how present user-experience optimization should be balanced against future user-experience impact, how policy update review cadence should lengthen as the system becomes more stable, how environment understanding should flow from raw edge signals into structured context observations and then into a presence-consumable context snapshot, and how the shared observation vocabulary should be extended safely as new edge types are added.
- Heuristic-learning style improvement should live in one unified outer maintenance loop rather than the hot decision path: feedback, replays, and tests may drive coordinated updates to edge mappers, observation reducers, vocabulary, and presence policy, but those changes remain review-gated before entering the normal runtime path.
- Presence should consume the compact context snapshot directly rather than introducing an additional presence-only feature view; richer observation evidence remains available separately for agent reasoning and debugging when needed.
- The current design preference is that raw fine-grained device history remains edge-local by default: core stores normalized observations plus provenance, while deeper agent inspection of device history should use explicit bounded edge-side diagnostics or history retrieval instead of continuous raw-history duplication into backend state.
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
- 4.5. Define milestone M4: first mature host-edge runtime that can run stably as a real edge surface with continuous observation, durable control behavior, and edge-local verification without requiring the backend maturity work to be finished
- 4.6. Define milestone M5: mature runtime ingestion and context path on top of stable host-edge input, including gateway handling, normalized observation storage, snapshot reduction, and context freshness / ambiguity handling
- 4.7. Define milestone M6: mature presence, agent, and action path on top of stable real-edge input, so the proactive runtime chain becomes reliable beyond the current validation slice
- 4.8. Define milestone M7: operational-readiness verification milestone that gates "implemented and ready to run" claims on end-to-end host-edge-path validation rather than CLI-only checks
- 4.9. Define milestone M8: first formal terminal-edge interaction surface, turning the desktop/CLI edge into a resident terminal `Device Edge` with pull-style user requests, presence-gated runtime push, and explicit terminal activity sensing on the normal runtime path rather than as a chat-special case
- 4.10. Define milestone M9: cloud-model-backed agent baseline, so the runtime can use a real cloud model for proposal and reply generation while preserving explicit `Presence Router` governance, inspectable planning surfaces, and bounded non-model fallback behavior
- 4.11. Define milestone M10: model grounding and runtime memory baseline, so model-backed proposal and reply generation are anchored in compact context snapshot, active runtime goals, bounded edge-history retrieval, and durable state instead of behaving like stateless channel chat
- 4.12. Define milestone M11: terminal/CLI interaction maturity pass, so the first terminal edge grows from a minimal resident daemon into a substantially more complete agent CLI surface with stronger interaction ergonomics, session readability, streaming/status visibility, input affordances, and human-usable command-line UX that can better stand beside tools such as Lobster, Codex, and Claude Code without changing the core presence-governed runtime architecture
- 4.13. Define milestone M12: prompt/context engineering and behavior-contract pass, so grounded model-backed proposal and reply generation advance from first runtime-memory wiring into explicit prompt/context assembly, prompt versioning, replay/eval harnesses, and inspectable behavior contracts that verify the runtime actually uses compact snapshot state, active goals, bounded memory, and edge evidence reliably
- 4.14. Define milestone M13: proposal-formation maturity pass, so the runtime advances from the current narrow reply-shaped proposal slice into a sufficiently capable proposal-formation system that can interpret edge-delivered signals and grounded runtime context into inspectable `reply`, `action`, `clarification`, and `no_intervention` proposals on the normal live chain
- 4.15. Define milestone M14: model-provider connection reliability and diagnostics, so real cloud-model usage becomes stable, observable, and protocol-aware before deeper action-loop behavior depends on it
- 4.16. Define milestone M15: runtime-native credential and runtime-config baseline, so OpenHalo can authenticate real model-provider access through its own inspectable local runtime configuration flow instead of depending on ad hoc shell environment variables or external tool-specific credential stores
- 4.17. Define milestone M16: post-action deliberation and interaction action loop, so action results or fresh observations can re-enter `Agent Runtime` inside the same interaction lifecycle and yield a new inspectable `reply`, `action`, `clarification`, or `no_intervention` outcome instead of terminating at a fixed completion formatter
- 4.18. Define milestone M17: agent behavior contracts and unified action/tool governance, so model-backed proposal formation, post-action deliberation, model-native tool calls, MCP/tool/skill calls, runtime-local tools, and external device actions are constrained by one inspectable runtime contract and capability registry before side effects or user-visible output occur
- 4.19. Define milestone M18: policy learning and review loop, so intervention feedback, ignored interactions, explicit user responses, and runtime replays can produce review-gated policy updates rather than remaining as ad hoc one-off heuristics
- 4.20. Define milestone M19: multi-edge interaction expansion after the first terminal/model baseline, so additional device surfaces can join the same presence-governed interaction model without re-centering the system on any single frontend
- 4.21. Define milestone M20: bounded-growth and storage-hygiene hardening pass after the first mature product slice, covering unbounded state growth, high-frequency persistence pressure, duplicated long-term storage, and other operational accumulation risks across the system

Milestone ownership clarification:

- The structural home for richer proposal formation from edge-delivered signals, including proposal classes such as `reply`, `action`, `clarification`, and `no_intervention`, belongs primarily to the `M6` `Agent Runtime` proposal-formation surface.
- The accepted `M6` implementation should not be read as full semantic completion of proposal formation; before model integration it establishes the correct live-chain location and a narrow deterministic slice, but not yet sufficiently capable open-ended intent interpretation.
- `M13` is now the explicit maturity milestone for this surface: it owns turning that narrow slice into a reliable multi-type proposal-formation capability on the live chain.
- Adjacent milestones deepen that behavior from other angles without changing the ownership boundary: `M9` supplies provider-backed generation, `M10` supplies runtime grounding and memory, `M12` supplies prompt/context and behavior-contract hardening, `M14` supplies model-provider reliability and diagnostics, `M15` deepens operator trust through runtime-native credentials, `M16` supplies post-action deliberation and same-interaction action-loop re-entry, `M17` hardens behavior contracts plus action/tool governance, and later milestones deepen adaptation through review-gated policy learning (`M18`) once proposal typing, runtime credentialing, post-action behavior, and tool governance are mature enough to evaluate. The current M15 implementation begins with a narrow single-file local runtime-config baseline rather than an environment-variable fallback.

Acceptance criteria for M13 proposal-formation maturity:

- The normal live chain can emit inspectable proposal classes `reply`, `action`, `clarification`, and `no_intervention` from edge-delivered signals without bypassing `Presence Router`
- Proposal formation consumes compact snapshot state, active goals, bounded memory, and relevant edge evidence on the actual runtime path rather than falling back to raw text-only heuristics
- Proposal records expose enough structured rationale to inspect why a given input became a reply, action, clarification, or no-intervention decision
- The accepted live-chain implementation does not grow redundant middle layers beyond the documented `event -> compact snapshot -> grounding bundle -> prompt/context package -> proposal formation -> Presence Router -> execution planning/action` shape; inspection sidecars may exist, but they must remain secondary to the main runtime path
- Narrow deterministic fallbacks remain available when the model is unavailable, but the primary accepted path for open-ended intent interpretation is model-backed and grounded
- Automated tests cover at least one accepted scenario for each proposal class plus failure-path or ambiguity handling where clarification or no-intervention is the correct outcome
- Human acceptance demonstrates the feature in simulated real usage: a tester can drive representative terminal/device interactions through the live runtime and observe all four proposal classes appear in appropriate scenarios with readable inspection output

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
- Post-action deliberation can emit inspectable `reply`, `action`, `clarification`, and `no_intervention` outcomes grounded in the prior interaction state, current compact snapshot, active goals, bounded memory, and the new result/evidence
- Any user-visible follow-up or next-step action produced by that re-entry still passes through `Presence Router` rather than bypassing governance because it is "post-action"
- The accepted implementation may still keep one current `primary action` per deliberation turn, but one interaction may span more than one deliberation turn with traceable lineage between turns
- Automated tests cover at least one result-driven summary-only case, one follow-up action case, and one clarification or silent-completion case on the normal live chain
- Human acceptance demonstrates a realistic terminal/device scenario where a remote action result causes either a natural-language follow-up or another planned action through the normal runtime path

Acceptance criteria for M17 agent behavior contracts and unified action/tool governance:

- The runtime has an explicit behavior contract for model-backed proposal formation and post-action deliberation that defines allowed proposal classes, required grounding inputs, allowed action/tool targets, and when clarification or no-intervention is required
- Device-edge actions, runtime-local tools, model-native tool calls, MCP/tool calls, and skill/procedure calls are represented through one runtime-owned action intent/result envelope with explicit executor kind, capability, side-effect class, visibility, permission/governance requirements, and provenance
- Provider-native tool-call syntax is normalized into the runtime action intent model before execution; model-native tool calls cannot directly bypass `Presence Router`, capability validation, action permissions, or result recording
- Side-effectful or user-visible actions require validation against the behavior contract and capability/action registry before `Action Layer` execution, while bounded read-only internal tools may remain inside proposal formation when explicitly marked as non-user-visible and non-side-effectful
- Invalid, unsupported, or policy-disallowed model proposals are rejected, repaired, clarified, or converted to `no_intervention` with inspectable metadata rather than being executed opportunistically
- Post-action deliberation can use model-backed proposal formation over structured action results and prior interaction lineage, with metadata proving whether the outcome was model-backed or deterministic fallback
- Automated tests cover contract validation, registry rejection, allowed device action, allowed runtime-local tool, normalized provider tool-call input, MCP/skill placeholder executor routing, and post-action model-backed proposal metadata
- Human acceptance demonstrates a real or simulated terminal/host scenario where an action result re-enters model-backed deliberation, produces a non-fixed follow-up proposal, passes validation and `Presence Router`, and records complete action/tool lineage

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

- In progress (`M7`, `M8`, `M9`, `M10`, `M11`, `M12`, `M13`, `M14`, and `M15` completed and accepted; the first M16 action-result reentry slice is implemented with bounded verification, while broader M16 acceptance remains in progress; `M17` behavior-contract/action-tool governance is now the next hardening milestone before `M18` policy learning/review; `M19` multi-edge interaction expansion remains later work, with storage hardening deferred to `M20`)

## Completed Sub-goals

### Completed: Project-level AGENTS enforcement baseline

Result:

- Project-level Codex hooks have been added in `.codex/hooks.json`
- Shared enforcement logic has been added in `agent_guard/codex_hooks.py`
- `AGENTS.md` now documents the internal per-turn audit and the conditional `Project.md Check` exception path
- Project progress updates are now also hook-enforced: when the user asks for a progress report, the response must include separate `Goal 1` through `Goal 4` sections with explicit architecture-aware labels for `状态`, `架构位置`, `本批完成`, `对整体链路的作用`, and `还缺什么`
- Edited turns are now also hook-enforced: when a turn uses `apply_patch`, the final response must include a `架构实现小结` block with explicit `架构位置`, `本步完成`, and `影响链路` labels
- A minimal automated test suite validates audit parsing and enforcement rules
- The hook entrypoint is now path-portable through `.codex/run_hook.py`, so `.codex/hooks.json` no longer hard-codes the repository checkout path

Acceptance criteria:

- The repository has project-level Codex hooks for session start and turn-end enforcement
- The enforced workflow validates that `Project.md` was read at session start
- The enforced workflow validates that every meaningful interaction performs a `Project.md` progress check
- The enforced workflow validates the required `Goal 1` through `Goal 4` architecture-aware structure for project progress updates
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

- The normal sense-first live chain can now emit inspectable `reply`, `action`, `clarification`, and `no_intervention` proposals from ordinary edge-delivered text without bypassing `Presence Router`
- Proposal formation now consumes compact snapshot state, active goals, bounded memory, and bounded edge evidence on the actual runtime path, while recorded interventions and inspection output expose structured proposal rationale together with provider/fallback metadata
- The provider boundary now supports structured proposal-plan parsing, provider proposal-type normalization, and deterministic grounded fallback when the model is unavailable, without adding a redundant middle interpretation layer beyond the documented hot path
- The live provider compatibility layer is now more tolerant of real structured-proposal response variants as well: string-valued actions such as `respond`, reply-text aliases such as `response`, and string rationale summaries are normalized onto the accepted `notification.show` / structured-rationale runtime shape instead of silently suppressing delivery after a successful model call
- The local inspection and acceptance ladder now includes bounded M13 tooling: `python -m device_edge.cli.cli_edge --inspect-chain` prints proposal type and rationale on the live chain, and `bin/verify-proposal-formation` exercises the accepted `reply`, `action`, `clarification`, and `no_intervention` scenarios end to end
- Fresh targeted automated verification and bounded human acceptance now prove all four proposal classes on representative live terminal/runtime interactions, including the `no_intervention` path recording a proposal and ending with a suppressed action result instead of dispatch
- The accepted first `M13` slice still executes at most one current `primary action` per planning turn; that is an intentional implementation bound for the slice, not a claim that future interaction handling should remain permanently single-step
- The accepted `M13` boundary stops at first-turn proposal typing plus primary-action dispatch; post-action semantic handling remains intentionally out of scope here and is now promoted into explicit `M16` action-loop work rather than being represented by a completion-summary patch

Acceptance criteria:

- The normal live chain can emit inspectable proposal classes `reply`, `action`, `clarification`, and `no_intervention` from edge-delivered signals without bypassing `Presence Router`
- Proposal formation consumes compact snapshot state, active goals, bounded memory, and relevant edge evidence on the actual runtime path rather than falling back to raw text-only heuristics
- Proposal records expose enough structured rationale to inspect why a given input became a reply, action, clarification, or no-intervention decision
- The accepted live-chain implementation does not grow redundant middle layers beyond the documented `event -> compact snapshot -> grounding bundle -> prompt/context package -> proposal formation -> Presence Router -> execution planning/action` shape
- Narrow deterministic fallbacks remain available when the model is unavailable, while the provider boundary stays ready for model-backed structured proposal output
- Automated tests cover at least one accepted scenario for each proposal class plus ambiguity/suppression handling
- Human acceptance demonstrates all four proposal classes with readable inspection output on the live runtime path

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
- Prefer the next post-M7 milestone sequence to stay narrow and layered: M8 formal terminal edge first, M9 cloud-model agent baseline second, M10 grounding and memory third, M11 terminal/CLI interaction maturity fourth, M12 prompt/context engineering fifth, M13 proposal-formation maturity sixth, M14 model-provider connection reliability and diagnostics seventh, M15 runtime-native credential/runtime-config baseline eighth, M16 post-action deliberation/action loop ninth, M17 behavior-contract/action-tool governance tenth, M18 policy learning/review eleventh, and bounded-growth hardening later at M20
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

- Post-M15 architecture expansion is now ready to move through `M16` post-action deliberation/action-loop work and then `M17` behavior-contract/action-tool governance; `M15` runtime-native credential/runtime-config baseline is accepted as complete, while `M18` policy learning/review and broader `M19` multi-edge interaction expansion remain later work and bounded-growth/storage-hygiene hardening remains intentionally deferred to `M20`

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
- We have now explicitly accepted and marked `M5` complete in the project baseline after live host-edge verification of the `observation -> snapshot -> intervention` chain
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
- We now want the first real non-CLI edge to be the runtime's own hosting server, represented as a first-class edge rather than hidden backend instrumentation
- We now want that first host edge to evolve beyond passive observation into an explicit operational-control surface, while still keeping the control boundary narrow and inspectable
- We now prefer the first host-edge capability envelope to observe whole-host state while limiting executable actions to the personal runtime's own process or service lifecycle
- We now prefer the host-edge interface layer to stay stable even if the runtime later moves from a plain Python process to `systemd` or another deployment supervisor
- We now prefer `runtime_control` actions to stay deployment-agnostic and `runtime.collect_logs` to return structured diagnostics plus raw tail text rather than only opaque log blobs
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
- We now hard-enforce the project progress report format at the hook layer: when the user asks for progress, the response must include separate `Goal 1` through `Goal 4` sections and each section must carry the required architecture-aware labels
- We now also hard-enforce architecture-aware final reply summaries for edited turns: when a turn uses `apply_patch`, the final response must include `架构实现小结` with `架构位置`, `本步完成`, and `影响链路`
- We now move active execution focus to M7 operational-readiness verification: end-to-end host-edge-path validation must now gate stronger “implemented and ready to run” claims on top of the newly accepted M6 runtime behavior
- We now have a dedicated M7 implementation plan in `docs/plans/2026-06-21-m7-operational-readiness-verification-plan.md`, focused on turning host-edge readiness into a concrete bounded acceptance gate instead of another feature-expansion batch
- The default `bin/verify-host-edge` readiness run is now defined to cover both host-edge control entry modes we rely on operationally: the explicit direct-action fast path and the runtime-originated initiative path that still flows through snapshot rebuild, proposal formation, `Presence Router`, and normal action planning before hitting the host edge
- The host-edge daemon verification surface now includes an explicit bounded `max_action_requests` control so local readiness runs can exit after handling the intended number of action requests rather than relying only on idle-time timing
- Refreshed M7 verification evidence now passed across both targeted automated suites and a bounded real `bin/verify-host-edge` run: the repository can now gate stronger “implemented and ready to run” claims on both the direct-action host-control path and the normal runtime-initiative host-control path, each validated against a separate real host-edge daemon
- We now consider M7 complete: host-edge-path operational-readiness verification is no longer only a documentation rule, but a concrete bounded acceptance gate with real runtime, host-daemon, websocket, persisted-state, and dual-path action evidence
- We now reorder the post-M7 roadmap so storage hardening is no longer the immediate next step: M8 formal terminal edge, M9 cloud-model-backed agent baseline, M10 model grounding/runtime memory, M11 terminal/CLI interaction maturity, M12 prompt/context engineering, M13 proposal-formation maturity, M14 model-provider connection reliability and diagnostics, M15 runtime-native credential/runtime-config baseline, M16 post-action deliberation/action loop, M17 behavior-contract/action-tool governance, M18 policy learning/review, M19 multi-edge interaction expansion, and M20 bounded-growth/storage-hygiene hardening
- We now intentionally defer bounded-growth and storage-hygiene hardening to M20, after the first formal terminal/model interaction surfaces plus explicit proposal-formation maturity, model-provider reliability, credential-baseline, action-loop, action/tool governance, and policy-learning design have been validated more concretely
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
- We now want proposal-formation maturity to become its own explicit milestone after prompt/context engineering, so the runtime can reliably distinguish reply, action, clarification, and no-intervention outcomes on the live chain before post-action deliberation and policy learning start adapting that behavior
- We now want model-provider connection reliability and diagnostics to become the immediate milestone after proposal-formation maturity, because deeper action-loop behavior should not depend on a model path that still hides protocol mismatches, timeouts, fallback policy, or health status
- We now want runtime-native credential/runtime-config work to become the immediate milestone after model-provider reliability, so real provider access can become a product-owned capability before deeper post-action behavior depends on it
- We now want post-action deliberation and same-interaction action-loop handling to remain its own explicit milestone after runtime-native credentialing, rather than being approximated by a completion-summary patch on the gateway path
- We now want behavior-contract and unified action/tool governance to become the immediate hardening milestone after post-action behavior, so model-backed proposal formation, model-native tools, MCP/tool calls, skills, runtime-local tools, and device actions are all constrained by one inspectable runtime contract before policy learning starts adapting behavior
- We now want policy learning and review to remain its own later milestone after proposal formation, runtime-native credentialing, post-action behavior, and action/tool governance all mature, rather than being hidden inside the first provider-integration batch
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
- The current live diagnosis for 2026-06-25 is therefore no longer "CRS is simply healthy again", but it is also no longer "the provider must be globally broken": the project baseline now records both mixed CRS response shapes on this feat branch and a same-machine `master` manual acceptance that still produced normal natural-language terminal dialogue, so the next follow-up should treat feat-branch regression analysis as the primary path while still keeping the provider contract mismatch in scope
- We now consider M11 complete: the resident terminal edge has moved beyond the minimal M8 daemon baseline into a more human-usable CLI surface with readable session rendering, bounded local transcript/history, explicit `/help` `/status` `/history` `/quit` edge-local affordances, and a refreshed `bin/verify-terminal-edge` acceptance path that still validates the real presence-governed runtime chain
- The M11 terminal acceptance script no longer assumes a deterministic provider reply string for its pull-stage readiness check; it now waits on persisted terminal delivery evidence, which keeps the acceptance path valid across both local fallback and real model-backed reply variants
- We now consider M12 complete: the runtime has an explicit versioned prompt/context package, proposal-level prompt provenance metadata, a first inspectable behavior-contract surface, and a bounded `bin/verify-prompt-contract` acceptance path that re-checks the recorded grounded prompt package locally
- The local inspection ladder now extends beyond M10 grounding metadata into explicit prompt/context engineering: one `--inspect-prompt-contract` run now prints prompt sections, behavior-contract checks, and replay/eval results on the same grounded runtime chain
- We now consider M13 complete: the normal sense-first live chain can emit inspectable `reply`, `action`, `clarification`, and `no_intervention` proposals from grounded edge-delivered text without bypassing `Presence Router`
- Proposal formation now records structured rationale together with provider/fallback metadata on the live chain, while keeping the documented `event -> compact snapshot -> grounding bundle -> prompt/context package -> proposal formation -> Presence Router -> execution planning/action` shape intact
- The provider boundary now supports structured proposal-plan parsing plus proposal-type normalization, and the runtime retains deterministic grounded fallback when the model is unavailable
- The proposal-formation provider parser now also tolerates plain `output_text` replies from an OpenAI-compatible `/responses` route, mapping them back into normal `reply` proposals instead of surfacing parser/provider errors as user-facing dialogue
- Host-edge daemon receive handling now preserves action requests that arrive while the daemon is waiting for observation acknowledgements, so continuous host observation traffic no longer swallows `runtime.status` requests planned by the normal terminal-to-runtime-to-host chain
- The repository now has a bounded M13 acceptance ladder: `bin/verify-proposal-formation --dry-run` lists the accepted scenario checks, and the real `bin/verify-proposal-formation` run exercises `reply`, `action`, `clarification`, and `no_intervention` with readable rationale on the live chain
- Fresh targeted automated verification and bounded human acceptance now pass for M13, and the project has now completed and accepted `M14` model-provider connection reliability and diagnostics against its provider-probe, health/status, failure-classification, and controlled-failure criteria
- The first M14 provider-stability hardening slice now classifies OpenAI-compatible response shapes, retries transient empty-output response shapes such as Codex-agent envelopes or completed responses with no output before surfacing failure, and keeps terminal-facing errors product-safe while preserving the raw provider shape and reason in proposal metadata for diagnostics
- The provider-backed proposal path now uses a Responses `json_schema` structured-output request format when the selected model declares structured-output support, so `reply`, `action`, `clarification`, and `no_intervention` proposal formation is constrained at the provider protocol layer rather than by action-specific local fallback rules
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
- The first M16 action-result reentry slice is now implemented: `action_result` frames with a known `interaction_id` can rebuild decision-time snapshot and grounding context, re-enter `Agent Runtime` as `post_action` proposals, pass through `Presence Router`, and either dispatch a governed follow-up reply/action or complete silently inside the same interaction lifecycle
- M16 post-action proposal formation now has a provider-backed path over structured action-result evidence and prior interaction lineage: `generate_post_action_proposal_plan` sends the action result into the configured `proposal_formation` model profile, records whether deterministic fallback was used, and preserves a deterministic post-action fallback only for provider-unavailable or unsupported-adapter cases
- M16 interaction lineage is now inspectable through multiple intervention records sharing the same `interaction_id`, with post-action metadata such as trigger, turn index, parent proposal/action capability, result status, snapshot fields, and grounding counts
- The action loop still keeps one current `primary_action` per deliberation turn, but a single interaction can now span more than one turn; the old fixed completion formatter remains only as fallback for missing or unknown interaction lineage
- The repository now has a bounded M16 acceptance helper: `bin/verify-action-loop --dry-run` lists the action-loop checks, `bin/verify-action-loop` exercises runtime-status reentry, follow-up action planning, silent completion after delivered notification, and post-action lineage in an in-process runtime scenario, and `bin/verify-action-loop --runtime-config-path config/runtime-config.openai-local.toml --require-model-backed` requires model-backed post-action metadata before accepting the real-provider path
- Broader M16 acceptance remains in progress rather than complete: the model-backed post-action path is implemented and covered with fake-provider tests, but real-provider acceptance is currently blocked in this environment by provider connection failure (`[Errno 101] Network is unreachable`); fresh-observation reentry and a fuller host/terminal real-process acceptance path remain follow-up work on top of this action-result reentry foundation
- Full regression verification should now watch formal `coverage.py` line coverage alongside pass/fail results. The current baseline is 87% line coverage over `personal_runtime`, `device_edge`, and `agent_guard` after 288 passing unittest cases; future full-test summaries should call out meaningful coverage drops or low-coverage risk areas, especially on the runtime/action/presence/model and edge paths
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
