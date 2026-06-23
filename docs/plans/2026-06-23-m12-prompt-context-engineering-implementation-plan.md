# M12 Prompt Context Engineering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the first accepted `M12` slice so grounded model-backed reply generation moves from thin snapshot wiring into explicit prompt/context assembly, prompt versioning, replay/eval inspection, and a behavior-contract surface that proves the runtime is actually carrying compact snapshot state, active goals, bounded memory, and bounded edge evidence into the model path.

**Architecture:** Keep the existing `Device Edge -> Edge Session Link -> Gateway -> State / Context -> Agent Runtime -> Presence Router -> Action Layer` chain intact. Treat `M12` as an `Agent Runtime` contract-maturity pass on top of the accepted `M9` through `M11` baseline: prompt/context assembly remains runtime-native, prompt versions stay explicit and inspectable, and replay/eval surfaces reuse recorded intervention state instead of introducing a second hidden chat transcript path.

**Tech Stack:** Python 3.11 standard library, `unittest`, existing gateway/local-inspection surfaces, existing runtime memory bundle, existing provider boundary, bash verification script, project docs

### Task 1: Lock the M12 prompt/context contract with failing tests

**Files:**
- Create: `tests/test_prompt_context.py`
- Modify: `tests/test_model_provider.py`
- Modify: `tests/test_chain_inspection.py`
- Modify: `tests/test_roundtrip_v0.py`

**Step 1: Write the failing tests**

Add coverage that proves:
- the runtime builds an explicit versioned prompt/context package instead of formatting snapshot and grounding ad hoc inside `build_openai_compatible_request`
- the prompt/context package exposes explicit sections for user text, compact snapshot, active goals, bounded recent memory, and bounded edge evidence
- the behavior-contract surface records inspectable checks showing those sections were present and internally consistent with the grounding bundle
- chain inspection exposes prompt context, behavior contract, and replay/eval output as first-class report sections

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_prompt_context tests.test_model_provider tests.test_chain_inspection tests.test_roundtrip_v0 -v
```

Expected: FAIL because the current runtime has grounding metadata but no explicit versioned prompt/context package or replay/eval contract surface.

### Task 2: Implement the explicit M12 prompt/context assembly layer

**Files:**
- Create: `personal_runtime/prompt_context.py`
- Modify: `personal_runtime/model_provider.py`
- Modify: `personal_runtime/agent_executor.py`

**Step 1: Add a versioned prompt/context package**

Implement a small runtime-owned prompt assembly module that:
- declares an explicit prompt/context version
- builds a structured package from user text, compact snapshot, active goals, bounded recent memory, and bounded edge history
- keeps the prompt shape stable and inspectable outside provider transport code

**Step 2: Route provider request construction through that package**

Update the provider layer so:
- request construction consumes the explicit package instead of raw loosely formatted strings
- deterministic fallback metadata still works
- proposal metadata records prompt/context version and bounded section summaries

**Step 3: Run focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_prompt_context tests.test_model_provider -v
```

Expected: PASS

### Task 3: Add replay/eval and behavior-contract inspection surfaces

**Files:**
- Create: `personal_runtime/prompt_replay.py`
- Modify: `personal_runtime/chain_inspection.py`
- Modify: `device_edge/cli/cli_edge.py`

**Step 1: Add a bounded replay/eval helper**

Implement a small replay/eval helper that:
- consumes the recorded prompt/context package plus grounding bundle
- verifies the prompt package and behavior contract still reflect compact snapshot, active goals, bounded recent memory, and bounded edge evidence
- returns a human-readable pass/fail checklist instead of opaque booleans only

**Step 2: Surface the new contract through inspection entrypoints**

Expose prompt context, behavior contract, and replay/eval output through the existing local inspection path so manual acceptance can inspect one live grounded run end to end.

**Step 3: Run focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_chain_inspection tests.test_roundtrip_v0 -v
```

Expected: PASS

### Task 4: Add bounded M12 acceptance tooling and docs

**Files:**
- Create: `bin/verify-prompt-contract`
- Modify: `tests/test_dev_env_scripts.py`
- Modify: `docs/dev-env.md`

**Step 1: Write the failing verification/doc tests**

Add coverage that proves:
- the new verification entrypoint has a dry-run mode
- the dry-run names prompt-context, behavior-contract, and replay-eval verification steps
- the dev documentation describes the new M12 acceptance path

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_dev_env_scripts -v
```

Expected: FAIL because the repository does not yet describe or expose the dedicated M12 prompt-contract verification path.

**Step 3: Implement the minimal verification/doc changes**

Add a bounded verification path so a human can verify:
- the live runtime inspection report includes the explicit prompt/context package
- behavior-contract checks confirm the prompt package carries snapshot, goals, recent memory, and edge evidence
- replay/eval output passes on the recorded intervention without re-querying a provider

**Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_dev_env_scripts -v
```

Expected: PASS

### Task 5: Verify M12 end to end and update project status conservatively

**Files:**
- Modify if needed: `Project.md`

**Step 1: Run targeted verification**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_prompt_context tests.test_model_provider tests.test_chain_inspection tests.test_roundtrip_v0 tests.test_dev_env_scripts -v
```

Expected: PASS

**Step 2: Run bounded manual acceptance**

Run:

```bash
bin/verify-prompt-contract --dry-run
bin/verify-prompt-contract
```

Expected:
- dry-run shows the inspect-chain, prompt-context, behavior-contract, replay-eval, and state-summary steps
- the real run exits cleanly after one grounded local inspection pass
- the printed report shows an explicit prompt/context version, prompt sections, behavior-contract checks, and replay/eval checks passing for snapshot, active goals, bounded recent memory, and bounded edge evidence

**Step 3: Update `Project.md` only if the full M12 bar is met**

If the repository only lands better metadata without explicit replay/eval and verification surfaces, record progress but keep `M12` in progress.

If verification proves:
- explicit prompt/context assembly
- prompt versioning
- inspectable behavior-contract checks
- bounded replay/eval acceptance on recorded grounded runtime state

then mark `M12` complete in `Project.md`, shift active execution focus to `M13`, and refresh the current progress summary accordingly.
