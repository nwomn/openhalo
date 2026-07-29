# M20.3 v2 Regression Migration Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Retire all bearer-authenticated test scaffolds and restore the full Python regression suite on the `edge.runtime.v2` P-256 challenge protocol.

**Architecture:** Product code remains bearer-free. Test support creates ephemeral P-256 identities and provisions their public keys in an isolated `PairingStore`, then drives the same `connect -> auth_challenge -> auth_proof -> connect_ok` ceremony as a Device Edge. In-process and WebSocket tests use that support rather than adding test-only bearer branches to `Gateway`, `SessionClient`, or command-line parsers.

**Tech Stack:** Python 3.12, `unittest`, `asyncio`, `websockets`, `cryptography`, `PairingStore`, `RuntimeGateway`, `SessionClient`.

### Task 1: Establish reusable v2 test support

**Files:**
- Create: `tests/v2_test_support.py`
- Create: `tests/test_v2_test_support.py`

**Step 1:** Write failing tests for a helper that creates an ephemeral P-256 Edge identity, locally provisions its public key, and returns valid `connect`, `auth_proof`, and `capability_announce` frames.

**Step 2:** Run `bin/test -m unittest tests.test_v2_test_support -v` and verify the tests fail because the helper does not exist.

**Step 3:** Implement only the helper functions needed by tests: a stable loopback audience, identity creation, local provisioning, direct Gateway frame authentication, and WebSocket authentication.

**Step 4:** Re-run the new test module and verify it passes without any bearer frame or token argument.

### Task 2: Remove bearer arguments from Edge and local CLI fixtures

**Files:**
- Modify: `device_edge/cli/cli_edge.py`
- Modify: `tests/test_edge_client_v0.py`
- Modify: `tests/test_chain_inspection.py`
- Modify: `tests/test_roundtrip_v0.py`

**Step 1:** Write failing tests asserting `run_cli_once`, `inspect_cli_once`, and the WebSocket helper use a v2 identity/audience rather than a `token` parameter.

**Step 2:** Replace token-only local session construction with an isolated pairing store and ephemeral Edge identity. Preserve the existing trace and inspection contracts.

**Step 3:** Migrate `SessionClient`, `EdgeSessionLink`, `TerminalEdgeDaemon`, and `HostEdgeDaemon` fixtures to `audience` plus P-256 identity.

**Step 4:** Run `bin/test -m unittest tests.test_edge_client_v0 tests.test_chain_inspection -v` and verify the migrated modules pass.

### Task 3: Migrate Gateway direct-frame regressions

**Files:**
- Modify: `tests/test_gateway_v0.py`
- Modify: `tests/test_interaction_pool.py`
- Modify: `tests/test_interaction_progress.py`
- Modify: `tests/test_runtime_orchestrator.py`
- Modify: `tests/test_runtime_persistence_v0.py`

**Step 1:** Add failing cases in each module that authenticate fixtures through the v2 helper before capability announcement, event injection, or action-result correlation.

**Step 2:** Replace `shared_token`, `auth: {token: ...}`, and single-frame legacy connects with helper-generated v2 authentication sequences.

**Step 3:** Keep negative bearer tests only where they assert explicit rejection; rename their data so it is not used as a happy-path fixture.

**Step 4:** Run the five modules together and resolve only behavior differences caused by the stricter pre-auth/session boundary.

### Task 4: Migrate real WebSocket and Runtime-entrypoint regressions

**Files:**
- Modify: `tests/test_roundtrip_v0.py`
- Modify: `tests/test_runtime_supervisor.py`
- Modify: `tests/test_dev_env_scripts.py`

**Step 1:** Write failing WebSocket tests that explicitly consume `auth_challenge`, send a signed proof, and only then announce capabilities or send events.

**Step 2:** Replace `--token-env` parser expectations and runtime startup arguments with pairing-store and identity-home expectations.

**Step 3:** Re-run all roundtrip/host-managed/runtime-entrypoint tests and verify normal Host Edge traffic still crosses the public WebSocket boundary.

### Task 5: Close the full regression and M20.3 acceptance record

**Files:**
- Modify: `Project.md`

**Step 1:** Run the focused M20.3 suite, then `bin/test -m unittest discover -s tests`.

**Step 2:** Only after full Python regression is green, record the final TUI/line-mode/manual acceptance evidence and remaining Android-environment limitation in `Project.md`.

**Step 3:** Run `git diff --check`, review the diff for bearer/shared-token happy-path remnants, and commit the migration in small reviewable commits.
