# Server-Safe Test Runner Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `bin/test` safe to run on the shared server by default, without moving the suite to CI or disabling loopback integration tests.

**Architecture:** `bin/test` launches the test process in one transient systemd service when systemd is available. The service gets a private network namespace, bounded CPU, memory, and task count; loopback remains available for in-process HTTP/WebSocket fixtures. A marker environment variable prevents nested `bin/test` calls from creating more scopes. Explicitly setting `OPENHALO_TEST_ISOLATION=0` keeps the existing direct execution fallback for environments without systemd.

**Tech Stack:** Bash, systemd-run, Python unittest.

### Task 1: Specify the isolated runner contract

**Files:**
- Modify: `tests/test_dev_env_scripts.py`
- Modify: `bin/test`

**Step 1:** Add a failing test that requires `bin/test` to declare private networking, CPU/memory/task limits, a nested-scope marker, and an explicit opt-out.

**Step 2:** Run the focused test and confirm it fails because the current wrapper directly execs Python.

### Task 2: Implement the transient-service wrapper

**Files:**
- Modify: `bin/test`

**Step 1:** Preserve direct root-venv Python execution when already inside the test service, when isolation is explicitly disabled, or when `systemd-run` is unavailable.

**Step 2:** Otherwise execute the root-venv Python command through `systemd-run --wait --pipe --collect --service-type=exec` with `PrivateNetwork=yes`, `CPUQuota=150%`, `MemoryMax=2G`, `TasksMax=256`, and `NoNewPrivileges=yes`.

**Step 3:** Propagate `OPENHALO_TEST_IN_SCOPE=1` so test subprocesses do not create nested systemd services.

### Task 3: Verify containment and compatibility

**Files:**
- Test: `tests/test_dev_env_scripts.py`
- Test: `tests/test_interaction_progress.py`

**Step 1:** Run the runner-contract test through the isolated `bin/test` command.

**Step 2:** Run the M20.2 focused suites, including the loopback WebSocket progress acceptance.

**Step 3:** Confirm `systemd-run` can bind loopback but cannot create an external TCP connection.

**Step 4:** Do not run full test discovery on the shared server until it has been separately observed under the new containment boundary.
