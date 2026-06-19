# Presence Decision Slice Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Land the first explicit snapshot-driven presence decision slice on the live runtime path, including suppression and intervention history.

**Architecture:** Keep the hot path shallow. Reuse stored normalized observations to build the compact snapshot, let `Presence Router` return an explicit decision object, and record intervention history in runtime state only when presence allows a user-facing action. Avoid introducing a broader policy system in this batch.

**Tech Stack:** Python 3, `unittest`, existing `personal_runtime` runtime modules

### Task 1: Lock the new presence behavior with tests

**Files:**
- Modify: `tests/test_gateway_v0.py`
- Modify: `tests/test_runtime_state_v0.py`

**Step 1: Write the failing tests**

Add tests that require:
- ambiguous location context suppresses a normal user-facing notification action
- a recent intervention cooldown suppresses a repeated normal notification action
- an allowed intervention is recorded in runtime history and survives state serialization

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_gateway_v0 tests.test_runtime_state_v0 -v`
Expected: FAIL because runtime state has no intervention history and the presence path does not yet return explicit suppression decisions.

**Step 3: Write minimal implementation**

Add the smallest state and router changes needed to pass the tests.

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_gateway_v0 tests.test_runtime_state_v0 -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_gateway_v0.py tests/test_runtime_state_v0.py personal_runtime/presence_router.py personal_runtime/runtime_state.py personal_runtime/gateway_server.py
git commit -m "feat: add explicit presence decision slice"
```

### Task 2: Verify and baseline the slice

**Files:**
- Modify: `Project.md`

**Step 1: Run broader verification**

Run the full test suite after the targeted tests pass.

**Step 2: Update the project baseline**

Record that the first snapshot-driven presence decision slice is implemented if the behavior lands cleanly.

**Step 3: Commit**

```bash
git add Project.md
git commit -m "docs: record first presence decision slice"
```
