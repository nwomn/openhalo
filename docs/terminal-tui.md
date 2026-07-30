# Terminal TUI Guide

## Purpose

The resident terminal edge now supports a full-screen Textual UI mode on top of the normal runtime path.

Use this surface when you want a foreground terminal session that is easier to read than the plain line-oriented daemon output, while still keeping the same `Device Edge -> Gateway -> State / Context -> Agent Runtime -> Presence Router -> Action Layer` chain.

The TUI is a presentation layer only. It does not introduce a second backend path.

## Launch

Start the runtime first:

```bash
OPENHALO_DEV_RUNTIME_HOST=127.0.0.1 bin/run-runtime-dev
```

Create a one-time development pairing code:

```bash
.venv/bin/python -m personal_runtime.pairing_cli create \
  --store .runtime/android-openai-dev-pairing.json
```

Pair and launch the full-screen Terminal Edge with an isolated local home:

```bash
EDGE_HOME="$PWD/.runtime/terminal-tui-dev-home"
.venv/bin/python -m openhalo.edge_cli --home "$EDGE_HOME" setup \
  --url ws://127.0.0.1:18765 \
  --pairing-code <one-time-code> \
  --display-name "Terminal TUI Dev"
.venv/bin/python -m openhalo.edge_cli --home "$EDGE_HOME" run
```

The pairing code is consumed after this successful setup. To return in a new
terminal, set `EDGE_HOME` to this same path and run
`.venv/bin/python -m openhalo.edge_cli --home "$EDGE_HOME" run`; do not run
`setup` again. For the line-oriented fallback, append `--line-mode` to that
same command.

## Layout

The Quiet Edge layout is intentionally small and stable:

- connection header: fixed OpenHalo identity, local Terminal Edge name, and a readable connection state
- transcript pane: scrollable `System`, `You`, and `OpenHalo` conversation treatment rather than protocol-style prefixes
- activity row: one safe live progress message for the active interaction
- receipt: a compact, focusable settled outcome that expands locally into its safe public timeline
- Composer: fixed message input plus local slash commands and width-adaptive keyboard help

The transcript pane is the only area that should keep growing during use. The input box should remain visible while the session stays active.

## Connection Header

The header is the primary at-a-glance session summary. It displays only the
OpenHalo identity, the local Terminal Edge display name, and a readable state:
`Connected`, `Connecting`, `Reconnecting`, `Offline`, or `Needs attention`.
It intentionally omits runtime counters and implementation diagnostics. Those
remain available through edge-local commands and diagnostics rather than
competing with the foreground conversation.

## Local Commands

These commands stay on the terminal edge and must not be forwarded as normal `text.input` events:

- `/help`
- `/status`
- `/history`
- `/quit`

Current behavior:

- `/help` shows the available local commands
- `/status` prints a readable session summary into the transcript
- `/history` reprints the bounded recent transcript
- `/quit` requests clean resident-session shutdown

## Interaction Rules

- Normal text is sent through the existing runtime path and should still receive normal runtime replies.
- Runtime-pushed messages should appear under the `OpenHalo` speaker label.
- Repeated explicit user input should continue working in one resident session.
- Presence cooldown logic is for runtime-initiated interruption, not for suppressing the user's own back-to-back requests.

## Input Sensing

The TUI reports draft-empty versus draft-nonempty changes through the normal `terminal.context` path as `terminal.input_state` and `terminal.input_draft_length` observations.

This is intentionally a lightweight foreground-input signal, not full IME composition semantics. Its current job is to let the resident daemon observe that the user is actively drafting text before the next submitted line exists.

When a nonempty draft arrives while the daemon is waiting to mark the terminal idle, the draft-state observation should wake that wait and be sent before a new `terminal.activity_state=idle` observation. That keeps `Terminal idle` from winning the race while the user is actively typing.

## Exit Behavior

Preferred exit path:

- type `/quit` in the input box

Compatibility exit path:

- `Ctrl+C`

Expected behavior:

- the session closes cleanly
- the TUI exits back to the shell
- the daemon does not enter the old reconnect loop after quit

## Manual Acceptance

Use one foreground session and validate a real user scenario instead of isolated control checks.

### User-scenario acceptance run

1. Start the runtime with:

```bash
OPENHALO_DEV_RUNTIME_HOST=127.0.0.1 bin/run-runtime-dev
```

2. Create a code, pair the TUI, and start it in a second terminal:

```bash
.venv/bin/python -m personal_runtime.pairing_cli create \
  --store .runtime/android-openai-dev-pairing.json
EDGE_HOME="$PWD/.runtime/terminal-tui-dev-home"
.venv/bin/python -m openhalo.edge_cli --home "$EDGE_HOME" setup \
  --url ws://127.0.0.1:18765 \
  --pairing-code <one-time-code> \
  --display-name "Terminal TUI Dev"
.venv/bin/python -m openhalo.edge_cli --home "$EDGE_HOME" run
```

3. Wait for the TUI to connect and confirm the Quiet Edge header, semantic transcript pane, active-progress row, fixed Composer, and keyboard help appear.
4. Type `hello runtime` and press Enter.
   Expectation: the transcript shows a `You` line followed by one real `OpenHalo` reply rather than only echoing the user text or going silent.
5. Type `check runtime status` and press Enter.
   Expectation: the transcript shows the user line and then a runtime-delivered status response on the same resident session.
6. Type `/status`.
   Expectation: the transcript updates locally with a readable session summary and no extra runtime request is created.
7. Type `/history`.
   Expectation: the transcript reprints recent `System`, `You`, and `OpenHalo` lines from the same session.
8. Type `/quit`.
   Expectation: the TUI exits cleanly back to a clear shell surface without a reconnect loop or residual UI pixels.

### Compact input sequence

```text
hello runtime
check runtime status
/status
/history
/quit
```

## Current Limits

This is the first Textual MVP, not the final terminal product surface.

Known limits:

- no multi-pane action/trace inspector inside the TUI yet
- no explicit command-output pane for tool execution yet
- no structured reasoning-summary panel yet
- no session picker, branch/fork view, or background-job dashboard yet

Those are later CLI-surface refinement topics, not regressions in the current `M11` acceptance bar.
