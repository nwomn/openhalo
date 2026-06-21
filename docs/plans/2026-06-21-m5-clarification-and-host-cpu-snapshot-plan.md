# M5 Clarification And Host CPU Snapshot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Clarify M5 into explicit acceptance-oriented sub-stages and continue M5 by adding a freshness-aware compact snapshot field for host CPU load ratio.

**Architecture:** Keep M5 framed as one umbrella milestone, but split its execution into smaller checkpoints that map cleanly onto `Gateway` and `State / Context` responsibilities. Continue implementation with one reducer-local host metric slice derived from `host.cpu_load_ratio`, reusing the existing snapshot-time freshness pattern and avoiding broader policy or aggregation work.

**Tech Stack:** Python 3, `unittest`, existing `personal_runtime` runtime modules, `Project.md`

### Task 1: Clarify M5 milestone structure in the project baseline

**Files:**
- Modify: `Project.md`

**Step 1: Update the M5 definition**

Refine the milestone text so M5 stays one milestone but is explicitly broken into smaller acceptance-oriented sub-stages such as:
- gateway ingest / normalized observation handling
- compact snapshot field pack growth
- freshness / ambiguity / evidence semantics
- end-to-end context-path verification

**Step 2: Align current progress wording**

Update the current phase and/or progress summary so it is clear which M5 sub-stage is currently in progress.

**Step 3: Commit**

```bash
git add Project.md
git commit -m "docs: clarify M5 execution breakdown"
```

### Task 2: Lock host CPU snapshot behavior with tests

**Files:**
- Modify: `tests/test_context_snapshot.py`
- Modify: `personal_runtime/context_snapshot.py`

**Step 1: Write the failing test**

Add tests that require:
- fresh `host.cpu_load_ratio` evidence resolves to `host.current_cpu_load_ratio`
- stale `host.cpu_load_ratio` evidence resolves to `unknown`

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: FAIL because the compact snapshot does not yet expose a host CPU load field.

**Step 3: Write minimal implementation**

Add the smallest reducer support needed to:
- expose `host.current_cpu_load_ratio`
- filter `host.cpu_load_ratio` observations by freshness
- prefer newer evidence when more than one fresh observation exists

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_context_snapshot.py personal_runtime/context_snapshot.py
git commit -m "feat: add host CPU load snapshot reducer"
```

### Task 3: Record the new M5 slice in the project baseline

**Files:**
- Modify: `Project.md`

**Step 1: Update completed-work tracking**

Record that M5 now includes a freshness-aware compact snapshot field for host CPU load if the slice lands cleanly.

**Step 2: Commit**

```bash
git add Project.md
git commit -m "docs: record host CPU snapshot slice"
```
