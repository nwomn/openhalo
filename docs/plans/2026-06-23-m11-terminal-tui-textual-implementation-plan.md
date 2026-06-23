# M11 Terminal TUI Textual Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a first full-screen Textual terminal UI for the resident terminal edge so the current line-oriented daemon gains a human-usable status bar, transcript pane, input box, and local-command discoverability without changing the runtime protocol path.

**Architecture:** Keep the existing `Device Edge -> Edge Session Link -> Gateway -> State / Context -> Agent Runtime -> Presence Router -> Action Layer` chain untouched. Implement the TUI as an edge-local presentation layer that reuses the current `TerminalEdgeDaemon` session logic through queue-backed input/output adapters and a dedicated `--tui` entry mode, so normal `text.input`, `terminal.context`, runtime push delivery, and local slash commands still flow through the same daemon behavior already verified in M8/M11.

**Tech Stack:** Python 3.11, `textual`, standard-library `queue`/`threading`, existing websocket daemon, `unittest`

### Task 1: Lock the Textual entry contract with failing tests

**Files:**
- Modify: `tests/test_terminal_daemon_m8.py`
- Modify: `pyproject.toml`

**Step 1: Write the failing tests**

Add coverage that proves:
- `build_terminal_daemon_parser()` accepts a `--tui` flag
- the project metadata declares `textual` as a runtime dependency
- the existing line mode remains the default when `--tui` is omitted

**Step 2: Run the focused tests to verify they fail**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_terminal_daemon_m8.TerminalEdgeDaemonTests -v
```

Expected: FAIL because `--tui` and the dependency declaration do not exist yet.

**Step 3: Write the minimal implementation**

Add the `--tui` parser flag and the `textual` dependency declaration while leaving the current non-TUI execution path unchanged.

**Step 4: Re-run the focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_terminal_daemon_m8.TerminalEdgeDaemonTests -v
```

Expected: PASS

### Task 2: Add queue-backed terminal adapters and a first Textual app shell

**Files:**
- Create: `device_edge/cli/terminal_tui.py`
- Modify: `tests/test_terminal_daemon_m8.py`

**Step 1: Write the failing tests**

Add coverage that proves:
- a queue-backed output adapter can accumulate daemon-rendered lines into whole transcript entries
- a queue-backed input adapter can feed user-entered lines to the daemon
- the Textual app exposes a top status bar, transcript view, and input widget

**Step 2: Run the focused tests to verify they fail**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_terminal_daemon_m8.TerminalEdgeDaemonTests -v
```

Expected: FAIL because the adapters and TUI app do not exist yet.

**Step 3: Write the minimal implementation**

Implement:
- a blocking queue-backed `readline()` input adapter for daemon stdin
- a line-buffering output adapter that emits completed lines to the TUI thread
- a small `TerminalEdgeApp` Textual shell with:
  - header/status line
  - scrollable transcript area
  - footer/help hint
  - single-line input box

**Step 4: Re-run the focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_terminal_daemon_m8.TerminalEdgeDaemonTests -v
```

Expected: PASS

### Task 3: Wire the Textual app to the existing daemon session loop

**Files:**
- Modify: `device_edge/cli/terminal_daemon.py`
- Modify: `device_edge/cli/terminal_tui.py`
- Modify: `tests/test_terminal_daemon_m8.py`

**Step 1: Write the failing tests**

Add coverage that proves:
- `main()` dispatches to the Textual app when `--tui` is provided
- the TUI bridge can start the daemon in the background with queue-backed input/output streams
- daemon-rendered `[system]`, `[user]`, and `[runtime]` lines are reflected into the TUI transcript
- the status bar can render connection/activity/pending state from the live daemon object

**Step 2: Run the focused tests to verify they fail**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_terminal_daemon_m8.TerminalEdgeDaemonTests tests.test_terminal_daemon_m8.TerminalEdgeAsyncSessionTests -v
```

Expected: FAIL because the TUI mode is not wired into the daemon entry path yet.

**Step 3: Write the minimal implementation**

Implement:
- a `run_textual_terminal_daemon(...)` helper that builds the Textual app and starts it
- a small daemon-thread launcher inside the app or bridge layer
- periodic status refresh from the live daemon object
- transcript updates that preserve the existing daemon rendering contract

**Step 4: Re-run the focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_terminal_daemon_m8 -v
```

Expected: PASS

### Task 4: Document and verify the new TUI mode conservatively

**Files:**
- Modify: `docs/dev-env.md`
- Modify: `tests/test_dev_env_scripts.py`

**Step 1: Write the failing tests**

Add coverage that proves the dev-environment guide now documents:
- `--tui` as the preferred full-screen UI mode
- the line mode as a fallback compatibility path
- the first manual TUI acceptance expectations: status bar, transcript pane, input box, and clean `/quit`

**Step 2: Run the focused tests to verify they fail**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_dev_env_scripts -v
```

Expected: FAIL because the TUI mode is not documented yet.

**Step 3: Write the minimal implementation**

Update the docs so a human can launch:

```bash
python -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:8765 --token dev-token --tui
```

and know what to validate visually.

**Step 4: Re-run the focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_dev_env_scripts -v
```

Expected: PASS

### Task 5: Verify the Textual MVP end to end

**Files:**
- Modify if needed: `Project.md`

**Step 1: Run targeted verification**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_terminal_daemon_m8 tests.test_dev_env_scripts -v
```

Expected: PASS

**Step 2: Run a manual launch check**

Run:

```bash
.venv/bin/python -u -m personal_runtime.main --host 127.0.0.1 --port 8765 --token dev-token
.venv/bin/python -u -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:8765 --token dev-token --tui
```

Expected:
- the TUI opens in full-screen mode
- a fixed status surface remains visible while transcript lines grow
- typed text appears in the transcript and still receives runtime replies
- `/help`, `/status`, `/history`, and `/quit` remain edge-local
- `/quit` exits the TUI cleanly without reconnect looping

**Step 3: Update `Project.md` only if the MVP bar is fully met**

If the repository only lands the first TUI shell and conservative docs, record progress but keep broader `M11` refinement open.
