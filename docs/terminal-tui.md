# Terminal TUI Guide

## Purpose

The resident Terminal Edge includes a conversation-first Textual UI mode over the normal OpenHalo runtime path. Its status bar, transcript pane, Active Interaction area, and input box remain visible as one resident surface:

```text
Device Edge -> Gateway -> State / Context -> Agent Runtime -> Presence -> Action
```

The TUI is a presentation layer only. It does not add a local agent loop, bypass the Gateway, or expose private model reasoning.

## Launch

Start the development Runtime:

```bash
OPENHALO_DEV_RUNTIME_HOST=127.0.0.1 bin/run-runtime-dev
```

Then start the Terminal Edge in a second terminal:

```bash
.venv/bin/python -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:18765 --token dev-token --tui
```

Omit `--tui` for the line-oriented compatibility mode. When `TERM` is unset or `TERM=dumb`, a requested TUI automatically falls back to line mode.

## Layout

The full-screen interface keeps conversation, transient work, and controls separate:

```text
┌ OpenHalo · terminal-edge-1                    ● Connected ┐
│ connection/activity/pending state and counters             │
├──────────────────── Transcript ─────────────────────────────┤
│ YOU       normal user messages                              │
│ OPENHALO  visible Runtime replies and cross-device results  │
│ SYSTEM    local connection and command notices              │
│ ERROR     safe public failure summaries                     │
├──────────────── Active Interaction ─────────────────────────┤
│ ◌ Preparing the next step                                   │
│   Selecting an appropriate device and capability            │
├──────────────────── Composer ────────────────────────────────┤
│ › Message OpenHalo, or use /help for local commands          │
└ Enter · ↑↓ history · Tab commands · Ctrl+L clear ───────────┘
```

### Header and connection chip

The Header shows the Terminal Edge identity, a compact global-device summary,
and a text-labelled Runtime connection state:

- `Global thread · 3/4 edges` means three of four bounded registered Edge
  participants currently have live Gateway sessions.
- Select that summary or press `Ctrl+D` to reveal the on-demand device overview.
  The overview lists safe device identity/type/role, online state, and public
  action-capability names; it is not a raw protocol or diagnostics dashboard.
- Press `Escape` to close the overview and return focus to the Composer.

Connection labels remain:

- `● Connected`
- `◌ Connecting`
- `↻ Reconnecting`
- `○ Offline`

The low-emphasis status line retains the full edge-local diagnostic summary: device, WebSocket state, activity, pending state, and user/runtime/local counters. `/status` writes the same kind of summary into the bounded daemon history.

### Transcript

The Transcript is reserved for durable, user-relevant session content. It distinguishes `YOU`, `OPENHALO`, `SYSTEM`, and `ERROR` with both text labels and color.

Textual treats all message bodies as text rather than Rich markup. Public Runtime summaries may be shown, but provider tokens, device credentials, tool internals, prompts, and private reasoning must not be rendered.

### Active Interaction

Interaction progress is transient. In TUI mode, phases such as deliberating,
planning, executing, and awaiting an action result update one Active Interaction
row in place. They do not create a permanent progress line for every phase.

When Runtime governance and planning select a cross-device action, that same
single row becomes a compact route, for example:

```text
terminal-edge-1 → Personal Runtime [Presence allow] → phone-edge-1 · notification.show
```

This is real Runtime-projected source, target, capability, and Presence decision
data rather than a route inferred from response prose. A multi-action turn is
summarized without exposing action payloads or private planning data. The route
clears when the matching interaction settles.

The ordinary line mode intentionally keeps the existing append-only `[progress] ...` behavior for scripts, logs, and non-full-screen terminals.

When a progress lifecycle settles, the panel disappears. A public failed completion can leave a safe error summary until the next user request. Connection loss takes precedence over stale interaction progress.

### Composer

The Composer remains visible while the resident session is active. Normal text is sent through the public Runtime path. Slash commands stay on the Terminal Edge.

When disconnected or reconnecting, Enter does not send normal text and does not erase the draft. In-flight requests are never replayed automatically after reconnect because doing so could duplicate a cross-device side effect.

## Local Commands

| Command | Behavior |
|---|---|
| `/help` | Show the available local commands. |
| `/status` | Write the current edge-local session summary. |
| `/history` | Replay the daemon's bounded recent transcript. |
| `/clear` | Clear only the currently visible TUI transcript. |
| `/reconnect` | End the current socket session and reconnect. |
| `/quit` | Request clean resident-session shutdown. |

