# M20 Harness Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the Hermes-backed Agent Harness without weakening OpenHalo
action governance, by enabling curated read-only research and Hermes-native
persistent memory alongside the completed action bridge.

**Architecture:** `RuntimeOrchestrator` remains the owner of the external
runtime action loop and continues to route all model-originated outcomes through
`Presence Router`, `Execution Planning`, and `Action Layer`. A small
OpenHalo-owned Harness contract converts each existing proposal-formation entry
point into a uniform input/outcome exchange; a temporary legacy adapter delegates
to the existing `ProposalFormation` implementation. `HermesHarnessRunner` owns
the internal Hermes loop, uses a curated read-only tool surface plus Hermes
memory, and can only return OpenHalo-governed actions for external effects.

**Tech Stack:** Python 3.11+, standard-library dataclasses and `typing.Protocol`,
existing `unittest` suite, Hermes Agent 0.18.2 reference clone at upstream
commit `e12626b34fb1024bf00f40f4759647f9cbd3f198`.

**Execution constraint:** Work on the existing `codex/m20-harness-foundation`
development branch. Do not create a worktree or commit autonomously.

## Reuse Audit Record

- Candidate: `NousResearch/hermes-agent`, commit
  `e12626b34fb1024bf00f40f4759647f9cbd3f198`, package version `0.18.2`, MIT.
- Reusable concepts: stateful conversation loop, normalized provider tool-call
  shape, context compression, session history, memory-provider lifecycle, tool
  hooks and bounded tool-loop behavior.
- Boundary constraint: its `AIAgent` and tool dispatcher are process-wide,
  CLI/gateway-oriented components with a broad dependency set and global tool
  registry. OpenHalo therefore uses a sealed runtime-scoped Hermes home and
  custom toolsets; it never enables Hermes' default, shell, file, skills,
  plugin, delegation, or browser surfaces in the Gateway process. The adapter
  regenerates the sealed Hermes configuration and masks environment-based
  Kanban/CDP/cloud-browser injection. M20 serializes this embedded scope and
  requires the Personal Runtime to own its process; co-hosting unrelated
  unconstrained Hermes callers needs a future subprocess-isolation design.
- Integration decision: reuse the pinned `AIAgent`, tool loop, HTTPS
  fetch/search, and native `memory` lifecycle behind `HarnessRunner`. The
  adapter exposes only the native `memory` tool plus declared OpenHalo research
  wrappers and `openhalo_action`; it keeps every other Hermes dispatcher path
  unavailable, and records durable-memory provenance without copying the memory
  body. An exception requires the written reuse-audit format required by
  `Project.md`.

## M20 Acceptance Status

Completed and accepted M20:

- `HarnessInput`, `HarnessOutcome`, and `HarnessRunner` now provide one
  runtime-owned deliberation seam for normal events, action-result re-entry,
  observation re-entry, and observation-driven interactions.
- `LegacyProposalHarness` maps that seam to the accepted proposal-formation
  implementation, so the external `Gateway -> Presence -> Execution Planning
  -> Action Layer` path remains behaviorally stable during migration.
- Harness runner metadata is retained in proposal/intervention metadata for
  inspection and replay.
- `HermesToolCallAdapter` accepts Hermes' normalized `ToolCall` shape and
  normalizes an explicitly registered call into an OpenHalo action intent,
  keeps only declared read-only internal tools inside the harness, and rejects
  unregistered tools before any handler can run.
- `JsonStateStore` serializes same-runtime writes, preventing an action-result
  worker and concurrent WebSocket cleanup from racing on the shared temporary
  state file.
- The pinned Hermes `AIAgent` runs behind `HermesHarnessRunner` with only the
  OpenHalo bridge tool enabled; real-use config explicitly selects it.
- Governed intent validation happens before Presence, action results retain a
  runtime-owned envelope, and MCP/skill targets terminate at registered
  placeholders until providers are introduced.
- Legacy working, procedural, semantic, and episodic compatibility views are
  explicit; they are not an implemented Hermes durable-memory engine.
- Chain inspection includes harness traces, evaluation, and a review-required
  promotion gate.

Configured-provider human acceptance is complete. The latest
`bin/verify-m20-harness --live --runtime-config-path config/runtime-config.toml`
run exited `0` after exercising a real provider, independent Gateway, and
WebSocket terminal edge. It produced sanitized evidence for all of the following:

- Hermes exposes no direct-execution tool path, including shell/process, file,
  code-execution, skill/plugin, delegation, arbitrary MCP, or any browser
  surface; the sole mutable internal exception is the explicitly allowlisted
  native `memory` tool.
