# Continuous Interaction Process Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend `InteractionPool` into a bounded source-neutral lifecycle manager for ongoing observation, action verification, recovery, and completion.

**Architecture:** `InteractionPool` is an internal sibling of Proposal Formation, Presence Router, and Execution Planning inside `Agent Runtime`, and remains the only process lifecycle store. Models may propose bounded continuation intent; Runtime validates it, `RuntimeOrchestrator` dispatches ordinary observations and health changes to `InteractionPool`, Edge supplies structured facts/coverage/evidence references, and the same Hermes child session is resumed for each continuation turn. No Coding-specific Runtime branch or independent `ContinuationRouter` module is introduced.

**Tech Stack:** Python Runtime, WebSocket Edge API, RuntimeState/SQLite, Hermes child sessions, and `unittest`.

## Implemented baseline

- Added compatible lifecycle, continuation policy, objective, watch, obligation, process-state, health, and lineage fields to `InteractionRecord`.
- Added atomic watch/obligation/state transition helpers and persistent action-result semantics.
- Added `InteractionPool` lifecycle operations for fact matching, bounded event hypotheses, evidence uncertainty, terminal watch resolution, and Edge health reconciliation; `RuntimeOrchestrator` owns the continuation dispatch and reawakening path.
- Added generic capability `process_contract` validation and proposal continuation intent parsing.
- Connected matching observations to the existing same-interaction observation re-entry path.
- Added Runtime maintenance health reconciliation and updated the canonical architecture documentation to show `InteractionPool` inside Agent Runtime.

## Remaining acceptance work

- Add complete evidence-query action transport and Edge adapter implementations.
- Add provider-backed continuation proposal fixtures and end-to-end process health re-entry acceptance.
- Verify Coding completion, camera-style feature/evidence escalation, Edge inactivity, retry, failure, and recovery with production Edge adapters.

## Cross-interaction context projection

`InteractionPool` remains the sole owner of Interaction records and related
process lookup. When a new Interaction is registered, the Pool may return a
bounded summary of persistent recent processes from the same source Edge and
stores only `{interaction_id, process_state_version}` references in the new
record's lineage. `RuntimeOrchestrator` places those summaries in the existing
grounding bundle for the new Hermes turn. No duplicate RuntimeState process
index or complete Interaction history is introduced.

## Verification evidence (2026-08-07)

- `tests.test_interaction_continuation` proves base-fact watch matching, bounded
  evidence uncertainty, inactive-watch handling, terminal watch resolution, and
  offline Edge health state through `InteractionPool` itself.
- `bin/verify-action-loop` passes using the current P-256 Edge session contract
  and exact action-result correlation; it also confirms that a fresh observation
  is recorded rather than re-entered while an action batch remains pending.
- `bin/verify-m20-harness --runtime-config-path
  tests/fixtures/llm-config-hermes-test.toml` passes its 163 automated contracts
  (4 expected skips), 18 deterministic Hermes evidence tests, and the Hermes
  configuration gate.
- `bin/test -B -m unittest` passes 750 tests with 4 expected skips.
