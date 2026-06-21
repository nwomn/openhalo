# M5 Runtime Health Snapshot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the M5 freshness work by adding a compact runtime-health snapshot field that ages stale host-edge health evidence out of the live context view.

**Architecture:** Keep the slice narrow. Reuse the existing snapshot-time freshness pattern from `user.current_location`, add one reducer for `runtime.health_state`, and avoid introducing broader host-metric aggregation or agent-policy changes in this batch.

**Tech Stack:** Python 3, `unittest`, existing `personal_runtime` runtime modules

### Task 1: Lock runtime-health snapshot behavior with tests

**Files:**
- Modify: `tests/test_context_snapshot.py`
- Modify: `personal_runtime/context_snapshot.py`

**Step 1: Write the failing test**

Add tests that require:
- fresh `runtime.health_state` evidence resolves to `runtime.current_health_state`
- stale `runtime.health_state` evidence resolves to `unknown`

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: FAIL because the compact snapshot does not yet expose a runtime-health field.

**Step 3: Write minimal implementation**

Add the smallest reducer support needed to:
- expose `runtime.current_health_state`
- filter `runtime.health_state` observations by freshness
- prefer newer evidence when more than one fresh observation exists

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_context_snapshot.py personal_runtime/context_snapshot.py
git commit -m "feat: add runtime health snapshot reducer"
```

### Task 2: Verify the slice and update the project baseline

**Files:**
- Modify: `Project.md`

**Step 1: Run targeted verification**

Run the relevant snapshot and runtime tests after the reducer test passes.

**Step 2: Update the project baseline**

Record that M5 now includes the first freshness-aware runtime health snapshot field if the slice lands cleanly.

**Step 3: Commit**

```bash
git add Project.md
git commit -m "docs: record runtime health snapshot slice"
```
