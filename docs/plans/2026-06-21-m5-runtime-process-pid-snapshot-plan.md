# M5 Runtime Process PID Snapshot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend M5.2 compact snapshot field-pack growth by adding a freshness-aware compact snapshot field for the runtime process pid.

**Architecture:** Keep the slice reducer-local and incremental. Reuse the existing snapshot-time freshness pattern, add one runtime-ingestion field derived from `runtime.process_pid`, and avoid widening this batch into process-lifecycle policy, presence behavior, or host-metric aggregation work.

**Tech Stack:** Python 3, `unittest`, existing `personal_runtime` runtime modules, `Project.md`

### Task 1: Lock runtime process-pid snapshot behavior with tests

**Files:**
- Modify: `tests/test_context_snapshot.py`
- Modify: `personal_runtime/context_snapshot.py`

**Step 1: Write the failing test**

Add tests that require:
- fresh `runtime.process_pid` evidence resolves to `runtime.current_process_pid`
- stale `runtime.process_pid` evidence resolves to `unknown`

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: FAIL because the compact snapshot does not yet expose a runtime process-pid field.

**Step 3: Write minimal implementation**

Add the smallest reducer support needed to:
- expose `runtime.current_process_pid`
- filter `runtime.process_pid` observations by freshness
- prefer newer evidence when more than one fresh observation exists

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_context_snapshot.py personal_runtime/context_snapshot.py
git commit -m "feat: add runtime process-pid snapshot reducer"
```

### Task 2: Record the new M5 slice in the project baseline

**Files:**
- Modify: `Project.md`

**Step 1: Update completed-work tracking**

Record that M5 now includes a freshness-aware compact snapshot field for runtime process pid if the slice lands cleanly.

**Step 2: Commit**

```bash
git add Project.md
git commit -m "docs: record runtime process-pid snapshot slice"
```
