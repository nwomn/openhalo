# M18 Proactive End-to-End Acceptance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prove that a high-salience observation can complete the normal proactive interaction lifecycle without calling a real model.

**Architecture:** Keep `ProactiveTriggerGate` deterministic and unchanged. In the Runtime Orchestrator integration test, inject a deterministic observation proposal, present an active terminal surface, and verify that the existing Interaction Pool, Presence Router, Action Layer, and action-result re-entry produce one completed interaction.

**Tech Stack:** Python 3.12, `unittest`, existing `RuntimeGateway` and `SessionClient` integration fixtures.

### Task 1: Add the failing positive-path integration test

**Files:**
- Modify: `tests/test_runtime_orchestrator.py`

**Step 1: Write the failing test**

Create an observation-driven proposal stub that asks for `notification.show`, then send a fresh `runtime.health_state=degraded` event while the terminal reports `active`.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_runtime_orchestrator.RuntimeOrchestratorTests.test_observation_driven_notification_completes_after_action_result`

Expected: the test initially exposes any missing positive presence/action-loop coverage or non-deterministic setup.

**Step 3: Make the smallest production change only if required**

Do not change M18 policy. Adjust only existing integration wiring that prevents the already-supported flow from completing.

**Step 4: Run test to verify it passes**

Run the same focused `unittest` command.

### Task 2: Verify and document scope

**Files:**
- Modify: `Project.md`
- Test: `tests/test_runtime_orchestrator.py`

**Step 1: Run focused M18 regression tests**

Run: `.venv/bin/python -m unittest tests.test_proactive_trigger_gate tests.test_m18_replay tests.test_runtime_orchestrator`

**Step 2: Update project baseline**

Record that M18 has deterministic end-to-end proactive lifecycle coverage, while its current Gate remains fixed-signal admission rather than user-knowledge-aware initiative.

**Step 3: Run full suite**

Run: `.venv/bin/python -m unittest discover -s tests -q`
