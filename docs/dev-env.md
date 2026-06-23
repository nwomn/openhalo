# Development Environment Workflow

## Default workflow

Default: work on a normal branch in the main workspace.

That is the normal path for day-to-day coding in this repository. Create or switch to a feature branch in the current workspace, and use the repository root interpreter so the branch shares one stable dependency set with the repository baseline.

Examples:

```bash
/root/personal-runtime-agent/.venv/bin/python -m unittest discover -s tests -v
```

```bash
bin/test -m unittest discover -s tests -v
```

## Optional worktree workflow

Advanced optional path: use a git worktree when you need parallel isolated tasks.

Worktrees are not the default workflow. Use one only when parallel isolation is worth the extra complexity, such as running a separate experiment beside your main branch work.

Optional: create a worktree-local `.venv`.

Use an isolated environment only when a worktree is intentionally changing dependency versions, trying a new library, or modifying packaging and installation behavior. In that case, keep the experiment local to that worktree instead of mutating the shared root environment first.

Create it explicitly:

```bash
bin/bootstrap-worktree-venv
```

Then use the local interpreter from that worktree:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Merge-back rule

Do not copy or diff `.venv` directories between a worktree and the main workspace.

If a dependency experiment succeeds, commit the source-of-truth file changes such as `pyproject.toml`, merge those changes, and then update the repository root `.venv` from the main workspace.

## Verification ladder

CLI device validation is acceptable for early module testing.

Use the existing desktop/CLI edge loop for the first pass when you want to confirm that a new runtime path, protocol shape, or state transition basically works.
Preferred command shape: `python -m device_edge.cli.cli_edge`

When you need to inspect the full M5 hot path as one human-readable chain, use:
Preferred command shape: `python -m device_edge.cli.cli_edge --inspect-chain --text "hello runtime"`

That inspection mode runs one local interaction and prints the chain in this order:

- trace
- normalized observations
- compact snapshot
- snapshot contract
- proposal
- presence decision
- recorded intervention

This is the fastest local way to confirm what the runtime actually consumed on the `normalized observations -> compact snapshot / snapshot contract -> Agent proposal -> Presence decision -> recorded intervention` chain without manually digging through multiple files.

That same inspection path is now also the first local `M9` acceptance surface for model-provider wiring.

For the first `M9` slice, inspect the `Proposal` section and confirm it contains:

- `llm_profile`
- `llm_provider`
- `llm_model`
- `used_deterministic_fallback`

Default local behavior should still work even without external credentials. In that case the proposal metadata should show deterministic fallback and the final user-facing message should remain the current local `"Runtime heard: ..."` reply style.

The repository now keeps a tracked default provider baseline in `config/llm-config.toml`.

When you want a machine-local override, create `.runtime/llm-config.toml`. The runtime prefers that local override when it exists and otherwise falls back to the tracked repository baseline.

When you want to test a real `openai_compatible` provider path later, keep the same command shape but provide:

- either `config/llm-config.toml` or a local `.runtime/llm-config.toml` override
- the provider auth env var referenced by that config, such as `OPENAI_API_KEY`

The acceptance command stays the same; only the provider result and fallback metadata should change.

That same inspection path is now also the first bounded local `M10` acceptance surface for grounding and runtime memory.

For the first `M10` slice, inspect the `Grounding Bundle` section and confirm it contains:

- compact snapshot state under `snapshot`
- one bounded `active_goals` list
- bounded `recent_memory` for user inputs, interventions, and action results
- bounded `edge_history` with `history_kind = "observation_window"`

Also inspect the `Proposal` metadata and confirm it contains:

- `grounding_bundle_version`
- `grounding_active_goal_count`
- `grounding_recent_user_inputs`
- `grounding_has_edge_history`

The current local `--inspect-chain` flow now exercises grounding through runtime-native state rather than raw input text alone: it seeds one active runtime goal, records recent runtime observations, performs one explicit bounded `runtime.edge_history` retrieval from the inspection host edge, and then prints the grounded proposal and recorded intervention in one report.

When you need to inspect the M6 initiative path as one human-readable chain, use:
Preferred command shape: `python -m device_edge.cli.cli_edge --inspect-agent-initiative`

That inspection mode runs one local initiative-triggered interaction and prints the chain in this order:

- trace
- normalized observations
- compact snapshot
- snapshot contract
- proposal
- presence decision
- recorded intervention
- action result

This is the fastest local way to confirm that a runtime-originated initiative now flows through the same `snapshot -> proposal -> Presence Router -> action` chain instead of depending on a direct-action bypass.

Host edge verification is required before documenting a module as implemented and operationally ready.

