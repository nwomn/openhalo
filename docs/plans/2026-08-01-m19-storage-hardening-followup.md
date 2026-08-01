# M19 Storage Hardening Follow-up Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the remaining M19 storage-safety gaps without changing the balanced retention policy.

**Architecture:** Keep SQLite as the authoritative Runtime repository and preserve pending mutation operations until a successful transaction commits. Harden migration input validation and deterministic resource cleanup at file/database boundaries; retain JSON only as migration and rollback material.

**Tech Stack:** Python 3, SQLite, pytest, JSONL diagnostics.

### Task 1: Reproduce failure and cleanup gaps

**Files:**
- Test: `tests/test_sqlite_state_store.py`
- Test: `tests/test_state_migration.py`
- Modify: `personal_runtime/sqlite_state_store.py`
- Modify: `personal_runtime/state_migration.py`

**Steps:**
1. Add tests for pending-operation restoration after a failed flush, trailing JSON rejection, and cleanup after migration/export failures.
2. Run the focused tests and confirm each fails for the intended reason.
3. Implement the smallest fixes at the transaction/file ownership boundaries.
4. Re-run focused tests, then the M19/runtime regression suites.

### Task 2: Verify release and runtime behavior

**Files:**
- Modify: `Project.md`

**Steps:**
1. Run the complete available regression suite and record environment-only failures separately.
2. Review the diff for accidental scope expansion or secret leakage.
3. Update the M19 operational status with fresh evidence and acceptance gaps.

### Task 3: Enforce the balanced physical quota

**Files:**
- Modify: `personal_runtime/sqlite_state_store.py`
- Modify: `openhalo/cli.py`
- Test: `tests/test_sqlite_state_store.py`
- Test: `tests/test_openhalo_cli.py`

**Steps:**
1. Add failing tests for quota rejection, eligible-history reclamation, and total-footprint pressure reporting.
2. Run the quota tests and confirm they fail for the missing enforcement behavior.
3. Implement preflight and in-transaction SQLite footprint checks with active-correlation protection.
4. Run the focused quota and owner CLI suites, then the complete regression suite.
