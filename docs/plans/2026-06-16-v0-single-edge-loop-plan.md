# V0 Single-Edge Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the first usable product slice: one desktop/CLI edge device connects to the backend runtime, registers capabilities, sends text input as an event, receives a generated response, and executes a local notification action.

**Architecture:** Keep v0 intentionally narrow. Use one long-lived WebSocket path between a single edge client and a single backend runtime. Model the backend with the agreed architecture shape, but implement the smallest viable versions of `Gateway`, `State / Context / Task`, a minimal `Agent Runtime` with an embedded same-device presence rule, and `Action Layer`. Model the frontend as one CLI-based `Device Edge` with a minimal capability runtime and local action executor.

**Tech Stack:** Python 3.11+, `asyncio`, `websockets`, `unittest`

---

## Recommended v0 Scope

### User-visible flow

1. Start the backend runtime server.
2. Start one CLI edge client on the same machine.
3. The edge client authenticates and connects to the backend.
4. The edge client registers one device and two capabilities:
   - `text.input`
   - `notification.show`
5. A user types text into the CLI edge.
6. The edge sends a normalized event to the backend.
7. The backend records the event, creates a task record, picks the same source device as the response target, generates a reply, and sends an action request back.
8. The edge executes `notification.show` locally by printing the response and returns an action result.

### Explicitly out of scope for v0

- multi-device routing
- camera or microphone ingestion
- persistence beyond process memory
- OpenClaw code extraction
- mobile clients
- true proactive presence behavior
- complex auth beyond a single shared dev token

## Minimal Product Checklist

### Backend

- WebSocket gateway endpoint
- shared-token auth check
- `connect` handshake
- device registration in memory
- capability registration in memory
- normalized event intake
- in-memory state and task store
- same-device response routing rule
- simple response generator
- action request dispatch
- action result handling

### Frontend / Device Edge

- long-lived session client
- reconnect loop
- CLI text input surface
- local capability registry
- event send path for `text.input`
- local action executor for `notification.show`
- action result send path

### Shared Protocol

- `connect`
- `connect_ok`
- `capability_announce`
- `event_push`
- `event_ack`
- `action_request`
- `action_result`
- `error`

## File Layout

### Create

- `pyproject.toml`
- `personal_runtime/__init__.py`
- `personal_runtime/protocol.py`
- `personal_runtime/runtime_state.py`
- `personal_runtime/presence_router.py`
- `personal_runtime/agent_executor.py`
- `personal_runtime/action_layer.py`
- `personal_runtime/gateway_server.py`
- `personal_runtime/main.py`
- `device_edge/__init__.py`
- `device_edge/session_client.py`
- `device_edge/capability_runtime.py`
- `device_edge/local_actions.py`
- `device_edge/cli_edge.py`
- `tests/test_protocol_v0.py`
- `tests/test_runtime_state_v0.py`
- `tests/test_gateway_v0.py`
- `tests/test_edge_client_v0.py`
- `tests/test_roundtrip_v0.py`

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `personal_runtime/__init__.py`
- Create: `device_edge/__init__.py`

**Step 1: Write the failing scaffold smoke test**

```python
import importlib
import unittest


class ImportSmokeTests(unittest.TestCase):
    def test_runtime_package_imports(self) -> None:
        self.assertIsNotNone(importlib.import_module("personal_runtime"))
        self.assertIsNotNone(importlib.import_module("device_edge"))
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_protocol_v0.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```toml
[project]
name = "personal-runtime-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["websockets>=12,<16"]
```

```python
# personal_runtime/__init__.py
"""Personal runtime v0 package."""
```

```python
# device_edge/__init__.py
"""Device edge v0 package."""
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_protocol_v0.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add pyproject.toml personal_runtime/__init__.py device_edge/__init__.py tests/test_protocol_v0.py
git commit -m "chore: scaffold v0 runtime packages"
```

## Task 2: Shared Protocol

**Files:**
- Create: `personal_runtime/protocol.py`
- Test: `tests/test_protocol_v0.py`

**Step 1: Write the failing protocol test**

```python
import unittest

from personal_runtime.protocol import build_connect_frame, validate_frame


class ProtocolTests(unittest.TestCase):
    def test_builds_connect_frame(self) -> None:
        frame = build_connect_frame(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
        )
        self.assertEqual(frame["type"], "connect")
        self.assertEqual(frame["device"]["device_id"], "desktop-dev-1")

    def test_rejects_frame_without_type(self) -> None:
        with self.assertRaises(ValueError):
            validate_frame({"device": {}})
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_protocol_v0.py -v`
Expected: FAIL with `ImportError` or missing functions

**Step 3: Write minimal implementation**

```python
REQUIRED_TYPES = {
    "connect",
    "connect_ok",
    "capability_announce",
    "event_push",
    "event_ack",
    "action_request",
    "action_result",
    "error",
}


