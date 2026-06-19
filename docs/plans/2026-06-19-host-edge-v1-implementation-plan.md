# Host Edge V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Land the first real host-class edge daemon that reports host and runtime health observations and executes a narrow runtime-scoped control surface against the current Python-process deployment.

**Architecture:** Reuse the existing websocket edge/runtime path instead of inventing a second transport. Keep the contract layer deployment-agnostic by adding host metrics, runtime health, and runtime control on top of the current edge session, while isolating deployment-specific process management inside a replaceable adapter.

**Tech Stack:** Python 3, unittest, existing `personal_runtime` and `device_edge` packages, Linux `/proc` reads for the first host metrics implementation

### Task 1: Make edge capabilities configurable and add observation event builders

**Files:**
- Modify: `device_edge/capability_runtime.py`
- Modify: `device_edge/session_client.py`
- Test: `tests/test_edge_client_v0.py`

**Step 1: Write the failing tests**

Add tests proving:

- `CapabilityRuntime` can accept an injected capability list instead of only the CLI defaults
- `SessionClient` can build an `event_push` frame carrying an explicit `event_id`
- the new observation payload shape contains `payload["observations"]`

Example test shape:

```python
runtime = CapabilityRuntime(
    capabilities=["host.metrics", "runtime.health", "runtime.control"]
)
self.assertEqual(
    runtime.capabilities,
    ["host.metrics", "runtime.health", "runtime.control"],
)

client = SessionClient(
    device_id="host-edge-1",
    device_type="server",
    token="dev-token",
    capabilities=["host.metrics"],
)
frame = client.build_observation_event(
    capability="host.metrics",
    observations=[
        {
            "name": "host.memory_pressure",
            "value": "normal",
            "observed_at": "2026-06-19T09:30:00Z",
            "confidence": 0.9,
        }
    ],
)
self.assertEqual(frame["type"], "event_push")
self.assertEqual(frame["capability"], "host.metrics")
self.assertIn("event_id", frame)
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_edge_client_v0.EdgeClientTests -v`
Expected: FAIL because the capability runtime is hard-coded and `SessionClient` cannot build observation events yet.

**Step 3: Write minimal implementation**

Implement:

- `CapabilityRuntime(capabilities: list[str] | None = None)`
- `SessionClient(..., capabilities: list[str] | None = None)`
- `SessionClient.build_observation_event(...)`

Keep CLI defaults unchanged when no capability override is provided.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_edge_client_v0.EdgeClientTests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_edge_client_v0.py device_edge/capability_runtime.py device_edge/session_client.py
git commit -m "feat: add configurable edge capabilities and observation events"
```

### Task 2: Add host observation collectors

**Files:**
- Create: `device_edge/host_observers.py`
- Test: `tests/test_host_observers.py`

**Step 1: Write the failing tests**

Add tests for two pure collection helpers:

- `build_host_metric_observations(snapshot, observed_at)`
- `build_runtime_health_observations(snapshot, observed_at)`

Use fake snapshots instead of real `/proc` reads in the unit tests.

Example test shape:

```python
observations = build_host_metric_observations(
    {
        "cpu_load_ratio": 0.31,
        "memory_used_bytes": 400,
        "memory_available_bytes": 600,
        "net_rx_bytes": 10,
        "net_tx_bytes": 12,
    },
    observed_at="2026-06-19T09:30:00Z",
)
self.assertEqual(observations[0]["name"], "host.cpu_load_ratio")
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_host_observers -v`
Expected: FAIL because the module does not exist yet.

**Step 3: Write minimal implementation**

Implement:

- small snapshot-to-observation mappers
- one Linux-first reader path for `/proc` data behind helper functions
- explicit `unknown` or `ambiguous` handling only when a required measurement cannot be derived safely

Keep raw OS fields local to the file.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_host_observers -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_host_observers.py device_edge/host_observers.py
git commit -m "feat: add host and runtime observation collectors"
```

### Task 3: Add the runtime-control adapter interface and Python-process adapter

**Files:**
- Create: `device_edge/runtime_control.py`
- Test: `tests/test_runtime_control.py`

**Step 1: Write the failing tests**

Add tests proving:

- `runtime.status` returns a structured `details` payload
- `runtime.collect_logs` returns structured `entries` plus `tail_text`
- `runtime.reload` returns `unsupported` when no reload command exists
- `runtime.restart` returns `accepted` with `handoff_expected=True`

Example test shape:

```python
adapter = PythonProcessAdapter(
    process_match_substring="personal_runtime.main",
    start_command=["python", "-m", "personal_runtime.main"],
    log_path=None,
)
result = adapter.execute({"capability": "runtime.reload", "payload": {}})
self.assertEqual(result["status"], "unsupported")
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_runtime_control -v`
Expected: FAIL because the adapter module does not exist yet.

**Step 3: Write minimal implementation**

Implement:

- a deployment-agnostic adapter interface
- a `PythonProcessAdapter` that uses explicit local config
- process matching by configured substring only
- structured return payloads for `status`, `restart`, `reload`, and `collect_logs`

