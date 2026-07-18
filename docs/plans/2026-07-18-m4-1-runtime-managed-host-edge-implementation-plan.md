# M4.1 Runtime-Managed Host Edge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Start, supervise, diagnose, and stop one colocated Host Edge from the Personal Runtime without bypassing the public Edge API.

**Architecture:** Add a Runtime-owned supervisor in `personal_runtime` that creates an ordinary `HostEdgeDaemon` and connects it to the already-listening Gateway through its loopback WebSocket URL. The supervisor is the only lifecycle owner: it records redacted lifecycle state in `RuntimeState`, performs bounded exponential retry with jitter, and cancels its current edge session before Gateway shutdown. `device_edge` remains independent from `personal_runtime`; its daemon still performs normal registration, capability announcement, observations, actions, and action results over Edge API frames.

**Tech Stack:** Python 3.11+, `asyncio`, `websockets`, `unittest`, existing `RuntimeGateway`, `HostEdgeDaemon`, `RuntimeState`, and JSON state persistence.

### Task 1: Add persisted, redacted managed-host lifecycle state

**Files:**
- Modify: `personal_runtime/runtime_state.py`
- Test: `tests/test_runtime_state_v0.py`

**Step 1: Write the failing test**

Add a `RuntimeState` round-trip test that records a managed Host Edge status and asserts that state, retry count, safe failure class, timestamp, and next retry delay persist. Include a token-like field in the input and assert it is not serialized.

```python
state.record_managed_host_edge_status(
    state="retrying",
    retry_attempt=2,
    latest_failure_class="ConnectionRefusedError",
    next_retry_delay_s=1.25,
    token="must-not-persist",
)
payload = state.to_dict()
self.assertEqual(payload["managed_host_edge"]["state"], "retrying")
self.assertNotIn("token", payload["managed_host_edge"])
```

**Step 2: Run the test to verify it fails**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_runtime_state_v0.RuntimeStateTests.test_managed_host_edge_status_round_trips_without_secrets -v`

Expected: FAIL because `RuntimeState` has no managed Host Edge status surface.

**Step 3: Write the minimal implementation**

Add `managed_host_edge: dict` to `RuntimeState`, a narrow `record_managed_host_edge_status(...)` method, and `to_dict` / `from_dict` support. Persist only state, retry metadata, timestamps, and exception class names; never accept or persist URL, token, exception message, credentials, or raw frames.

**Step 4: Run the test to verify it passes**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_runtime_state_v0.RuntimeStateTests.test_managed_host_edge_status_round_trips_without_secrets -v`

Expected: PASS.

### Task 2: Write failing supervisor lifecycle tests

**Files:**
- Create: `tests/test_managed_host_edge_supervisor.py`
- Create: `personal_runtime/managed_host_edge.py`

**Step 1: Write the failing tests**

Cover the M4.1 lifecycle contract with a fake Host Edge session factory and injected `sleep` / jitter sources:

- `start()` creates exactly one background supervisor task and records `starting`.
- a connection failure records `retrying`, retries after bounded exponential backoff plus bounded jitter, and does not terminate the Runtime.
- a successful `on_connected` signal records `connected` and resets failure backoff so the next disconnect retries at the initial delay.
- delayed Gateway readiness recovers without creating a second edge session.
- `stop()` cancels an active session, records `disconnected`, and leaves no supervisor task or reconnect sleep running.

```python
supervisor = ManagedHostEdgeSupervisor(
    gateway=gateway,
    daemon_factory=lambda: daemon,
    sleep=fake_sleep,
    jitter_source=lambda: 0.5,
)
await supervisor.start()
await wait_until(lambda: len(session_calls) == 2)
await supervisor.stop()
self.assertEqual(gateway.state.managed_host_edge["state"], "disconnected")
self.assertIsNone(supervisor.task)
```

**Step 2: Run the tests to verify they fail**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_managed_host_edge_supervisor -v`

Expected: FAIL because the supervisor module does not exist.

### Task 3: Implement one Runtime-owned Host Edge supervisor

**Files:**
- Create: `personal_runtime/managed_host_edge.py`
- Modify: `device_edge/host/host_daemon.py`
- Test: `tests/test_managed_host_edge_supervisor.py`

**Step 1: Write the minimal implementation**

Create `ManagedHostEdgeSupervisor` with `start()` and `stop()` ownership methods. Its loop must invoke the existing `HostEdgeDaemon.run_websocket_daemon_session(...)` with the Gateway's loopback URL and no bounded session limits. Add only an `on_connected` callback parameter to the daemon session method so the supervisor can transition to `connected` after the normal Edge API connect acknowledgement.

Use this retry calculation after each failed session:

```python
base_delay = min(
    initial_delay_s * backoff_multiplier ** consecutive_failures,
    max_delay_s,
)
delay = min(base_delay + jitter_source() * max_jitter_s, max_delay_s)
```

On a successful connection, reset `consecutive_failures` before any later disconnect. Treat cancellation as normal shutdown; safe failure diagnostics contain only exception class names. The supervisor must own one task and one current session at most.

**Step 2: Run focused tests to verify they pass**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_managed_host_edge_supervisor tests.test_host_daemon_v1 -v`

