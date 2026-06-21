# M5 Runtime Ingestion And Context Closeout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close M5 as a milestone by adding a compact decision-time snapshot contract with explicit field status/evidence and by proving that the live gateway path consumes that contract end to end.

**Architecture:** Keep the hot path shallow. Preserve the existing compact snapshot field surface for `Presence Router`, add a parallel contract/evidence view for M5.3, and thread that view through gateway-side intervention recording for M5.4 without widening into richer presence policy or agent-behavior redesign.

**Tech Stack:** Python 3, `unittest`, existing `personal_runtime` runtime modules, `Project.md`

### Task 1: Lock the M5.3 snapshot contract with tests

**Files:**
- Modify: `tests/test_context_snapshot.py`
- Modify: `personal_runtime/context_snapshot.py`

**Step 1: Write the failing test**

Add tests that require:
- the snapshot builder can return a contract view with per-field status for fresh, stale, missing, and ambiguous outcomes
- the contract view includes bounded supporting evidence for fields that are consumed later
- the existing compact field values remain unchanged for current callers

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: FAIL because the snapshot builder does not yet expose a contract/evidence view.

**Step 3: Write minimal implementation**

Add the smallest support needed to:
- preserve `build_context_snapshot(...) -> dict` as the compact field API
- expose a parallel decision-time contract builder with per-field `value`, `status`, and recent supporting evidence
- reuse existing reducer semantics instead of rewriting the whole reducer surface

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
Expected: PASS

### Task 2: Lock the M5.4 gateway live-path proof with tests

**Files:**
- Modify: `tests/test_gateway_v0.py`
- Modify: `personal_runtime/gateway_server.py`

**Step 1: Write the failing test**

Add tests that require:
- normal-path gateway intervention recording includes the decision-time snapshot contract used for evaluation
- a live host/runtime telemetry sample appears in that recorded contract when the normal path fires later
- stale telemetry evidence is recorded as stale or unknown rather than silently treated as current truth

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_gateway_v0 -v`
Expected: FAIL because gateway intervention records do not yet store the contract/evidence view.

**Step 3: Write minimal implementation**

Add the smallest support needed to:
- build the contract view alongside the compact snapshot in the normal gateway path
- pass only the compact snapshot into current presence logic
- record the contract view into intervention history for replay and human inspection

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_gateway_v0 -v`
Expected: PASS

### Task 3: Record M5 completion and human-acceptance baseline

**Files:**
- Modify: `Project.md`

**Step 1: Update milestone status**

Record that:
- M5.3 now has an explicit decision-time contract for freshness / ambiguity / evidence
- M5.4 now has live-path verification through gateway intervention records
- M5 is complete and ready for human acceptance with a concrete verification baseline

**Step 2: Final verification**

Run:
- `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_context_snapshot -v`
- `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_gateway_v0 -v`
- `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_roundtrip_v0 -v`

Expected: PASS