- Hermes can perform configured, audited read-only `fetch` and `search`
  research without a browser process or GUI dependency. Browser-backed
  rendering is explicitly deferred beyond M20.
- The configured-provider acceptance ladder proves both `openhalo_web_fetch`
  and `openhalo_web_search`; search requires an operator-configured
  `search_url_template` whose rendered public host is already allowed.
- Hermes native persistent memory survives a new runner/session and is recalled
  later, while OpenHalo records provenance/replay metadata rather than a second
  durable memory body.
- The live recall sentinel need only be contained in Hermes' post-write native
  memory file; Hermes may autonomously phrase or consolidate the surrounding
  entry. Evidence records the actual entry hash and file digest, never a copied
  memory body.
- Hermes periodic background memory and skill review remains disabled in M20;
  normal audited turns retain autonomous native memory writes, while re-entry
  turns receive read context without the native `memory` write tool at either
  Hermes dispatch layer. A future background fork must install the same
  OpenHalo audit and dispatch gates.
- Real acceptance covers the governed outer action loop, allowed research, and
  cross-session memory recall, including an allowed search turn.

Current hardening note:

- Hermes error-request dumps are redirected into the same per-turn temporary
  sandbox and removed after the run, so they do not become a second durable
  prompt or provider-header store.
- The sealed Hermes memory nudge interval is `0`. M20 creates a fresh agent for
  each runtime turn, so a positive periodic nudge would not provide a real
  review cadence and would become an unaudited write path if agent reuse were
  introduced later.

Source-governance correction:

- Remote research is an untrusted source marker, not a global action/memory
  kill switch. The adapter binds a research-assisted action to the current
  normal user request and its audited research references; the runtime verifies
  that binding, proposal consistency, capability registration, and risk before
  Presence. M20 permits only a low-risk requesting-user notification in this
  path; elevated actions are `confirmation_required` and fail closed until that
  interaction exists.
- Hermes native `memory` is the single M20 durable-memory interface rather
  than a second OpenHalo facade. It may autonomously add, consolidate, replace,
  or remove bounded user/profile and agent-operational entries under the
  OpenHalo behavior contract. A remote source is not a persistent instruction:
  research may inform normal reasoning, but its directives must never be saved
  as memory or authorize a user-visible action. Audit records preserve
  hashes/references rather than bodies.
- A research-assisted action is accepted only with a complete local audit
  record (tool call, source/result hashes, result length, policy/egress
  decision, and duration) and a normalized runtime action intent. Incomplete
  audit records and Hermes action proposals without intents fail before
  Presence; execution planning independently fails closed if a harness-marked
  action lacks an allowed, matching runtime envelope.
- The positive live fetch/search scenarios test the real configured-provider
  network path. The live hostile-page scenario may fetch and hash the fixture,
  or safely decline it with no side effects. Deterministic forced action and
  memory cases separately prove runtime rejection and native-memory threat
  scanning, so a silent live model response is never treated as the boundary
  proof.
- `memory.write_approval: false` allows Hermes' bounded native memory workflow
  to run without a CLI approval prompt; it is not the OpenHalo security
  boundary. The runtime-scoped home, behavior contract, dispatcher allowlist,
  native threat scanning, and body-free audit establish the M20 boundary, and
  the sealed harness removes `HERMES_YOLO_MODE`.

## Deferred M20.1 Scope

M20.1 follows M20 rather than expanding this acceptance batch. It will design
an OpenHalo-owned procedural-memory and skill-draft lifecycle: Hermes may
distill a proven workflow into a non-executable draft with provenance and
bounded declarative content, but a draft cannot load as an active Hermes skill
until OpenHalo validates and explicitly activates it. Generic Hermes skill,
plugin, file, shell, browser, delegation, and MCP paths remain outside M20 and
M20.1's initial active surface.

## Completion Batches

### Task 6: Install the Pinned Hermes Core and Add an Action Bridge

**Files:**
- Modify: `pyproject.toml`
- Modify: `personal_runtime/hermes_adapter.py`
- Test: `tests/test_hermes_adapter.py`

Pin Hermes with its exact upstream Git commit. Add one dedicated
`openhalo_action` Hermes tool in a dedicated toolset. Its handler may only
capture a validated OpenHalo action intent in run-local state and return a
deferred tool result; it must never execute a device action, MCP call, skill,
or policy write. Hermes' native, separately audited `memory` tool remains
available for persistent memory.

### Task 7: Add the Real Hermes Harness Runner

**Files:**
- Modify: `personal_runtime/hermes_adapter.py`
- Modify: `personal_runtime/agent_harness.py`
- Test: `tests/test_hermes_adapter.py`

