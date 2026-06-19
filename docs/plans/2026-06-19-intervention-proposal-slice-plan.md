# Intervention Proposal Slice Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align the live normal runtime path with the documented `snapshot -> proposal -> presence -> action` shape by introducing a minimal intervention proposal layer.

**Architecture:** Keep the change small. Let the agent layer build a simple inspectable proposal from text input plus compact snapshot, pass that proposal into `Presence Router`, and only then generate the final user-facing action if presence allows it.

**Tech Stack:** Python 3, `unittest`, existing `personal_runtime` modules

### Task 1: Lock the proposal layer behavior with tests

**Files:**
- Modify: `tests/test_gateway_v0.py`
- Modify: `tests/test_roundtrip_v0.py`

**Step 1: Write the failing tests**

Add tests that require:
- the normal path to record or trace an explicit intervention proposal before the presence decision
- the proposal payload to drive the chosen action capability and target when presence allows it

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_gateway_v0 tests.test_roundtrip_v0 -v`
Expected: FAIL because the runtime still goes directly from snapshot into presence and final action generation.

**Step 3: Write minimal implementation**

Add the smallest inspectable proposal object and thread it through the normal path.

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_gateway_v0 tests.test_roundtrip_v0 -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_gateway_v0.py tests/test_roundtrip_v0.py personal_runtime/agent_executor.py personal_runtime/presence_router.py personal_runtime/gateway_server.py
git commit -m "feat: add intervention proposal layer"
```

### Task 2: Verify and baseline the slice

**Files:**
- Modify: `Project.md`

**Step 1: Run broader verification**

Run the full test suite after the targeted tests pass.

**Step 2: Update the project baseline**

Record the proposal-layer slice if it lands cleanly and still fits the current Goal 4 acceptance path.

**Step 3: Commit**

```bash
git add Project.md
git commit -m "docs: record intervention proposal slice"
```
