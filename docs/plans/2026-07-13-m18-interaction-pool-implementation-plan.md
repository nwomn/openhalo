# M18 Interaction Pool Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add observation-driven M18 interaction admission to the normal runtime lifecycle, with source-neutral interaction pooling and inspectable offline replay.

**Architecture:** Keep the existing hot path intact: a deterministic observation gate decides whether passive evidence merits registration, then a normal `Interaction Pool` record enters Proposal Formation, Presence Router, Execution Planning, Action Layer, and action-result re-entry exactly like a user-originated turn. The gate performs no semantic intent conclusion; Proposal Formation remains the only semantic proposal source. Multiple interaction scopes coexist, while only an identical causal/idempotency key coalesces.

**Tech Stack:** Python 3.12, `unittest`, existing `RuntimeGateway`, `RuntimeOrchestrator`, JSON persisted `RuntimeState`, OpenAI-compatible proposal adapter.

### Task 1: Add a source-neutral Interaction Pool

**Files:**
- Create: `personal_runtime/interaction_pool.py`
- Create: `tests/test_interaction_pool.py`
- Modify: `personal_runtime/runtime_state.py`

**Step 1: Write the failing tests**

Cover a pool that registers a normal interaction from a trigger, preserves `origin` and `causal_scope`, returns the existing active interaction only for the same causal key, and permits a different causal key to remain active concurrently.

```python
pool = InteractionPool(state, interaction_id_factory=lambda: "interaction-2")
first = pool.register(trigger=trigger("scope-a"), source_device_id="phone")
duplicate = pool.register(trigger=trigger("scope-a"), source_device_id="phone")
second = pool.register(trigger=trigger("scope-b"), source_device_id="terminal")

self.assertTrue(first.created)
self.assertFalse(duplicate.created)
self.assertTrue(second.created)
self.assertEqual({item["interaction_id"] for item in state.interactions}, {"interaction-1", "interaction-2"})
```

Also cover action-result lookup by the additive `(interaction_id, interaction_turn_id, request_id)` triple and an interaction turn record containing the action `request_id`.

**Step 2: Run tests to verify they fail**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_interaction_pool -v`

Expected: FAIL because `personal_runtime.interaction_pool` does not exist.

**Step 3: Write minimal implementation**

Implement an `InteractionPool` backed by `RuntimeState.interactions`, with:

```python
@dataclass(frozen=True)
class InteractionRegistration:
    interaction: dict
    created: bool

class InteractionPool:
    def register(self, *, trigger: dict, source_device_id: str, participant_device_ids: list[str]) -> InteractionRegistration: ...
    def get(self, interaction_id: str) -> dict | None: ...
    def record_turn(self, interaction_id: str, *, turn_id: str, request_id: str | None = None) -> dict: ...
```

Use an exact `causal_scope["key"]` comparison only while the matching interaction is not completed. Persist restart-safe interaction/turn sequence state plus `origin`, `causal_scope`, `trigger`, bounded `turns`, and participant device IDs in ordinary interaction records; do not add an M18-only lifecycle type.

**Step 4: Run tests to verify they pass**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_interaction_pool -v`

Expected: PASS.

### Task 2: Route normal turns and results through the pool

**Files:**
- Modify: `personal_runtime/gateway_server.py`
- Modify: `personal_runtime/runtime_orchestrator.py`
- Modify: `personal_runtime/action_layer.py`
- Modify: `device_edge/shared/local_action_executor.py`
- Modify: `tests/test_runtime_orchestrator.py`

**Step 1: Write the failing tests**

Add a regression with two independently open interactions. Dispatch actions for both, return their `action_result` frames in reverse order, and assert each result re-enters only its original interaction. Assert a duplicate/mismatched result triple does not re-enter. Assert an ordinary text turn receives `origin="user_event"`, while an agent-initiative turn receives `origin="agent_initiative"`.

**Step 2: Run tests to verify they fail**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_runtime_orchestrator.RuntimeOrchestratorTests -v`

Expected: FAIL because normal turns still scan the latest intervention directly and do not record source-neutral pool metadata.

**Step 3: Write minimal implementation**

Instantiate `InteractionPool` from `RuntimeGateway`. Replace direct interaction creation/latest-intervention linear lookups in `RuntimeOrchestrator` with pool registration and lookup. Add one runtime-generated `interaction_turn_id` per deliberation turn, keep existing edge `turn_id` unchanged, use `request_id` as the action correlation, and attach the additive triple to outgoing `action_request`/`action_result` frames and stored turns. Preserve existing frame compatibility and existing `interaction_id` behavior.

**Step 4: Run tests to verify they pass**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_runtime_orchestrator -v`

Expected: PASS.

### Task 3: Add deterministic observation trigger admission

**Files:**
- Create: `personal_runtime/proactive_trigger_gate.py`
- Create: `tests/test_proactive_trigger_gate.py`
- Modify: `personal_runtime/runtime_state.py`

**Step 1: Write the failing tests**

Define the desired pure gate API and cover:

```python
decision = gate.evaluate(
    observations=observations,
    snapshot_contract=snapshot_contract,
    state=state,
    current_time="2026-07-13T10:00:00Z",
)
self.assertEqual(decision.status, "trigger")
self.assertEqual(decision.causal_scope["key"], expected_key)
```

