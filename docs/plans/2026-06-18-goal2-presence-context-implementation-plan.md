# Goal 2 Presence Context Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Land the first code and test scaffolding that turns the Goal 2 presence/context design baseline into concrete runtime contracts.

**Architecture:** Keep the current runtime hot path explicit and incremental. Introduce contract types and lightweight reducers before attempting richer presence policy work, and preserve the separation between normalized runtime observations, compact context snapshot, and later agent reasoning.

**Tech Stack:** Python 3, unittest, existing `personal_runtime` and `device_edge` packages

### Task 1: Add shared context contract types

**Files:**
- Create: `personal_runtime/context_contracts.py`
- Test: `tests/test_context_contracts.py`

**Step 1: Write the failing tests**

Add tests that define the intended shape for:

- a device contract with `device_id`, `device_type`, `role`, `profile`, and capability names
- a capability contract with `name`, `observations`, and `actions`
- a runtime observation record with provenance fields

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_context_contracts -v`
Expected: FAIL because the module and types do not exist yet.

**Step 3: Write minimal implementation**

Create simple Python data structures that model the contracts without yet wiring them into runtime behavior.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_context_contracts -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_context_contracts.py personal_runtime/context_contracts.py
git commit -m "feat: add context contract types"
```

### Task 2: Add compact runtime observation storage

**Files:**
- Modify: `personal_runtime/runtime_state.py`
- Test: `tests/test_runtime_state_v0.py`

**Step 1: Write the failing test**

Add a test showing runtime state can store normalized observations with provenance separately from raw edge details.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_runtime_state_v0.RuntimeStateTests.test_records_runtime_observation_with_provenance -v`
Expected: FAIL because observation storage APIs do not exist yet.

**Step 3: Write minimal implementation**

Extend runtime state with normalized observation storage and serialization support.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_runtime_state_v0.RuntimeStateTests.test_records_runtime_observation_with_provenance -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_runtime_state_v0.py personal_runtime/runtime_state.py
git commit -m "feat: store normalized runtime observations"
```

### Task 3: Add first compact snapshot reducers

**Files:**
- Create: `personal_runtime/context_snapshot.py`
- Test: `tests/test_context_snapshot.py`

**Step 1: Write the failing tests**

Add tests for small reducers that:

- select a current location from recent observations
- keep `unknown` when evidence is missing
- keep `ambiguous` when evidence conflicts tightly

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: FAIL because the reducer module does not exist yet.

**Step 3: Write minimal implementation**

Implement a tiny reducer-based snapshot builder for a first small field set.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_context_snapshot.py personal_runtime/context_snapshot.py
git commit -m "feat: add compact context snapshot reducers"
```

### Task 4: Expose snapshot for presence and evidence for agent reasoning

**Files:**
- Modify: `personal_runtime/gateway_server.py`
- Modify: `personal_runtime/presence_router.py`
- Test: `tests/test_gateway_v0.py`

**Step 1: Write the failing tests**

Add tests proving:

- presence consumes compact snapshot fields
- deeper reasoning paths can still inspect supporting observations when needed

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_gateway_v0 -v`
Expected: FAIL because snapshot plumbing does not exist yet.

**Step 3: Write minimal implementation**

Thread compact snapshot data into the presence path while preserving access to stored observations for later layers.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_gateway_v0 -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_gateway_v0.py personal_runtime/gateway_server.py personal_runtime/presence_router.py
git commit -m "feat: route presence through compact context snapshot"
```

### Task 5: Document first heuristic-learning maintenance hooks

**Files:**
- Modify: `Project.md`
- Optionally modify: `docs/plans/2026-06-18-goal2-presence-context-design.md`

**Step 1: Write the update**

Document which artifacts the outer loop is expected to refine first:

- vocabulary
- edge mappers
- reducers
- presence policy

**Step 2: Review for consistency**

Check that the design baseline and project baseline describe the same outer-loop responsibilities.

**Step 3: Commit**

```bash
git add Project.md docs/plans/2026-06-18-goal2-presence-context-design.md
git commit -m "docs: define presence context learning loop hooks"
```
