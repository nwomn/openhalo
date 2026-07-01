# M13 Proposal Formation Maturity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the first accepted `M13` slice so the live runtime can turn ordinary edge-delivered signals plus grounded runtime context into inspectable `reply`, `action`, `clarification`, and `no_intervention` proposals on the normal chain without bypassing `Presence Router`.

**Architecture:** Keep the documented hot path unchanged: `event -> compact snapshot -> grounding bundle -> prompt/context package -> proposal formation -> Presence Router -> execution planning/action`. Treat `M13` as an `Agent Runtime` maturity pass on top of the accepted `M12` baseline: proposal formation becomes multi-type and rationale-rich, but proposal typing still lives inside the existing `agent_executor`, provider boundary, inspection surfaces, and action planner rather than introducing a new top-level interpretation subsystem.

**Tech Stack:** Python 3.11 standard library, `unittest`, existing gateway/local inspection surfaces, existing provider boundary, existing host/terminal inspection helpers, bash verification scripts, project docs

## Follow-on Design Note After The First Accepted Slice

The accepted first `M13` slice should not be mistaken for the final interaction-semantics shape.

Follow-on work should let proposal formation move from one-shot text classification toward an interaction-lifecycle view that can:

- distinguish passive observation evidence from explicit user intent
- recognize approved user-configured triggers that promote otherwise passive observations into actionable intent
- infer whether one or more observations together constitute an interaction
- classify that interaction as `pull`, `push`, `background`, or `silent`
- suggest candidate participant surfaces, visibility intent, and the current `primary action`
- preserve requester-facing acknowledgement or result-reporting semantics when an explicit command also requires a remote edge action

Those outputs remain model-suggested candidates. `Presence Router` should keep final governance authority over what may actually appear on which device or surface at decision time.

The first implementation may still dispatch only one `primary action` per planning turn, but the data shape should stay compatible with later multi-turn `action loop` execution where action results or fresh observations trigger reproposal inside the same interaction lifecycle.

### Task 1: Lock the M13 proposal taxonomy with failing tests

**Files:**
- Modify: `tests/test_model_provider.py`
- Modify: `tests/test_gateway_v0.py`
- Modify: `tests/test_chain_inspection.py`
- Modify: `tests/test_roundtrip_v0.py`

**Step 1: Write the failing tests**

Add coverage that proves:
- ordinary `text.input` events can now yield all four accepted proposal classes on the normal live chain: `reply`, `action`, `clarification`, and `no_intervention`
- proposal metadata records structured rationale, confidence/fallback markers, and grounded context usage instead of only reply-generation metadata
- ambiguous or underspecified user input yields `clarification` or `no_intervention` rather than always collapsing to `notification.show`
- host/runtime-oriented requests expressed through normal user text can become `runtime.status` action proposals on the normal path instead of requiring only direct-action or agent-initiative entry

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_model_provider tests.test_gateway_v0 tests.test_chain_inspection tests.test_roundtrip_v0 -v
```

Expected: FAIL because the current runtime still reduces normal user text to one narrow reply-shaped proposal and does not expose the full M13 proposal taxonomy.

### Task 2: Implement multi-type proposal planning behind the provider boundary

**Files:**
- Modify: `personal_runtime/model_provider.py`
- Modify: `personal_runtime/agent_executor.py`
- Modify: `config/llm-config.toml`
- Modify: `tests/fixtures/llm-config-test.toml`

**Step 1: Add a proposal-plan representation**

Implement a small provider-facing plan/result type for normal text proposal formation that can carry:
- proposal class
- user-facing reply text when applicable
- action capability/payload when applicable
- clarification question when applicable
- no-intervention reason when applicable
- structured rationale metadata plus deterministic fallback markers

**Step 2: Add model-backed and deterministic proposal planning**

Extend the existing provider boundary so:
- normal text proposal formation requests use a dedicated M13 proposal profile
- the model-facing request explicitly asks for one bounded structured proposal outcome
- the runtime still falls back deterministically when the provider is unavailable
- deterministic fallback uses grounded heuristics only as a narrow backup and keeps rationale metadata inspectable

**Step 3: Run focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_model_provider -v
```

Expected: PASS

### Task 3: Thread M13 proposal classes through the live runtime chain

**Files:**
- Modify: `personal_runtime/agent_executor.py`
- Modify: `personal_runtime/action_layer.py`
- Modify: `personal_runtime/gateway_server.py`
- Modify if needed: `personal_runtime/presence_router.py`

**Step 1: Map normal text into the accepted proposal taxonomy**

Update the normal proposal builder so:
- `reply` proposals still surface through `notification.show`
- `action` proposals can target narrow accepted runtime actions such as `runtime.status`
- `clarification` proposals surface as user-facing clarification messages on the same normal action path
- `no_intervention` proposals are recorded, pass through `Presence Router`, and intentionally stop before action dispatch

**Step 2: Preserve the hot-path shape**

Keep the live chain lean by:
- reusing the existing prompt/context package and grounding bundle
- recording the chosen proposal plan directly in intervention history
- avoiding a second hidden interpretation layer between provider output and proposal formation

**Step 3: Run focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_gateway_v0 tests.test_roundtrip_v0 -v
```

Expected: PASS

### Task 4: Expose rationale-rich M13 inspection and acceptance surfaces

**Files:**
- Modify: `personal_runtime/chain_inspection.py`
- Modify: `device_edge/cli/cli_edge.py`
- Modify: `tests/test_chain_inspection.py`
- Create: `bin/verify-proposal-formation`
- Modify: `tests/test_dev_env_scripts.py`
- Modify: `docs/dev-env.md`

**Step 1: Add a dedicated inspection entrypoint**

Expose one bounded local inspection path that can drive representative scenarios and print:
- trace
- compact snapshot and snapshot contract
- grounding bundle
- prompt/context and behavior contract
- proposal type, rationale, fallback markers, and resulting action or suppression behavior

**Step 2: Add bounded manual acceptance tooling**

Add a verification entrypoint that runs at least one accepted scenario for each of:
- `reply`
- `action`
- `clarification`
- `no_intervention`

The verifier should fail if any scenario does not produce the expected proposal class or if the report omits readable proposal rationale.

**Step 3: Run focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_chain_inspection tests.test_dev_env_scripts -v
```

Expected: PASS

### Task 5: Verify M13 end to end and update project status conservatively

**Files:**
- Modify if needed: `Project.md`

**Step 1: Run targeted automated verification**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_model_provider tests.test_gateway_v0 tests.test_chain_inspection tests.test_roundtrip_v0 tests.test_dev_env_scripts -v
```

Expected: PASS

**Step 2: Run bounded manual acceptance**

Run:

```bash
bin/verify-proposal-formation --dry-run
bin/verify-proposal-formation
```

Expected:
- dry-run lists the four scenario checks and the inspection commands behind them
- the real run exits cleanly after exercising reply, action, clarification, and no-intervention scenarios
- the printed output shows readable proposal type and rationale for each scenario on the live runtime path

**Step 3: Update `Project.md` only if the full M13 bar is met**

If the repository lands richer proposal metadata but still cannot demonstrate all four proposal classes on the normal live chain, record progress but keep `M13` in progress.

If verification proves:
- inspectable `reply`, `action`, `clarification`, and `no_intervention` proposal classes on the normal live chain
- grounded proposal formation using compact snapshot, active goals, bounded memory, and edge evidence
- structured rationale visible in recorded interventions and local inspection output
- automated coverage plus bounded manual acceptance for all four classes

then mark `M13` complete in `Project.md`, shift active execution focus to `M14`, and refresh the current progress summary accordingly.
