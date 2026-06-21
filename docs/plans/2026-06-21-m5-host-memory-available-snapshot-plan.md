# M5 Host Memory Available Snapshot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend M5.2 compact snapshot field-pack growth by adding a freshness-aware compact snapshot field for host available memory.

**Architecture:** Keep the slice reducer-local and incremental. Reuse the existing snapshot-time freshness pattern, add one host-metric field derived from `host.memory_available_bytes`, and avoid widening this batch into threshold policy, metric aggregation, or agent-behavior changes.

**Tech Stack:** Python 3, `unittest`, existing `personal_runtime` runtime modules, `Project.md`

### Task 1: Lock host available-memory snapshot behavior with tests

**Files:**
- Modify: `tests/test_context_snapshot.py`
- Modify: `personal_runtime/context_snapshot.py`

**Step 1: Write the failing test**

Add tests that require:
- fresh `host.memory_available_bytes` evidence resolves to `host.current_memory_available_bytes`
- stale `host.memory_available_bytes` evidence resolves to `unknown`

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: FAIL because the compact snapshot does not yet expose a host available-memory field.

**Step 3: Write minimal implementation**

Add the smallest reducer support needed to:
- expose `host.current_memory_available_bytes`
- filter `host.memory_available_bytes` observations by freshness
- prefer newer evidence when more than one fresh observation exists

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_context_snapshot.py personal_runtime/context_snapshot.py
git commit -m "feat: add host available-memory snapshot reducer"
```

### Task 2: Record the new M5 slice in the project baseline

**Files:**
- Modify: `Project.md`

**Step 1: Update completed-work tracking**

Record that M5 now includes a freshness-aware compact snapshot field for host available memory if the slice lands cleanly.

**Step 2: Commit**

```bash
git add Project.md
git commit -m "docs: record host available-memory snapshot slice"
```
