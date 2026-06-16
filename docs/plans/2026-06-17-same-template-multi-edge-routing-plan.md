# Same-Template Multi-Edge Routing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prove that two instances of the same edge template can connect to one runtime and route a normal notification action from one device to another.

**Architecture:** Keep the current v0 runtime shape and extend it minimally. Persist device and capability state as before, but add an in-memory live connection registry for WebSocket mode so the gateway can deliver an `action_request` to a different connected device. Keep the direct-action fast path intact and let the normal path use a simple "other connected device with required capability" routing rule before we build richer presence logic.

**Tech Stack:** Python 3.11+, `asyncio`, `websockets`, `unittest`

### Task 1: Document the routing target rule in tests

**Files:**
- Modify: `tests/test_runtime_state_v0.py`
- Modify: `personal_runtime/presence_router.py`

**Step 1: Write the failing test**

```python
def test_presence_prefers_other_device_with_requested_capability(self) -> None:
    devices = {
        "desktop-dev-1": {"capabilities": {"text.input", "notification.show"}},
        "desktop-dev-2": {"capabilities": {"text.input", "notification.show"}},
    }

    target = choose_response_device(
        source_device_id="desktop-dev-1",
        devices=devices,
        required_capability="notification.show",
    )

    self.assertEqual(target, "desktop-dev-2")
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_runtime_state_v0 -v`
Expected: FAIL because `choose_response_device()` does not accept the new routing inputs yet.

**Step 3: Write minimal implementation**

```python
def choose_response_device(
    source_device_id: str,
    devices: dict | None = None,
    required_capability: str | None = None,
) -> str:
    if not devices or not required_capability:
        return source_device_id

    for device_id, payload in devices.items():
        if device_id == source_device_id:
            continue
        if required_capability in payload["capabilities"]:
            return device_id
    return source_device_id
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_runtime_state_v0 -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_runtime_state_v0.py personal_runtime/presence_router.py
git commit -m "feat: add minimal cross-edge routing rule"
```

### Task 2: Prove cross-edge delivery over real WebSockets

**Files:**
- Modify: `tests/test_roundtrip_v0.py`
- Modify: `device_edge/session_client.py`

**Step 1: Write the failing integration test**

```python
async def test_websocket_roundtrip_routes_action_to_other_connected_edge(self) -> None:
    gateway = RuntimeGateway(shared_token="dev-token")
    source = SessionClient("desktop-dev-1", "desktop-cli", "dev-token")
    target = SessionClient("desktop-dev-2", "desktop-cli", "dev-token")

    async with gateway.run_test_server() as server_info:
        ...
        self.assertEqual(action_request["device_id"], "desktop-dev-2")
```

The test should:
- connect both clients
- announce capabilities from both
- send `source.build_text_event("hello routed runtime")`
- assert the source socket gets `event_ack`
- assert the target socket gets the `action_request`
- have the target client execute the action and return `action_result`
- assert the gateway records the result

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_roundtrip_v0.WebSocketRoundtripTests.test_websocket_roundtrip_routes_action_to_other_connected_edge -v`
Expected: FAIL because the gateway currently only replies on the same socket.

**Step 3: Write minimal implementation**

Add:
- a live connection table on `RuntimeGateway`
- connect-time registration of `device_id -> websocket`
- disconnect cleanup in the handler
- a gateway dispatch helper that sends cross-device `action_request` frames to the target socket immediately
- a small helper in `SessionClient` if needed to keep the test readable

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_roundtrip_v0.WebSocketRoundtripTests.test_websocket_roundtrip_routes_action_to_other_connected_edge -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_roundtrip_v0.py device_edge/session_client.py personal_runtime/gateway_server.py
git commit -m "feat: route websocket actions across same-template edges"
```

### Task 3: Protect direct-action and regression behavior

**Files:**
- Modify: `tests/test_gateway_v0.py`
- Modify: `personal_runtime/gateway_server.py`

**Step 1: Write the failing regression test**

```python
async def test_normal_path_can_target_other_device_in_sync_mode(self) -> None:
    ...
    self.assertEqual(replies[-1]["device_id"], "desktop-dev-2")
```

Keep direct-action tests intact and add one sync-mode assertion showing that the ordinary path can now choose another device when state contains a matching peer capability.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_gateway_v0 -v`
Expected: FAIL because sync routing still defaults to the source device.

**Step 3: Write minimal implementation**

Pass the runtime device map into `choose_response_device()` when the normal path builds its notification action.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_gateway_v0 -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_gateway_v0.py personal_runtime/gateway_server.py
git commit -m "test: cover sync cross-edge routing behavior"
```

### Task 4: Full verification and milestone documentation

**Files:**
- Modify: `Project.md`

**Step 1: Update the project baseline**

Record that M2 has started with same-template dual-edge routing and that WebSocket delivery now supports routing an action to a second connected edge instance.

**Step 2: Run full verification**

Run: `.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS

**Step 3: Commit the verified milestone**

```bash
git add Project.md
git commit -m "docs: update progress for multi-edge routing slice"
```