Expected: PASS. Existing standalone daemon behavior remains covered while the managed supervisor proves failure, recovery, reset, and cancellation behavior.

### Task 4: Start and stop the supervisor from the Runtime entrypoint

**Files:**
- Modify: `personal_runtime/main.py`
- Modify: `tests/test_roundtrip_v0.py`
- Test: `tests/test_roundtrip_v0.py`

**Step 1: Write the failing tests**

Test that `run_server(...)` creates and starts the supervisor only after `gateway.run_server(...)` has yielded a loopback URL, stops it before leaving the Gateway context, and accepts an explicit disabled option. Test the parser defaults to enabled and that `--disable-host-edge` is an opt-out.

```python
await run_server(
    host="127.0.0.1",
    port=8765,
    token="dev-token",
    state_path=Path(".runtime/test.json"),
    manage_host_edge=True,
    host_edge_supervisor_factory=fake_factory,
)
self.assertEqual(events, ["gateway_ready", "supervisor_start", "supervisor_stop"])
```

**Step 2: Run the tests to verify they fail**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_roundtrip_v0.CliEntryTests -v`

Expected: FAIL because Runtime startup has no managed Host Edge lifecycle.

**Step 3: Write the minimal implementation**

Extend `run_server(...)` with internal, injectable supervisor construction for tests. Build the normal host daemon from `read_host_metric_snapshot`, `PythonProcessAdapter`, and `build_runtime_health_provider`, using the Runtime token only in memory. Add parser options:

- `--disable-host-edge`
- `--host-edge-device-id` (default `host-edge-1`)
- `--host-edge-idle-timeout` (default `30.0`)

Start the supervisor immediately after the Gateway is listening and stop it in a `finally` block before closing that Gateway. Do not add a private Runtime-to-edge invocation path.

**Step 4: Run focused tests to verify they pass**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_roundtrip_v0.CliEntryTests tests.test_managed_host_edge_supervisor -v`

Expected: PASS.

### Task 5: Prove the managed edge uses the public API end to end

**Files:**
- Modify: `tests/test_roundtrip_v0.py`
- Test: `tests/test_roundtrip_v0.py`

**Step 1: Write the failing integration test**

Start only `RuntimeGateway.run_server(...)` and the managed supervisor, wait for `host-edge-1` in `gateway.live_connections`, then connect a normal `SessionClient` terminal edge. Send the normal direct `runtime.status` request and assert that the Host Edge returns an `action_result` over the WebSocket frame path. Assert that the Host Edge registered capabilities and observation events through existing gateway handling.

**Step 2: Run the test to verify it fails**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_roundtrip_v0.ManagedHostEdgeWebSocketTests.test_runtime_managed_host_edge_registers_and_handles_runtime_status -v`

Expected: FAIL until Runtime startup owns the supervisor.

**Step 3: Run the test to verify it passes**

Run: `/root/openhalo/.venv/bin/python -m unittest tests.test_roundtrip_v0.ManagedHostEdgeWebSocketTests.test_runtime_managed_host_edge_registers_and_handles_runtime_status -v`

Expected: PASS, demonstrating the standard Edge API boundary without a manually launched `host_daemon` process.

### Task 6: Update operator documentation and validate the whole slice

**Files:**
- Modify: `docs/dev-env.md`
- Modify: `Project.md`
- Test: `tests/test_dev_env_scripts.py`

**Step 1: Document the new default and explicit opt-out**

Replace the M4.1 runtime/host startup directions with one Runtime command plus one terminal edge command. Retain standalone `host_daemon` instructions only as an explicit edge-development diagnostic path, not the normal deployment operation. State that `--disable-host-edge` is intended for isolated fixtures and deployments that cannot host the companion edge.

**Step 2: Update the project baseline**

Record the M4.1 implementation status, completed acceptance coverage, and any remaining human acceptance requirement in `Project.md`. Do not mark the milestone accepted until the required human acceptance has run.

**Step 3: Run complete automated verification**

Run: `/root/openhalo/.venv/bin/python -m unittest discover -s tests -v`

Expected: PASS, aside from any independently recorded local-worktree setup issue. Then run `bin/verify-host-edge --dry-run` to confirm docs and existing verifier command shapes remain intelligible.

**Step 4: Commit**

```bash
git add personal_runtime device_edge/host/host_daemon.py tests docs/dev-env.md Project.md
git commit -m "feat: supervise colocated host edge from runtime"
```
