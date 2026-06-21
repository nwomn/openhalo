# M5 Runtime Process Memory RSS Snapshot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend M5 context maturity by adding a freshness-aware compact snapshot field for runtime process RSS memory.

**Architecture:** Keep the slice reducer-local and incremental. Reuse the existing snapshot-time freshness pattern, add one compact runtime field derived from `runtime.process_memory_rss_bytes`, and avoid widening this batch into threshold policy, aggregation, or agent-behavior changes.

**Tech Stack:** Python 3, `unittest`, existing `personal_runtime` runtime modules

### Task 1: Lock runtime process RSS snapshot behavior with tests

**Files:**
- Modify: `tests/test_context_snapshot.py`
- Modify: `personal_runtime/context_snapshot.py`

**Step 1: Write the failing test**

Add tests that require:
- fresh `runtime.process_memory_rss_bytes` evidence resolves to `runtime.current_process_memory_rss_bytes`
- stale `runtime.process_memory_rss_bytes` evidence resolves to `unknown`

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: FAIL because the compact snapshot does not yet expose a runtime process RSS field.

**Step 3: Write minimal implementation**

Add the smallest reducer support needed to:
- expose `runtime.current_process_memory_rss_bytes`
- filter `runtime.process_memory_rss_bytes` observations by freshness
- prefer newer evidence when more than one fresh observation exists

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_context_snapshot.py personal_runtime/context_snapshot.py
git commit -m "feat: add runtime process RSS snapshot reducer"
```

### Task 2: Verify the slice and update the project baseline

**Files:**
- Modify: `Project.md`

**Step 1: Run targeted verification**

Run the relevant snapshot tests after the reducer test passes.

**Step 2: Update the project baseline**

Record that M5 now includes a freshness-aware compact snapshot field for runtime process RSS memory if the slice lands cleanly.

**Step 3: Commit**

```bash
git add Project.md
git commit -m "docs: record runtime process RSS snapshot slice"
```
