# OpenHalo Project

## Current Snapshot

This is the canonical project baseline. Read this section first; load linked
detail documents only when the task needs their evidence or design depth.

| Field | Current baseline |
| --- | --- |
| Phase | Post-M16 multi-edge and productization expansion |
| Current milestone | `M18` / Issue `#17` Persistent Personal Runtime refactor |
| Parent milestone | `M18` observation understanding and Main Hermes runtime |
| Next route | `M18` -> remaining `M17.8` -> `M17.11` -> `M17.9` -> `M17.10` -> `M20.1` -> `M21` -> `M22` -> `M23` |
| Accepted baseline | `M17.0` through `M17.7.2`, `M18.1`, `M4.1`, `M19`, `M20`, `M20.2`, and `M20.3` |
| Accepted cross-cutting slice | Hosted Coding Bridge adapter ([#14](https://github.com/nwomn/openhalo/issues/14)); parent/design tracked by [#10](https://github.com/nwomn/openhalo/issues/10) and [#11](https://github.com/nwomn/openhalo/issues/11) |
| Goal status | Goals 1-3 completed; Goal 4 runtime execution in progress; Goal 5 productization in progress; Goal 6 future research |
| Visual identity | Confirmed primary OpenHalo logo: the lower-left indigo `soft halo little ghost` with mint halo and muted periwinkle backdrop ([asset](assets/brand/openhalo-logo-primary.png)); selected 2026-08-23 |
| Execution source | [OpenHalo Development GitHub Project](https://github.com/users/nwomn/projects/1) |

Project tracking rules:

- Goals are the durable strategic baseline; GitHub Project `Initiative` is the active execution theme.
- Existing `M0` through `M23` identifiers remain historical identifiers.
- Future execution hierarchy uses Parent Issues and sub-issues rather than deeper milestone numbering.
- `M17` is the parent Issue; `M17.8`, `M17.9`, `M17.10`, and `M17.11` are its child Issues.
- A milestone becomes active only when its Parent Issue or child Issue is ready for implementation; later roadmap items remain planning drafts.

Progressive disclosure:

- Current implementation work: read the linked GitHub Issue and its plan/acceptance document.
- Architecture decisions: read the relevant file under `docs/plans/` or `docs/design/`.
- Completed evidence: read [`docs/history/project-completed-progress.md`](/root/openhalo/docs/history/project-completed-progress.md).
- M19 storage and owner-runtime evidence: read [`docs/history/m19-operational-status.md`](/root/openhalo/docs/history/m19-operational-status.md).
- Long-term research questions: read [`docs/research/project-open-questions.md`](/root/openhalo/docs/research/project-open-questions.md).

## Project Summary

OpenHalo is a new personal agent runtime system oriented around `device -> context -> presence -> action`, rather than the traditional `channel -> session -> agent` product shape.

The intended product is not "another chat agent entry point". OpenHalo is a personal runtime that can exist across multiple devices, maintain continuity across contexts, and decide how to surface itself through the most appropriate device or interaction surface. The current product direction is increasingly `presence-first`: the runtime should proactively infer user situation across input channels, decide whether to intervene, and learn intervention policy over time rather than waiting only for explicit user requests.

At the current stage, the project has moved from pure architecture-definition into an implemented and testable runtime baseline that now spans both the completed v0 single-edge WebSocket loop and the first same-template multi-edge routing slice. The architecture baseline and early milestone framing are in place, the first end-to-end desktop/CLI closed loop can be executed both in-process and across two real local processes, and the runtime can now route a normal action from one connected edge instance to another while preserving core state across restarts. The desktop/CLI surface has now been promoted into the first formal long-running terminal edge, with both user-initiated and runtime-initiated interaction still expressed through the normal `device -> context -> presence -> action` architecture rather than a chat-centered exception path. The current frontend baseline now includes both bounded scripted acceptance for repeatable verification and a true foreground live terminal session that reads user input from `stdin` on the same resident edge session.

The accepted M4.1 implementation moves colocated Host Edge process ownership into Personal Runtime: after Gateway readiness, Runtime starts one normal loopback Host Edge, persists redacted lifecycle diagnostics, retries failures with bounded exponential backoff and jitter, and cancels the session before Gateway shutdown. Its two-process human acceptance confirmed automatic Host Edge registration, a routed `runtime.status` action executed by `host-edge-1`, and clean shutdown without launching `host_daemon` separately.

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
- 2026-08-05 / 2026-08-23 ambient camera Edge direction: the future fixed-camera `Device Edge` uses a Runtime-confirmed scene profile and allowlisted Feature subscriptions. The Edge performs local low-cost feature extraction, structured Observations, candidate-event detection, and bounded pre/post-event evidence buffering; `Personal Runtime` remains responsible for scene/profile governance, high-level video/audio understanding, evidence queries, Presence, and action decisions. Raw camera/microphone upload is not the default. The first physical validation target is a mains-powered fixed desk/room Edge using the received Sipeed MaixCAM standard kit (integrated display, Wi-Fi, and vendor camera), a user-provided 64 GB TF card that must first receive the MaixCAM system image, and a bounded read-only diagnostic status contract; it is not a wearable or custom PCB. Basic stock-device bring-up has passed (Wi-Fi, development-host connection, MaixPy `hello_maix.py`, and camera preview). The `riscv64` device lacks `cryptography`, a compiler, and Rust; current `cryptography 46.x` releases have no Linux `riscv64` wheel, so a narrow OpenSSL-backed P-256 Camera Edge bootstrap was implemented. On the real MaixCAM it created a persistent identity, produced an ECDSA-SHA256 proof accepted by the OpenHalo Gateway verifier, then completed one-time pairing and a subsequent no-code authenticated `edge.runtime.v2` reconnect with the owner Runtime at `ws://8.153.37.167:8765`; it now registers a structured `camera.health` capability and has completed one real accepted health Observation batch (`connected`, `not_checked`, `ready`, and free-space) with an atomically stored local status payload. The server retains an active, non-revoked `camera-edge-1` record. An attempted direct Maix display adapter was deliberately deferred: `Display()` starts the vendor multimedia/sensor stack and temporarily blocked device management, so it cannot yet be claimed as a status-only display or run beside the capture path. The first authorized local-vision Feature is now opt-in `person_presence.v1`: one Camera Edge process owns Maix camera + YOLO11, requires repeated matching local samples before changing state, and publishes only `{state: present|absent|unavailable, count, feature_version}` and confidence through `camera.person_presence`; raw frames, geometry, other labels, face/OCR/gesture inference, evidence buffering, and display are excluded. The initial physical run safely persisted `unavailable` during a sensor timeout; after an owner reboot, the repeated real-device run completed camera/NPU inference and Runtime persistence as `{state: absent, count: 0}` at `2026-08-23T09:48:17.464423Z`, with normal multimedia release. This is narrow Feature acceptance for `absent` and safe failure reporting only; it is not a `present`/identity evaluation, supervised service, Scene-Profile/Feature-Subscription governance, or full M17.10 acceptance. The repeatable owner-development procedure is in [MaixCAM Camera Edge Development Runbook](docs/ops/maixcam-camera-edge-runbook.md). Detailed design is recorded in [M17.10 Ambient Camera Edge Design](docs/plans/2026-08-05-m17-10-ambient-camera-edge-design.md).
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
- `InteractionPool` is an internal sibling module of `Proposal Formation`, `Presence Router`, and `Execution Planning` inside `Agent Runtime`; it is not a new top-level process/lifecycle domain and is not part of the Hermes implementation itself. It owns interaction lifecycle, turn/action-result correlation, and re-entry state, while `RuntimeOrchestrator` coordinates continuation dispatch and reawakening of the same Hermes child session. Hermes-native child sessions perform semantic work, while Runtime remains authoritative for concurrency, context projection, Presence, executor validation, result correlation, timeout, recovery, and completion.
- Hermes-native child sessions have isolated conversation histories. Before initial work and every result-set continuation, Runtime supplies a bounded shared-context projection containing the OpenHalo identity contract, relevant durable MemoryStore facts, active goals, exact device roster, and interaction lineage/results. This is not a copy of the persistent main-agent transcript; Runtime records lifecycle/audit pointers while Hermes MemoryStore remains the semantic durable-memory authority.
- Model-native tool calls, MCP tool calls, runtime-local tools, skill/procedure invocations, and external device actions should converge into one runtime-owned action intent/result model before side effects occur; provider-native tool syntax is an adapter input, not a permission to bypass OpenHalo action governance
- `Personal Runtime` is the authoritative source of a bounded structured device roster projected from registered device identity, capability contracts, and live availability. The Agent Harness receives that roster and performs semantic target selection from it; `Runtime` validates and governs the selected exact device target but must not replace it through keyword routing or another semantic fallback.
- The executor kind for a model-native action is selected by the OpenHalo adapter or action registry, not by a model-supplied tool argument; the M20 `openhalo_action` bridge is limited to governed `Device Edge` actions, while runtime-local, MCP, and skill/procedure routes remain OpenHalo-owned registrations
- Agent behavior should be constrained by explicit prompt/context contracts, behavior contracts, capability/action registry validation, and post-generation validation or repair before any user-visible or side-effectful action is executed
- The long-horizon interaction-intelligence direction is a multimodal, time-aware model that may interpret continuous vision, audio, text, screen, and device evidence into interaction candidates such as `silence`, `observe_more`, `intervene`, or `delegate`; it must stop at a candidate boundary and never bypass Runtime-owned Presence, privacy, permission, routing, action validation, result recording, or feedback handling
- Personal multimodal data is user-owned and remains local to the relevant Device Edge and Personal Runtime by default. A future shared training corpus may contain only explicitly consented, reviewable, minimized interaction traces with documented provenance and licensing; it must not be built through default raw audio, video, or screen telemetry collection
- Presence policy should remain explicit and inspectable even when model-generated or model-repaired; models are not the only durable representation of proactive behavior
- A host-resident edge running on the runtime's own server is still modeled as a first-class `Device Edge`; physical co-location does not waive the `Edge Session Link <-> Gateway` boundary
- The runtime should support both a normal deliberative path and an explicit edge-requested fast path for direct actions
- A direct action fast path may bypass the normal `Agent Runtime` path, including `Presence Router`, but it must still pass through `Gateway`, validate structured input against the exact registered target capability/schema, restrict `runtime.*` actions to the explicit runtime-control allowlist, update runtime state/context, and record action results; on the normal path, a valid `runtime.* -> runtime.control` mapping remains subject to all ordinary Presence, modality, privacy, and schema filtering
- Runtime feedback interpretation should treat `ignore != negative`; explicit rejection or repeated similar-context dismissal should carry more weight than one-off non-response
- Presence policy updates should optimize for both immediate user experience and likely future user experience, rather than greedily maximizing the current interaction outcome
- For the first same-template multi-edge slice, ordinary routed actions should prefer a different online edge instance with the required capability before falling back to the source device
- Ordinary development work should be branch-first in the main workspace and should reuse the repository root `.venv` by default, while optional worktree-based dependency or packaging experiments should use an explicitly created worktree-local `.venv`
- Runtime startup should distinguish restart-heavy development acceptance from the installed personal Runtime: development helpers use port `18765` by default, while an installed Runtime is started and supervised as an implementation detail by the global `openhalo` command. Product users have one personal installation model, not a choice between visible system-service and personal modes. The obsolete `systemd` Runtime deployment has been retired; the current product deployment is the personal command/data model only.
- The personal installation owns one durable home, `OPENHALO_HOME` (default `~/.openhalo`), containing personal configuration, device identities, pairing records, state, and logs. Immutable program releases live separately under `~/.local/share/openhalo/releases/<commit>` with an atomically selected `current` release, so a program update never silently discards personal Runtime or Edge data.
- The host-class `Device Edge` is lifecycle-owned by its colocated `Personal Runtime`: after Gateway is listening, Runtime starts and supervises one loopback WebSocket Host Edge using the normal public Edge API. Host Edge startup or reconnect failure is not a Runtime-fatal condition; its supervisor must retry continuously with bounded backoff, preserve an inspectable unavailable/retrying state, and stop the edge task when Runtime stops. Physical colocation does not permit direct backend calls or removal of the `Edge Session Link <-> Gateway` boundary.
- Gateway binds each real WebSocket to exactly one successfully authenticated `device_id`: post-connect frames must carry that same identity, unauthenticated frames receive `not_connected`, cross-device frames receive `device_mismatch`, and a second live socket cannot silently replace an existing device session. The current pairing registry implements one-time-code issuance, device-specific bearer credentials, hash-only Runtime persistence, revocation, and restart survival; it is an accepted development compatibility baseline, not the product authentication target. Product Edges must use a one-time pairing code only to register a device public key, then authenticate every later Edge Session Link through a Runtime nonce challenge signed by that device's private key. The signed challenge binds the canonical Runtime audience, `device_id`, nonce, and expiry. Product mode must reject bearer device credentials and legacy shared tokens rather than retaining either as a fallback. Product Edge endpoints must support both `ws://` and `wss://`; plaintext `ws://` is a first-class, preferred owner connection path and must not be rejected merely because it uses a public IP address or lacks a domain, while `wss://` remains an optional compatible transport. P-256 proof, pairing, revocation, and audience binding remain mandatory for both schemes; `ws://` intentionally does not promise transport confidentiality, so the endpoint UI/CLI must state the selected scheme without turning it into a blocking TLS policy. An Edge persists only its Runtime endpoint, public identity metadata, and protected private key material, while Runtime persists public-key/device metadata, revocation state, and audit-safe pairing facts. For the first cross-platform product slice, an Edge stores its private key as `$OPENHALO_HOME/devices/<device_id>/identity.ed25519` (default root `~/.openhalo`), with parent directories `0700` and the file `0600`; it never enters `config.json`, logs, diagnostics, exports, or pairing receipts. Native system-keychain storage may later wrap or migrate this key, but is not a first-slice requirement. The detailed pairing ceremony, endpoint trust, rotation, recovery, and migration rules remain a dedicated design pass before implementation.
- CLI device validation is acceptable for early module testing, but host-edge verification is required before documenting a module as fully implemented and operationally ready
- In this project, `manual acceptance` or `human acceptance` means testing implemented functionality in a simulated real usage scenario, rather than only checking static output, isolated unit behavior, or non-interactive script success

Initial productization target:

- The first productized OpenHalo slice should package three surfaces together rather than treating them as unrelated developer processes: phone `Device Edge`, desktop/computer `Device Edge`, and server-side `Personal Runtime` plus host-class `Device Edge`
- OpenHalo remains one source monorepo while its product surfaces have independent distribution lifecycles. Shared source, protocol definitions, pairing semantics, and end-to-end regression stay together; Runtime and each Edge are separately installable, version-selectable, and updateable deliverables rather than separate GitHub repositories or one all-or-nothing installed program.
- OpenHalo exposes one personal-owner installation model across these surfaces: one global `openhalo` command for Runtime control and one `~/.openhalo` data home by default. A background Runtime/Host Edge supervisor may exist internally, but setup, start, status, logs, pairing, revocation, diagnostics, update, and rollback must not require the user to choose or operate a system-service mode.
- The Linux Runtime should support one primary install command or script that installs the globally available `openhalo` command and configures both `Personal Runtime` and the co-installed Host Edge under the personal owner, while still preserving the `Device Edge -> Edge API -> Gateway -> Personal Runtime` boundary
- Terminal Edge should be independently installable through one primary user command and expose `openhalo-edge`; its connection and device credential remain in the same owner-controlled `~/.openhalo` home without requiring root or a second configuration model
- Runtime and Terminal Edge program lifecycles must be independent even when both are installed on one machine: they use separate immutable release roots and separate update/rollback commands. `openhalo update` may stage, switch, and restart only Personal Runtime plus its managed Host Edge; `openhalo-edge update` may stage and switch only Terminal Edge. Neither command may replace, restart, or roll back the other surface. Pairing and owner data remain durable local data across either program update, and a later compatibility policy must reject or warn on unsupported Edge/Runtime protocol combinations rather than coupling release cadence by default.
- The Windows desktop edge should be installable through a normal user-facing installer rather than only through a development shell; the productized desktop package may include the runtime and host edge as optional local components that are installed but disabled by default
- The Android phone edge should be deliverable as an APK suitable for real-device installation outside Android Studio
- The standard deployment scene is: one public server running `Personal Runtime + host edge`, one computer running the desktop edge, and one phone running the phone edge
- The computer-server deployment scene is: one computer running `Personal Runtime + host edge + desktop edge`, with the phone edge connecting to the computer-hosted runtime
- Program releases and durable personal data are separate. The fixed-commit installer atomically selects `current` for bootstrap. The first GitHub Release update slice now provides `openhalo update --check`, `openhalo update`, and `openhalo rollback` from an installed immutable release: it resolves the latest non-prerelease Release only when its `release-manifest.json`, `SHA256SUMS`, and archive agree on one 40-character commit and SHA-256; stages the program privately; stops a running Runtime only after staging; atomically selects the candidate; starts it with the candidate Python; and restores the preceding release/Runtime if it does not become ready. It never installs directly from mutable `master` or resets `OPENHALO_HOME`. This is an unsigned GitHub-HTTPS/checksum baseline that verifies the published OpenHalo archive, not yet manifest-signature verification, hash-locked dependency wheelhouse, or persistent-state migration support; releases must preserve compatible state until an explicit migration/recovery design is implemented.
- M22 product blocker recorded from user feedback: the current manual `stop -> fixed SHA installer -> version check -> start` sequence is bootstrap or recovery plumbing, not an acceptable normal update experience. The ordinary owner path must be one `openhalo update` command with clear progress and outcome; it must select a verified immutable release, preserve compatible `OPENHALO_HOME` data, stage and health-check before activation, restart only after a successful switch, and automatically restore the previous release on failure. Users must not need to handle commit IDs, release paths, symlink switching, runtime PIDs, or service-management choices during a normal update.
- Product packaging is now an explicit product milestone, not only a release-engineering afterthought; UI polish, installation flow, hidden per-user supervision, endpoint pairing, safe release switching, and deployment clarity all count as part of the first productized slice

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
- The current design preference is that raw fine-grained device history remains edge-local by default: core stores normalized observations plus provenance, while deeper agent inspection of device history should use explicit bounded edge-side diagnostics or history retrieval instead of continuous raw-history duplication into backend state. Terminal Edge Coding activity uses an append-oriented, paged local journal: a simultaneous-active-task limit is only a resource guard, active task history is never truncated by event count, the UI loads bounded pages, and only completed-task history is reclaimed by configurable local capacity policy.
- Normalized Terminal Edge Coding activity enters Personal Runtime through the registered ordinary observation ingress. Coding source names carry vocabulary and provenance only; they do not activate source-specific suppression, priority, emphasis, or `record_only` lifecycle behavior. Generic privacy, retention, context, relevance, Agent Harness, Interaction Pool, and Presence policy apply uniformly. Individual Runtime observations remain bounded summaries or local evidence references and never become a continuous raw reasoning, full-output, or full-diff mirror.
- Agent initiative should be a first-class high-salience input to presence evaluation rather than a low-priority afterthought, but it should still remain subject to suppression, privacy, and timing policy.
- Runtime interaction lifecycle should be source-neutral through one bounded `InteractionPool` inside `Agent Runtime`: explicit user events, admitted observation-driven triggers, agent initiative, and later action-result or fresh-observation re-entry all register or resume ordinary interactions rather than using source-specific lifecycle paths. `M18` may decide whether passive evidence merits registration, but once registered its interaction has the same proposal, presence, action, result-routing, and completion semantics as a chat-originated interaction. A separate top-level `ContinuationRouter` is not part of the architecture; continuation coordination remains an internal `RuntimeOrchestrator` responsibility over `InteractionPool` records.
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

Goal 4 owns the milestone ladder from the initial architecture baseline through runtime execution, multi-edge expansion, observation understanding, productization, and later ecosystem integration.

The complete milestone definitions and acceptance criteria are maintained in the [milestone acceptance matrix](/root/openhalo/docs/plans/milestone-acceptance-matrix.md). `Project.md` keeps only the route and current status so the Agent can load detailed criteria when a milestone becomes active.

Current milestone groups:

- `M0`-`M16`: architecture, runtime, context, presence, model, terminal, and action-loop foundations; accepted baseline.
- `M17.0`-`M17.7.2`: public Edge API and Android/multi-edge foundations; accepted baseline.
- `M17.8`-`M17.11`: current Device Edge expansion under parent Issue `M17`.
- `M18`-`M19`: observation understanding and bounded storage; `M18.1` and `M19` accepted, broader `M18` remains on the active route.
- `M20`-`M20.3`: Harness, action governance, progress presentation, and stable Terminal Edge; accepted baseline.
- Hosted Coding Bridge adapter ([#14](https://github.com/nwomn/openhalo/issues/14)): accepted cross-cutting Terminal Edge capability; it does not create a new milestone or alter the active `M17.8` route.
- `M20.1`, `M21`, `M22`, `M23`: later procedural-memory, policy-learning, productization, and ecosystem-bridge route.

Goal-level acceptance rules:

- Each milestone has a clear scope and explicit acceptance criteria in the matrix.
- Each milestone can be accepted independently, with dependencies recorded in its definition.
- A milestone is not active merely because it exists on the roadmap; it becomes active when its Issue or child Issue is ready for implementation.

Status:

- In progress; the current execution target is `M18` / Issue `#17` Persistent Personal Runtime refactor.

### Goal 5: Productize OpenHalo into an installable three-end system

We need OpenHalo to become a coherent product that can be installed, configured, connected, and tried without requiring the user to manually run unrelated developer processes.

Sub-goals:

- 5.1. Define one personal-owner deployment shape across phone edge, desktop/computer edge, and Runtime/Host Edge, with `OPENHALO_HOME` defaulting to `~/.openhalo`
- 5.2. Provide a Linux personal Runtime installation path that installs and internally supervises `Personal Runtime + Host Edge` together through the global `openhalo` command
- 5.3. Provide a Windows desktop edge installer that can connect to a remote Runtime and can optionally include disabled-by-default local Runtime/Host Edge components under the same personal-owner model
- 5.4. Provide an Android APK delivery path for the phone edge outside Android Studio
- 5.5. Define first-run setup, endpoint pairing, connection health, diagnostics, and recent-activity UI expectations across phone and desktop surfaces
- 5.6. Provide staged immutable-release updates, safe rollback, and explicit persistent-state migration handling without data loss
- 5.7. Verify the two accepted deployment scenes: standard public-server deployment and computer-server deployment

Acceptance criteria:

- A written productization baseline exists for the first installable OpenHalo slice
- The accepted deployment scenes are documented clearly enough that a user can tell what machines and packages are required
- Linux Runtime/Host Edge installation can be performed through one primary command or script and results in hidden personal supervision with `openhalo` status/log visibility
- Windows desktop edge installation produces a user-facing installed app, not only a development-shell entrypoint
- Android phone edge delivery produces an installable APK preserving the accepted daily-use phone-edge behavior
- Phone, desktop, runtime, and host edge all continue to communicate through the public Edge API boundary; packaging must not introduce hidden backend shortcuts
- Program updates are verified immutable releases that stage before activation, retain the prior executable release for rollback, and preserve compatible `~/.openhalo` data; unsupported state migrations stop explicitly rather than silently resetting data
- Manual acceptance demonstrates both standard public-server deployment and computer-server deployment using packaged or packaging-equivalent artifacts

Status:

- In progress (`M22` is the first concrete implementation milestone for this goal; staged update/rollback is part of this packaging baseline, while broader product polish, app-store distribution, account/login UX, and encrypted local secret storage remain later hardening)

### Goal 6: Build toward user-sovereign multimodal interaction intelligence

OpenHalo's long-horizon product direction is an interaction model that can remain appropriately present across continuous multimodal evidence, rather than only answering an isolated turn after a user asks. This goal does not make every user train a separate foundation model, and it does not replace the Personal Runtime with an opaque end-to-end action system.

Sub-goals:

- 6.1. Define the interaction-model boundary: a future model may synthesize time-aware candidates from vision, audio, text, screen, and structured device evidence, but `Personal Runtime` remains authoritative for Presence, privacy, permissions, routing, action validation, result correlation, audit, and feedback
- 6.2. Define the personalization boundary between a general interaction prior, user-owned Runtime memory and Presence policy, and optional user-controlled local adaptation; personal context must not be assumed to train a distinct foundation model for every user
- 6.3. Define a user-sovereign interaction-trace lifecycle: local capture and replay, reviewable minimization/redaction, explicit contribution consent, provenance and license records, retention, export, and the limitations of withdrawal after model training
- 6.4. Define the future open research path for a general interaction prior, combining legally usable public data, synthetic or simulated scenarios, and explicitly consented real interaction traces without default raw audio, video, or screen telemetry collection
- 6.5. Derive future concrete implementation milestones only after the privacy, data-governance, model-boundary, and evaluation contracts are specific enough to accept independently

Acceptance criteria:

- A written design defines the target model as an interaction-candidate generator, with Runtime-owned governance and action execution remaining outside the model boundary
- The project distinguishes a general multimodal interaction prior from per-user Runtime context, policy, memory, and any optional local adaptation
- The data-governance design makes local ownership the default and requires user review, explicit consent, minimization/redaction, provenance, and licensing before a trace can enter a shared corpus
- The design identifies that learned `silence`, timing, modality choice, and intervention intensity require time-aligned outcomes and negative or counterfactual evidence, not only generic multimodal question-answer data
- The first implementation milestone, if any, is scoped separately and does not alter the current execution route until its privacy, lifecycle, and evaluation acceptance criteria are approved

Status:

- Future / not started. This is a strategic Goal rather than a scheduled milestone; it does not change the active `M17.8` through `M23` execution route.

## Historical Reference Links

Detailed early Android and multi-edge preparation notes are preserved in the [M17 preparation archive](/root/openhalo/docs/history/m17-preparation-notes.md). The active M17 route and current acceptance boundaries remain in `Current Snapshot` and `Current Project Progress`.

## Completed Progress Index

The detailed acceptance history is preserved in [the completed-progress archive](/root/openhalo/docs/history/project-completed-progress.md). This section keeps only the current baseline needed for planning.

Accepted implementation baseline:

- `M17.0` through `M17.7.2`: public Edge API, registration, Android Edge, mobile hardening, screen/context observation, multi-edge lineage, and mobile liveness.
- `M18.1`: observation-to-snapshot decision-space integration.
- `M4.1`: Runtime-managed Host Edge lifecycle.
- `M19`: bounded SQLite state, retention, diagnostics rotation, and owner-runtime storage acceptance.
- `M20`: Hermes Agent Harness and governed action loop.
- `M20.2`: Runtime-owned interaction progress lifecycle and Android progress presentation.
- `M20.3`: stable independent Terminal Edge and user-facing receipt/progress surface.
- Hosted Coding Bridge adapter ([#14](https://github.com/nwomn/openhalo/issues/14)): managed Codex App Server lifecycle, bounded coding attention/steering, local approvals, and existing P-256/session preservation; accepted 2026-08-04.

The detailed archive is historical evidence, not a second current-status source. Update the current summary and route here when a milestone changes status.

## Research Backlog

The low-frequency design questions previously embedded here are preserved in the [research backlog](/root/openhalo/docs/research/project-open-questions.md). Load that document when doing research or making a related architecture decision; it is not required for ordinary milestone implementation.

## Current Project Progress

The project is in the post-M16 multi-edge and productization expansion phase.

### Current execution state

- `M18` / Issue `#17` is now owner-authorized as the active Runtime refactor. Its first implementation slice introduces independent ContextFact, ContextEnvelope, Main-session, Scheduler, and attention-validation modules with unit-level contracts; Gateway remains only ingress validation, Observation persistence, ContextFact materialization, and handoff. The Main-session manager is now wired into normal Hermes semantic calls: it persists a Runtime-owned identity before invocation, injects that identity as the native Hermes session ID, restores it after SQLite-backed Runtime restart when available, and otherwise creates a new audited generation. The remaining M17 Edge milestones retain their scope and provide later physical acceptance inputs.
- 2026-08-23 M18 foundation release: `v0.1.23` publishes the ContextFact/Envelope, SQLite v2, scheduler, Main-session, attention, Edge evidence-read, and architecture-diagram slice at commit `fa78ea3`. Its release manifest retains `sqlite-v1` as the updater compatibility level so existing installed clients can discover and stage the release; the candidate Runtime upgrades its database internally to SQLite v2 on first start.
- `M17.11` and `M17.9` remain queued Device Edge child Issues after the active M17.10 slice. The M17.10 hardware validation uses the received Sipeed MaixCAM standard kit with a bounded read-only diagnostic display; M17.10 is not accepted until its separately documented Observation, governance, evidence, privacy, and human-acceptance criteria are met.
- The generic `registration registry -> ContextFact -> ContextEnvelope -> Main Hermes` implementation belongs to broader `M18` under [issue #17](https://github.com/nwomn/openhalo/issues/17), not to M17.10. M17.10 supplies real Camera Edge facts and later hardware acceptance input for that Runtime refactor; it must not absorb Main Hermes implementation scope merely because the MaixCAM exposes the current gap.
- 2026-08-21 `M17.11` first physical-validation reference: use open-source ESP-KVM on an ESP32-P4 plus TC358743 HDMI-to-CSI bridge as the first Proxy Interaction Edge hardware candidate after `M17.8`. It provides a bounded HDMI/video, USB HID, virtual-media, and optional isolated ATX path for an unmodified target; OpenHalo must adapt it through its own paired Edge identity and public Edge API. This is a validation reference only, not a vendor, board, or protocol lock-in for the hardware-independent M17.11 contract.
- 2026-08-21 `M17.11` procurement note: the first purchased controller is the Waveshare `ESP32-P4-WIFI6` (SKU 32020), with an onboard ESP32-C6 for the intended wireless deployment, paired with the Geekworm C790 capture bridge. This board is not covered by ESP-KVM's current prebuilt `p4-eth` or `funcev` images, so a dedicated board profile and Wi-Fi/USB/capture pin validation remain required before it can count as physical acceptance evidence.
- 2026-08-21 `M17.11` first mobile-target validation profile: use the owner's Redmi K70 Ultra as the initial controlled-phone target. Because the handset has no currently verified native USB-C video-output path, the first bench route is `phone wireless display -> Miracast HDMI receiver -> C790` for observation and `ESP32-P4 USB device/HID -> phone USB OTG` for input; a generic USB-C-to-HDMI dock is not part of this phone-specific baseline. This remains a compatibility-path experiment: acceptance must separately record casting setup/recovery, end-to-end latency, keyboard/mouse coverage, secure-screen and gesture limitations, and whether the phone can maintain OTG while charging.
- The remaining M17 child milestones follow the active M18 Runtime refactor and provide Edge-specific acceptance evidence without changing its generic registered-context contract.
- `M20.1`, `M21`, `M22`, and `M23` remain later roadmap items with planning summaries rather than active implementation tasks.
- `M19` is accepted and reopens only if bounded-storage or response-path regressions recur.

### Current architecture direction

- Frontend remains `Device Edge`; backend remains `Personal Runtime`.
- The runtime path remains `event -> compact snapshot -> grounding bundle -> prompt/context package -> model-backed proposal formation -> Presence Router -> execution planning/action`.
- 2026-08-07 continuous interaction implementation: `InteractionPool` is a sibling internal module of Proposal Formation, Presence Router, and Execution Planning inside `Agent Runtime`; it extends the former one-shot ledger into the source-neutral lifecycle manager. Persistent interactions retain bounded objectives, watches, obligations, process state, health, and Hermes child-session lineage. `RuntimeOrchestrator` dispatches ordinary Edge facts, bounded evidence, action results, timeouts, and health changes to `InteractionPool`, then reawakens the same Hermes session when another semantic turn is required. No independent `ContinuationRouter`, Coding lifecycle, or device-specific Runtime lifecycle is introduced. Edge remains responsible for high-density structured facts, coverage, and bounded evidence buffers, while Runtime owns event interpretation, evidence escalation, health reconciliation, Presence, and final completion decisions. The interaction-pool continuation, ActionBatch, and full Python regression acceptance all pass on this baseline.
- 2026-08-08 Pool-owned cross-interaction context projection: when a new user Interaction is created, `InteractionPool` now returns a bounded summary of same-source persistent/recent process records and stores only their Interaction IDs plus process-state versions in the new record lineage. `RuntimeOrchestrator` carries those summaries through the existing grounding bundle to the new Hermes turn, so status queries can use authoritative completed/failed/monitoring facts without a duplicate RuntimeState process index or full Interaction-history injection. Focused Pool and Orchestrator regressions cover the projection and reference boundary.
- 2026-08-08 projection hardening: shared-edge summaries retain causal/process/capability labels for disambiguation, Pool and grounding apply independent byte/count limits, and every Pool-owned lifecycle/process mutation advances the persisted process-state version used by lineage references.
- 2026-08-08 SQLite recovery/update hardening: Runtime state recovery preserves the corrupt database and sidecars, updater integrity-checks SQLite before switching releases, and rollback/migration moves the database together with its WAL/SHM artifacts.
- 2026-08-08 Coding action contract repair: Execution Planning canonicalizes a Hermes `coding.turn.start` `instruction` payload to the registered Edge `task` schema before injecting the Runtime-owned workspace and Interaction identifiers, preventing a valid coding request from being rejected as an unregistered capability.
- 2026-08-08 architecture upgrade is In Progress/P0 in [issue #17](https://github.com/nwomn/openhalo/issues/17): parallel per-Interaction workers, non-blocking Gateway ingress, a persistent Main Hermes semantic session, Child Session context relief, and versioned Runtime state/evidence projection must be implemented as one coupled Runtime/Hermes loop.
- 2026-08-09 non-blocking Gateway ingress acceptance slice completed: authenticated WebSocket frames now start independently, while frames carrying the same explicit Interaction identity (including Coding activity observations) are serialized in arrival order. Capability registration remains a short ordered ingress prerequisite and outbound frames remain serialized per WebSocket. This removes the observed background-coding-to-normal-dialogue head-of-line block without changing the Gateway -> Agent Runtime architecture; the broader per-Interaction worker, priority, coalescing, and Main Hermes loop work remains in [issue #17](https://github.com/nwomn/openhalo/issues/17).
- 2026-08-09 manual acceptance evidence: while Coding `interaction-62` was active, status-query `interaction-63` completed at 08:30:18 UTC before the Coding `turn_completed` observation at 08:30:53 UTC; a later `interaction-64` correctly reported the completed state. This accepts removal of the foreground-dialogue head-of-line block. The same run also exposed an open result-projection gap: Runtime persisted the finished file and passing-test evidence, but the later user reply said that no artifact/test detail was available. Child-process result evidence must therefore be projected into the bounded authoritative context used by the Main Hermes loop before the broader interaction-context acceptance can close.
- 2026-08-09 Main Hermes architecture clarification: the persistent Main Session spans semantic Proposal Formation and semantic Execution Planning across the Agent Runtime, so one continuous memory can connect user intent, process understanding, proposal, action intent, and result interpretation. Runtime retains deterministic action validation/execution boundaries, while Presence Router remains an explicit model-independent governance gate; Child Sessions handle process-local context and return bounded semantic deltas to Main.
- 2026-08-23 registered-Edge context decision: registering a schema-valid Observation provider is the default context-admission path for OpenHalo personality. Runtime must generically project every accepted registered Observation into a provenance-bearing, freshness-aware context fact for Main Hermes, without per-device or per-Observation Runtime reducer/prompt code. Runtime's shared schema, bounded-value, coalescing, stale/`unknown`, and raw-media/evidence boundaries remain; Presence Router separately governs proactive action. Current fixed compact-snapshot code is a transitional implementation gap, not the target architecture.
- 2026-08-23 #17 refactor contract documented: replace `fixed observation name -> fixed compact snapshot field` with `registration registry -> generic ContextFact table -> versioned ContextEnvelope -> Main Hermes`. The migration keeps a temporary legacy projection only for already-shipped Presence rules, requires registered-Edge visibility without Runtime name branches, and has explicit unknown/stale, same-name multi-device, bounded-query, and real-MaixCAM-to-phone acceptance criteria.
- 2026-08-23 M18 implementation layout: the architecture diagram now renders `Gateway -> ContextFact Materializer/SQLite -> ContextEnvelope Compiler -> InteractionScheduler -> Main Hermes or per-Interaction Child -> Presence -> Runtime Validation -> Action Layer`; evidence escalation is a correlated `context.evidence.read` Edge action. This makes the implemented internal modules and their one-way boundaries explicit without turning Gateway or the Orchestrator into a multi-layer service.
- The accepted target layout, concurrency rules, authority boundaries, and Main/Child context contract are documented in [Main Hermes And Parallel Interaction Runtime Design](docs/design/2026-08-09-main-hermes-interaction-runtime-design.md) and tracked for implementation by [issue #17](https://github.com/nwomn/openhalo/issues/17).
- Cross-boundary traffic must continue through `Edge Session Link <-> Gateway`.
- Presence remains an explicit, inspectable governance layer inside `Agent Runtime`.
- 2026-08-03 Coding Agent Bridge direction: the Codex-first bridge is a cross-cutting capability inside the existing Terminal Edge, not a new Device Edge identity or coding-specific Runtime lifecycle. Terminal Edge owns local App Server observation, bounded evidence, and confirmed turn steering; broader M18 owns attention admission, sealed `experience_discovery`, Interaction Pool registration, Presence, and proposal governance; M20.1 remains the later owner of governed Skill drafts. The delivery is tracked under [#10](https://github.com/nwomn/openhalo/issues/10) with design child [#11](https://github.com/nwomn/openhalo/issues/11), and does not alter the active `M17.8 -> M17.11 -> M17.9 -> M17.10` route.
- 2026-08-03 hosted Coding Bridge implementation: Terminal Edge now owns a managed stdio Codex App Server lifecycle, one independent Codex thread per OpenHalo interaction, bounded `coding.attention.v1` evidence, `coding.turn.start`, confirmed `coding.turn.steer`, and local Codex approval handling. Runtime remains the authority for task interpretation and governance; no second Device Edge identity or provider-specific Runtime shortcut was introduced.
- 2026-08-04 Issue [#16](https://github.com/nwomn/openhalo/issues/16) implementation direction: the existing hosted bridge gains an expandable structured Coding activity panel and exact foreground correction/interrupt routing through the outer composer. New activity events use the neutral `coding.activity.v1` ordinary-observation vocabulary; the previous `coding.attention.v1` name remains readable only for historical compatibility and is not dual-written. Edge-local active-task journals are paged and durable without a small per-task event ceiling; the default concurrent-active guard is 32 and completed-task cleanup is capacity-based. This cross-cutting work does not alter the active `M17.8 -> M17.11 -> M17.9 -> M17.10` route.
- 2026-08-04 Issue [#16](https://github.com/nwomn/openhalo/issues/16) Edge acceptance: a real paired Terminal Edge displayed live Coding activity, selected an explicit task, routed outer-composer correction to the exact Codex turn, interrupted it with `Esc`, and loaded local history with `PageUp`. Runtime received `coding.activity.v1` as an ordinary observation with reasoning, command, test, agent-message, correction, and turn-lifecycle events. The acceptance also found and fixed late same-turn activity reopening a completed local task; the focused Issue #16 regression set passes 88 tests.
- 2026-08-05 Issue [#16](https://github.com/nwomn/openhalo/issues/16) activity-stream follow fix: a second acceptance pass found the Coding activity panel appeared stuck at the first minutes while the task kept running. Runtime and Edge-local records proved the data path was healthy (runtime received `coding.activity` until 08:38:20Z; the Edge journal held 46 events and the task completed), and the root cause was purely presentational: `#coding-activity-log` was a fixed-height `Static`, whose virtual size never grows with content, so overflow was clipped and no scrolling existed. The fix wraps the text in a `VerticalScroll` container (`#coding-activity-scroll`) whose virtual size tracks content, adds anchored bottom-follow on each refresh, pauses follow while the user scrolls up and resumes at the bottom, and keeps follow paused during `PageUp` history paging. Two auto-scroll regression tests were added; the full regression passes 858 tests (4 intentional skips, 19 subtests). Published as `v0.1.15` with immutable GitHub Release assets (`openhalo-v0.1.15.tar.gz`, `release-manifest.json`, `SHA256SUMS`).
- 2026-08-09 Issue [#16](https://github.com/nwomn/openhalo/issues/16) is formally closed: its Terminal Edge activity-window scope is accepted and complete. It remains a completed Coding Bridge work item, not a separate Runtime milestone and not evidence that broader `M18` or [#17](https://github.com/nwomn/openhalo/issues/17) is complete.
- 2026-08-04 Issue [#14](https://github.com/nwomn/openhalo/issues/14) acceptance: focused bridge/runtime coverage and the full Python regression passed (730 tests, 4 intentional skips); owner Terminal Edge acceptance kept the existing P-256 device/session boundary, completed local Codex approval, created and ran `openhalo_codex_demo.py`, and observed the Codex turn completion. Issue #14 is accepted for its adapter scope; the separate Runtime receipt-timing follow-up remains outside this closeout.
- Detailed architecture and milestone evidence are loaded from linked documents rather than repeated in this baseline.

### Current acceptance anchors

- `M18.1` is accepted; mobile observation evidence now enters the compact snapshot decision space with freshness-aware handling.
- `M19` is accepted; SQLite-backed bounded persistence, retention, diagnostics rotation, migration, and owner-runtime acceptance are documented in the [M19 operational archive](/root/openhalo/docs/history/m19-operational-status.md).
- `M20`, `M20.2`, and `M20.3` are accepted; their detailed Harness, progress, Terminal, Android, and human-acceptance evidence remains in the [completed progress archive](/root/openhalo/docs/history/project-completed-progress.md).
- Hosted Coding Bridge adapter ([#14](https://github.com/nwomn/openhalo/issues/14)) is accepted; the separate Runtime receipt-timing follow-up remains outside this closeout.
- `M22` productization remains an active Goal 5 direction; packaging, update, pairing, and three-end deployment details must be checked against the latest implementation documents and Issues.

### Next execution route

1. `M17.8` mobile sensitive-screen capture governance.
2. `M17.11` Proxy Interaction Edge baseline.
3. `M17.9` native Windows Desktop Edge baseline.
4. `M17.10` Ambient Home Presence Edge baseline.
5. Broader `M18` Agent Harness-controlled observation understanding.
6. `M20.1` governed procedural-memory and skill lifecycle.
7. `M21` policy learning and review.
8. `M22` first packaged three-end product slice.
9. `M23` Home Assistant and smart-home bridge.

For detailed evidence, read the linked archives or the relevant milestone plan/Issue rather than expanding this section with another historical log.

## Progress Update Rules

When updating this file:

- Keep `Current Snapshot`, goal statuses, the active route, and acceptance summaries current.
- Keep completed work clearly marked in the `Completed Progress Index`; preserve detailed evidence in the linked archive.
- Add new milestones or sub-goals only when they become concrete enough to evaluate.
- Do not mark a sub-goal complete unless its acceptance criteria are satisfied.
- Do not copy detailed implementation history, raw investigation logs, or low-frequency research questions back into this baseline.