`/history` is different from Composer history: `/history` displays recent session output, while Up and Down recall previously submitted input.

Typing `/` opens the command suggestion area. Tab and Shift+Tab complete matching commands.

## Keyboard Controls

| Key | Behavior |
|---|---|
| `Enter` | Send normal text or execute a local command. |
| `Up` / `Down` | Navigate session-local input history and restore the original draft. |
| `Tab` / `Shift+Tab` | Complete matching slash commands. |
| `Escape` | Close command suggestions. |
| `PageUp` / `PageDown` | Scroll the Transcript. |
| `End` | Return to the latest Transcript content. |
| `Ctrl+D` | Toggle the on-demand Device Edge overview. |
| `Ctrl+L` | Clear the visible Transcript. |
| `Ctrl+C` | Request clean shutdown. |

Input history is held only in memory for the current process. It is not written to disk as a new persistence surface.

## Input Sensing

The TUI continues to report `draft_empty` and `draft_nonempty` through `terminal.context`, including `terminal.input_draft_length`. This is a lightweight activity signal, not full IME composition capture.

Draft observations use the same Edge API path as other terminal context. They do not create a second backend channel.

## Resize Behavior

At narrow widths, the detailed status row is hidden and Transcript padding is reduced. At short heights, the footer and Active Interaction area compact. The Transcript, Active Interaction, and Composer remain the primary layout priorities.

Long and CJK messages wrap inside the Transcript. User-initiated scrollback is preserved when new output arrives; `End` resumes the latest view.

## Reconnect and Exit

After unexpected WebSocket loss, the resident daemon uses bounded exponential
retry and shows `Reconnecting`. The first interruption and eventual recovery are
user-relevant lifecycle events; individual retry attempts update the Active
Interaction row in place rather than flooding the TUI Transcript. Plain line mode
keeps append-only retry diagnostics for scripts and logs. The daemon clears stale
pending/progress/route state, preserves unsubmitted Composer text, and does not
automatically resend a request that may already have reached the Runtime.

While offline, a persistent Composer note explains that Enter will not send or
erase the draft. Repeated Enter presses do not append duplicate system notices.
A recovered status is shown briefly and then disappears.

Use `/reconnect` to request an immediate fresh socket session. Use `/quit` or `Ctrl+C` for clean shutdown. Expected exit behavior:

- the WebSocket session closes;
- the Textual app returns to the shell;
- pending queue readers are cancelled cleanly;
- the resident reconnect loop does not restart after quit.

## Manual Acceptance

Use this as a real user scenario in one foreground session rather than treating widget checks as sufficient evidence.

1. Start the Runtime and TUI with the commands above.
2. Confirm the chip transitions from Connecting to Connected and the global
   summary reflects the currently connected Edge roster.
3. Press `Ctrl+D`; confirm the overview marks the Terminal as the current Edge,
   shows other online/offline devices, then closes with `Escape`.
4. Submit `check runtime status` and confirm `YOU` and `OPENHALO` transcript entries appear.
5. Use a cross-device action and confirm the single Active Interaction row shows
   the Runtime-projected source, Presence decision, target, and capability; it
   disappears after completion without Transcript spam.
6. Type `/st`, press Tab, and confirm completion to `/status`.
7. Use Up and Down to recall input and restore an unfinished draft.
8. Type `/history` and confirm it replays the daemon's bounded output rather than Composer history.
9. Resize between wide, narrow, and short windows; confirm the Composer remains usable.
10. Stop the Runtime with an unsubmitted draft present; confirm one interruption
    event, an in-place retry counter/delay, a persistent Composer note, and no
    repeated retry lines in the TUI Transcript.
11. Restart the Runtime; confirm one recovery event, automatic reconnect, and no
    automatic replay of an in-flight request.
12. Type `/quit`; confirm a clean return to the shell without a Textual traceback.
13. Run once without `--tui` and once with `TERM=dumb --tui`; confirm readable line-mode fallback and append-only progress/retry diagnostics.

## Current Limits

This M20.3 slice does not add a session picker, branch/fork viewer, tool trace inspector, background job dashboard, multi-line editor, or durable input history. Structured protocol errors beyond existing public Runtime completion summaries remain a later contract decision.