Implement `HermesHarnessRunner` using the installed `run_agent.AIAgent` with
only the dedicated OpenHalo action, curated read-only research, and Hermes
memory toolsets enabled. Convert `HarnessInput` into the OpenHalo behavior
contract and grounded context supplied to the Hermes turn, then convert final
text or captured bridge intent into `HarnessOutcome`. Hermes provider/session,
fetch/search, and memory behavior are reused; no OpenHalo-native provider, general
tool loop, or durable-memory engine is added.

### Task 8: Make Hermes the Configured Default and Preserve Safe Fallback

**Files:**
- Modify: `personal_runtime/gateway_server.py`
- Modify: `config/runtime-config.example.toml`
- Modify: test runtime-config fixtures
- Test: `tests/test_runtime_orchestrator.py`

Select Hermes by default for real runtime config. Test and offline fixtures may
explicitly select the existing deterministic compatibility adapter. A missing
Hermes dependency or provider failure must produce inspectable failure/fallback
metadata; it may not silently claim a Hermes-backed result.

### Task 9: Govern Intent Execution and Memory/Terminal Outcomes

**Files:**
- Modify: `personal_runtime/runtime_orchestrator.py`
- Modify: `personal_runtime/execution_planning.py`
- Modify: `personal_runtime/runtime_state.py`
- Test: `tests/test_runtime_orchestrator.py`
- Test: `tests/test_gateway_v0.py`

Validate bridge intents against behavior contract and capability registry before
Presence. Record execution class, visibility, provenance, terminal reason, and
Hermes tool/memory audit metadata. Route MCP and skill/procedure intents to
explicit placeholder executors until real providers are registered. Do not use
OpenHalo `harness_memory` as a second durable-memory store on the Hermes path.

### Task 10: Trace, Eval, and Human Acceptance

**Files:**
- Modify: `personal_runtime/chain_inspection.py`
- Modify: `personal_runtime/proposal_harness.py`
- Create: `bin/verify-m20-harness`
- Test: focused harness, gateway, and replay tests

Produce replayable M20 traces with Hermes/fallback provenance, action-intent
validation, internal research/memory audit references, action-result re-entry,
and terminal reason. Run real local Gateway/edge scenarios using the pinned
Hermes core and a configured provider for action, research, and memory recall,
then record the human-acceptance evidence before marking M20 accepted.

## Task 1: Define Harness Contracts

**Files:**
- Create: `personal_runtime/agent_harness.py`
- Test: `tests/test_agent_harness.py`

**Step 1: Write failing tests**

Test that a normal runtime event becomes a `HarnessInput` carrying interaction
lineage, compact snapshot, grounding bundle, and correlation. Test that a
proposal-style outcome preserves the exact `InterventionProposal` payload and
declares `action` or `no_intervention` as its terminal intent.

**Step 2: Verify failure**

Run: `.venv/bin/python -m unittest tests.test_agent_harness`

Expected: import failure because `personal_runtime.agent_harness` does not yet
exist.

**Step 3: Implement the minimal contract**

Add immutable dataclasses for `HarnessInput` and `HarnessOutcome`, a
`HarnessOperation` enum for normal, post-action, post-observation, and
observation-driven proposal formation, and a `HarnessRunner` protocol. Do not
add provider, memory, tool execution, or Hermes imports in this task.

**Step 4: Verify green**

Run: `.venv/bin/python -m unittest tests.test_agent_harness`

Expected: PASS.

## Task 2: Add the Legacy Compatibility Adapter

**Files:**
- Modify: `personal_runtime/agent_harness.py`
- Test: `tests/test_agent_harness.py`

**Step 1: Write failing tests**

Use a real `ProposalFormation` test double. Assert that the adapter selects the
operation-specific legacy method, sends the original arguments unchanged, and
returns a `HarnessOutcome` that contains the legacy proposal without executing
an action.

**Step 2: Verify failure**

Run: `.venv/bin/python -m unittest tests.test_agent_harness`

Expected: missing `LegacyProposalHarness` failure.

**Step 3: Implement the minimal adapter**

Add `LegacyProposalHarness`. Its only responsibility is argument translation
from `HarnessInput` to the existing proposal methods and conversion to
`HarnessOutcome`. It must not contain model calls, prompts, provider handling,
or action dispatch.

**Step 4: Verify green**

Run: `.venv/bin/python -m unittest tests.test_agent_harness`

Expected: PASS.

## Task 3: Route the Live Runtime Through the Seam

