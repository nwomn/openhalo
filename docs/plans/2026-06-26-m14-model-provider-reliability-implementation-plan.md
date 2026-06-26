# M14 Model Provider Reliability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the real model-provider path stable, observable, and diagnosable before later action-loop behavior depends on it.

**Architecture:** Keep model-provider reliability inside the existing `Agent Runtime -> model_provider` boundary rather than adding a new top-level subsystem. Provider calls should remain downstream of `event -> compact snapshot -> grounding bundle -> prompt/context package -> proposal formation`, but the provider boundary must classify response shapes, record non-secret evidence, retry only bounded retryable failures, and surface product-safe terminal messages while preserving raw diagnostics in runtime metadata.

**Tech Stack:** Python 3.11 standard library, `unittest`, existing `openai_compatible` adapter, existing runtime state/intervention metadata, existing terminal and inspection flows, bash verification scripts, project docs

## Current Diagnostic Baseline

The current M14 slice has already landed a first hardening pass:

- OpenAI-compatible response shapes are classified for `message_output_text`, `codex_agent_envelope_empty_output`, `completed_empty_output`, and unknown forms
- proposal generation retries one retryable empty-output response shape before surfacing failure
- terminal-facing failure text is product-safe while metadata keeps `provider_failure_shape`, `provider_failure_reason`, and attempt counts

Current unresolved diagnosis:

- clearing `.runtime` restored stable live terminal/model replies
- a minimal reconstructed pollution state containing recent provider-failure action results did not reproduce the bad response shape
- persisted-state pollution is therefore unconfirmed
- the next recurrence must be captured with request/response shape evidence before cleanup

## Task 1: Add Provider Probe Entrypoint

**Files:**
- Modify: `personal_runtime/model_provider.py`
- Create: `personal_runtime/provider_probe.py`
- Create: `tests/test_provider_probe.py`
- Create: `bin/probe-model-provider`
- Modify: `tests/test_dev_env_scripts.py`

**Step 1: Write the failing tests**

Add tests proving a provider probe can report:

- selected profile, provider, model, endpoint, and wire API
- auth env presence without printing the secret value
- HTTP success/failure class
- latency in milliseconds
- top-level response shape
- response id when present
- output count and output_text presence
- instructions presence and a short non-secret summary

Use transport injection in tests so no real network is required.

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m unittest tests.test_provider_probe tests.test_dev_env_scripts
```

Expected: FAIL because there is no probe module or executable yet.

**Step 3: Implement minimal probe behavior**

Create a small probe API that uses existing config loading and request-building paths. The probe should return structured data, not only print text. The CLI wrapper should render a readable report and exit nonzero only for configuration/auth/transport failures, not for a merely incompatible provider response shape.

**Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m unittest tests.test_provider_probe tests.test_dev_env_scripts
```

Expected: PASS

## Task 2: Persist Provider Evidence On Live Proposal Calls

**Files:**
- Modify: `personal_runtime/model_provider.py`
- Modify: `personal_runtime/agent_executor.py`
- Modify: `personal_runtime/gateway_server.py`
- Modify: `tests/test_model_provider.py`
- Modify: `tests/test_gateway_v0.py`

**Step 1: Write the failing tests**

Add tests proving live proposal metadata records non-secret evidence for both success and failure:

- request fingerprint or prompt/context fingerprint
- prompt size or request byte size
- response shape
- response id when present
- output count
- attempt count and retry count
- latency or per-attempt elapsed time when the transport supplies it

The request fingerprint must not include the provider key and should be stable for identical request payloads.

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m unittest tests.test_model_provider tests.test_gateway_v0
```

Expected: FAIL because success metadata does not yet include enough provider evidence.

**Step 3: Implement evidence capture**

Keep the implementation narrow:

- compute a stable hash from the JSON request payload before sending
- classify every response payload with `classify_openai_compatible_response_shape`
- attach evidence to `ProposalPlan.metadata`
- preserve the current user-facing fallback behavior

Do not persist raw provider responses by default. Store summaries only.

**Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m unittest tests.test_model_provider tests.test_gateway_v0
```

