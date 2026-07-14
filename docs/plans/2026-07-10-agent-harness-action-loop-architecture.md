# Agent Harness and Runtime Action Loop Architecture

## Purpose

This note records a future OpenHalo architecture direction. It is not an immediate refactor plan.

The current milestone sequence should continue to finish the already-defined functional slices first, so the system can keep becoming runnable and product-shaped. This document should be revisited when OpenHalo reaches the later architecture refactor milestone that is explicitly intended to reshape the existing implementation around a more complete agent harness and runtime action loop.

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

- agent-private tools: search, retrieval, compression, summarization, local diagnostics, and other reasoning helpers that stay inside the harness loop. They may be auto-approved only when explicitly classified as bounded, non-user-visible, and non-side-effectful; network or data-egress tools still require OpenHalo-owned allowlist, budget, timeout, audit, and prompt-injection controls.
- runtime-governed actions: edge notifications, cross-device control, durable memory/policy writes, or any other user-visible or side-effectful operation. These must exit the harness as an OpenHalo action intent and pass through `Presence Router`, execution planning, and `Action Layer`.

The adapter must disable or replace any Hermes default that would directly execute an OpenHalo-governed action. Hermes may decide that it wants an action; it cannot become the authority that dispatches an edge action.

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

This architecture should be deferred until the current near-term functional milestones have made the system simple, runnable, and product-shaped.

Before this refactor, OpenHalo should continue finishing the already-defined functional path, including Android edge durability, liveness, privacy governance, product packaging, and other active milestones.

When the refactor milestone starts, the implementation should avoid a big-bang rewrite. It should first document the existing runtime chain in harness terms, then move behavior behind explicit contracts one layer at a time:

- prompt/context package contract
- memory retrieval and write contract
- action-result re-entry contract
- terminal outcome contract
- replay/eval gate contract

## Non-Goals

- Do not replace OpenHalo's presence-first architecture with a generic agent framework.
- Do not move device action execution inside the model loop without `Presence Router`, execution planning, and action governance.
- Do not make memory writes automatic just because a model mentions a fact.
- Do not make this document a blocker for current runnable-system milestones.
