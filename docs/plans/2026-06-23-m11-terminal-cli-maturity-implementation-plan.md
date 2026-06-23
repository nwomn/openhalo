# M11 Terminal CLI Maturity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the first accepted `M11` slice so the resident terminal edge becomes a human-usable agent CLI with stronger session readability, local input affordances, live status visibility, and a bounded manual acceptance path, without changing the core presence-governed runtime architecture.

**Architecture:** Keep the existing `Device Edge -> Edge Session Link -> Gateway -> State / Context -> Agent Runtime -> Presence Router -> Action Layer` chain unchanged. Treat `M11` as a terminal-edge UX maturity layer on top of the accepted `M8` through `M10` baseline: local slash-command affordances, readable terminal rendering, and explicit session-status visibility stay edge-local, while all normal user text, runtime push, grounding, proposal formation, and presence decisions continue to flow through the existing runtime path.

**Tech Stack:** Python 3.11 standard library, `unittest`, existing websocket terminal daemon, existing trace recorder, bash verification script, project docs

### Task 1: Lock the M11 terminal UX contract with failing tests

**Files:**
- Modify: `tests/test_terminal_daemon_m8.py`
- Modify: `tests/test_roundtrip_v0.py`
- Modify: `tests/test_chain_inspection.py`

**Step 1: Write the failing tests**

Add coverage that proves:
- the terminal daemon renders readable session status lines for connect, ready, idle, and runtime-delivered messages
- local slash commands such as `/help`, `/status`, `/history`, and `/quit` are handled edge-locally instead of being forwarded as normal `text.input`
- the daemon keeps a bounded local transcript or session summary that `/history` and `/status` can expose
- runtime-delivered `notification.show` messages are rendered with a terminal-specific readable prefix while keeping the normal action-result shape

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_terminal_daemon_m8 tests.test_roundtrip_v0 tests.test_chain_inspection -v
```

Expected: FAIL because the current terminal daemon does not yet expose local command handling, session rendering, or readable status/history output.

### Task 2: Implement the minimal M11 terminal UX layer

**Files:**
- Modify: `device_edge/cli/terminal_daemon.py`
- Modify: `device_edge/shared/local_actions.py`
- Modify: `device_edge/shared/session_client.py`

**Step 1: Add local terminal session state and rendering helpers**

Implement a small edge-local UX layer that tracks:
- connection state
- terminal activity state
- pending runtime reply state
- counts for user requests, runtime-delivered messages, and local commands
- a bounded readable transcript for recent user/runtime/system lines

**Step 2: Add slash-command affordances**

Handle a narrow first command set entirely on the edge:
- `/help`
- `/status`
- `/history`
- `/quit`

Keep normal user text behavior unchanged for non-command input.

**Step 3: Add readable terminal rendering and trace/status visibility**

Render:
- startup and connection status lines
- user input echo lines
- runtime message lines with a terminal-specific prefix
- idle and exit status lines

Keep the first implementation intentionally simple and line-oriented instead of introducing token streaming or curses-style terminal control.

**Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_terminal_daemon_m8 tests.test_roundtrip_v0 tests.test_chain_inspection -v
```

Expected: PASS

### Task 3: Add bounded M11 acceptance tooling and docs

**Files:**
- Modify: `bin/verify-terminal-edge`
- Modify: `docs/dev-env.md`
- Modify: `tests/test_dev_env_scripts.py`

**Step 1: Write the failing verification/doc tests**

Add coverage that proves:
- `bin/verify-terminal-edge --dry-run` now exposes the M11 local command or UX verification intent
- the dev-environment doc describes the new terminal affordances and preferred manual acceptance path

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_dev_env_scripts -v
```

Expected: FAIL because the current verification and docs do not yet describe the M11 terminal maturity surface.

**Step 3: Implement the minimal verification/documentation changes**

Extend the bounded terminal verification path and docs so a human can verify:
- readable terminal session output
- local command affordances
- repeated live input in one resident session
- the unchanged runtime-path behavior for pull, allowed push, and suppressed push

**Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_dev_env_scripts -v
```

Expected: PASS

### Task 4: Verify M11 end to end and update project status conservatively

**Files:**
- Modify if needed: `Project.md`

**Step 1: Run targeted verification**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_terminal_daemon_m8 tests.test_roundtrip_v0 tests.test_chain_inspection tests.test_dev_env_scripts -v
```

Expected: PASS

**Step 2: Run bounded manual acceptance**

Run:

```bash
bin/verify-terminal-edge --dry-run
bin/verify-terminal-edge
```

Expected:
- dry-run shows the terminal-daemon, terminal-stdin, terminal-pull, runtime-push-active, runtime-push-idle, and state-check steps
- the real run exits cleanly with persisted evidence for pull success, push allow, and push suppress
- the terminal daemon log or stdout shows the new M11 readability and local-command affordances in a human-usable way

**Step 3: Update `Project.md` only if the full M11 bar is met**

If the repository only lands partial CLI ergonomics, record the progress but keep `M11` in progress.

If verification proves:
- readable resident terminal UX
- local terminal input affordances
- explicit session-status visibility
- bounded manual acceptance evidence on the live runtime path

then mark `M11` complete in `Project.md`, shift active execution focus to `M12`, and refresh the current progress summary accordingly.
