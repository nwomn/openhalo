# M8 Terminal Edge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the desktop/CLI edge into the first formal long-running terminal `Device Edge` with pull-style user requests, presence-gated runtime push, and a bounded manual acceptance path.

**Architecture:** Reuse the existing `Edge Session Link <-> Gateway -> State / Context -> Agent Runtime -> Presence Router -> Action Layer` chain instead of adding a chat-special-case side path. The terminal edge will become a resident websocket daemon that emits explicit terminal-activity observations, sends normal `text.input` events for pull requests, receives normal `notification.show` actions for runtime push, and relies on `Presence Router` to suppress push when recent terminal-activity evidence says the terminal is idle or unknown.

**Tech Stack:** Python, `unittest`, bash, existing websocket gateway, runtime state persistence, terminal stdout/stdin

### Task 1: Add terminal-activity context and presence gating

**Files:**
- Modify: `personal_runtime/context_snapshot.py`
- Modify: `personal_runtime/presence_router.py`
- Test: `tests/test_context_snapshot.py`
- Test: `tests/test_gateway_v0.py`

**Step 1: Write the failing tests**

Add coverage that proves:
- terminal-activity observations reduce into a compact snapshot field
- stale terminal-activity evidence ages out to `unknown`
- runtime-initiated `notification.show` to a terminal edge is suppressed when the terminal is idle
- the same push is allowed when the terminal is active

**Step 2: Run tests to verify they fail**

Run:

```bash
./bin/test -m unittest tests.test_context_snapshot tests.test_gateway_v0 -v
```

Expected: FAIL because terminal snapshot fields and terminal-aware presence suppression do not exist yet.

**Step 3: Write minimal implementation**

Add a compact snapshot field such as `terminal.current_activity_state`, thread it through the existing snapshot contract, and teach `Presence Router` to suppress runtime push to terminal edges when recent terminal-activity evidence is not `active`.

**Step 4: Run tests to verify they pass**

Run:

```bash
./bin/test -m unittest tests.test_context_snapshot tests.test_gateway_v0 -v
```

Expected: PASS

### Task 2: Build the resident terminal edge surface

**Files:**
- Create: `device_edge/cli/terminal_daemon.py`
- Modify: `device_edge/shared/session_client.py`
- Modify: `device_edge/shared/local_actions.py`
- Test: `tests/test_edge_client_v0.py`
- Test: `tests/test_roundtrip_v0.py`
- Test: `tests/test_terminal_daemon_m8.py`

**Step 1: Write the failing tests**

Add coverage that proves:
- `SessionClient` can build terminal-activity observation events cleanly
- a terminal daemon announces `text.input`, `notification.show`, and terminal-context capability surfaces
- the daemon can send a pull-style text request after marking itself active
- the daemon can receive and acknowledge runtime-pushed `notification.show` actions in a long-running websocket session

**Step 2: Run tests to verify they fail**

Run:

```bash
./bin/test -m unittest tests.test_edge_client_v0 tests.test_roundtrip_v0 tests.test_terminal_daemon_m8 -v
```

Expected: FAIL because the terminal daemon module and helpers do not exist yet.

**Step 3: Write minimal implementation**

Create a dedicated resident terminal daemon that:
- maintains one long-running websocket edge session
- emits explicit terminal-activity observations on the normal event path
- sends user-entered text as normal `text.input`
- executes inbound `notification.show` actions locally and returns `action_result`
- supports bounded scripted input / idle controls for automated and human acceptance work

**Step 4: Run tests to verify they pass**

Run:

```bash
./bin/test -m unittest tests.test_edge_client_v0 tests.test_roundtrip_v0 tests.test_terminal_daemon_m8 -v
```

Expected: PASS

### Task 3: Add bounded terminal-edge acceptance tooling and docs

**Files:**
- Create: `bin/verify-terminal-edge`
- Modify: `docs/dev-env.md`
- Test: `tests/test_dev_env_scripts.py`
- Test: `tests/test_chain_inspection.py`

**Step 1: Write the failing tests**

Add coverage that proves:
- the repository exposes a bounded `bin/verify-terminal-edge --dry-run` path
- the dev-environment doc describes terminal-edge verification
- any new terminal inspection surface is documented and callable

**Step 2: Run tests to verify they fail**

Run:

```bash
./bin/test -m unittest tests.test_dev_env_scripts tests.test_chain_inspection -v
```

Expected: FAIL because the terminal-edge verification script and docs do not exist yet.

**Step 3: Write minimal implementation**

Add a bounded terminal-edge verification script that starts the runtime server, starts the terminal daemon, proves:
- one pull-style terminal request roundtrip
- one presence-gated runtime push allow while terminal activity is fresh
- one presence-gated runtime push suppress after terminal idle evidence

Then update docs with the preferred command shape and acceptance intent.

**Step 4: Run tests to verify they pass**

Run:

```bash
./bin/test -m unittest tests.test_dev_env_scripts tests.test_chain_inspection -v
```

Expected: PASS

### Task 4: Verify M8 end to end and update project status

**Files:**
- Modify if needed: `Project.md`
- Modify if needed: `docs/dev-env.md`

**Step 1: Run targeted verification**

Run:

```bash
./bin/test -m unittest tests.test_context_snapshot tests.test_gateway_v0 tests.test_edge_client_v0 tests.test_roundtrip_v0 tests.test_terminal_daemon_m8 tests.test_dev_env_scripts tests.test_chain_inspection -v
```

Expected: PASS

**Step 2: Run bounded human-acceptance verification**

Run:

```bash
bin/verify-terminal-edge --dry-run
bin/verify-terminal-edge
```

Expected:
- dry-run prints runtime, terminal-daemon, scripted pull, runtime-push, and state-check commands
- bounded real run exits cleanly with persisted evidence for pull success, push allow, and push suppression

**Step 3: Update `Project.md` only if the acceptance bar is truly met**

If the verification only lands partial terminal behavior, record progress but keep `M8` in progress.

If the verification proves:
- resident terminal edge behavior
- pull-style request handling
- presence-gated runtime push
- bounded manual acceptance evidence

then mark `M8` complete in `Project.md` and refresh the current progress summary accordingly.
