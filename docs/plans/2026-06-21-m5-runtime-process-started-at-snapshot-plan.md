# M5 Runtime Process Started-At Snapshot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend M5.2 compact snapshot field-pack growth by adding a freshness-aware compact snapshot field for runtime process start time.

**Architecture:** Keep the slice reducer-local and incremental. Reuse the existing snapshot-time freshness pattern, add one runtime-side field derived from `runtime.process_started_at`, and avoid widening this batch into restart heuristics, policy changes, or broader time-semantics work.

**Tech Stack:** Python 3, `unittest`, existing `personal_runtime` runtime modules, `Project.md`

### Task 1: Lock runtime process started-at snapshot behavior with tests

**Files:**
- Modify: `tests/test_context_snapshot.py`
- Modify: `personal_runtime/context_snapshot.py`

**Step 1: Write the failing test**

Add tests that require:
- fresh `runtime.process_started_at` evidence resolves to `runtime.current_process_started_at`
- stale `runtime.process_started_at` evidence resolves to `unknown`

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: FAIL because the compact snapshot does not yet expose a runtime process started-at field.

**Step 3: Write minimal implementation**

Add the smallest reducer support needed to:
- expose `runtime.current_process_started_at`
- filter `runtime.process_started_at` observations by freshness
- prefer newer evidence when more than one fresh observation exists

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_context_snapshot.py personal_runtime/context_snapshot.py
git commit -m "feat: add runtime process started-at snapshot reducer"
```

### Task 2: Record the new M5 slice in the project baseline

**Files:**
- Modify: `Project.md`

**Step 1: Update completed-work tracking**

Record that M5 now includes a freshness-aware compact snapshot field for runtime process start time if the slice lands cleanly.

**Step 2: Commit**

```bash
git add Project.md
git commit -m "docs: record runtime process started-at snapshot slice"
```