def validate_frame(frame: dict) -> dict:
    frame_type = frame.get("type")
    if frame_type not in REQUIRED_TYPES:
        raise ValueError(f"Unsupported frame type: {frame_type!r}")
    return frame


def build_connect_frame(device_id: str, device_type: str, token: str) -> dict:
    return {
        "type": "connect",
        "device": {
            "device_id": device_id,
            "device_type": device_type,
        },
        "auth": {"token": token},
    }
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_protocol_v0.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add personal_runtime/protocol.py tests/test_protocol_v0.py
git commit -m "feat: add v0 gateway protocol frames"
```

## Task 3: Runtime State And Presence Stub

**Files:**
- Create: `personal_runtime/runtime_state.py`
- Create: `personal_runtime/presence_router.py`
- Test: `tests/test_runtime_state_v0.py`

**Step 1: Write the failing state test**

```python
import unittest

from personal_runtime.presence_router import choose_response_device
from personal_runtime.runtime_state import RuntimeState


class RuntimeStateTests(unittest.TestCase):
    def test_registers_device_and_capability(self) -> None:
        state = RuntimeState()
        state.register_device("desktop-dev-1", "desktop-cli")
        state.register_capability("desktop-dev-1", "text.input")
        self.assertIn("desktop-dev-1", state.devices)
        self.assertIn("text.input", state.devices["desktop-dev-1"]["capabilities"])

    def test_presence_defaults_to_source_device(self) -> None:
        target = choose_response_device(source_device_id="desktop-dev-1")
        self.assertEqual(target, "desktop-dev-1")
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_runtime_state_v0.py -v`
Expected: FAIL with missing modules

**Step 3: Write minimal implementation**

```python
class RuntimeState:
    def __init__(self) -> None:
        self.devices = {}
        self.events = []
        self.tasks = []

    def register_device(self, device_id: str, device_type: str) -> None:
        self.devices.setdefault(
            device_id,
            {"device_type": device_type, "capabilities": set()},
        )

    def register_capability(self, device_id: str, capability_name: str) -> None:
        self.devices[device_id]["capabilities"].add(capability_name)
```

```python
def choose_response_device(source_device_id: str) -> str:
    return source_device_id
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_runtime_state_v0.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add personal_runtime/runtime_state.py personal_runtime/presence_router.py tests/test_runtime_state_v0.py
git commit -m "feat: add v0 runtime state and presence stub"
```

## Task 4: Backend Gateway And Action Pipeline

**Files:**
- Create: `personal_runtime/agent_executor.py`
- Create: `personal_runtime/action_layer.py`
- Create: `personal_runtime/gateway_server.py`
- Create: `personal_runtime/main.py`
- Test: `tests/test_gateway_v0.py`

**Step 1: Write the failing gateway test**

```python
import asyncio
import unittest

from personal_runtime.gateway_server import RuntimeGateway


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_connect_event_and_action_roundtrip(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token")
        reply = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {"device_id": "desktop-dev-1", "device_type": "desktop-cli"},
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "hello"},
                },
            ]
        )
        self.assertEqual(reply[-1]["type"], "action_request")
        self.assertEqual(reply[-1]["action"]["capability"], "notification.show")
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_gateway_v0.py -v`
Expected: FAIL with missing gateway implementation

**Step 3: Write minimal implementation**

```python
def generate_reply(user_text: str) -> str:
    return f"Runtime heard: {user_text}"
```

```python
def build_notification_action(target_device_id: str, message: str) -> dict:
    return {
        "type": "action_request",
        "device_id": target_device_id,
        "action": {
            "capability": "notification.show",
            "payload": {"message": message},
        },
    }
```

```python
class RuntimeGateway:
    def __init__(self, shared_token: str) -> None:
        self.shared_token = shared_token
        self.state = RuntimeState()

    async def handle_test_frames(self, frames: list[dict]) -> list[dict]:
        replies = []
        for frame in frames:
            if frame["type"] == "connect":
                if frame["auth"]["token"] != self.shared_token:
                    replies.append({"type": "error", "message": "unauthorized"})
                    continue
                self.state.register_device(
                    frame["device"]["device_id"],
                    frame["device"]["device_type"],
                )
                replies.append({"type": "connect_ok"})
            elif frame["type"] == "capability_announce":
                for name in frame["capabilities"]:
                    self.state.register_capability(frame["device_id"], name)
            elif frame["type"] == "event_push":
                text = frame["payload"]["text"]
                target = choose_response_device(frame["device_id"])
                replies.append({"type": "event_ack"})
                replies.append(
                    build_notification_action(
                        target,
                        generate_reply(text),
                    )
                )
        return replies
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_gateway_v0.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add personal_runtime/agent_executor.py personal_runtime/action_layer.py personal_runtime/gateway_server.py personal_runtime/main.py tests/test_gateway_v0.py
git commit -m "feat: add v0 backend gateway loop"
```

## Task 5: Edge Client And Local Action Execution

**Files:**
- Create: `device_edge/session_client.py`
- Create: `device_edge/capability_runtime.py`
- Create: `device_edge/local_actions.py`
- Create: `device_edge/cli_edge.py`
- Test: `tests/test_edge_client_v0.py`

**Step 1: Write the failing edge client test**

```python
import unittest

