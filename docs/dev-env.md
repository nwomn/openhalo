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
Preferred command shape: `.venv/bin/python -m device_edge.cli.cli_edge`

When you need to inspect the full M5 hot path as one human-readable chain, use:
Preferred command shape: `.venv/bin/python -m device_edge.cli.cli_edge --inspect-chain --text "hello runtime"`

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

Default tracked behavior now comes from `config/llm-config.toml`. Real-use profiles in that file surface provider failures explicitly, while bounded test fixtures may still opt into deterministic fallback for offline verification.

The repository now keeps a tracked default provider baseline in `config/llm-config.toml`.

When you want to use a non-default provider config, pass it explicitly with `--llm-config-path` instead of relying on an implicit local override file.

When you want to test a real `openai_compatible` provider path later, keep the same command shape but provide:

- either the tracked `config/llm-config.toml` baseline or an explicit `--llm-config-path /abs/path/to/llm-config.toml`
- the provider auth env var referenced by that config, such as `CRS_OAI_KEY`

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

That same inspection path is now also the first bounded local `M12` acceptance surface for prompt/context engineering and behavior-contract verification.

Use:
Preferred command shape: `.venv/bin/python -m device_edge.cli.cli_edge --inspect-prompt-contract --text "hello runtime"`

For the first `M12` slice, inspect these sections in the printed report:

- `Prompt Context`
- `Behavior Contract`
- `Replay Eval`

Confirm the prompt/context section shows:

- an explicit prompt/context version
- `compact_snapshot`
- `active_goals`
- `recent_memory`
- `edge_evidence`

Confirm the behavior contract shows passing checks for:

- compact snapshot presence
- active goals presence
- recent memory presence
- edge evidence presence
- grounding bundle version match

Confirm the replay/eval section reports a passing re-check of the recorded prompt/context package without requiring a second provider call.

Use `bin/verify-prompt-contract` for the default bounded M12 prompt/context acceptance path.

Use `bin/verify-prompt-contract --dry-run` first when you want to inspect the exact inspect-chain, prompt/context, behavior contract, replay/eval, and state-summary commands without running the acceptance pass.

That same local inspection surface is now also the bounded `M13` acceptance path for proposal-formation maturity.

Use:
Preferred command shape: `.venv/bin/python -m device_edge.cli.cli_edge --inspect-chain --text "hello runtime"`

For the first `M13` slice, inspect the `Proposal` section and confirm it now exposes:

- `proposal_type`
- `proposal_rationale`
- grounded metadata such as prompt/context and runtime memory carry-through
- the final action capability or intentional lack of action when the result is `no_intervention`

The accepted M13 taxonomy is:

- `reply`
- `action`
- `clarification`
- `no_intervention`

Use `bin/verify-proposal-formation` for the default bounded M13 proposal-formation acceptance path.

Use `bin/verify-proposal-formation --dry-run` first when you want to inspect the four scenario commands behind that acceptance run:

- one `reply`
- one `action`
- one `clarification`
- one `no_intervention`

The M13 acceptance expectation is that each scenario prints readable proposal rationale and that `no_intervention` records a proposal on the live chain without dispatching a user-facing action.

Use `bin/verify-model-provider` for the bounded M14 model-provider acceptance path.

Use `bin/verify-model-provider --dry-run` first when you want to inspect the provider-probe, controlled failure, and model-health checks without calling the configured provider. The provider-probe prints a non-secret JSON report covering the selected profile, provider, model, endpoint, auth-env presence, wire API, response shape, latency, and failure class when applicable. The controlled failure check exercises a bad response-shape path, and the model-health check verifies that provider status can be persisted into runtime state.

When you need to inspect the M6 initiative path as one human-readable chain, use:
Preferred command shape: `.venv/bin/python -m device_edge.cli.cli_edge --inspect-agent-initiative`

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
Preferred command shape: `.venv/bin/python -m device_edge.host.host_daemon`

Use `bin/verify-host-edge` for the default bounded local host-edge verification run.

