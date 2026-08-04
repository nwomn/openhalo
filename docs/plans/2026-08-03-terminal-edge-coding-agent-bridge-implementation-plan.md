# Terminal Edge Coding Agent Bridge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the existing Terminal Edge with a Codex-first coding-agent bridge that emits bounded ordinary Coding observations to Personal Runtime and supports exact foreground correction/interrupt plus explicitly confirmed Runtime steering, while leaving M18 experience discovery and M20.1 skill governance as their existing owners.

**Architecture:** The bridge is a connector/capability inside the existing Terminal Edge and does not create a second Device Edge identity. A local Codex App Server adapter converts thread/turn/item events into bounded `coding.activity.v1` ordinary observations, sends them over the existing `Edge Session Link -> Gateway`, and keeps detailed evidence in a durable paged Edge-local journal. M18 consumes them through its existing generic observation ingress, Harness-controlled experience discovery, Interaction Pool, Presence Router, and governed Action Layer; M20.1 later distills proven workflows into OpenHalo-owned Skill drafts.

**Tech Stack:** Python 3.11+, existing `edge_api` v2 protocol, `device_edge.cli` Terminal Edge, Codex App Server JSON-RPC/JSONL, Personal Runtime M18 Interaction Pool and Harness, `unittest`, existing `bin/test` containment, GitHub Projects v2.

## Project and GitHub execution shape

- Keep the active `M17.8 -> M17.9 -> M17.10` route unchanged; do not create `M17.11` and do not attach the work to the unrelated M17.8 mobile privacy Issue.
- Create one cross-cutting parent Issue, `[Cross-cutting] Terminal Edge Coding Agent Bridge`, with `Initiative=Device Edge`, `Historical Goal=Cross-cutting`, `Architecture=Device Edge`, `Type=Feature`, `Priority=P1`, and no new Milestone.
- Create a design child Issue first. After its PR is accepted, create implementation children for the Terminal Edge adapter and M18 integration. The M18 child uses repository Milestone `M18`; the Terminal Edge enabling child remains cross-cutting until a concrete delivery milestone is opened.
- Keep M20.1 as a linked future dependency, not an implementation child in the first batch. It should open only after repeated coding workflows have produced reviewable procedural evidence.
- Keep the Project status transitions explicit: `Backlog -> Ready -> In Progress -> Review -> Acceptance -> Done`. Only `Auto-add sub-issues to project` is currently guaranteed by repository documentation; do not assume PR or Issue closure automation.

## Public contracts

### `coding.activity.v1`

Add a rich observation-provider registration to the existing Terminal Edge capability announcement. The contract is a bounded ordinary observation, not a full transcript:

- `agent`: first value `codex`; future adapters use the same semantic envelope.
- `agent_session_id` and `agent_turn_id`: exact local App Server identifiers.
- `interaction_id`, plus exact `agent_session_id` and `agent_turn_id`, binds activity to the OpenHalo task and Codex lineage.
- `event_kind`: reasoning summary, plan update, agent message, command execution, file change, test result, approval waiting/resolution, user correction, and turn lifecycle.
- `phase`, `observed_at`, `confidence`, and `causal_parent` for Runtime freshness, deduplication, and interaction lineage.
- `workspace_ref`: stable local workspace/repository reference; do not use it as a device identity.
- `summary` and `evidence_ref`: bounded, body-free or locally retrievable evidence pointers. Detailed prompt/output/diff content stays in the Edge-local paged journal.

The Runtime may persist normalized observations, provenance, summaries, decisions, outcomes, TTL, and body-free references in its existing bounded SQLite ledger. It must not receive an unbounded transcript dump as the steady-state path. Coding observations use the same generic ingress and governance as other observations; there is no Coding-specific `record_only`, ignore, or priority path. The default 32-task bound is only simultaneous-active resource protection; active local history has no event-count ceiling and completed history is reclaimed only by capacity policy.

### Confirmation and steering actions

