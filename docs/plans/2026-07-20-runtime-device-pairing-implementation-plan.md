# Runtime Device Pairing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let Personal Runtime issue, remember, revoke, and authenticate a distinct credential for each paired Device Edge.

**Architecture:** A Runtime-local pairing registry is independent from the general runtime state snapshot so a local administrator CLI and Gateway can safely coordinate pairing-code issuance. The Edge presents a short-lived `auth.kind = "pairing"` code once; Gateway atomically consumes it, stores only the hash of a new device credential, registers the device through the existing runtime state path, and returns that raw credential in `connect_ok`. Future sessions use `auth.kind = "device"` with the persisted device credential.

**Tech Stack:** Python 3.11+, JSON state files, `fcntl.flock` on the Linux Runtime host, `secrets`, `hashlib`, WebSockets, `unittest`/`pytest`.

## Public Contract

The local Runtime administrator creates a one-time code:

```bash
python -m personal_runtime.pairing_cli create \
  --store /var/lib/openhalo/pairing.json \
  --ttl-seconds 600
```

The first Edge connection uses:

```json
{
  "type": "connect",
  "device": {"device_id": "android-edge-...", "device_type": "android-phone"},
  "auth": {"kind": "pairing", "token": "one-time-code"}
}
```

Gateway returns `connect_ok` plus `auth.kind = "device"` and one raw `token`.
The Edge stores the Runtime URL and this device token locally, then uses the same
device ID and `auth.kind = "device"` for future connects. Pairing must be sent
over `wss://` outside local development; Runtime's loopback Gateway remains
plain WebSocket behind the TLS-terminating proxy.

## Task 1: Durable Pairing Registry

**Files:**
- Create: `personal_runtime/pairing_store.py`
- Create: `tests/test_pairing_store.py`

**Step 1: Write failing tests**

```python
def test_claiming_fresh_code_returns_device_token_and_persists_only_hash(tmp_path):
    store = PairingStore(tmp_path / "pairing.json")
    code = store.create_pairing_code(ttl_seconds=60, now=NOW)
    token = store.claim_pairing_code(code, "phone-1", "android-phone", now=NOW)
    assert token
    assert token not in (tmp_path / "pairing.json").read_text()
```

Cover expiration, one-time consumption, device-token authentication, and
revocation.

**Step 2: Run the new test file and verify RED**

Run: `PYTHONPATH=. ../../.venv/bin/python -m pytest -q tests/test_pairing_store.py`

Expected: import failure because `PairingStore` does not exist.

**Step 3: Implement the minimal registry**

Use random `secrets.token_urlsafe` values; store SHA-256 hashes, timestamps,
device metadata, and revoked state in a mode-0600 JSON file under an exclusive
`fcntl.flock` lock. Reload inside every operation so the local CLI and live
Gateway observe each other's mutations.

**Step 4: Run the registry tests and verify GREEN**

Run: `PYTHONPATH=. ../../.venv/bin/python -m pytest -q tests/test_pairing_store.py`

Expected: PASS.

## Task 2: Runtime-local Pairing Administration

**Files:**
- Create: `personal_runtime/pairing_cli.py`
- Create: `tests/test_pairing_cli.py`

**Step 1: Write failing CLI tests**

Test `create`, `list`, and `revoke` using a temporary registry path. `list`
must expose no raw code or device token.

**Step 2: Run the CLI tests and verify RED**

Run: `PYTHONPATH=. ../../.venv/bin/python -m pytest -q tests/test_pairing_cli.py`

Expected: module entrypoint missing.

**Step 3: Implement the CLI**

Expose `create --store --ttl-seconds`, `list --store`, and `revoke --store
--device-id`. Emit a code only for `create`; all other output is safe metadata.

**Step 4: Run CLI tests and verify GREEN**

Run: `PYTHONPATH=. ../../.venv/bin/python -m pytest -q tests/test_pairing_cli.py`

Expected: PASS.

## Task 3: Gateway Credential Exchange

**Files:**
- Modify: `personal_runtime/gateway_server.py`
- Modify: `personal_runtime/main.py`
- Modify: `tests/test_gateway_v0.py`

**Step 1: Write failing Gateway tests**

Test a successful pairing `connect`, the returned device credential, reconnect
with `auth.kind = "device"`, an expired or consumed code, and a revoked device.
Use real WebSocket coverage for the credential return path.

**Step 2: Run the targeted tests and verify RED**

Run: `PYTHONPATH=. ../../.venv/bin/python -m pytest -q tests/test_gateway_v0.py -k pairing`

Expected: pairing authentication is unsupported.

**Step 3: Implement minimal Gateway integration**

Add an optional pairing-store path to Runtime construction and startup. Resolve
`auth.kind = "pairing"` by claiming a code and return the minted credential in
`connect_ok`; resolve `auth.kind = "device"` by authenticating the stored hash.
Keep the existing untagged shared-token path as explicit legacy/development
compatibility for Host and Terminal edges until they migrate.

**Step 4: Run focused Gateway and roundtrip verification**

Run: `PYTHONPATH=. ../../.venv/bin/python -m pytest -q tests/test_gateway_v0.py tests/test_roundtrip_v0.py`

Expected: PASS.

## Task 4: Integration Documentation and Project Baseline

**Files:**
- Modify: `docs/edge-api.md`
- Modify: `docs/runtime-deploy.md`
- Modify: `Project.md`

**Step 1: Document the Edge handoff**

Specify the pairing request/response fields, persistence expectations, Runtime
CLI, `wss://` production requirement, and credential revocation behavior.

**Step 2: Update the project baseline**

Record the generic Runtime pairing foundation, the accepted legacy compatibility
boundary, and the remaining Android UI/TLS-default work.

**Step 3: Run documentation and focused regression checks**

Run: `git diff --check` and the Task 3 test command.

Expected: no diff errors and passing focused suites.

## Task 5: Review, Commit, and Push

**Files:**
- Verify: all files above

**Step 1: Review the diff for raw credential leakage**

Confirm JSON registry, diagnostics, CLI `list`, and docs never expose device
token values. Only the `create` CLI response and the successful pairing
`connect_ok` may contain a raw secret.

**Step 2: Run final verification**

Run: `PYTHONPATH=. ../../.venv/bin/python -m pytest -q tests/test_pairing_store.py tests/test_pairing_cli.py tests/test_gateway_v0.py tests/test_roundtrip_v0.py`

Expected: PASS.

**Step 3: Commit and push**

```bash
git add personal_runtime tests docs Project.md
git commit -m "feat: add runtime device pairing"
git push -u origin codex/runtime-pairing
```
