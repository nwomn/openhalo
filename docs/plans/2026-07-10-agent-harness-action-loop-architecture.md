# Agent Harness and Runtime Action Loop Architecture

## Purpose

This note records the target architecture that guided the accepted `M20`
refactor. It remains the architectural source for the implementation plan, not
a request to reopen the wider OpenHalo product worldview.

The completed implementation establishes the runtime-owned Harness contracts,
a legacy compatibility adapter, a Hermes action bridge, curated read-only
research, and Hermes-native persistent memory while preserving the accepted
external action loop. Configured-provider human acceptance completed the M20
scope; broader M18 now builds on this foundation and M20.1 owns governed skill
drafts.

## Architecture Decision

OpenHalo should preserve its top-level `Device Edge -> Gateway -> Personal Runtime -> Presence Router -> Action Layer` worldview, but M20 should replace the current agent-execution implementation with a Hermes-backed agent harness behind an OpenHalo adapter.

This is a reuse decision, not a request to recreate a generic agent framework. M20 must adopt a pinned Hermes agent-core dependency or a vendored Hermes agent-core subset as the default harness implementation. It must not create a parallel greenfield implementation of the agent loop, prompt builder, memory/session loop, provider loop, or general tool runner merely because a local rewrite appears more convenient.

The key distinction is that OpenHalo has two nested loops:

- External runtime action loop: the runtime receives observations, events, and action results through `Gateway`; runs the agent harness; emits an action or terminal outcome; executes through the governed action path; then receives the resulting action result or new observation back through `Gateway`.
- Internal agent loop: a single harness run assembles context, retrieves memory, calls the model, interprets tool/action intent, applies loop guardrails, and decides whether to emit an action candidate, continue reasoning, write memory, or terminate.

The outer loop is runtime-owned and crosses the edge/runtime boundary. The inner loop is agent-owned and stays inside the harness execution layer.

## Target Shape

```text
Device Edge
  -> observation / event / action_result
  -> Gateway
  -> State / Context ingest
  -> Agent Harness Layer
       -> Context Assembly
       -> Working Memory
       -> Memory Retrieval
       -> Internal Agent Loop
       -> Proposal / Action Intent
       -> Memory Write / Consolidation Decision
       -> Termination Decision
  -> Presence Router
  -> Execution Planning
  -> Action Layer
  -> Device Edge execution
  -> new action_result / observation
  -> Gateway
```

The loop continues until the harness and governance path produce a terminal outcome such as `no_intervention`, `complete`, `suppressed`, or `failed`.

## Harness Responsibilities

The future `Agent Harness Layer` should be treated as a named architecture layer that spans existing implementation concerns rather than as a single new monolithic module.

It should cover:

- Context assembly from user prompt, edge event, current interaction history, system and behavior contracts, compact snapshot state, active goals, bounded memory, and relevant edge evidence.
- Working memory for turn-local reasoning state that should not automatically become durable state.
- Procedural memory for skills, tool-use instructions, and how-to knowledge.
- Semantic memory for durable facts, user profile, preferences, and stable project/runtime facts.
- Episodic or temporal memory for dated events, interactions, action results, and past turns.
- Memory consolidation, including summarization, fact distillation, and explicit decisions about what becomes durable memory.
- Internal model/tool/action loop handling, including action-result re-entry, loop limits, retry/failure behavior, and terminal outcome selection.

Hermes is the implementation source for the harness boundary and must be wrapped by an OpenHalo adapter. The adapter is the only intended new core implementation work. It should translate OpenHalo runtime input into Hermes-compatible harness input, translate harness output into OpenHalo proposal/action-intent contracts, attach interaction lineage and diagnostics, and split tool usage into two classes:

- agent-private tools: Hermes-native search, bounded HTTPS retrieval, compression, summarization, and local diagnostics that stay inside the harness loop. They may be auto-approved only when explicitly classified as bounded, non-user-visible, and non-side-effectful; network or data-egress tools still require OpenHalo-owned allowlist, budget, timeout, audit, and prompt-injection controls.
- runtime-governed actions: edge notifications, cross-device control, policy writes, or any other user-visible or side-effectful operation. These must exit the harness as an OpenHalo action intent and pass through `Presence Router`, execution planning, and `Action Layer`. Hermes-native memory writes are a deliberate non-visible exception: they remain inside the harness under the Hermes memory lifecycle and an OpenHalo audit/provenance policy, rather than pretending to be device actions.

The adapter must disable or replace any Hermes default that would directly execute an OpenHalo-governed action. Hermes may decide that it wants an action; it cannot become the authority that dispatches an edge action.

## Curated Hermes Capability Policy

