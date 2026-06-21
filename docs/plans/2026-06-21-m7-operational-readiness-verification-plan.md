# M7 Operational Readiness Verification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn M7 into a concrete host-edge readiness gate by verifying both the direct-action fast path and the runtime-originated initiative path against a real separate host-edge daemon.

**Architecture:** M7 should not expand the runtime feature surface. It should harden the acceptance boundary around the existing `Gateway -> State / Context -> Presence Router -> Action Layer -> Host Edge` chain so that stronger "implemented and ready to run" claims depend on a bounded real host-edge verification run instead of CLI-only or in-process checks.

**Tech Stack:** Python, `unittest`, bash, existing websocket gateway, host-edge daemon, JSON runtime state persistence

### Task 1: Add the missing verification control surface

**Files:**
- Modify: `device_edge/host/host_daemon.py`
- Test: `tests/test_host_daemon_v1.py`

**Step 1: Write the failing test**

Add coverage that proves the host daemon parser and entrypoint accept a bounded `max_action_requests` control and forward it into `run_forever`.

**Step 2: Run test to verify it fails**

Run: `./bin/test -m unittest tests.test_host_daemon_v1 -v`
Expected: FAIL because `--max-action-requests` is unknown or not forwarded.

**Step 3: Write minimal implementation**

Add the parser flag, extend `run_forever(...)`, and forward the value into `run_websocket_daemon_session(...)`.

**Step 4: Run test to verify it passes**

Run: `./bin/test -m unittest tests.test_host_daemon_v1 -v`
Expected: PASS

### Task 2: Make the readiness script verify both host-edge paths

**Files:**
- Modify: `bin/verify-host-edge`
- Modify: `device_edge/shared/session_client.py`
- Test: `tests/test_dev_env_scripts.py`
- Test: `tests/test_edge_client_v0.py`

**Step 1: Write the failing tests**

Add coverage that expects:
- `SessionClient` can build an `agent_initiative` event frame
- `bin/verify-host-edge --dry-run` shows both the direct-action check and the runtime-initiative check

**Step 2: Run tests to verify they fail**

Run: `./bin/test -m unittest tests.test_edge_client_v0 tests.test_dev_env_scripts -v`
Expected: FAIL because the helper and richer dry-run shape do not exist yet.

**Step 3: Write minimal implementation**

Update the session client with a small helper for initiative events, then update `bin/verify-host-edge` so it:
- waits for the runtime and host edge to be connected
- sends one direct `runtime.status` request
- sends one initiative-driven `runtime.status` request through the normal presence/planning path
- verifies persisted runtime state for host observations, initiative intervention recording, and two runtime-status action results

**Step 4: Run tests to verify they pass**

Run: `./bin/test -m unittest tests.test_edge_client_v0 tests.test_dev_env_scripts -v`
Expected: PASS

### Task 3: Document the M7 readiness gate clearly

**Files:**
- Modify: `docs/dev-env.md`
- Modify: `Project.md`

**Step 1: Write the failing test**

Add or extend documentation coverage so `docs/dev-env.md` states that the default host-edge readiness run now covers both the fast path and the normal initiative path.

**Step 2: Run test to verify it fails**

Run: `./bin/test -m unittest tests.test_dev_env_scripts -v`
Expected: FAIL because the wording is still fast-path-only.

**Step 3: Write minimal implementation**

Update the dev-environment doc and record the new M7 progress in `Project.md` without prematurely marking M7 complete.

**Step 4: Run test to verify it passes**

Run: `./bin/test -m unittest tests.test_dev_env_scripts -v`
Expected: PASS

### Task 4: Verify the bounded readiness flow end to end

**Files:**
- Modify if needed: `bin/verify-host-edge`
- Test: `tests/test_host_daemon_v1.py`
- Test: `tests/test_roundtrip_v0.py`
- Test: `tests/test_dev_env_scripts.py`

**Step 1: Run targeted verification**

Run:
- `./bin/test -m unittest tests.test_host_daemon_v1 tests.test_edge_client_v0 tests.test_dev_env_scripts tests.test_roundtrip_v0 -v`
- `bin/verify-host-edge --dry-run`

Expected:
- automated tests pass
- dry-run output shows runtime, host-daemon, client verification, and state verification commands

**Step 2: Decide Project.md status update**

If the evidence only strengthens the gate, keep `M7` in progress and record completed work.
If the evidence satisfies the full M7 acceptance bar, then and only then mark the milestone complete in `Project.md`.
