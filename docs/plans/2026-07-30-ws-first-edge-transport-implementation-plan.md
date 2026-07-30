# WS-First Edge Transport Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make direct IP `ws://` and `wss://` equally supported Edge transports, make the installed Runtime bind publicly by default, and publish the resulting Runtime so existing installations can use `openhalo update`.

**Architecture:** The Runtime keeps one P-256 public-key identity per paired Edge, but the signed audience becomes the precise endpoint chosen and persisted for that Edge, not one global Gateway URL. This permits a direct-IP `ws://` terminal and a proxy-backed `wss://` phone to coexist while reconnects still reject a changed endpoint. `ws://` is intentionally unauthenticated at the transport layer; pairing, challenge proofs, and revocation remain mandatory.

**Tech Stack:** Python 3.11+, `websockets`, pytest, Android/Kotlin unit tests, GitHub Releases.

### Task 1: Allow complete ws and wss URLs in the shared Python endpoint policy

**Files:**
- Modify: `edge_api/endpoint.py`
- Modify: `tests/test_runtime_endpoint.py`

**Step 1: Write the failing test**

Add public-IP and DNS `ws://` examples to the allow list, and keep `http://`, missing hosts, and malformed URLs in the rejection list.

```python
@pytest.mark.parametrize("url", [
    "ws://198.51.100.15:8765",
    "ws://runtime.example.test/openhalo/edge",
    "wss://runtime.example.test/openhalo/edge",
])
def test_runtime_endpoint_allows_complete_ws_or_wss_urls(url: str) -> None:
    assert validate_runtime_endpoint(url) == url
```

**Step 2: Run the test to verify it fails**

Run: `OPENHALO_TEST_ISOLATION=0 .venv/bin/python -m pytest -q tests/test_runtime_endpoint.py`

Expected: public `ws://` cases fail because the current policy permits loopback only.

**Step 3: Write the minimal implementation**

Accept only `ws` and `wss` schemes with a non-empty parsed hostname. Remove loopback/IP classification and describe the validator as a syntax/policy gate for both supported transports.

**Step 4: Run the test to verify it passes**

Run: `OPENHALO_TEST_ISOLATION=0 .venv/bin/python -m pytest -q tests/test_runtime_endpoint.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add edge_api/endpoint.py tests/test_runtime_endpoint.py
git commit -m "feat: allow ws edge endpoints"
```

### Task 2: Make pairing audience endpoint-specific rather than a Gateway-wide TLS URL

**Files:**
- Modify: `personal_runtime/gateway_server.py:1475-1540`
- Modify: `personal_runtime/main.py:111-151`
- Modify: `tests/test_gateway_v0.py`
- Modify: `tests/test_openhalo_edge_cli.py`

**Step 1: Write the failing tests**

Add a Gateway connect/pairing test where a configured Runtime accepts `ws://198.51.100.15:8765`, records that exact audience for the device, and rejects a later reconnect that presents a different URL. Change the Terminal CLI public-IP `ws://` setup test from a rejection to a successful paired configuration.

```python
assert response["type"] == "auth_challenge"
assert store.get_device("terminal-edge-9")["audience"] == "ws://198.51.100.15:8765"
```

**Step 2: Run the tests to verify they fail**

Run: `OPENHALO_TEST_ISOLATION=0 .venv/bin/python -m pytest -q tests/test_gateway_v0.py tests/test_openhalo_edge_cli.py`

Expected: the Gateway emits `audience_mismatch` before pairing and Terminal setup rejects the public `ws://` URL.

**Step 3: Write the minimal implementation**

Validate every incoming audience with `validate_runtime_endpoint`, then remove only the Gateway-wide equality check. During first pairing persist the supplied endpoint; on a credentialed reconnect keep the existing exact per-device audience comparison. Keep `gateway.audience` only as the managed Host Edge's local endpoint, assigning the loopback-translated server URL after binding when no explicit audience is supplied.

**Step 4: Run the tests to verify they pass**

Run: `OPENHALO_TEST_ISOLATION=0 .venv/bin/python -m pytest -q tests/test_gateway_v0.py tests/test_openhalo_edge_cli.py tests/test_runtime_endpoint.py`

Expected: PASS, including existing signed-authentication and distinct-audience rejection coverage.

**Step 5: Commit**

```bash
git add personal_runtime/gateway_server.py personal_runtime/main.py tests/test_gateway_v0.py tests/test_openhalo_edge_cli.py
git commit -m "feat: pair edges to ws or wss endpoints"
```

### Task 3: Make the installed Runtime's default bind direct-IP capable

**Files:**
- Modify: `openhalo/cli.py:35-42`
- Modify: `tests/test_openhalo_cli.py`
- Modify: `docs/runtime-deploy.md`
- Modify: `README.md`
- Modify: `README.zh-CN.md`

**Step 1: Write the failing test**

