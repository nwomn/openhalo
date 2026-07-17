# M20 Interaction Action-Loop Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore a governed multi-action external loop in which a Hermes-backed interaction may emit an `ActionBatch`, wait for every correlated result, and resume with the same scoped context.

**Architecture:** `InteractionPool` remains the durable concurrent lifecycle owner. Hermes provides the semantic worker: each interaction has an isolated native child-session identity, receives a bounded projection of OpenHalo's shared context, and emits an `ActionBatch` or a terminal outcome. Runtime validates every intent, applies Presence and execution planning individually, dispatches the valid batch, waits for the entire batch, and resumes only after the result set is complete.

**Tech Stack:** Python 3.12, `unittest`, OpenHalo Runtime, Hermes 0.18.2 adapter.

### Task 1: Write the failing ActionBatch contract tests

**Files:**
- Modify: `personal_runtime/agent_harness.py`
- Modify: `personal_runtime/hermes_adapter.py`
- Test: `tests/test_hermes_adapter.py`

**Step 1: Write the failing test**

Create a runner fixture that calls `openhalo_action` twice with distinct tool-call IDs. Assert that the returned `HarnessOutcome` carries both intents in stable order, retains distinct IDs, and does not report `no_intervention` or `multiple_external_action_intents`.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -B -m unittest tests.test_hermes_adapter.HermesToolCallAdapterTests.test_harness_runner_returns_batch_for_multiple_bridge_actions -v`

Expected: FAIL because the runner converts the batch into `no_intervention`.

**Step 3: Write minimal implementation**

Add runtime-owned `ActionBatch` collection semantics. Empty batches are invalid, exact duplicates fold deterministically, distinct valid intents remain, and every output exposes a stable batch ID. Extend `HarnessOutcome` while retaining its single-intent compatibility field.

**Step 4: Run test to verify it passes**

Run the targeted test from Step 2.

### Task 2: Write the failing InteractionPool batch lifecycle tests

**Files:**
- Modify: `personal_runtime/interaction_pool.py`
- Test: `tests/test_interaction_pool.py`

**Step 1: Write the failing test**

Record two action requests under one action batch, resolve one, and assert the interaction remains awaiting results. Resolve the second and assert the batch becomes resumable. Attempt a new batch during the wait and expect a clear rejection.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -B -m unittest tests.test_interaction_pool.InteractionPoolTests.test_batch_stays_awaiting_until_all_results_resolve -v`

Expected: FAIL because current turns permit only one request correlation.

**Step 3: Write minimal implementation**

Persist batch and action IDs on dispatch records. Add atomic `record_action_batch`, exact batch lookup, partial/complete status, and pending-batch guard. Old persisted single-request turns restore as one-action legacy batches.

**Step 4: Run test to verify it passes**

Run the focused InteractionPool tests.

### Task 3: Write the failing child-session context projection tests

**Files:**
- Modify: `personal_runtime/interaction_pool.py`
- Modify: `personal_runtime/hermes_adapter.py`
- Modify: `personal_runtime/prompt_context.py`
- Test: `tests/test_hermes_adapter.py`

**Step 1: Write the failing test**

Use a fake Hermes child factory to capture normal and post-action inputs. Assert both receive one stored child-session ID and an `openhalo_shared_context` projection containing system identity, relevant memory/goal metadata, device roster, interaction lineage, and the correlated result set, but no unrelated raw transcript.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -B -m unittest tests.test_hermes_adapter.HermesToolCallAdapterTests.test_child_session_continuation_receives_scoped_shared_context -v`

Expected: FAIL because no child-session or shared-context projection contract exists.

**Step 3: Write minimal implementation**

Persist `agent_session_id` on the interaction record. Project only relevant Runtime context and Hermes durable-memory references into each initial/continuation child turn. Do not copy a main-agent transcript; do not expose shell, plugin, browser, or generic skill execution.

**Step 4: Run test to verify it passes**

Run the focused Hermes adapter tests.

### Task 4: Write the failing Runtime ActionBatch dispatch tests

**Files:**
- Modify: `personal_runtime/runtime_orchestrator.py`
- Modify: `personal_runtime/gateway_server.py`
- Test: `tests/test_runtime_orchestrator.py`

**Step 1: Write the failing test**

Use a harness that returns two valid device actions. Assert Runtime emits two requests with one batch ID, does not re-enter the Harness on the first result, then resumes exactly once with the ordered result set after the second. Add a concurrent second interaction and a conflicting/invalid batch rejection case.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -B -m unittest tests.test_runtime_orchestrator.RuntimeOrchestratorTests.test_action_batch_waits_for_all_results_before_reentry -v`

Expected: FAIL because Runtime plans only one request and resumes after the first result.

**Step 3: Write minimal implementation**

Validate and plan each intent before dispatch, retain one interaction-level batch record, persist partial results without new model work, and resume the child only with a complete ordered result set. Distinct invalid/conflicting batches finish as `action_batch_rejected`, never fake `no_intervention`.

**Step 4: Run test to verify it passes**

Run the focused Runtime orchestrator test module.

### Task 5: Verify and record M20 revalidation state

**Files:**
- Modify: `Project.md`
- Test: `tests/test_hermes_adapter.py`
- Test: `tests/test_interaction_pool.py`
- Test: `tests/test_runtime_orchestrator.py`

**Step 1: Run focused verification**

Run: `.venv/bin/python -B -m unittest tests.test_hermes_adapter tests.test_interaction_pool tests.test_runtime_orchestrator -v`

**Step 2: Run full verification**

Run: `.venv/bin/python -B -m unittest discover -s tests -q`

**Step 3: Inspect quality gate**

Run: `git diff --check`

**Step 4: Update documented status**

Keep M20 reopened until configured-provider Terminal/Android multi-action human acceptance completes.
