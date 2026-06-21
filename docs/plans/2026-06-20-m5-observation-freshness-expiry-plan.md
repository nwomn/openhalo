# M5 Observation Freshness And Expiry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the first M5 observation freshness and expiry slice so compact context snapshots stop treating stale evidence as current truth.

**Architecture:** Keep the hot path small and explicit. Add a minimal freshness policy at the snapshot reducer layer first, then thread an explicit snapshot timestamp through the gateway so live presence decisions are built from fresh observation evidence instead of whatever happens to be newest in absolute history.

**Tech Stack:** Python 3, `unittest`, existing `personal_runtime` runtime modules

### Task 1: Lock stale-observation behavior with snapshot tests

**Files:**
- Modify: `tests/test_context_snapshot.py`
- Modify: `personal_runtime/context_snapshot.py`

**Step 1: Write the failing test**

Add tests that require:
- stale `user.location` observations older than the freshness window return `unknown`
- fresh `user.location` observations still resolve normally when a snapshot time is provided

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: FAIL because snapshot reducers do not yet accept a reference timestamp or filter expired observations.

**Step 3: Write minimal implementation**

Add the smallest reducer support needed to:
- accept an optional snapshot timestamp
- filter stale location observations using a small freshness window
- preserve existing `unknown` and `ambiguous` behavior for fresh evidence

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_context_snapshot.py personal_runtime/context_snapshot.py
git commit -m "feat: add snapshot freshness filtering"
```

### Task 2: Thread snapshot time through the gateway path

**Files:**
- Modify: `tests/test_gateway_v0.py`
- Modify: `personal_runtime/gateway_server.py`

**Step 1: Write the failing test**

Add a gateway test that requires:
- stale location evidence is ignored when a later text event triggers snapshot construction
- the resulting normal path does not get suppressed by stale conflicting evidence

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_gateway_v0 -v`
Expected: FAIL because gateway snapshot building does not yet pass an explicit decision-time timestamp into the reducer.

**Step 3: Write minimal implementation**

Use the event decision timestamp as the snapshot reference time when building the live compact snapshot.

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_gateway_v0 -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_gateway_v0.py personal_runtime/gateway_server.py
git commit -m "feat: use fresh observations for live snapshots"
```

### Task 3: Verify the slice and update the project baseline

**Files:**
- Modify: `Project.md`

**Step 1: Run broader verification**

Run the targeted runtime test suites after the snapshot and gateway tests pass.

**Step 2: Update the project baseline**

Record that the first M5 freshness/expiry slice is implemented if the behavior lands cleanly.

**Step 3: Commit**

```bash
git add Project.md
git commit -m "docs: record M5 freshness baseline"
```
