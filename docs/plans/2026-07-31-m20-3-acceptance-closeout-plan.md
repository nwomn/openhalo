# M20.3 Acceptance Closeout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Close the remaining automated and human-acceptance gates for the M20.3 Quiet Edge milestone without reintroducing legacy bearer authentication.

**Architecture:** The Terminal Edge remains a normal P-256-authenticated Device Edge. The legacy real-WebSocket regression suite must use the same paired `Edge Session Link -> Gateway` proof ceremony as a product Edge, including the Runtime-managed Host Edge. Human acceptance uses an isolated owner-state home and configured Provider, so it tests the public interaction path and Quiet Edge presentation rather than a deterministic fixture.

**Tech Stack:** Python 3.12, unittest/pytest, `websockets`, Textual, OpenHalo `edge.runtime.v2` P-256 pairing.

### Task 1: Record the v2 regression migration contract

**Files:**
- Modify: `tests/test_roundtrip_v0.py`
- Reuse: `tests/v2_test_support.py`

**Step 1: Write the failing migrated real-WebSocket test setup**

Replace one legacy direct `connect`/token setup with a provisioned `TestEdge` that sends a connect frame, receives `auth_challenge`, returns its P-256 proof, then announces capabilities.

**Step 2: Run it to verify the historical test fails**

Run: `.venv/bin/python -m pytest -q tests/test_roundtrip_v0.py`

Expected: the remaining legacy tests fail with `pairing_required`, old `token` constructor arguments, or post-connect authentication errors.

**Step 3: Apply the smallest shared test helpers needed**

Use `build_test_edge`, `provision_test_edge`, and the existing SessionClient WebSocket proof methods. Do not add production bearer compatibility or weaken the Runtime pairing gate.

**Step 4: Run the focused file**

Run: `.venv/bin/python -m pytest -q tests/test_roundtrip_v0.py`

Expected: all real-WebSocket cases pass through P-256 authentication.

### Task 2: Migrate managed Host Edge real-WebSocket cases

**Files:**
- Modify: `tests/test_roundtrip_v0.py`
- Reuse: `device_edge/host/host_daemon.py`, `tests/v2_test_support.py`

**Step 1: Write the failing Host setup using a deterministic ephemeral identity**

Replace each removed `token=` argument with `identity=` and `audience=`, and provision its public key in the test Runtime PairingStore before the daemon connects.

**Step 2: Run the focused Host tests to verify the expected old-constructor failure**

Run: `.venv/bin/python -m pytest -q tests/test_roundtrip_v0.py -k 'host_edge or runtime_status'

Expected: failure before migration because `HostEdgeDaemon` no longer accepts bearer credentials.

**Step 3: Apply the minimal v2 setup**

Create one helper local to the test file for a paired Host daemon. Preserve the existing test adapters, event ordering, and assertions.

**Step 4: Run the focused Host tests**

Run: `.venv/bin/python -m pytest -q tests/test_roundtrip_v0.py -k 'host_edge or runtime_status'

Expected: PASS.

### Task 3: Close automated M20.3 regression

**Files:**
- Modify only when test evidence identifies a production defect.
- Test: `tests/test_roundtrip_v0.py`, `tests/test_terminal_daemon_m8.py`, `tests/test_terminal_presentation.py`, `tests/test_terminal_tui_receipt.py`, `tests/test_openhalo_edge_cli.py`

**Step 1: Run the migrated real-WebSocket suite**

Run: `.venv/bin/python -m pytest -q tests/test_roundtrip_v0.py`

Expected: PASS.

**Step 2: Run the M20.3 focused group**

Run: `.venv/bin/python -m pytest -q tests/test_roundtrip_v0.py tests/test_terminal_daemon_m8.py tests/test_terminal_presentation.py tests/test_terminal_tui_receipt.py tests/test_openhalo_edge_cli.py`

Expected: PASS.

**Step 3: Run the repository regression suite**

Run: `.venv/bin/python -m pytest -q`

Expected: PASS; report any failures outside this migration separately rather than masking them.

### Task 4: Prepare product-like Quiet Edge acceptance

**Files:**
- Modify: `docs/plans/2026-07-29-m20-3-terminal-edge-design.md`
- Modify: `Project.md`

**Step 1: Create an isolated Runtime and pairing home**

Use a new temporary `OPENHALO_HOME`, a copied owner `runtime-config.toml`, a new state file, and a loopback `ws://127.0.0.1:<free-port>` endpoint. Never place Provider credentials in the repository, output, or project documentation.

**Step 2: Launch Runtime and pair Terminal Edge**

Run the Runtime with managed Host Edge enabled, create a one-time pairing code, use `openhalo-edge setup`, then start `openhalo-edge run` in a real TTY.

**Step 3: Owner performs the live acceptance**

Verify natural-language reply, Quiet Edge rendering at normal and narrow width, receipt expansion, slow-progress display, reconnect with preserved draft, and `/quit`/Ctrl-C terminal restoration.

**Step 4: Record only outcome evidence**

Update the M20.3 status only after both the all-green full suite and owner-confirmed live TTY acceptance. Record no secrets, raw provider output, private reasoning, or device keys.