If a change is going to be described in project documentation as a completed module that is ready to run in the intended runtime environment, it must be verified through the host edge path we already built, not only through the CLI device path.
Preferred command shape: `python -m device_edge.host.host_daemon`

Use `bin/verify-host-edge` for the default bounded local host-edge verification run.

The script starts the runtime server, starts the host daemon with bounded idle, action-count, and session controls, verifies one targeted `runtime.status` direct action through the normal gateway path, verifies one runtime-originated initiative path to the same host edge through `Presence Router` and the normal action-planning path, then checks persisted runtime state before waiting for the host daemon to exit cleanly.

Use `bin/verify-host-edge --dry-run` first when you want to inspect the exact commands without starting processes.

Use `bin/verify-terminal-edge` for the bounded M8 terminal-edge acceptance path.

The terminal-edge verification path is intended to prove three user-facing terminal behaviors on the normal runtime chain:

- one pull-style terminal request
- one runtime push allow while terminal activity evidence is fresh
- one runtime push suppress after terminal idle evidence

Use `bin/verify-terminal-edge --dry-run` first when you want to inspect the exact runtime, terminal-daemon, push, and state-check commands without starting the acceptance run.

The current `M11` terminal/CLI maturity pass adds a thin edge-local UX layer on top of that same runtime path. The resident terminal daemon now keeps a bounded readable session transcript, prints explicit system/runtime/user line prefixes, and exposes a small local command set for human-friendly control without inventing a second backend path.

The first local command affordances are:

- `/help`
- `/status`
- `/history`
- `/quit`

Use them only for edge-local ergonomics:

- `/help` prints the available local commands
- `/status` prints a readable `Session status` line with connection, activity, counts, and pending-reply visibility
- `/history` prints the bounded recent session transcript
- `/quit` exits the resident terminal session cleanly

Those commands must stay local to the terminal edge. They should not be forwarded as normal `text.input` runtime events.

For a true live terminal session, start the runtime first and then run the resident terminal daemon in the foreground. In that mode the daemon keeps one websocket edge session open, reads user requests from `stdin`, emits fresh `terminal.activity_state` observations on the normal runtime path, and still handles runtime-pushed `notification.show` actions in the same session.

Preferred command shape:

```bash
python -m personal_runtime.main --host 127.0.0.1 --port 8765 --token dev-token
```

Preferred full-screen TUI mode:

```bash
python -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:8765 --token dev-token --tui
```

The new `--tui` mode uses a Textual full-screen UI as the preferred resident terminal surface. The first MVP intentionally keeps the same daemon/runtime protocol path while replacing the plain log stream with a fixed layout:

- a top status bar that remains visible while the session runs
- a scrollable transcript pane for `[system]`, `[user]`, and `[runtime]` lines
- a bottom input box for normal user text and local slash commands

See `docs/terminal-tui.md` for the dedicated TUI guide covering layout, status-bar semantics, local commands, exit behavior, and current limits.

Use the older non-TUI foreground command as the compatibility fallback when you need a plain line-oriented terminal session or when diagnosing UI-specific problems:

```bash
python -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:8765 --token dev-token
```

Type a line and press Enter to send a normal `text.input` event. Leave the terminal idle to let the daemon emit an idle observation. The bounded `bin/verify-terminal-edge` flow remains the preferred acceptance script when you want a repeatable proof run instead of manual `stdin` interaction.

For manual live-terminal acceptance, repeated explicit user input should continue to receive repeated replies in the same resident session. The current presence cooldown is intended to suppress repeated runtime-initiated user-facing interruption, not to suppress a user's own back-to-back terminal requests.

For the first manual `M11` acceptance pass, confirm all of these in one foreground session:

- startup prints readable `[system]` status lines instead of silent blocking
- typing normal text still produces normal runtime replies
- typing `/help` prints local command guidance without creating a runtime request
- typing `/status` prints a readable `Session status` line
- typing `/history` prints recent `[system]`, `[user]`, and `[runtime]` lines
- typing `/quit` exits the terminal edge cleanly

For the first manual full-screen Textual acceptance pass, confirm all of these in one `--tui` session:

- the app opens in a full-screen terminal layout instead of scrolling plain startup logs
- the status bar stays visible while connection, activity, and pending-reply state change
- the transcript pane grows without overwriting the input box
- the input box accepts both normal text and local slash commands
- `/quit` closes the session cleanly and exits the TUI without reconnect looping

For the current live-terminal baseline, a single `Ctrl+C` in the foreground terminal-daemon session should now terminate the CLI device cleanly during normal TTY use. If manual acceptance still requires repeated interrupt signals, treat that as a terminal-edge interaction regression rather than expected behavior.