Test `skip` for stale/sensitive/duplicate evidence, `defer` for a coalescible fresh context-only screen change, `trigger` for a high-salience runtime-health transition, and exact-key deduplication without suppressing a different trigger reason at the same timestamp.

**Step 2: Run tests to verify they fail**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_proactive_trigger_gate -v`

Expected: FAIL because the gate module does not exist.

**Step 3: Write minimal implementation**

Implement a pure `ProactiveTriggerGate.evaluate()` returning `skip`, `defer`, or `trigger`, reason codes, safe evidence references, a primary evidence device, and a causal scope. Store only bounded fingerprints/timestamps/outcomes in `RuntimeState.proactive_trigger_state`; never duplicate screen text. The first policy is intentionally conservative: stale/unknown/sensitive evidence is rejected, derived liveness evidence cannot self-trigger, known runtime-health/process failure transitions trigger, and only exact scope fingerprints coalesce. Until M17.8 governance is accepted, `mobile.screen_context` raw text/labels/package details are excluded from trigger fingerprints and proactive prompts.

**Step 4: Run tests to verify they pass**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_proactive_trigger_gate -v`

Expected: PASS.

### Task 4: Form observation-driven proposals on the normal chain

**Files:**
- Modify: `personal_runtime/model_provider.py`
- Modify: `personal_runtime/agent_executor.py`
- Modify: `personal_runtime/runtime_orchestrator.py`
- Modify: `tests/test_model_provider.py`
- Modify: `tests/test_runtime_orchestrator.py`

**Step 1: Write the failing tests**

Add a provider-request test that requires a proactive prompt to describe the trigger as evidence rather than a user command, and permits `action` or `no_intervention`. Add an in-process gateway test where a high-salience observation creates an interaction with `origin="observation_driven"`, calls Proposal Formation, and routes the result through Presence Router. Add a test proving an existing unrelated interaction does not block this registration and a proactive terminal action obeys the same terminal-presence suppression as other proactive turns.

**Step 2: Run tests to verify they fail**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_model_provider tests.test_runtime_orchestrator -v`

Expected: FAIL because no observation-driven proposal entrypoint exists.

**Step 3: Write minimal implementation**

Add a dedicated proactive proposal request builder/generator and `ProposalFormation.build_observation_driven_proposal()`. Its structured rationale records trigger evidence and intent signals, but Proposal Formation remains the only semantic interpreter. In `RuntimeOrchestrator`, call the M18 gate after ordinary observation ingestion; when it returns `trigger`, register a normal pool interaction and run the existing snapshot → grounding → proposal → Presence → execution chain. M16 re-entry remains only for observations causally attached to an existing interaction.

**Step 4: Run tests to verify they pass**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_model_provider tests.test_runtime_orchestrator -v`

Expected: PASS.

### Task 5: Add safe chronological M18 offline replay

**Files:**
- Create: `personal_runtime/m18_replay.py`
- Create: `personal_runtime/m18_replay_cli.py`
- Create: `tests/test_m18_replay.py`
- Modify: `docs/dev-env.md`

**Step 1: Write the failing tests**

Build a persisted-state payload containing chronological normalized observations. Assert the replay sorts observations by `(observed_at, original_index)`, groups a shared `source_event_id` as one ingress batch, reconstructs state incrementally, never dispatches an action, and reports every `skip`, `defer`, and `trigger` with evidence references and causal scope.

```python
report = replay_m18_state_history(payload)
self.assertEqual(report["action_dispatch_count"], 0)
self.assertEqual(report["decisions"][1]["status"], "trigger")
```

**Step 2: Run tests to verify they fail**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_m18_replay -v`

Expected: FAIL because the replay module does not exist.

**Step 3: Write minimal implementation**

Replay sorted normalized observations into a clean in-memory `RuntimeState`, grouping a shared `source_event_id` as one ingress batch, invoke only the deterministic gate/Interaction Pool registration path, and return JSON-safe inspection records. Add a `python -m personal_runtime.m18_replay_cli --state <path>` command; it must not instantiate action dispatch or call a provider. Document the command and the need for reviewer labels when deciding whether a timeline point deserved attention.

**Step 4: Run tests to verify they pass**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_m18_replay -v`

Expected: PASS.

### Task 6: Verify the integrated M18 slice

**Files:**
- Modify: `Project.md`
- Test: `tests/test_interaction_pool.py`
- Test: `tests/test_proactive_trigger_gate.py`
- Test: `tests/test_m18_replay.py`

**Step 1: Run focused regression**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_interaction_pool tests.test_proactive_trigger_gate tests.test_m18_replay tests.test_runtime_orchestrator tests.test_model_provider -v`

Expected: PASS.

**Step 2: Run full regression**

Run: `/root/openhalo/.venv/bin/python -m unittest discover -s tests`

Expected: PASS.

**Step 3: Inspect a real persisted state without dispatching actions**

Run: `/root/openhalo/.venv/bin/python -m personal_runtime.m18_replay_cli --state /root/openhalo/.runtime/state.json`

Expected: JSON report with no action dispatch, decision counts, and inspectable candidate records.

**Step 4: Update project progress and commit**

Update `Project.md` only after implementation and acceptance evidence are known. Stage the focused files and commit using a descriptive M18 message.
