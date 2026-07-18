# Development Environment Workflow

## Default workflow

Default: work on a normal branch in the main workspace.

That is the normal path for day-to-day coding in this repository. Create or switch to a feature branch in the current workspace, and use the repository root interpreter so the branch shares one stable dependency set with the repository baseline.

Examples:

```bash
.venv/bin/python -m unittest discover -s tests -v
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

## Android edge local workflow

When working on the `M17` native Android `Device Edge`, keep the same checkout
open in both Codex and Android Studio, but let each tool own its normal layer:

- Open the repository root in Codex for project-wide context and non-Android
  code or documentation work.
- Open only `device_edge/android_edge/` in Android Studio for the native mobile
  app.
- Keep Python runtime and backend work on the repository root `.venv`; do not
  try to route Android Studio builds through the repository Python environment.
- Let Android Studio manage its own JDK, SDK, Gradle sync, device deployment,
  and Logcat workflow.

Preferred local Android verification ladder:

- Confirm the phone is visible before a run with `adb devices -l`.
- Wait for the first Android Studio Gradle sync to finish; the first sync may
  take noticeably longer because Android, Kotlin, and Compose dependencies are
  downloaded on demand.
- Use the Android Studio device selector to confirm the intended phone model is
  selected.
- Run the `app` configuration from Android Studio and expect the debug build to
  install and launch on the connected device.

The current verified baseline for this repository is that
`device_edge/android_edge/` syncs successfully, a USB-connected Android phone
is recognized through `adb`, and the debug app can be installed and launched on
real hardware.

Use `docs/android-edge-install.md` for the fuller Android Studio setup,
phone-preparation checklist, and local proxy-authentication notes.

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

When you need to inspect a long-running runtime without starting a new
interaction, use the read-only context viewer against the runtime state file:

```powershell
.\.venv\Scripts\python.exe -m personal_runtime.context_viewer --state-path .runtime\android-openai-dev-state.json --diagnostic-log-path .runtime\android-openai-dev-diagnostics.jsonl --watch
```

On Linux or the server, the wrapper form is:

```bash
bin/runtime-context-viewer --state-path .runtime/state.json --diagnostic-log-path .runtime/runtime-diagnostics.jsonl --watch
```

The viewer does not modify runtime state or the hot path. It reads the persisted
state JSON and optional diagnostic JSONL, then shows the context surface that is
relevant to what the agent can see now or most recently saw:

- latest accepted ingress events so edge uploads can be verified
- latest normalized runtime observations so observation ingestion can be verified
- current agent-visible compact snapshot and evidence contract
- only the observations that currently participate in snapshot evidence
- latest agent turn summary, snapshot contract, and prompt/context package

### M18 offline admission replay

To review whether M18 noticed the right observation points without contacting a
model provider or dispatching an action, replay a persisted state file through
only the deterministic admission gate and Interaction Pool:

```bash
.venv/bin/python -m personal_runtime.m18_replay_cli --state .runtime/state.json
```

The command is read-only: it reconstructs observations chronologically in
memory, groups a shared source event as one ingress batch, and reports every
`skip`, `defer`, and `trigger` decision with safe evidence references and causal
scope. It never starts an Android build, calls a provider, or dispatches an
action. Use the report with reviewer labels for points that deserved attention
and points that should remain silent.

This is the preferred way to confirm whether a live edge observation, such as
`mobile.screen_context`, reached the runtime, how it was normalized, and whether
it is currently represented in compact snapshot evidence. A standalone
`mobile.screen_context` observation remains passive by default and the M18 Gate
may defer it, while its allowlisted structural signals can contribute as
sanitized context evidence after another M18 trigger has been admitted.

For a long-running server runtime, run the viewer directly on the server against
the supervised runtime's persisted state and diagnostic log. The current
Alibaba Cloud deployment uses:

```bash
ssh aliyun_server
cd /root/openhalo
.venv/bin/python -m personal_runtime.context_viewer \
  --state-path /var/lib/openhalo/runtime-state.json \
  --diagnostic-log-path /var/log/openhalo/runtime-diagnostics.jsonl \
  --limit 80