from device_edge.capability_runtime import CapabilityRuntime
from device_edge.local_actions import execute_action


class EdgeClientTests(unittest.TestCase):
    def test_registers_minimal_capabilities(self) -> None:
        runtime = CapabilityRuntime()
        self.assertEqual(
            runtime.capabilities,
            ["text.input", "notification.show"],
        )

    def test_executes_notification_action(self) -> None:
        result = execute_action(
            {"capability": "notification.show", "payload": {"message": "hello"}}
        )
        self.assertEqual(result["status"], "ok")
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_edge_client_v0.py -v`
Expected: FAIL with missing edge modules

**Step 3: Write minimal implementation**

```python
class CapabilityRuntime:
    def __init__(self) -> None:
        self.capabilities = ["text.input", "notification.show"]
```

```python
def execute_action(action: dict) -> dict:
    capability = action["capability"]
    if capability != "notification.show":
        return {"status": "error", "reason": "unsupported"}
    print(action["payload"]["message"])
    return {"status": "ok"}
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_edge_client_v0.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add device_edge/session_client.py device_edge/capability_runtime.py device_edge/local_actions.py device_edge/cli_edge.py tests/test_edge_client_v0.py
git commit -m "feat: add v0 device edge client"
```

## Task 6: End-To-End Roundtrip

**Files:**
- Test: `tests/test_roundtrip_v0.py`
- Modify: `personal_runtime/gateway_server.py`
- Modify: `device_edge/session_client.py`
- Modify: `device_edge/cli_edge.py`

**Step 1: Write the failing roundtrip test**

```python
import asyncio
import unittest

from personal_runtime.gateway_server import RuntimeGateway
from device_edge.local_actions import execute_action


class RoundtripTests(unittest.IsolatedAsyncioTestCase):
    async def test_user_text_roundtrips_back_to_same_edge(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token")
        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {"device_id": "desktop-dev-1", "device_type": "desktop-cli"},
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "status?"},
                },
            ]
        )
        action = replies[-1]["action"]
        result = execute_action(action)
        self.assertEqual(result["status"], "ok")
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_roundtrip_v0.py -v`
Expected: FAIL until previous pieces are wired together

**Step 3: Write minimal implementation**

Implement any missing glue so that:

- the edge client announces both capabilities after connect
- a text event can be emitted from the CLI edge runtime
- the backend creates an `action_request`
- the edge executes the action and can return an `action_result`

**Step 4: Run test suite to verify it passes**

Run: `python -m unittest -v`
Expected: PASS for existing hook tests plus all new v0 tests

**Step 5: Commit**

```bash
git add personal_runtime/gateway_server.py device_edge/session_client.py device_edge/cli_edge.py tests/test_roundtrip_v0.py
git commit -m "feat: complete v0 single-edge roundtrip"
```

## Manual Verification

After the tests pass, verify the product manually:

1. Start the backend:

```bash
python -m personal_runtime.main
```

2. Start the edge client:

```bash
python -m device_edge.cli.cli_edge
```

3. Type a line of input such as:

```text
hello runtime
```

4. Confirm:

- the edge reports connected
- the backend acknowledges the event
- the edge prints or displays the generated response

## Notes

- Keep auth intentionally simple in v0: one shared local development token.
- Keep presence routing intentionally trivial in v0: always respond on the source device.
- Keep state intentionally in memory for v0.
- Do not add persistence, camera, microphone, or multi-device routing until this loop works end-to-end.

## Immediate Step 2 After V0

Once the single-edge loop works end-to-end, the next recommended slice should stay small but become more product-representative.

### Goal

Prove that the system is becoming a personal runtime rather than just a chat loop with device transport.

### Additions

- add minimal persistence for device registration and recent event history
- add one second surface or second device so routing crosses a real boundary
- add one non-text capability so the system is not only a text roundtrip

### Recommended Step 2 candidate

The simplest useful follow-up is:

- keep the existing desktop/CLI edge
- add a second surface such as a lightweight viewer or second local edge process
- persist registered devices plus a small recent event log
- add one simple non-text capability such as `notification.tap`, `clipboard.read`, `file.watch`, or a minimal sensor-style event

### What this proves

- runtime continuity survives beyond one in-memory exchange
- the backend can route across more than one surface
- the capability model is not limited to text chat
- the project starts to demonstrate personal-runtime behavior rather than only transport correctness