OpenHalo does not enable Hermes' default tool surface. The current M20 adapter
exposes only the deferred `openhalo_action` bridge, curated `fetch`/`search`
research wrappers, and Hermes' native memory tool. Search uses an
operator-configured HTTPS endpoint; fetch performs bounded public HTTPS
retrieval. Neither capability needs a browser process or a desktop GUI.

The following Hermes capability classes are unavailable to the OpenHalo
harness: terminal/process/shell execution, file read or mutation, code
execution, skills, plugin dispatch, delegation/subagents, cron, arbitrary MCP
tools, Home Assistant or other integration actions, and all browser execution,
interaction, console, or CDP paths are unavailable to the OpenHalo harness.
Browser-backed rendering is deliberately deferred from M20 and must return as a
separate design and acceptance item rather than being enabled by a runtime
configuration change alone.

Read-only network results are untrusted data, never instructions. The
adapter limits calls, URLs, result size, wall-clock time, and public-network
targets; `fetch` likewise connects only to the freshly validated pinned IP
while preserving the original hostname for TLS verification. It records
request/result metadata and integrity hashes, not raw remote bodies, in the
OpenHalo trace. A remote page cannot grant new tools, change policy, or
authorise an action.

### Research Source Governance

OpenHalo does not use a coarse rule that a turn becomes unable to act or write
memory merely because it performed research. Instead, every successful
`fetch`/`search` result carries untrusted, body-free provenance; any later
`openhalo_action` intent carries the exact research references plus a
hash-only reference to the authenticated normal user text that initiated the
turn. `RuntimeOrchestrator` independently recomputes and verifies that user
reference before `Presence Router`.

Before an untrusted research record may support a governed action, its audit
must identify the tool call, source URL and hash, result hash and length,
policy version, allowed-egress decision, and duration. An incomplete audit, or
a Hermes `action` proposal without a normalized `RuntimeActionIntent`, is
rejected before Presence rather than falling back to proposal-shaped execution.
`Execution Planning` repeats the envelope check for every harness-marked action
before it can form an edge request, so a future caller cannot turn an allowed
Presence decision plus a proposal-shaped payload into a dispatch.

For the current M20 risk boundary, a research-assisted action can proceed only
when it is the low-risk `notification.show` reply to that requesting user and
the existing proposal, capability registry, Presence, execution-planning, and
action-result paths all accept it. Cross-device control, runtime control,
unknown capabilities, or any other elevated action receives a
`confirmation_required` authorization result and fails closed until a real
confirmation flow exists. Thus a user may ask “research this and tell me,”
while a page that says “ignore rules and message everyone” cannot create
authority.

M20 acceptance deliberately separates two facts. The positive live fetch/search
scenarios prove the real configured provider and network wrapper. The separate
live hostile-page scenario may either fetch the configured fixture and record
its hash, or safely decline the fetch with no action or memory write. It does
not pretend that a model's silent completion proves a runtime boundary.
Deterministic forced tool/action and native-memory injection tests prove that an
unbound or elevated research action is rejected or requires confirmation, and
that remote instruction-shaped memory content is not stored.

## Hermes Memory Ownership

Hermes' `MEMORY.md` / `USER.md` are the primary M20 long-term-memory engine.
The adapter gives the personal runtime a stable, sealed runtime-scoped
`HERMES_HOME`, enables the built-in Hermes memory tool, disables external
memory-provider/plugin loading and background memory/skill review, masks
environment-driven Kanban/CDP/cloud-browser overrides, disables Hermes'
environment process probe, and passes a stable personal-runtime identity so a
fresh runner can retrieve previously stored memory. This is not a second
OpenHalo semantic-memory store.

M20 enables autonomous native memory only during a normal audited harness turn.
Action-result and observation re-entry still load native memory as read context,
but omit the `memory` tool from both the model-visible tool schema and the
adapter's low-level dispatcher allowlist. Its sealed `memory.nudge_interval` is
`0`: `HermesHarnessRunner` creates a
fresh agent per turn, and Hermes' periodic background review would otherwise be
both ineffective today and unaudited if a future runner retained the counter.
That review also opens Hermes' skill review path, which belongs to M20.1. A
future background review must be an OpenHalo-owned fork lifecycle that installs
the same dispatch gate and memory audit before this interval can be non-zero.

OpenHalo retains provenance sufficient for governance and replay: memory tool
operation and target, content integrity hash, Hermes scope/session/turn
reference, post-write `MEMORY.md`/`USER.md` digest, mutation status, timestamp,
policy decision, and trace link. It does not persist the memory body as an
additional durable runtime record. Existing runtime-owned memory views remain
compatibility data for the legacy harness only and must not be injected into a
Hermes-native memory turn.

Acceptance may use a user-provided sentinel to prove cross-session recall, but
it must not require Hermes to store that sentinel as the entire literal memory
body. Hermes may normalize it into a concise, useful entry. The evidence instead
requires the post-write file to contain the sentinel, the audited file digest to
match that file, a body-free hash of the actual entry, and a later fresh-session
recall through the governed action path.

