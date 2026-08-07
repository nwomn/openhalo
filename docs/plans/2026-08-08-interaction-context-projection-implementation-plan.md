# Interaction Context Projection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let a new user Interaction receive a bounded, authoritative summary of relevant ongoing or recently settled InteractionPool processes.

**Architecture:** `InteractionPool` remains the sole owner of Interaction lifecycle state and relationship lookup. When it creates a new Interaction, it deterministically selects a bounded set of source-relevant persistent-process summaries, persists only their IDs and state versions in the new Interaction lineage, and returns the summaries with the registration. `RuntimeOrchestrator` passes that returned projection to the existing grounding bundle and Hermes call; it does not maintain a duplicate process-state store. Hermes interprets the user's language and composes a response from Runtime facts, but does not own or overwrite lifecycle truth.

**Tech Stack:** Python Runtime, `InteractionPool`, RuntimeState/SQLite persistence, Hermes Harness, `unittest`.

### Task 1: Define and test Pool-owned related-process projection

**Files:**

- Modify: `tests/test_interaction_pool.py`
- Modify: `personal_runtime/interaction_pool.py`

1. Add a failing test that creates and completes a persistent source Interaction, then registers a new user Interaction from the same Edge.
2. Assert the registration returns a bounded summary containing the completed Interaction's ID, lifecycle state, final observation, health, and process-state version.
3. Assert the new Interaction persists only `context_process_refs` (ID and version), not the source Interaction's full record.
4. Add the minimal Pool methods/registration result field to make the test pass. Exclude unrelated devices and one-shot records from the process projection.

### Task 2: Project Pool summaries into normal Hermes grounding

**Files:**

- Modify: `tests/test_runtime_orchestrator.py`
- Modify: `personal_runtime/runtime_memory.py`
- Modify: `personal_runtime/runtime_orchestrator.py`

1. Add a failing orchestrator test using a capturing Harness: seed a completed persistent Interaction, send a new `text.input` request from the same Edge, and inspect the real `HarnessInput.grounding_bundle`.
2. Assert the grounding bundle has the authoritative `related_processes` summary and the newly created Interaction retains only its reference lineage.
3. Add the optional grounding-bundle input and pass `InteractionRegistration.related_process_summaries` from the normal-turn path.
4. Keep observation-driven and post-action paths unchanged unless they explicitly create a new user Interaction.

Review hardening:

- Shared-edge summaries carry `causal_scope_key`, `process_id`, and `source_capability` where available; callers that know a process can filter by those identifiers.
- `InteractionPool` bounds each summary to 4 KiB and Runtime Memory independently bounds the grounding projection to four summaries and 16 KiB.
- Every Pool mutation that changes lifecycle, process state, health, watch, obligation, or action correlation advances the persisted process-state version, so lineage references remain auditable.

### Task 3: Document and verify

**Files:**

- Modify: `Project.md`
- Modify: `docs/plans/2026-08-06-interaction-process-continuation-implementation-plan.md`
- Modify: `docs/plans/2026-06-16-runtime-architecture-design.md`

1. Record that cross-Interaction query grounding is Pool-owned, bounded, and does not introduce a RuntimeState process replica or top-level Process domain.
2. Run focused Pool/orchestrator/Hermes tests, then `bin/test`, `bin/verify-action-loop`, and the M20 Harness verifier.
3. Run a local live Terminal Edge acceptance: complete a Coding Interaction and ask its status from a new user Interaction; verify the response grounding includes the settled process fact.

### Task 4: Publish

1. Bump the package version, commit the implementation and documentation on `master`, push `master`, build the release archive, and publish a matching GitHub Release.
2. Update the installed local Runtime and Terminal Edge only after release asset verification.