**Files:**
- Modify: `personal_runtime/gateway_server.py`
- Modify: `personal_runtime/runtime_orchestrator.py`
- Test: `tests/test_runtime_orchestrator.py`

**Step 1: Write failing integration test**

Inject a capturing HarnessRunner through `RuntimeGateway`, send a normal text
event, and assert that it receives a normal `HarnessInput` with the same
correlation and interaction IDs. Assert that the response still becomes an
`action_request` through Presence and Execution Planning.

**Step 2: Verify failure**

Run: `.venv/bin/python -m unittest tests.test_runtime_orchestrator.RuntimeOrchestratorTests.test_orchestrator_uses_harness_for_normal_turn`

Expected: constructor rejects the injected harness or no harness call occurs.

**Step 3: Implement the minimal integration**

Create `LegacyProposalHarness` during gateway construction unless a runner is
injected. Replace each direct `proposal_formation` invocation in
`RuntimeOrchestrator` with a helper that builds `HarnessInput` and consumes the
outcome proposal. Preserve the existing `proposal_formation` attribute as a
test compatibility surface during this migration batch.

**Step 4: Verify green**

Run: `.venv/bin/python -m unittest tests.test_agent_harness tests.test_runtime_orchestrator`

Expected: PASS.

## Task 4: Preserve Re-entry and Fail-Fast Semantics

**Files:**
- Modify: `tests/test_runtime_orchestrator.py`
- Modify: `tests/test_gateway_v0.py` if action-result coverage needs the public path

**Step 1: Write failing tests**

Cover post-action and post-observation HarnessInput operations. Assert that the
same interaction and prior proposal lineage are present, and that a missing or
invalid outcome is an explicit runtime error rather than a silently fabricated
proposal.

**Step 2: Verify failure**

Run: `.venv/bin/python -m unittest tests.test_runtime_orchestrator tests.test_gateway_v0`

Expected: the new contract assertions fail.

**Step 3: Implement only the boundary validation required by the tests**

Validate that a runner returns a proposal-shaped outcome for proposal
operations, retain current source/target/action-result correlation behavior,
and attach Harness metadata to intervention diagnostics. Do not change
Presence policy or provider fallback behavior.

**Step 4: Verify green**

Run: `.venv/bin/python -m unittest tests.test_runtime_orchestrator tests.test_gateway_v0`

Expected: PASS.

## Task 5: Prepare Hermes Adapter Admission

**Files:**
- Create: `personal_runtime/hermes_adapter.py`
- Test: `tests/test_hermes_adapter.py`
- Modify: `docs/plans/2026-07-10-agent-harness-action-loop-architecture.md`

**Step 1: Write failing tests**

Test that a Hermes-normalized tool call becomes an OpenHalo action-intent
candidate with provenance and cannot be dispatched by the adapter. Test that a
read-only, explicitly allowlisted internal helper remains internal and returns
an auditable internal result.

**Step 2: Verify failure**

Run: `.venv/bin/python -m unittest tests.test_hermes_adapter`

Expected: missing adapter module failure.

**Step 3: Implement only after the runtime boundary is green**

Use the pinned source through an explicitly reviewed integration mechanism.
The adapter must translate input/output and tool lifecycle only; it may not
instantiate a competing Gateway, dispatch device actions, or write durable
memory directly.

**Step 4: Verify and commit in small units**

Run focused tests after each task, then:

```bash
.venv/bin/python -m unittest
git add personal_runtime tests docs Project.md
git commit -m "feat: add M20 harness foundation"
```

Expected: full suite passes before a Hermes adapter is made the default runner.

## Revised Completion Plan: Curated Hermes Capabilities

### Task 11: Add a Sealed Hermes Capability Policy

**Files:**
- Modify: `config/runtime-config.example.toml`
- Modify: `personal_runtime/hermes_adapter.py`
- Test: `tests/test_hermes_adapter.py`

**Step 1: Write the failing tests**

Assert that a Hermes runner exposes only `openhalo`, `openhalo_research`, and
the native Hermes `memory` toolset. Assert that shell/process, file,
code-execution, skills, plugins, delegation, MCP, and all browser toolsets are
absent. Add rejection tests for unapproved hosts, private addresses, non-HTTPS
URLs, redirects, and exhausted read-only-call budget.

**Step 2: Run the focused test**

Run: `.venv/bin/python -m unittest tests.test_hermes_adapter`

Expected: FAIL because the runner still enables only the action bridge and has
no sealed capability policy.

**Step 3: Implement the minimum policy**