```

From the local Windows development machine, `aliyun_server` is the expected SSH
alias in the user-level SSH config. It points at the Alibaba Cloud host
`8.153.37.167` as `root` with the local private key configured outside this
repository. Prefer the alias over spelling out the host, user, or key path in
project commands.

For a one-shot remote check without opening an interactive shell:

```bash
ssh aliyun_server "cd /root/openhalo && .venv/bin/python -m personal_runtime.context_viewer --state-path /var/lib/openhalo/runtime-state.json --diagnostic-log-path /var/log/openhalo/runtime-diagnostics.jsonl --limit 80"
```

Use this as the manual observation-acceptance loop:

1. Run the viewer once to record `generated_at`, recent counts, and the latest
   observations before the user action.
2. Perform the real edge action on the device, such as opening a normal Android
   app, scrolling, locking the phone, or turning the screen off.
3. Run the viewer again and compare the newest `observed_at` timestamps against
   `generated_at`. Fresh evidence should usually be seconds old during active
   foreground use.
4. Inspect `Latest Accepted Ingress Events` to prove the Gateway accepted the
   uploaded frame from the expected `device_id` and capability.
5. Inspect `Latest Normalized Observations` to prove runtime ingestion stored
   the observation with the expected name, source, value fields, confidence, and
   passive/snapshot status.
6. Inspect `Current Snapshot Evidence Only` and the latest prompt/context
   package to confirm whether the observation is agent-visible now. For M17.5,
   `mobile.screen_context` should remain stored passive evidence and may show
   `in_current_snapshot_evidence: false`.
7. If the output is too large, save a local or server-side snapshot and review
   the bounded latest sections rather than the entire raw state file.

For M17.5 Android screen-context acceptance, pass criteria in the viewer are:

- the latest accepted ingress event comes from the expected Android device,
  such as `android-edge-782d0247`, with capability `mobile.screen_context`
- normal unlocked app use produces `mobile.screen_context` with
  `capture_mode=accessibility_tree`, bounded `visible_text_summary`, optional
  `interactive_elements`, and `raw_screenshot_uploaded=false`
- locked or screen-off states produce health-only evidence such as
  `mobile.screen_capture_health` or a health-only screen-context observation
  with `capture_pause_reason=locked` or `screen_off`
- high-frequency activity may produce health-only throttling observations with
  `capture_pause_reason=throttled`
- the current compact snapshot and prompt context do not treat M17.5 screen
  observations as direct user intent

Sensitive banking/payment/login screen governance is deliberately not accepted
through M17.5. If viewer evidence shows sensitive app text reaching
`mobile.screen_context`, record it as M17.8 evidence rather than reopening
M17.5, because M17.8 owns the allowlist-first sensitive-screen capture model.

The default view omits historical/offline device registry noise and diagnostic
tail entries, but keeps recent ingress and normalized observations visible
because those are the operator-facing proof that an edge upload reached the
runtime. Use `--debug-history` only when a future debug-only persisted history
section is needed.

That same inspection path is now also the first local `M9` acceptance surface for model-provider wiring.

For the first `M9` slice, inspect the `Proposal` section and confirm it contains:

- `llm_profile`
- `llm_provider`
- `llm_model`
- `used_deterministic_fallback`

Default runtime model behavior now comes from the local `config/runtime-config.toml` file. Real-use profiles in that file surface provider failures explicitly, while bounded test fixtures may still opt into deterministic fallback for offline verification.

The repository keeps a tracked template in `config/runtime-config.example.toml`; copy that shape to the ignored local `config/runtime-config.toml` for real provider use.

When you want to use a non-default provider config, pass it explicitly with `--runtime-config-path` instead of relying on an implicit local override file. The older `--llm-config-path` spelling remains a compatibility alias.

The local default `config/runtime-config.toml` is currently aligned with the
official OpenAI provider configuration. Keep its OpenAI API key only in that
ignored local file; do not add it to the tracked template or a worktree command.

When you want to test a real `openai_compatible` provider path later, keep the same command shape but provide:

- either the local `config/runtime-config.toml` or an explicit `--runtime-config-path /abs/path/to/runtime-config.toml`
- the provider `api_key` inside that runtime config

The acceptance command stays the same; only the provider result and fallback metadata should change.

Before starting the full live path, run the provider probe:

```bash
bin/verify-model-provider
```

To probe the current OpenAI default explicitly:

```bash
bin/verify-model-provider --runtime-config-path config/runtime-config.toml
```

Acceptance requires `ok: true`. If the first structured-output request hits a
`codex_agent_envelope_empty_output` shape and the probe recovers with
`request_format: "prompt_json"`, that is an accepted recovery path. If the
probe reports `ok: false`, keep the `failure_class`, `response_shape`,
`request_format`, `retried_shapes`, and `latency_ms` fields for diagnosis before
continuing.

When running a full regression pass, also check line coverage with `coverage.py`
and compare it against the current baseline. Install `coverage` into the shared
root `.venv` if it is missing, then run:

```bash
.venv/bin/python -m coverage run --source=personal_runtime,device_edge,agent_guard -m unittest -v
.venv/bin/python -m coverage report
```

The current formal line-coverage baseline is 87% over `personal_runtime`,
`device_edge`, and `agent_guard` after 288 passing unittest cases. Treat that
number as a watch baseline rather than a hard gate for now: meaningful drops,
especially in `Gateway`, `Agent Runtime`, `Presence Router`, model-provider,
host-edge, or terminal-edge paths, should be called out in the verification
summary. Low-coverage modules should be listed when relevant so follow-up tests
can be prioritized.

For real-use terminal acceptance with the current runtime-config baseline, use
two long-running processes. The Runtime manages its colocated Host Edge by
default after the Gateway is listening, so the development runtime should use
port `18765` while the long-running server runtime keeps port `8765`; see
`docs/runtime-deploy.md` for the systemd-backed server path.

```bash
OPENHALO_DEV_RUNTIME_HOST=127.0.0.1 bin/run-runtime-dev
```

`bin/run-runtime-dev` now reads `config/runtime-config.toml` by default, which
is the local OpenAI configuration for this development environment. Override
`OPENHALO_DEV_RUNTIME_CONFIG_PATH` only for a separate provider configuration;
an ignored `config/runtime-config.openai-local.toml` is not assumed to exist in
every worktree. Override `OPENHALO_DEV_STATE_PATH` when separate runs need
separate evidence.

```bash
.venv/bin/python -m device_edge.cli.terminal_daemon \
  --url ws://127.0.0.1:18765 \
  --token dev-token \
  --device-id terminal-edge-1