The script starts the runtime server, starts the host daemon with bounded idle, action-count, and session controls, verifies one targeted `runtime.status` direct action through the normal gateway path, verifies one runtime-originated initiative path to the same host edge through `Presence Router` and the normal action-planning path, then checks persisted runtime state before waiting for the host daemon to exit cleanly.

Use `bin/verify-host-edge --dry-run` first when you want to inspect the exact commands without starting processes.

Use `bin/verify-terminal-edge` for the bounded M8 terminal-edge acceptance path.

The terminal-edge verification path is intended to prove three user-facing terminal behaviors on the normal runtime chain:

- one pull-style terminal request
- one runtime push allow while terminal activity evidence is fresh
- one runtime push suppress after terminal idle evidence

Use `bin/verify-terminal-edge --dry-run` first when you want to inspect the exact runtime, terminal-daemon, push, and state-check commands without starting the acceptance run.

For a formal live acceptance scenario that matches current intended use, run all three long-lived participants together:

1. Start the runtime:

   ```bash
   .venv/bin/python -m personal_runtime.main \
     --host 127.0.0.1 \
     --port 8765 \
     --token dev-token \
     --state-path .runtime/manual-acceptance-state.json
   ```

2. Start the host edge in a second terminal:

   ```bash
   .venv/bin/python -m device_edge.host.host_daemon \
     --url ws://127.0.0.1:8765 \
     --token dev-token \
     --device-id host-edge-1 \
     --runtime-process-match personal_runtime.main \
     --runtime-start-command ".venv/bin/python -m personal_runtime.main" \
     --idle-timeout 5 \
     --trace
   ```

3. Start the terminal edge in a third terminal:

   ```bash
   .venv/bin/python -m device_edge.cli.terminal_daemon \
     --url ws://127.0.0.1:8765 \
     --token dev-token \
     --device-id terminal-edge-1
   ```

4. In the terminal edge, send normal user text such as `你好`, `你是谁？`, and `check runtime status`.

Acceptance expectations:

- normal dialogue returns natural user-facing text instead of provider/parser errors such as `Real model reply unavailable`
- `check runtime status` forms a `runtime.status` action, routes it to `host-edge-1`, and returns a readable status summary to the terminal edge
- host-edge trace shows handling and completing the `runtime.status` action request
- persisted runtime state contains both `terminal-edge-1` and `host-edge-1`, host observations, and at least one `runtime.status` action result

The host edge receive loop must preserve action requests that arrive while it is waiting for observation acknowledgements. If `check runtime status` remains planned in state but never completes while host observations continue, treat that as a host-edge receive-loop regression.

## Model-provider bad-shape recurrence workflow

If the terminal/model path starts returning provider-shape failures again, preserve evidence before cleaning state or restarting into a fresh acceptance run.

Do not delete `.runtime` first. Stop the runtime and terminal edge, then back up the current state:

```bash
cp .runtime/state.json .runtime/state.bad.$(date +%s).json
```

Capture the provider metadata already recorded in runtime state:

```bash
rg -n "provider_failure_shape|provider_retried_shapes|provider_attempt_count|provider_retry_count|provider_failure_reason|llm_profile|llm_provider|llm_model|grounding_recent" .runtime/state.json
```

Capture recent persisted runtime memory separately so the investigation can tell whether the request was influenced by old user input, interventions, or action results:

```bash
rg -n "Real model reply unavailable|recent_memory|action_results|interventions|text.input" .runtime/state.json
```

Only after that evidence is preserved, run a clean-state comparison. Either move `.runtime` aside or delete it intentionally:

```bash
mv .runtime .runtime.bad-preserved
```

Then restart the runtime on the default state path and repeat the same terminal prompts. If the clean run succeeds, keep both the bad-state backup and clean-state result. If the clean run also fails, treat the provider route or model contract as the primary suspect rather than persisted-state pollution.

