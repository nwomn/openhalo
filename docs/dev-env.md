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

For a true live terminal session, start the runtime first and then run the resident terminal daemon in the foreground. In that mode the daemon keeps one websocket edge session open, reads user requests from `stdin`, emits fresh `terminal.activity_state` observations on the normal runtime path, and still handles runtime-pushed `notification.show` actions in the same session.

Preferred command shape:

```bash
python -m personal_runtime.main --host 127.0.0.1 --port 8765 --token dev-token
```

```bash
python -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:8765 --token dev-token
```

Type a line and press Enter to send a normal `text.input` event. Leave the terminal idle to let the daemon emit an idle observation. The bounded `bin/verify-terminal-edge` flow remains the preferred acceptance script when you want a repeatable proof run instead of manual `stdin` interaction.

For manual live-terminal acceptance, repeated explicit user input should continue to receive repeated replies in the same resident session. The current presence cooldown is intended to suppress repeated runtime-initiated user-facing interruption, not to suppress a user's own back-to-back terminal requests.
