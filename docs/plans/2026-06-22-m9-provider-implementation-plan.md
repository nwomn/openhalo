# M9 Provider Configuration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the first accepted `M9` slice with a mature provider/model/profile configuration layer, one `openai_compatible` adapter path, deterministic local fallback, and a human-inspectable acceptance flow.

**Architecture:** Keep the existing `Gateway -> State / Context -> Agent Runtime -> Presence Router -> Action Layer` chain intact. Add a provider boundary inside `Agent Runtime`, resolve text-reply generation through a named model profile, preserve deterministic fallback when provider execution fails, and expose provider/profile/fallback provenance through the existing chain-inspection path instead of creating a separate side channel.

**Tech Stack:** Python 3.11 standard library, `tomllib`, `urllib.request`, `unittest`, existing CLI inspection path

### Task 1: Lock the provider configuration boundary with tests

**Files:**
- Create: `tests/test_model_provider.py`
- Modify: `tests/test_gateway_v0.py`
- Modify: `tests/test_chain_inspection.py`

**Step 1: Write the failing provider-unit tests**

Add tests that prove:
- a TOML-backed provider/model/profile config can be loaded and resolved
- an `openai_compatible` provider request can be built from one named profile
- a mocked provider response can produce a structured notification reply plan
- provider failure falls back to the deterministic local reply path with explicit metadata

**Step 2: Run test to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_model_provider -v`
Expected: FAIL because the provider module does not exist yet.

**Step 3: Write the failing gateway and inspection tests**

Add tests that prove:
- a sense-first text proposal records `llm_profile`, provider/model provenance, and fallback state in proposal metadata
- chain inspection exposes the new metadata for human review

**Step 4: Run tests to verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_gateway_v0 tests.test_chain_inspection -v`
Expected: FAIL because the gateway and inspection surfaces do not yet carry provider metadata.

### Task 2: Add the provider/model/profile configuration module

**Files:**
- Create: `personal_runtime/model_provider.py`
- Create: `.runtime/llm-config.toml`

**Step 1: Implement the config dataclasses and loader**

Add:
- provider config
- model config
- profile config
- runtime config container
- a default loader that reads `.runtime/llm-config.toml`

**Step 2: Implement the deterministic fallback path**

Add one helper that always returns the current local reply style:

```python
f"Runtime heard: {user_text}"
```

That helper should also emit explicit metadata saying fallback was used.

**Step 3: Run focused tests**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_model_provider -v`
Expected: some tests still fail until the adapter path exists, but the config-loading surface should be close to green.

### Task 3: Add the first `openai_compatible` adapter path

**Files:**
- Modify: `personal_runtime/model_provider.py`

**Step 1: Implement request building**

Use one narrow Responses-API-style request shape with:
- `model`
- bounded `input`
- explicit `reasoning.effort`
- explicit `text.verbosity`

**Step 2: Implement response parsing**

Parse a bounded reply surface into one notification reply plan.

**Step 3: Keep provider execution injectable**

Allow an injected transport callable in tests so unit tests do not depend on network access.

**Step 4: Run focused tests**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_model_provider -v`
Expected: PASS

### Task 4: Thread model profiles into the live runtime path

**Files:**
- Modify: `personal_runtime/agent_executor.py`
- Modify: `personal_runtime/gateway_server.py`
- Modify: `device_edge/cli/cli_edge.py`

**Step 1: Update sense-first proposal generation**

Make the normal text-input path:
- resolve one named profile
- generate reply text through the provider layer
- place the final message into `action_payload["message"]`
- record provider/profile/fallback metadata in the proposal

**Step 2: Preserve current non-text and initiative behavior**

Keep:
- agent-initiative runtime-control actions deterministic
- `Presence Router` unchanged
- the deterministic direct-action path unchanged

**Step 3: Run focused tests**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_model_provider tests.test_gateway_v0 -v`
Expected: PASS

### Task 5: Extend human inspection and acceptance

**Files:**
- Modify: `personal_runtime/chain_inspection.py`
- Modify: `tests/test_chain_inspection.py`
- Modify: `docs/dev-env.md`

**Step 1: Expose provider and fallback provenance clearly**

Ensure the existing inspection output makes it easy to see:
- chosen profile
- provider
- model id
- whether deterministic fallback was used

**Step 2: Document the manual acceptance path**

Document one local acceptance path:
- default local inspection with deterministic fallback

Document one optional real-provider path:
- same inspection flow with `.runtime/llm-config.toml` and `OPENAI_API_KEY`

**Step 3: Run focused tests**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_chain_inspection -v`
Expected: PASS

### Task 6: Verify the M9 slice and update project status

**Files:**
- Modify: `Project.md`

**Step 1: Run targeted verification**

Run:
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_model_provider tests.test_gateway_v0 tests.test_chain_inspection tests.test_roundtrip_v0 -v`

Expected:
- all targeted tests pass
- local inspection remains usable

**Step 2: Record completed work conservatively**

Update `Project.md` to record the landed configuration layer, first adapter path, and acceptance flow without prematurely marking all of `M9` complete unless the full milestone bar is truly satisfied.
