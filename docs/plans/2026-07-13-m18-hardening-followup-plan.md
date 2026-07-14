# M18 Hardening Follow-up Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Close the security and correctness gaps found while reviewing the M18 Interaction Pool implementation, without invoking Android tooling.

**Architecture:** M18 remains a deterministic admission gate followed by ordinary source-neutral interactions. The gate must refuse causally linked evidence, proposal formation must receive only an M18-safe context view, and every resulting action must return only from its selected target edge. `Presence Router` remains the common delivery arbiter, while replay remains a read-only Gate plus Interaction Pool evaluator.

**Tech Stack:** Python 3.12, `unittest`, existing Personal Runtime modules. All verification uses `.venv/bin/python -B -m unittest`; do not run Gradle, Android Studio, SDK tools, or dependency downloads.

### Task 1: Redact M18 provider context at both boundaries

**Files:**
- Modify: `personal_runtime/context_snapshot.py`
- Modify: `personal_runtime/runtime_memory.py`
- Modify: `personal_runtime/runtime_orchestrator.py`
- Modify: `personal_runtime/agent_executor.py`
- Modify: `personal_runtime/model_provider.py`
- Test: `tests/test_model_provider.py`
- Test: `tests/test_runtime_orchestrator.py`

**Step 1: Write failing provider-request tests**

Pass a snapshot containing `mobile.current_screen_context` rich fields (`visible_text_summary`, labels, package name, UI affordances) and raw edge history to `generate_observation_driven_proposal_plan`. Capture the actual request and assert no raw field or value reaches it, while allowed structural state such as `screen_kind`, `capture_mode`, and `sensitivity` remains available.

**Step 2: Verify the test fails**

Run: `.venv/bin/python -B -m unittest tests.test_model_provider.ModelProviderConfigTests.test_observation_driven_provider_request_redacts_raw_mobile_screen_context -v`

Expected: FAIL because the current request serializes the original snapshot and grounding bundle.

**Step 3: Implement the smallest shared sanitizer**

Add an M18-only allowlist sanitizer for `mobile.current_screen_context`. Use it before M18 grounding is built and again at `generate_observation_driven_proposal_plan` as a provider-boundary defense. Exclude raw edge history entirely from observation-driven proposal contexts.

**Step 4: Verify the focused tests pass**

Run: `.venv/bin/python -B -m unittest tests.test_model_provider tests.test_runtime_orchestrator -v`

Expected: PASS.

### Task 2: Preserve causal and chronological admission semantics

**Files:**
- Modify: `personal_runtime/proactive_trigger_gate.py`
- Modify: `personal_runtime/m18_replay.py`
- Test: `tests/test_proactive_trigger_gate.py`
- Test: `tests/test_m18_replay.py`

**Step 1: Write failing Gate/replay tests**

Cover `parent_event_id` and `reentry_parent` returning `skip: causally_linked_observation`, a sustained failed health/process state producing one trigger until recovery or cooldown expiry, and interleaved event timestamps replaying in true batch-time order.

**Step 2: Verify each test fails**

Run: `.venv/bin/python -B -m unittest tests.test_proactive_trigger_gate tests.test_m18_replay -v`

Expected: FAIL because parented evidence can be admitted, repeated health heartbeats receive distinct scopes, and replay keeps first-seen event order.

**Step 3: Implement bounded state-aware admission**

Reject causally linked observations inside the Gate itself. Track bounded health/process failure state or cooldown independently from exact event-id deduplication. Group replay batches first, then order batches by their earliest observation timestamp and original index.

**Step 4: Verify the focused tests pass**

Run: `.venv/bin/python -B -m unittest tests.test_proactive_trigger_gate tests.test_m18_replay -v`

Expected: PASS.

### Task 3: Enforce delivery, result ownership, and contained failure paths

**Files:**
- Modify: `personal_runtime/gateway_server.py`
- Modify: `personal_runtime/runtime_orchestrator.py`
- Modify: `personal_runtime/presence_router.py`
- Modify: `personal_runtime/model_provider.py`
- Modify: `docs/edge-api.md`
- Test: `tests/test_gateway_v0.py`
- Test: `tests/test_runtime_orchestrator.py`
- Test: `tests/test_model_provider.py`

**Step 1: Write failing tests**

Cover a wrong-device `action_result` being rejected without state mutation or turn resolution; an idle terminal being suppressed for an observation-driven `notification.show` without a target hint; and malformed config/provider payload failures returning contained M18 `no_intervention` rather than raising.

**Step 2: Verify each test fails**

Run: `.venv/bin/python -B -m unittest tests.test_gateway_v0 tests.test_runtime_orchestrator tests.test_model_provider -v`

Expected: FAIL because triple-only correlation accepts the wrong edge, no-hint routing can choose idle terminal, and some configuration/type failures escape containment.

**Step 3: Implement the narrow guards**

Bind action results to the stored intervention target at Gateway validation and orchestration. Evaluate all candidate terminal notification surfaces before target selection. Expand only the observation-driven provider failure boundary to contain config and malformed-payload exceptions. Correct the public action-result documentation to the strict triple requirement.

**Step 4: Verify the focused tests pass**

Run: `.venv/bin/python -B -m unittest tests.test_gateway_v0 tests.test_runtime_orchestrator tests.test_model_provider -v`

Expected: PASS.

### Task 4: Verify the runtime-only slice and update the baseline

**Files:**
- Modify: `Project.md`
- Modify: `docs/dev-env.md`
- Test: `tests/test_interaction_pool.py`
- Test: `tests/test_proactive_trigger_gate.py`
- Test: `tests/test_m18_replay.py`
- Test: `tests/test_runtime_orchestrator.py`
- Test: `tests/test_model_provider.py`
- Test: `tests/test_gateway_v0.py`

**Step 1: Run the runtime-only regression suite**

Run: `.venv/bin/python -B -m unittest tests.test_interaction_pool tests.test_proactive_trigger_gate tests.test_m18_replay tests.test_runtime_orchestrator tests.test_model_provider tests.test_gateway_v0 -v`

Expected: PASS without Android/Gradle output.

**Step 2: Run the read-only M18 replay**

Run: `.venv/bin/python -B -m personal_runtime.m18_replay_cli --state .runtime/android-openai-dev-state.json`

Expected: a JSON report with `action_dispatch_count: 0`; it never calls a provider or Android tool.

**Step 3: Update project wording from planned to bounded implementation in progress**

Record the verified backend slice, remaining manual multi-edge acceptance, and the replay limitation that it evaluates only Gate plus Interaction Pool.