Expected: PASS

## Task 3: Broaden Failure Classification And Retry Policy

**Files:**
- Modify: `personal_runtime/model_provider.py`
- Modify: `tests/test_model_provider.py`

**Step 1: Write the failing tests**

Add tests for failure classes:

- missing auth env: fail fast, no retry
- connection or timeout: bounded retry if configured retryable
- HTTP 401/403: fail fast
- HTTP 429/5xx: bounded retry
- protocol-shape mismatch: bounded retry only for explicitly retryable shapes
- parser/structured-output error: fail fast unless the provider returned plain `output_text`, which should still map to `reply`

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m unittest tests.test_model_provider
```

Expected: FAIL because current retry behavior only covers a narrow response-shape class.

**Step 3: Implement minimal classification**

Introduce small internal helper functions for failure classification. Keep retry attempts bounded and deterministic. Do not add backoff complexity until real evidence says it is needed.

**Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m unittest tests.test_model_provider
```

Expected: PASS

## Task 4: Add Recurrence Evidence Capture Workflow

**Files:**
- Modify: `docs/dev-env.md`
- Modify: `tests/test_dev_env_scripts.py`
- Modify if needed: `bin/probe-model-provider`

**Step 1: Write the failing documentation tests**

Add tests that confirm `docs/dev-env.md` documents:

- backing up `.runtime/state.json` before cleanup
- running the provider probe before deleting state
- collecting provider metadata keys such as `provider_failure_shape`, `provider_failure_reason`, `provider_attempt_count`, and response shape
- comparing clean-state and existing-state behavior

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m unittest tests.test_dev_env_scripts
```

Expected: FAIL until the doc and script references exist.

**Step 3: Update the docs**

Document the recurrence workflow:

1. stop before deleting `.runtime`
2. copy `.runtime/state.json` to a timestamped backup
3. run the provider probe
4. capture relevant `rg` output from the state file
5. only then run clean-state acceptance
6. preserve both bad and clean state files for comparison

**Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m unittest tests.test_dev_env_scripts
```

Expected: PASS

## Task 5: Add Bounded Human Acceptance

**Files:**
- Create: `bin/verify-model-provider-reliability`
- Modify: `tests/test_dev_env_scripts.py`
- Modify: `docs/dev-env.md`

**Step 1: Write the failing tests**

Add tests proving the verification script exists, is executable, and supports `--dry-run`.

The dry run should list:

- provider probe
- clean-state terminal acceptance
- bad-state evidence preservation
- state metadata inspection

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m unittest tests.test_dev_env_scripts
```

Expected: FAIL because the verifier does not exist.

**Step 3: Implement the bounded verifier**

The verifier should avoid secret printing and should not delete `.runtime` automatically. It may create a dedicated temporary state path for clean-state acceptance, but the manual bad-state workflow must remain explicit.

**Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m unittest tests.test_dev_env_scripts
```

Expected: PASS

## Task 6: Verify M14 Progress And Update Project Conservatively

**Files:**
- Modify if needed: `Project.md`

**Step 1: Run targeted automated verification**

Run:

```bash
.venv/bin/python -m unittest tests.test_model_provider tests.test_gateway_v0 tests.test_roundtrip_v0 tests.test_dev_env_scripts tests.test_provider_probe
```

Expected: PASS

**Step 2: Run bounded human acceptance**

Run:

```bash
bin/probe-model-provider
bin/verify-model-provider-reliability --dry-run
```

Then run live terminal acceptance with a clean state and preserve any bad-state evidence if a failure recurs.

**Step 3: Update `Project.md` only to the proven level**

If only probe and evidence capture are implemented, record M14 progress but keep M14 in progress.

Only mark M14 complete when the implementation satisfies the full acceptance bar:

- provider probe exists and works without exposing secrets
- response shapes and failure classes are recorded on live calls
- retry behavior is bounded and type-aware
- terminal-facing fallback remains explicit and product-safe
- human acceptance demonstrates both a real configured provider path and one controlled failure path with readable diagnostics