- `coding.suggestion.offer` is a Runtime-to-Terminal action that renders a bounded recommendation with reason, scope, and explicit choices: accept, ignore, or suppress for this task.
- The Terminal returns the choice as the exact correlated `action_result`; it does not call Codex directly while rendering the offer.
- Only an accepted offer can lead Runtime to dispatch `coding.turn.steer` to the same Terminal Edge. The payload must bind exact `device_id`, `agent_session_id`, `agent_turn_id`, `suggestion_id`, and confirmation reference.
- A stale turn, missing confirmation, duplicate request, disconnected App Server, or mismatched session must fail closed with an inspectable structured result.

## Task 1: Freeze the design contract

**Files:**

- Modify: `Project.md`
- Create: `docs/plans/2026-08-03-terminal-edge-coding-agent-bridge-implementation-plan.md`
- Modify: `docs/edge-api.md` when the public contract moves from design to implementation
- Modify: `docs/dev/github-workflow.md` only if the Project taxonomy or automation boundary changes

**Steps:**

1. Review the current `M18` direction: ordinary Edge observations, bounded source-Edge evidence, `observe_more`, sealed `experience_discovery`, Interaction Pool registration, and body-free Runtime ledger records.
2. Review the current M20.3 Terminal Edge contract and preserve one P-256-authenticated device/session boundary.
3. Land this design plan and the corresponding design Issue before changing Runtime or Terminal behavior.
4. Run `git diff --check` and the project guard before opening the design PR.

## Task 2: Add the Codex-first Terminal Edge adapter

Implementation decision for the first delivery: use hosted stdio only. The
Terminal Edge launches and supervises `codex app-server --listen stdio://` and
does not attach to an external App Server. Each `coding.turn.start` action owns
one independent App Server thread/turn; `coding.suggestion.offer` and
`coding.turn.steer` remain governed confirmation flows. Codex approvals stay
local to the Terminal TUI/line mode.

**Files:**

- Create: `device_edge/cli/coding_agent_bridge.py`
- Create: `device_edge/cli/codex_app_server.py`
- Modify: `device_edge/shared/session_client.py`
- Modify: `device_edge/shared/edge_session_link.py`
- Modify: `edge_api/protocol.py`
- Modify: `device_edge/cli/terminal_daemon.py`
- Modify: `openhalo/edge_cli.py`
- Test: `tests/test_coding_agent_bridge.py`
- Test: `tests/test_terminal_daemon_m8.py`

**Steps:**

1. Add a JSON-RPC/JSONL App Server client that launches or attaches to a local Codex App Server, performs `initialize`, subscribes to a thread, and consumes `thread/*`, `turn/*`, and `item/*` notifications without exposing provider internals to the Terminal transcript.
2. Normalize Codex events into the `coding.activity.v1` envelope and coalesce high-frequency tool/output deltas before sending them through the existing Terminal Edge WebSocket.
3. Widen capability registration helpers from string-only annotations to `str | dict` while preserving all existing legacy capabilities and v2 authentication behavior.
4. Keep the Bridge under the existing Terminal Edge device/session and expose its local lifecycle as `connected`, `degraded`, `reconnecting`, or `unsupported`; a Bridge failure must not terminate the ordinary Terminal Edge.
5. Add a bounded task-local evidence cache and an explicit read path for later `observe_more` requests. Do not continuously upload raw prompt, diff, command output, or agent reasoning content.
6. Add explicit local action handlers for `coding.turn.start`, `coding.suggestion.offer`, and `coding.turn.steer`; route each start to an independent App Server thread/turn, route accepted steering through `turn/steer`, and return exact action-result correlation.
7. Add deterministic fake-App-Server tests for startup, event ordering, coalescing, reconnect, stale turn rejection, accepted steering, refusal, and App Server failure degradation.

## Task 3: Keep Coding activity on the ordinary M18 observation path

**Files:**

