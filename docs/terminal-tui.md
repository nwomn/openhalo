# Terminal TUI Guide

## Purpose

The resident terminal edge now supports a full-screen Textual UI mode on top of the normal runtime path.

Use this surface when you want a foreground terminal session that is easier to read than the plain line-oriented daemon output, while still keeping the same `Device Edge -> Gateway -> State / Context -> Agent Runtime -> Presence Router -> Action Layer` chain.

The TUI is a presentation layer only. It does not introduce a second backend path.

## Launch

Start the runtime first:

```bash
python -m personal_runtime.main --host 127.0.0.1 --port 8765 --token dev-token
```

Then start the full-screen terminal edge:

```bash
python -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:8765 --token dev-token --tui
```

If you need the older compatibility path, omit `--tui` and use the line-oriented foreground daemon.

## Layout

The current MVP layout is intentionally small and stable:

- title bar: fixed app identity for the resident terminal surface
- status bar: live connection, activity, pending state, and session counters
- transcript pane: scrollable `[system]`, `[user]`, and `[runtime]` session history
- input box: normal user text entry plus local slash commands
- help bar: always-visible reminder of local command affordances

The transcript pane is the only area that should keep growing during use. The input box should remain visible while the session stays active.

## Status Bar

The status bar is the primary at-a-glance session summary.

Current fields:

- `device`: active terminal edge device id
- `connection`: current websocket session state
- `activity`: latest terminal activity state sent on the runtime path
- `state`: `waiting` when a runtime reply is pending, otherwise `ready`
- `user`: number of forwarded normal user requests
- `runtime`: number of runtime-delivered messages rendered locally
- `local`: number of edge-local slash commands handled without forwarding

This status surface is edge-local UI state. It should help a foreground operator understand what the resident edge is doing without inspecting persisted runtime state by hand.

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
- Runtime-pushed messages should appear in the transcript with the `[runtime]` prefix.
- Repeated explicit user input should continue working in one resident session.
- Presence cooldown logic is for runtime-initiated interruption, not for suppressing the user's own back-to-back requests.

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

Run one foreground session and validate:

- the app opens in a full-screen layout
- the status bar stays visible while the transcript grows
- a normal message produces both `[user]` and `[runtime]` lines
- `/help`, `/status`, and `/history` update the transcript locally
- `/quit` exits the TUI cleanly

Suggested input sequence:

```text
hello runtime
/help
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