```

Use `--host-edge-idle-timeout 30` on the Runtime command to control the
managed Host Edge observation interval. `--disable-host-edge` is reserved for
isolated fixtures or deployments that deliberately cannot run a colocated edge.

Expected real-use smoke path:

- `你好？` should produce a normal model-backed Chinese reply
- `check runtime status` should route to the host edge and return runtime status
- a follow-up context question should not crash the terminal edge with WebSocket
  `1011` keepalive timeout
- `谢谢` or another closing acknowledgement should either receive a natural
  short reply or close quietly without disconnecting the session

Acceptance passes when:

- `bin/verify-model-provider` reports `ok: true`
- the terminal edge connects to the runtime and stays connected through the
  interaction sequence
- the host edge receives and executes the `runtime.status` action
- the Chinese dialogue path uses the configured model provider rather than the
  local deterministic `Runtime heard: ...` fallback
- any recovered `codex_agent_envelope_empty_output` is visible through
  `retried_shapes` plus a final successful request format, rather than being
  hidden or reported as a credential failure

For the bounded `M17.1` registration-driven multi-device acceptance path, use:

```bash
bin/verify-m17-1-registration-extension --dry-run
bin/verify-m17-1-registration-extension
```

The dry run lists the scenario checkpoints before execution. The live run
simulates a terminal source edge, a phone notification edge, a public speaker
edge, and an ambient desk-light edge through public Edge API frames.

Acceptance passes when the output shows registered devices, registered
capabilities, registered observations, one accepted registered observation,
strict observation rejection for an unregistered observation, phone notification
as the planner-selected action, and planner selection rationale that explains
why the public audio and ambient light candidates were rejected.

Known residual real-provider behavior:

- Occasional provider/relay errors may still surface as explicit runtime replies
  such as `Real model reply unavailable: ...`
- A single surfaced provider error is not a credential failure when
  `bin/verify-model-provider` still reports `ok: true` and
  `auth_source: runtime_config`
- Repeated `codex_agent_envelope_empty_output`, HTTP 5xx, timeout, or parser
  failures should be treated as provider/relay stability evidence and captured
  with the provider metadata from the latest recorded intervention
- The current accepted relay model baseline is `gpt-5.5`; `gpt-5.4` is not the
  terminal live-path baseline because it can return a Codex-agent envelope once
  compact snapshot fields are present
- A real-use comparison with an ignored official OpenAI local config showed
  faster and more stable `gpt-5.5` responses than the current relay baseline;
  that supports treating intermittent `codex_agent_envelope_empty_output`
  results as provider/relay compatibility evidence rather than an M15
  runtime-config or credential-resolution blocker

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

Use `bin/verify-action-loop` for the bounded M16 post-action action-loop acceptance path.

Use `bin/verify-action-loop --dry-run` first when you want to inspect the scripted checks without running them. The acceptance run exercises a `runtime.status` result that re-enters `Agent Runtime` and produces a governed follow-up reply, a fresh observation that re-enters the same open interaction and plans a follow-up action, a post-action result that plans another follow-up action in the same interaction, and a delivered notification result that completes silently while preserving `post_action` and `post_observation` intervention lineage.

For real model-backed M16 acceptance, first run `bin/verify-model-provider --runtime-config-path config/runtime-config.toml`, then run `bin/verify-action-loop --runtime-config-path config/runtime-config.toml --require-model-backed`. The model-backed run must show `model-backed-post-action ok`, proving the post-action proposal came from provider-backed proposal formation rather than deterministic formatting.

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
Preferred M4.1 command shape: start `bin/run-runtime-dev` and let it manage
the loopback Host Edge. `.venv/bin/python -m device_edge.host.host_daemon`
remains an edge-development diagnostic entrypoint, not the normal deployment
operation.

Use `bin/verify-host-edge` for a bounded standalone Host Edge diagnostic run.

The existing script remains a bounded standalone-edge diagnostic. M4.1 normal
acceptance instead starts only Runtime plus a source edge, verifies automatic
Host Edge registration, and routes `runtime.status` through the public Edge API.

Use `bin/verify-host-edge --dry-run` first when you want to inspect the exact commands without starting processes.

Use `bin/verify-terminal-edge` for the bounded M8 terminal-edge acceptance path.

The terminal-edge verification path is intended to prove three user-facing terminal behaviors on the normal runtime chain:

- one pull-style terminal request
- one runtime push allow while terminal activity evidence is fresh
- one runtime push suppress after terminal idle evidence

Use `bin/verify-terminal-edge --dry-run` first when you want to inspect the exact runtime, terminal-daemon, push, and state-check commands without starting the acceptance run.

For a formal live acceptance scenario that matches current intended use, run
the Runtime and one source edge together:

1. Start the runtime:

   ```bash
   OPENHALO_DEV_RUNTIME_HOST=127.0.0.1 \
   OPENHALO_DEV_STATE_PATH=.runtime/manual-acceptance-state.json \
   bin/run-runtime-dev
   ```

2. Start the terminal edge in a second terminal:

   ```bash
   .venv/bin/python -m device_edge.cli.terminal_daemon \
     --url ws://127.0.0.1:18765 \
     --token dev-token \
     --device-id terminal-edge-1
   ```

3. In the terminal edge, send normal user text such as `你好`, `你是谁？`, and `check runtime status`.

Acceptance expectations:

- normal dialogue returns natural user-facing text instead of provider/parser errors such as `Real model reply unavailable`
- `check runtime status` forms a `runtime.status` action, routes it to `host-edge-1`, and returns a readable status summary to the terminal edge
- Runtime state shows the managed `host-edge-1` connection and completed `runtime.status` action request
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
OPENHALO_DEV_RUNTIME_HOST=127.0.0.1 bin/run-runtime-dev
```

