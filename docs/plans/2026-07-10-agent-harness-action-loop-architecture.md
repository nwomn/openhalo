# Agent Harness and Runtime Action Loop Architecture

## Purpose

This note records a future OpenHalo architecture direction. It is not an immediate refactor plan.

The current milestone sequence should continue to finish the already-defined functional slices first, so the system can keep becoming runnable and product-shaped. This document should be revisited when OpenHalo reaches the later architecture refactor milestone that is explicitly intended to reshape the existing implementation around a more complete agent harness and runtime action loop.

## Architecture Decision

OpenHalo should preserve its top-level `Device Edge -> Gateway -> Personal Runtime -> Presence Router -> Action Layer` worldview, but its agent execution core should mature toward a Hermes-style agent harness.

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