Do not implement arbitrary shell passthrough.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_runtime_control -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_runtime_control.py device_edge/runtime_control.py
git commit -m "feat: add runtime control adapter and python process backend"
```

### Task 4: Add the independent host-edge daemon loop

**Files:**
- Create: `device_edge/host_daemon.py`
- Modify: `device_edge/session_client.py`
- Test: `tests/test_host_daemon_v1.py`

**Step 1: Write the failing tests**

Add tests proving:

- the daemon sends connect and capability announce once
- the daemon can emit initial `host.metrics` and `runtime.health` observation events
- the daemon can handle a `runtime.status` action request and return a structured `action_result`

Example test shape:

```python
daemon = HostEdgeDaemon(
    device_id="host-edge-1",
    token="dev-token",
    runtime_control_adapter=fake_adapter,
    host_metrics_provider=fake_metrics,
    runtime_health_provider=fake_health,
)
bootstrap_frames = daemon.build_bootstrap_frames()
self.assertEqual(bootstrap_frames[0]["type"], "connect")
self.assertEqual(bootstrap_frames[1]["type"], "capability_announce")
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_host_daemon_v1 -v`
Expected: FAIL because the daemon module does not exist yet.

**Step 3: Write minimal implementation**

Implement:

- a long-lived host-edge daemon object
- bootstrap frame builders
- one observation cycle helper
- action handling for `runtime.control`
- a reconnect-friendly loop boundary that does not assume runtime availability is continuous

Keep the manual CLI entrypoint in the same file for the first slice.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_host_daemon_v1 -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_host_daemon_v1.py device_edge/host_daemon.py device_edge/session_client.py
git commit -m "feat: add independent host edge daemon"
```

### Task 5: Record host observations in runtime state with provenance

**Files:**
- Modify: `personal_runtime/gateway_server.py`
- Modify: `personal_runtime/runtime_state.py`
- Test: `tests/test_gateway_v0.py`

**Step 1: Write the failing tests**

Add tests proving:

- `event_push` frames with `payload["observations"]` are stored in raw event history
- each normalized observation is recorded in `state.observations`
- provenance uses the enclosing `device_id`, `capability`, and `event_id`

Example test shape:

```python
replies = gateway.run_roundtrip(
    [
        host_client.build_connect_frame(),
        host_client.build_capability_announce_frame(),
        host_client.build_observation_event(
            capability="runtime.health",
            observations=[
                {
                    "name": "runtime.health_state",
                    "value": "healthy",
                    "observed_at": "2026-06-19T09:30:00Z",
                    "confidence": 0.9,
                }
            ],
        ),
    ]
)
self.assertEqual(replies[-1]["type"], "event_ack")
self.assertEqual(gateway.state.observations[-1].name, "runtime.health_state")
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_gateway_v0 -v`
Expected: FAIL because the gateway only stores raw events today.

**Step 3: Write minimal implementation**

Implement:

- observation extraction from `event_push` payloads
- `RuntimeObservation` creation with provenance
- a small `record_observations` helper if the state API becomes clearer that way

Keep raw event history and normalized observation storage both enabled.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_gateway_v0 -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_gateway_v0.py personal_runtime/gateway_server.py personal_runtime/runtime_state.py
git commit -m "feat: record host observations with runtime provenance"
```

### Task 6: Add end-to-end host-edge control and restart-recovery tests

**Files:**
- Modify: `tests/test_roundtrip_v0.py`
- Modify: `device_edge/host_daemon.py`
- Optionally modify: `device_edge/runtime_control.py`

**Step 1: Write the failing tests**

Add integration tests proving:

- a connected host edge can receive `runtime.status` and return structured data over the real websocket path
- a simulated `runtime.restart` returns `accepted`
- later `runtime.health` observations can confirm recovery after the disruptive action

Use a fake adapter in tests instead of actually killing the test runtime process.

Example test shape:

```python
result = await host_daemon.handle_action_request(
    {
        "type": "action_request",
        "device_id": "host-edge-1",
        "action": {"capability": "runtime.restart", "payload": {}},
    }
)
self.assertEqual(result["result"]["status"], "accepted")
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_roundtrip_v0 -v`
Expected: FAIL because the host-edge control path does not exist yet.

**Step 3: Write minimal implementation**

Implement:

- end-to-end wiring for host-edge control actions
- reconnect-safe health re-observation after a restart handoff
- trace lines that make the restart flow inspectable in manual demos

Do not try to implement whole-host remediation or arbitrary process control in this slice.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_roundtrip_v0 -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_roundtrip_v0.py device_edge/host_daemon.py device_edge/runtime_control.py
git commit -m "feat: add host edge runtime control roundtrip"
```

### Task 7: Document the landed host-edge slice

**Files:**
- Modify: `Project.md`
- Optionally modify: `docs/plans/2026-06-19-host-edge-v1-design.md`

**Step 1: Write the update**

Document:

- which host-edge capabilities actually landed
- whether the first adapter is still Python-process only
- which runtime control actions are implemented versus `unsupported`
- what tests and manual demo path now exist

**Step 2: Review for consistency**

Check that `Project.md` matches the final implementation and does not over-claim whole-host operational control.

**Step 3: Commit**

```bash
git add Project.md docs/plans/2026-06-19-host-edge-v1-design.md
git commit -m "docs: record first host edge slice"
```