Add an `openhalo setup` test with no host argument and assert that its saved configuration and output use `0.0.0.0` with port `8765`.

```python
exit_code, output = _run(home, "setup")
assert json.loads(output) == {"host": "0.0.0.0", "port": 8765, "state": "configured"}
```

**Step 2: Run the test to verify it fails**

Run: `OPENHALO_TEST_ISOLATION=0 .venv/bin/python -m pytest -q tests/test_openhalo_cli.py`

Expected: the current default is `127.0.0.1`.

**Step 3: Write the minimal implementation**

Set the owner-facing `openhalo setup --host` default to `0.0.0.0`; keep `--host 127.0.0.1` as an explicit local-only choice and leave repository development entrypoints unchanged. Replace the reverse-proxy/domain-first deployment instructions with direct `ws://<server-ip>:8765` setup, preserving `wss://` as a compatible optional URL. Explain that an existing installation must run `openhalo setup` once after updating to adopt the new bind default.

**Step 4: Run the tests to verify they pass**

Run: `OPENHALO_TEST_ISOLATION=0 .venv/bin/python -m pytest -q tests/test_openhalo_cli.py tests/test_runtime_supervisor.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add openhalo/cli.py tests/test_openhalo_cli.py README.md README.zh-CN.md docs/runtime-deploy.md
git commit -m "feat: bind installed runtimes publicly by default"
```

### Task 4: Remove Android stable-mode TLS rejection while retaining URL validation

**Files:**
- Modify: `device_edge/android_edge/app/src/main/java/dev/openhalo/android/edge/EdgeApiFrames.kt:107-128`
- Modify: `device_edge/android_edge/app/src/test/java/dev/openhalo/android/edge/EdgeApiFramesTest.kt:83-112`
- Modify: Android user-facing endpoint copy if it still states a TLS-only requirement

**Step 1: Write the failing Kotlin tests**

Change stable-mode expectations so both `ws://198.51.100.15:8765` and `wss://runtime.example/openhalo/edge` are accepted. Preserve rejections for non-WebSocket schemes, malformed URLs, and empty hosts.

```kotlin
assertTrue(pairingTransportAllowed(RUNTIME_MODE_STABLE, "ws://198.51.100.15:8765"))
assertNull(runtimeUrlValidationError(RUNTIME_MODE_STABLE, "ws://198.51.100.15:8765"))
```

**Step 2: Run the test to verify it fails**

Run: `cd device_edge/android_edge && ./gradlew testDebugUnitTest --tests '*EdgeApiFramesTest'`

Expected: the stable `ws://` assertions fail because the current code demands `wss://`.

**Step 3: Write the minimal implementation**

Make transport acceptance depend only on the existing complete `ws`/`wss` URL validation. Remove the stable-mode `wss` error branch without adding a replacement mode or token path.

**Step 4: Run the test to verify it passes**

Run: `cd device_edge/android_edge && ./gradlew testDebugUnitTest --tests '*EdgeApiFramesTest'`

Expected: PASS; if the local Android SDK is unavailable, record that limitation and preserve the source-level unit test change for CI/device verification.

**Step 5: Commit**

```bash
git add device_edge/android_edge/app/src/main/java/dev/openhalo/android/edge/EdgeApiFrames.kt device_edge/android_edge/app/src/test/java/dev/openhalo/android/edge/EdgeApiFramesTest.kt
git commit -m "feat: allow ws mobile edge pairing"
```

### Task 5: Verify the integrated owner path and publish an updateable Runtime Release

**Files:**
- Modify: `Project.md`
- Create: `dist/release-v0.1.1/` (ignored release assets)

**Step 1: Run focused verification**

Run:

```bash
OPENHALO_TEST_ISOLATION=0 .venv/bin/python -m pytest -q \
  tests/test_runtime_endpoint.py \
  tests/test_openhalo_edge_cli.py \
  tests/test_openhalo_cli.py \
  tests/test_runtime_supervisor.py \
  tests/test_gateway_v0.py
```

Expected: PASS. Run the Android unit command when the SDK is available.

**Step 2: Record acceptance status**

Update `Project.md` with the ws/wss implementation and direct-IP acceptance evidence; do not mark M20.3 or M22 fully accepted while their remaining gates are open.

**Step 3: Build and validate immutable assets**

After merging to `master`, create tag `v0.1.1`, build from its exact 40-character commit with `scripts/build_release.py`, and compare the manifest, `SHA256SUMS`, and downloaded archive SHA-256.

**Step 4: Publish and make the live update available**

Create a stable GitHub Release with exactly the Runtime archive, manifest, and checksum assets. On the existing `v0.1.0` installed Runtime run only `openhalo update --check` and assert it reports `update_available` for `v0.1.1`; the owner performs the mutating `openhalo update` command personally.

**Step 5: Commit**

```bash
git add Project.md
git commit -m "docs: record ws first runtime release"
```
