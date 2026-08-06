# Continuous Interaction Process Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend `InteractionPool` into a bounded source-neutral lifecycle manager for ongoing observation, action verification, recovery, and completion.

**Architecture:** `InteractionPool` remains the only process lifecycle store. Models may propose bounded continuation intent; Runtime validates it, `ContinuationRouter` matches ordinary observations and health changes, Edge supplies structured facts/coverage/evidence references, and the same Hermes child session is resumed for each continuation turn. No Coding-specific Runtime branch is introduced.

**Tech Stack:** Python Runtime, WebSocket Edge API, RuntimeState/SQLite, Hermes child sessions, and `unittest`.

## Implemented baseline

- Added compatible lifecycle, continuation policy, objective, watch, obligation, process-state, health, and lineage fields to `InteractionRecord`.
- Added atomic watch/obligation/state transition helpers and persistent action-result semantics.
- Added `ContinuationRouter` with fact matching, bounded event hypotheses, evidence uncertainty, terminal watch resolution, and Edge health reconciliation.
- Added generic capability `process_contract` validation and proposal continuation intent parsing.
- Connected matching observations to the existing same-interaction observation re-entry path.
- Added Runtime maintenance health reconciliation and project architecture documentation.

## Remaining acceptance work

- Add complete evidence-query action transport and Edge adapter implementations.
- Add provider-backed continuation proposal fixtures and end-to-end process health re-entry acceptance.
- Verify Coding completion, camera-style feature/evidence escalation, Edge inactivity, retry, failure, recovery, and full regression through `bin/test`.
