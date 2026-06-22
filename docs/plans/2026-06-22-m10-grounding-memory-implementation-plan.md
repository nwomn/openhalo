# M10 Grounding And Runtime Memory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the first accepted `M10` slice so model-backed reply and proposal generation are grounded in compact snapshot state, active runtime goals, bounded recent runtime memory, and explicit bounded edge-history retrieval instead of behaving like stateless channel chat.

**Architecture:** Keep the existing `Gateway -> State / Context -> Agent Runtime -> Presence Router -> Action Layer` chain intact. Add one explicit runtime-native grounding bundle inside `Agent Runtime`, source it from durable `RuntimeState` plus compact snapshot plus optional bounded edge-history retrieval, expose it through proposal metadata and inspection output, and keep model/provider concerns behind the existing `model_provider` boundary.

**Tech Stack:** Python 3.11 standard library, `unittest`, existing `RuntimeGateway`, `HostEdgeDaemon`, `TraceRecorder`, CLI/inspection entrypoints

### Task 1: Lock the M10 grounding contract with tests

**Files:**
- Create: `tests/test_runtime_memory.py`
- Modify: `tests/test_model_provider.py`
- Modify: `tests/test_gateway_v0.py`
- Modify: `tests/test_chain_inspection.py`

**Step 1: Write the failing runtime-memory unit tests**

Add tests that prove:
- `RuntimeState` can store and persist explicit runtime goals
- runtime memory can build a bounded grounding bundle from snapshot, goals, recent interaction history, and optional edge-history payload
- recent interaction memory is bounded and summarized rather than mirroring all events blindly

**Step 2: Run test to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_runtime_memory -v`
Expected: FAIL because the runtime-memory module and goal helpers do not exist yet.

**Step 3: Write the failing model-provider tests**

Add tests that prove:
- model requests now include a serialized grounding bundle rather than only raw user text plus compact snapshot
- the provider request still remains bounded and inspectable

**Step 4: Run test to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_model_provider -v`
Expected: FAIL because the provider request builder does not yet accept grounding input.

### Task 2: Add durable runtime goals and grounding-bundle helpers

**Files:**
- Create: `personal_runtime/runtime_memory.py`
- Modify: `personal_runtime/runtime_state.py`
- Modify: `tests/test_runtime_state_v0.py`
- Modify: `tests/test_runtime_persistence_v0.py`

**Step 1: Add explicit runtime-goal helpers**

Introduce a small goal record shape inside `RuntimeState` with:
- `goal_id`
- `title`
- `status`
- `summary`
- `updated_at`

Use the existing durable state store so active goals survive restart.

**Step 2: Add bounded recent-interaction grounding helpers**

Implement helpers that derive:
- active goals
- bounded recent user inputs
- bounded recent interventions and action outcomes
- compact durable-state summary

Keep the first implementation intentionally small and inspectable.

**Step 3: Run focused tests**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_runtime_memory tests.test_runtime_state_v0 tests.test_runtime_persistence_v0 -v`
Expected: PASS

### Task 3: Thread grounding bundles into model calls

**Files:**
- Modify: `personal_runtime/model_provider.py`
- Modify: `personal_runtime/agent_executor.py`

**Step 1: Extend the provider request shape**

Make the `openai_compatible` request carry:
- current user text
- compact snapshot
- runtime grounding bundle

The bundle should be serialized in a bounded way that stays readable during manual inspection and testing.

**Step 2: Record inspectable grounding provenance**

Proposal metadata should surface enough evidence to confirm grounding happened, including:
- grounding bundle version
- count of active goals
- count of recent memory items
- whether bounded edge history was attached

**Step 3: Run focused tests**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_model_provider tests.test_gateway_v0 -v`
Expected: PASS

### Task 4: Add explicit bounded edge-history retrieval into the M10 inspection path

**Files:**
- Modify: `personal_runtime/gateway_server.py`
- Modify: `personal_runtime/chain_inspection.py`
- Modify: `device_edge/cli/cli_edge.py`
- Modify: `tests/test_chain_inspection.py`
- Modify: `tests/test_roundtrip_v0.py`

**Step 1: Add a bounded retrieval hook for inspection/manual acceptance**

For the first accepted `M10` slice, keep retrieval explicit and narrow:
- inspection flows may request one bounded `runtime.edge_history` window from a connected host edge
- retrieved history should be included in the grounding bundle and recorded in durable state
- the runtime must still work when no edge-history retrieval is available

**Step 2: Extend the inspection report**

Expose:
- grounding bundle
- bounded retrieved edge history
- proposal grounding metadata

This should let a human confirm the runtime is grounded in runtime-native state rather than only raw input text.

**Step 3: Run focused tests**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_chain_inspection tests.test_roundtrip_v0 -v`
Expected: PASS

### Task 5: Add a manual M10 acceptance entrypoint and document it

**Files:**
- Modify: `docs/dev-env.md`
- Modify: `Project.md`

**Step 1: Document the acceptance command**

Add one bounded manual acceptance command that demonstrates:
- model-backed reply path
- active runtime goals in grounding
- recent runtime memory in grounding
- bounded edge-history retrieval in grounding

**Step 2: Record milestone completion conservatively**

Once targeted tests and manual acceptance evidence both pass, update `Project.md` to mark `M10` completed and move active execution focus to `M11`.

### Task 6: Verify the M10 slice end to end

**Files:**
- Modify: `Project.md`

**Step 1: Run targeted verification**

Run:
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_runtime_memory tests.test_runtime_state_v0 tests.test_runtime_persistence_v0 tests.test_model_provider tests.test_gateway_v0 tests.test_chain_inspection tests.test_roundtrip_v0 -v`

**Step 2: Run the manual acceptance path**

Run one bounded inspection command that prints the new grounding bundle and retrieved edge history.

**Step 3: Update project status**

Record completed M10 work, acceptance evidence, and the shift to `M11` as the next active milestone.