- Modify: `personal_runtime/runtime_state.py`
- Modify: `personal_runtime/gateway_server.py`
- Modify: `personal_runtime/context_snapshot.py` only for fields that are proven presence-relevant
- Modify: `personal_runtime/proactive_trigger_gate.py` or its successor ingress guard
- Modify: `personal_runtime/agent_harness.py` / `personal_runtime/hermes_adapter.py` for the sealed `experience_discovery` input projection
- Modify: `personal_runtime/runtime_orchestrator.py`
- Test: `tests/test_gateway_v0.py`
- Test: `tests/test_runtime_orchestrator.py`
- Test: `tests/test_proactive_trigger_gate.py`
- Test: `tests/test_m18_replay.py`

**Steps:**

1. Register and validate the `coding.activity.v1` schema through the existing capability/observation registry; unknown or malformed observations are rejected at Gateway without state mutation.
2. Do not add a Coding-specific admission branch. The existing generic observation path applies provenance/causal/deduplication/rate/budget checks and returns `skip`, `defer`, `observe_more`, or `trigger` according to the same policy used for other observations.
3. Feed admitted evidence into the existing sealed `experience_discovery` skill through a bounded Snapshot, source-Edge evidence window, Hermes native memory, and Runtime projection. The skill may propose an experience candidate but may not dispatch a Codex action.
4. Register admitted work as an ordinary Interaction Pool record and reuse the existing proposal -> Presence -> execution -> action-result lifecycle. Do not introduce a coding-specific interaction lifecycle.
5. Add fixture tests for repeated correction, omitted verification, repeated failure, low-value tool chatter, natural pause, stale evidence, duplicate evidence, and `observe_more` evidence retrieval.
6. Extend offline M18 replay to report Coding activity decisions without calling a provider or dispatching an action.

## Task 4: Integrate confirmation and steering

**Files:**

- Modify: `personal_runtime/action_layer.py`
- Modify: `personal_runtime/execution_planning.py`
- Modify: `personal_runtime/presence_router.py`
- Modify: `personal_runtime/runtime_orchestrator.py`
- Modify: `device_edge/cli/terminal_daemon.py`
- Test: `tests/test_execution_planning.py`
- Test: `tests/test_action_layer.py`
- Test: `tests/test_terminal_daemon_m8.py`
- Test: `tests/test_runtime_orchestrator.py`

**Steps:**

1. Register the two coding action capabilities with exact input schemas and `Device Edge` executor kind.
2. Make Presence govern whether a suggestion is offered, where it is shown, and how frequently it may recur; no model output may bypass this decision.
3. Require an accepted `coding.suggestion.offer` result before planning `coding.turn.steer`.
4. Validate exact agent session/turn lineage, confirmation binding, capability registration, online state, and payload schema before dispatch.
5. Record accepted, ignored, suppressed, stale, failed, and completed outcomes in existing action/intervention ledgers so future M21 review can use them.

## Task 5: Acceptance and project closeout

**Files:**

- Modify: `Project.md` only when architecture or acceptance status changes
- Modify: `docs/dev-env.md`
- Create or modify: `bin/verify-terminal-edge-coding-agent`
- Test: focused Bridge, Gateway, Runtime, and M18 replay suites

**Steps:**

1. Run focused fake-App-Server, Terminal Edge, Gateway registration, M18 gate, action-planning, and replay tests through `bin/test`.
2. Run the full Python regression and confirm ordinary Terminal Edge, Android, Host Edge, and M20.3 receipt/progress tests remain green.
3. Run a real local Codex acceptance: Codex activity reaches Runtime, Runtime produces a Presence-governed suggestion, an explicit acceptance steers the exact active turn, and refusal produces no Codex mutation.
4. Inspect persisted state and diagnostic output to confirm only bounded normalized evidence, body-free references, decisions, and outcomes are retained by Runtime.
5. Move the GitHub Project items manually through Review and Acceptance, link the PRs, record human-acceptance evidence, and mark the parent Done only after both Terminal and M18 children are accepted.
6. Do not mark M18 or M20.1 complete from this feature alone; update `Project.md` only with the new cross-cutting architecture/evidence and the actual child acceptance status.