Create a config-backed immutable policy and register only OpenHalo-owned facade
tools. Require HTTPS, DNS/IP checks before every request and redirect,
configured host rules, time and response budgets, and untrusted-content
envelopes. Set the isolated Hermes
config to disable lazy installs, all external memory providers, and background
memory/skill review.

**Step 4: Run the focused test**

Run: `.venv/bin/python -m unittest tests.test_hermes_adapter`

Expected: PASS.

### Task 12: Enable Hermes MemoryStore With Body-Free OpenHalo Audit

**Files:**
- Modify: `personal_runtime/hermes_adapter.py`
- Modify: `personal_runtime/runtime_orchestrator.py`
- Modify: `personal_runtime/runtime_state.py`
- Test: `tests/test_hermes_adapter.py`
- Test: `tests/test_runtime_orchestrator.py`
- Test: `tests/test_runtime_state_v0.py`

**Step 1: Write the failing tests**

Run an agent that uses native Hermes `memory`, construct a fresh runner against
the same scoped Hermes home, and prove the preference appears in the later
Hermes prompt. Assert that native add, replace, remove, and batch mutations
retain real Hermes task/tool-call references, source hashes, scope hashes, and
no memory body. Research remains an untrusted source marker rather than a
global memory kill switch; remote instructions, role claims, and tool
directives must be rejected by Hermes' native strict memory safeguards and the
OpenHalo behavior contract.

**Step 2: Run the focused tests**

Run: `.venv/bin/python -m unittest tests.test_hermes_adapter tests.test_runtime_orchestrator tests.test_runtime_state_v0`

Expected: FAIL because `skip_memory=True` and no Hermes provenance surface
exists.

**Step 3: Implement the minimum integration**

Use Hermes' `set_hermes_home_override` ContextVar to run each personal-runtime
scope against an OpenHalo-owned `HERMES_HOME`; retain Hermes `MemoryStore` as
the only durable content store. Enable the native `memory` tool and install a
runtime-scoped audit callback that captures only changed mutations after Hermes
supplies task/tool-call metadata. Leave legacy `harness_memory` available only
to the legacy runner.

**Step 4: Run the focused tests**

Run: `.venv/bin/python -m unittest tests.test_hermes_adapter tests.test_runtime_orchestrator tests.test_runtime_state_v0`

Expected: PASS.

### Task 13: Persist Sanitized Research and Memory Provenance

**Files:**
- Modify: `personal_runtime/harness_evaluation.py`
- Modify: `personal_runtime/chain_inspection.py`
- Modify: `personal_runtime/runtime_state.py`
- Test: `tests/test_harness_evaluation.py`
- Test: `tests/test_chain_inspection.py`

**Step 1: Write the failing tests**

Assert a completed research tool record contains tool name, policy version,
approved host/query reference, duration, result hash, and decision—but no raw
page body. Assert memory provenance is exposed through chain inspection with no
memory body, and promotion is blocked for rejected egress or missing audit.

**Step 2: Run the focused tests**

Run: `.venv/bin/python -m unittest tests.test_harness_evaluation tests.test_chain_inspection`

Expected: FAIL because harness traces currently contain only outcome and
legacy-memory counts.

**Step 3: Implement the minimum trace extension**

Attach sanitized internal-tool records and Hermes-memory provenance IDs to the
harness outcome, runtime state, and replay trace. Extend chain inspection and
the promotion gate without storing remote or durable-memory contents.

**Step 4: Run the focused tests**

Run: `.venv/bin/python -m unittest tests.test_harness_evaluation tests.test_chain_inspection`

Expected: PASS.

### Task 14: Expand the M20 Acceptance Ladder

**Files:**
- Modify: `bin/verify-m20-harness`
- Modify: `tests/test_dev_env_scripts.py`
- Modify: `Project.md`

**Step 1: Write the failing verifier test**

Require the verifier's dry-run and live report to include the action bridge,
allowed research, prohibited-tool surface, persistent-memory write/recall, and
audit checks.

**Step 2: Run the focused test**

Run: `.venv/bin/python -m unittest tests.test_dev_env_scripts`

Expected: FAIL because the current verifier proves only the governed action
loop.

**Step 3: Implement the acceptance ladder**

Add deterministic local-provider scenarios for research and memory persistence,
then require a configured-provider Gateway/terminal human run covering a
permitted public-web read, a research-assisted reply that still passes through
Presence and execution planning, a user preference memory recall after a fresh
runner, and a hostile-page case where unbound or elevated research-derived
intents are rejected or require confirmation rather than gaining authority.

**Step 4: Run verification**

Run: `.venv/bin/python -m unittest`

Expected: PASS before conducting and recording human acceptance; only then may
M20 be changed back to accepted.