Preferred full-screen TUI mode:

```bash
.venv/bin/python -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:18765 --token dev-token --tui
```

The new `--tui` mode uses a Textual full-screen UI as the preferred resident terminal surface. The first MVP intentionally keeps the same daemon/runtime protocol path while replacing the plain log stream with a fixed layout:

- a top status bar that remains visible while the session runs
- a scrollable transcript pane for `[system]`, `[user]`, and `[runtime]` lines
- a bottom input box for normal user text and local slash commands

See `docs/terminal-tui.md` for the dedicated TUI guide covering layout, status-bar semantics, local commands, exit behavior, and current limits.

The TUI draft-input signal is also part of the idle-sensing behavior: a nonempty draft should wake the daemon's idle wait and be sent before a fresh `terminal.activity_state=idle` observation, so active typing is not immediately reported as terminal idle.

Use the older non-TUI foreground command as the compatibility fallback when you need a plain line-oriented terminal session or when diagnosing UI-specific problems:

```bash
.venv/bin/python -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:18765 --token dev-token
```

Type a line and press Enter to send a normal `text.input` event. Leave the terminal idle to let the daemon emit an idle observation. The bounded `bin/verify-terminal-edge` flow remains the preferred acceptance script when you want a repeatable proof run instead of manual `stdin` interaction.

