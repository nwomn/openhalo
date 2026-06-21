# M6 Dual-Entry Proactive Runtime Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Land the first completion-quality `M6` slice by making the proactive runtime support both observation-driven and agent-initiative-triggered intervention on the same live proposal, presence, and action path.

**Architecture:** Keep the current hot path explicit and incremental. Reuse the accepted `observation -> snapshot -> proposal -> presence -> action` chain from `M5`, add one explicit agent-initiative entrypoint that builds the same snapshot and proposal artifacts, and let execution planning widen only enough to choose between `notification.show`, `runtime.status`, `runtime.collect_logs`, and `runtime.edge_history`.

**Tech Stack:** Python, `unittest`, existing websocket gateway, CLI edge, host-edge daemon

### Task 1: Lock the M6 acceptance surface with tests

**Files:**
- Modify: `tests/test_gateway_v0.py`
- Modify: `tests/test_roundtrip_v0.py`
- Modify: `tests/test_chain_inspection.py`

**Step 1: Write the failing gateway tests**

Add tests that prove:
- the runtime can accept an explicit agent-initiative trigger frame
- that trigger rebuilds a decision-time snapshot from stored observations
- the resulting intervention record marks the proposal source as `agent_initiative`
- the allowed action can target a host edge with `runtime.control` when the proposal requests `runtime.status`

**Step 2: Run test to verify it fails**

Run: `bin/test -m unittest tests.test_gateway_v0 -v`
Expected: FAIL because the gateway has no explicit agent-initiative entrypoint and cannot turn a proactive request into a runtime-control action on the normal path.

**Step 3: Write the failing roundtrip and inspection tests**

Add tests that prove:
- a real websocket host edge can receive a proactive `runtime.status` action from the normal path, not only from the direct-action bypass
- chain inspection can show whether a recorded intervention came from `sense_first` or `agent_initiative`

**Step 4: Run tests to verify they fail**

Run: `bin/test -m unittest tests.test_roundtrip_v0 tests.test_chain_inspection -v`
Expected: FAIL because there is no proactive websocket path and the inspection report does not yet expose the proposal source.

### Task 2: Add the explicit M6 proposal and execution-planning surface

**Files:**
- Modify: `personal_runtime/agent_executor.py`
- Modify: `personal_runtime/action_layer.py`

**Step 1: Implement the minimal proposal expansion**

Expand `InterventionProposal` so it can carry:
- `source`
- `action_capability`
- `action_payload`
- `message`
- optional `target_device_hint`

Keep the sense-first text-input path intact, but add a separate builder for agent-initiative triggers that can request one of the narrow host-control actions already supported by the host edge.

**Step 2: Implement minimal execution planning**

Add one planner/helper that turns an allowed proposal into the final action request:
- `notification.show` should still build a notification request
- `runtime.status`, `runtime.collect_logs`, and `runtime.edge_history` should build runtime-control action requests with the proposal payload

**Step 3: Run focused tests**

Run: `bin/test -m unittest tests.test_gateway_v0 tests.test_roundtrip_v0 -v`
Expected: The previously failing tests move closer to green, but may still fail until gateway routing is updated.

### Task 3: Thread agent initiative through the live gateway path

**Files:**
- Modify: `personal_runtime/gateway_server.py`
- Modify: `personal_runtime/presence_router.py`
- Modify: `personal_runtime/runtime_state.py`
- Optionally modify: `device_edge/shared/session_client.py`

**Step 1: Add the explicit proactive trigger envelope**

Teach the gateway to accept one new `event_push` payload shape for the normal path, such as:

```python
{
    "agent_initiative": {
        "capability": "runtime.status",
        "payload": {},
        "reason": "runtime_health_check"
    }
}
```

This path must:
- use the same stored observations as the sense-first path
- build the same compact snapshot and snapshot contract
- build an initiative-sourced proposal
- pass through the same `Presence Router`
- record intervention history with proposal source and decision-time contract

**Step 2: Keep suppression unified**

Presence must still be able to suppress the initiative path for ambiguity or cooldown. The new path may carry stronger salience in the proposal, but it must not bypass governance.

**Step 3: Run focused tests**

Run: `bin/test -m unittest tests.test_gateway_v0 tests.test_roundtrip_v0 tests.test_chain_inspection -v`
Expected: PASS

### Task 4: Add a bounded manual acceptance path and document M6

**Files:**
- Modify: `device_edge/cli/cli_edge.py`
- Modify: `personal_runtime/chain_inspection.py`
- Modify: `docs/dev-env.md`
- Modify: `Project.md`

**Step 1: Add a small human-verifiable entrypoint**

Expose one bounded local or websocket helper that can demonstrate both:
- sense-first proposal source
- agent-initiative proposal source

The command should print the inspected chain in the same report style used for M5 so the user can review the intervention evidence directly.

**Step 2: Update docs only if acceptance criteria are truly met**

Record `M6` as complete in `Project.md` only if all of the following are true:
- the live runtime supports both sense-first and agent-initiative proposal entry
- both paths converge on the same `Presence Router`
- the allowed action path can execute both notification and narrow host-control actions
- the initiative path is covered by automated tests and a manual acceptance command

**Step 3: Run full verification before making completion claims**

Run:
- `bin/test -m unittest tests.test_gateway_v0 tests.test_roundtrip_v0 tests.test_chain_inspection tests.test_edge_client_v0 -v`
- `bin/verify-host-edge --dry-run`

Expected:
- all targeted tests pass
- the host-edge verification command remains available and still references the normal runtime/host path