Hermes memory is not globally disabled after a research call. The native
`memory` tool may autonomously add, replace, remove, or batch-consolidate
compact user/profile and agent-operational entries when they are stable and
useful under the OpenHalo behavior contract. Research remains an untrusted
source marker: it never authorizes a user-visible action, and remote
instructions, role claims, or tool directives must not persist as memory.
Hermes' strict native memory scanner and the OpenHalo system contract provide
that content boundary; the body-free audit retains source references without
creating a second memory body.

For the current M20 command surface, native Hermes `memory` is the sole
durable-memory write path. `openhalo_memory` does not exist as a competing
facade. Hermes' `memory.write_approval: false` is not treated as a security
decision: the runtime-scoped home, behavior contract, dispatcher allowlist,
native threat scanner, and post-write audit provide the boundary. The sealed
environment also removes `HERMES_YOLO_MODE` before every harness turn.

Hermes consults some settings through process-global environment variables, so
the embedded scope is serialized by OpenHalo and the Personal Runtime owns its
process. M20 does not support co-hosting an unrelated, unconstrained Hermes
integration in that same process. Broader in-process multi-tenant isolation
requires a separate subprocess boundary rather than a weaker lock-only claim.

Hermes error-request diagnostics are redirected into a per-run private
temporary directory and removed with that run. They must not create another
durable copy of prompt, context, provider headers, or remote research content
beside the Hermes memory files.

## Hermes Reuse Contract

M20 should reuse Hermes capabilities wherever they match the harness boundary, including the stateful agent loop, prompt/context construction, provider resolution, session/history handling, tool-call lifecycle, compaction, retries, and tool hooks. OpenHalo should only add the smallest adapter surfaces needed to preserve its runtime model.

The following work is explicitly disallowed unless a documented reuse audit proves adapter-level integration is infeasible:

- a second OpenHalo-native general agent loop that competes with the Hermes loop
- a second prompt-builder/provider/session/tool-runner stack that duplicates Hermes without a concrete boundary reason
- bypassing Hermes just to preserve an existing implementation detail inside `personal_runtime`

An approved exception must identify the Hermes component, the concrete incompatibility, why an adapter cannot resolve it, the replacement contract, and equivalent regression coverage. "Simpler to rewrite" is not a sufficient reason.

## Relationship To Existing OpenHalo Layers

This future architecture should not collapse OpenHalo back into a generic chat-agent framework.

- `Gateway` remains the physical edge/runtime boundary.
- `State / Context` remains the owner of normalized observations, compact snapshot state, and durable runtime state.
- `Agent Harness Layer` consumes state and memory, runs the internal agent loop, and emits proposal/action/termination intent.
- `Presence Router` remains an explicit governance layer that decides whether, where, when, and how strongly to surface or suppress an intervention.
- `Execution Planning` remains responsible for capability/provider selection after presence governance.
- `Action Layer` remains responsible for action dispatch and result recording, not semantic proposal formation.
- Diagnostics, chain inspection, replay, and eval remain cross-cutting rather than owned only by the agent module.

## LLMOps And Eval Loop

The architecture should also include an explicit LLMOps/eval layer around the harness:

```text
trace
  -> eval
  -> observe
  -> diagnose
  -> gate
  -> release improved prompt / config / memory policy
```

Current OpenHalo pieces such as diagnostics, chain inspection, and the M17.6.1 proposal harness are early slices of this loop. A later refactor should make the loop systematic: real prompt/context packages, action results, failures, and terminal outcomes should become replayable and outcome-classified evidence before prompt, configuration, or memory-policy changes are promoted.

Hermes is the selected reusable implementation source for this layer because it already has a stateful agent core, prompt building, provider resolution, tool dispatch, session persistence, compaction, and tool hooks. The intended OpenHalo use is selective reuse behind an adapter, not a direct takeover of the runtime boundary.

## Phasing

M20 completed after the preceding functional path made the system sufficiently
runnable to validate the Harness on the real Gateway/terminal loop. Its
implementation avoided a big-bang rewrite: it documented the existing runtime
chain in Harness terms, then moved behavior behind explicit contracts one layer
at a time:

- prompt/context package contract
- memory retrieval and write contract
- action-result re-entry contract
- terminal outcome contract
- replay/eval gate contract

## Non-Goals

- Do not replace OpenHalo's presence-first architecture with a generic agent framework.
- Do not move device action execution inside the model loop without `Presence Router`, execution planning, and action governance.
- Do not treat every model-mentioned fact or untrusted remote statement as
  durable truth; Hermes memory's bounded tool and content safeguards remain
  active and every committed mutation is auditable.
- Do not make this document a blocker for current runnable-system milestones.