The current provider follow-up diagnosis is that clearing `.runtime` restored stable natural-language replies, but a minimal reconstructed pollution state did not reproduce the bad response shape. After the proposal path moved to Responses `json_schema` structured output, manual host-edge acceptance was broadly stable: normal dialogue recovered, `check runtime status` and a later Chinese runtime-status request formed `runtime.status` actions, and later turns did not remain polluted. One prompt still returned a single `codex_agent_envelope_empty_output` under `provider_wire_api=responses` and `provider_request_format=json_schema`, so future work should treat this as an occasional provider bad-shape failure unless new evidence shows persistent state corruption.

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

For a true live terminal session, start the runtime first and then run the resident terminal daemon in the foreground. In that mode the daemon keeps one websocket edge session open, reads user requests from `stdin`, emits fresh `terminal.activity_state` observations on the normal runtime path, and still handles runtime-pushed `notification.show` actions in the same session. In Textual TUI mode, draft input changes are also sent as `terminal.input_state` and `terminal.input_draft_length` observations so foreground typing can be observed before a line is submitted.

Preferred command shape:

```bash
.venv/bin/python -m personal_runtime.main --host 127.0.0.1 --port 8765 --token dev-token
```

Preferred full-screen TUI mode:

```bash
.venv/bin/python -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:8765 --token dev-token --tui
```

The new `--tui` mode uses a Textual full-screen UI as the preferred resident terminal surface. The first MVP intentionally keeps the same daemon/runtime protocol path while replacing the plain log stream with a fixed layout:

- a top status bar that remains visible while the session runs
- a scrollable transcript pane for `[system]`, `[user]`, and `[runtime]` lines
- a bottom input box for normal user text and local slash commands

See `docs/terminal-tui.md` for the dedicated TUI guide covering layout, status-bar semantics, local commands, exit behavior, and current limits.

The TUI draft-input signal is also part of the idle-sensing behavior: a nonempty draft should wake the daemon's idle wait and be sent before a fresh `terminal.activity_state=idle` observation, so active typing is not immediately reported as terminal idle.

Use the older non-TUI foreground command as the compatibility fallback when you need a plain line-oriented terminal session or when diagnosing UI-specific problems:

```bash
.venv/bin/python -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:8765 --token dev-token
```

Type a line and press Enter to send a normal `text.input` event. Leave the terminal idle to let the daemon emit an idle observation. The bounded `bin/verify-terminal-edge` flow remains the preferred acceptance script when you want a repeatable proof run instead of manual `stdin` interaction.

For manual live-terminal acceptance, repeated explicit user input should continue to receive repeated replies in the same resident session. The current presence cooldown is intended to suppress repeated runtime-initiated user-facing interruption, not to suppress a user's own back-to-back terminal requests.

For the current manual `M11` acceptance bar, prefer one real user-scenario foreground session instead of isolated command pokes:

1. Start the runtime with `.venv/bin/python -m personal_runtime.main --host 127.0.0.1 --port 8765 --token dev-token`.
2. Start the host edge with `.venv/bin/python -m device_edge.host.host_daemon --url ws://127.0.0.1:8765 --token dev-token --device-id host-edge-1 --runtime-process-match personal_runtime.main --runtime-start-command ".venv/bin/python -m personal_runtime.main" --idle-timeout 5 --trace`.
3. Start the terminal surface with `.venv/bin/python -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:8765 --token dev-token --tui`.
4. Send `hello runtime`.
   Expectation: the session shows both `[user] hello runtime` and one real `[runtime] ...` reply line on the same resident session.
5. Send `check runtime status`.
   Expectation: the session shows a readable runtime-delivered status response from the host edge rather than suppressing delivery after the user text arrives.
6. Send `/status` and `/history`.
   Expectation: both stay edge-local, the transcript remains readable, and no extra runtime request is created for those slash commands.
7. Send `/quit`.
   Expectation: the TUI exits cleanly without a reconnect loop.

If you need the plain compatibility path instead of the TUI, run `.venv/bin/python -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:8765 --token dev-token` and apply the same user-scenario expectations to the line-oriented transcript.

For the current live-terminal baseline, a single `Ctrl+C` in the foreground terminal-daemon session should now terminate the CLI device cleanly during normal TTY use. If manual acceptance still requires repeated interrupt signals, treat that as a terminal-edge interaction regression rather than expected behavior.