For manual live-terminal acceptance, repeated explicit user input should continue to receive repeated replies in the same resident session. The current presence cooldown is intended to suppress repeated runtime-initiated user-facing interruption, not to suppress a user's own back-to-back terminal requests.

For the current manual `M11` acceptance bar, prefer one real user-scenario foreground session instead of isolated command pokes:

1. Start the runtime with `OPENHALO_DEV_RUNTIME_HOST=127.0.0.1 bin/run-runtime-dev`; it starts `host-edge-1` automatically.
2. Start the terminal surface with `.venv/bin/python -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:18765 --token dev-token --tui`.
3. Send `hello runtime`.
   Expectation: the session shows both `[user] hello runtime` and one real `[runtime] ...` reply line on the same resident session.
4. Send `check runtime status`.
   Expectation: the session shows a readable runtime-delivered status response from the host edge rather than suppressing delivery after the user text arrives.
5. Send `/status` and `/history`.
   Expectation: both stay edge-local, the transcript remains readable, and no extra runtime request is created for those slash commands.
6. Send `/quit`.
   Expectation: the TUI exits cleanly without a reconnect loop.

If you need the plain compatibility path instead of the TUI, run `.venv/bin/python -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:18765 --token dev-token` and apply the same user-scenario expectations to the line-oriented transcript.

For the current live-terminal baseline, a single `Ctrl+C` in the foreground terminal-daemon session should now terminate the CLI device cleanly during normal TTY use. If manual acceptance still requires repeated interrupt signals, treat that as a terminal-edge interaction regression rather than expected behavior.

## M20 Hermes Harness acceptance

M20 uses Hermes as the internal harness loop while OpenHalo continues to govern
all user-visible and side-effectful action intents. Hermes-native
`MEMORY.md`/`USER.md` are the durable memory store; OpenHalo keeps only hashes,
scope/session references, and replay provenance.

Before a real research acceptance run, configure an operator-approved public
search endpoint and hosts in local `config/runtime-config.toml`:

```toml
[harness]
runner = "hermes"

[harness.hermes]
# Keep the verifier's default fetch/hostile fixtures, or override both URLs
# below with operator-controlled HTTPS URLs that match this allowlist.
allowed_hosts = ["example.com", "httpbingo.org", "research.example.net"]
search_url_template = "https://research.example.net/search?q={query}"
```

`search_url_template` must contain `{query}`, and every URL used by the
verifier must match the explicit `allowed_hosts` policy. The verifier defaults
to `https://example.com/` for fetch and an `httpbingo.org` hostile fixture, so
keep those hosts in the allowlist when using its default URLs. Otherwise pass
matching `--research-url`, `--hostile-research-url`, and
`--hostile-content-sha256` values. Replace `research.example.net` with the
operator-approved public search endpoint and include any redirect hosts it
requires. M20 uses direct bounded HTTPS fetch/search and does not require
Chromium, a browser process, or a desktop GUI. Browser-backed rendering is
deferred to a later hardening item.

Run the deterministic gate first, then the configured-provider run:

```bash
bin/verify-m20-harness --runtime-config-path config/runtime-config.toml
bin/verify-m20-harness --live --runtime-config-path config/runtime-config.toml
```

The live run verifies a governed action, fetch, search, a research-assisted
reply that remains Presence-governed, hostile-content source governance, and
cross-session Hermes-memory recall. The recall is displayed back to the
requesting terminal through a low-risk governed `notification.show` action,
then completes through the normal post-action path; it must not issue research
or another memory write. Remote content is recorded as untrusted; it cannot
authorize an action or memory write by itself. It writes only sanitized
evidence to `.runtime/m20-harness-live-evidence.json`; each new evidence file
requires human review before it is used to change milestone status, and the
recorded M20 acceptance has already undergone that review. Positive fetch/search
runs verify the real provider/network path. The hostile-page run may record its fixture hash or
safely decline the fetch without side effects; deterministic forced action and
injected-memory tests are the separate enforcement proof, so a model merely
ending silently is not accepted as a security-boundary claim. M20 uses
autonomous native memory only in normal audited turns; re-entry turns retain
read context but receive no native `memory` write tool. Hermes periodic
background review remains disabled.
