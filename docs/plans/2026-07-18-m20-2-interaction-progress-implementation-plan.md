# M20.2 Interaction Progress Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver a safe, Runtime-owned interaction-progress lifecycle to the independent Runtime Console and through the public Edge API to Terminal Edge, without implementing Android rendering in this branch.

**Architecture:** A new Runtime-internal `Display Lifecycle` accepts strict body-free events from Gateway, Agent Runtime, Presence/Execution Planning, and Action Layer boundaries. It correlates and sequences events per interaction, records a safe diagnostic, and fans out to independent presentation targets. `Runtime Console Presenter` is a local, non-blocking sink that renders a human-readable OpenHalo activity view directly in the Runtime process, including when no Edge exists. `Gateway` remains the only cross-boundary transport and projects only product phase plus safe presentation hint to visibility-authorized progress-capable Edges; Terminal and Android each render only their authorized interactions. A later rich management dashboard is an independently authorized `Operator Edge` through `Gateway`, never a backend-internal UI or a dependency of Runtime execution.

**Ordering clarification:** Progress is an independent display side-channel and must not reorder the normal `event -> action_request -> action_result` path. A same-Terminal `notification.show` body remains immediate action output; `awaiting_action_result` and `completing` may truthfully appear afterwards. M20.3 owns the later Terminal UI treatment that makes those distinct categories easy to read.

**Tech Stack:** Python 3.11+, `websockets`, `unittest`, public `edge.runtime.v1` JSON frames.

**Current server-side status:** `Runtime Console Presenter` is implemented and automatically verified alongside the Runtime/Gateway/Terminal progress path. It renders fixed OpenHalo phase text from the already-safe lifecycle reduction, remains available with zero connected Edges, and ignores local console-output failure. The embedded Hermes Agent receives a no-op thinking callback and raw spinner-output sink at construction, so Hermes' quiet-mode and tool spinners cannot leak into that console. Android rendering and real-device acceptance remain local-user work.

### Task 1: Document the accepted scope

**Files:**
- Modify: `Project.md`
- Create: `docs/plans/2026-07-18-m20-2-interaction-progress-implementation-plan.md`

**Step 1:** Record the `Display Lifecycle` boundary, public-data restrictions, and the user-owned Android implementation/acceptance boundary.

**Step 2:** Keep M20.2 explicitly in progress; do not claim acceptance before Runtime Console, Runtime/Gateway/Terminal tests and the separate Android local run exist.

### Task 2: Define and test the public progress contract

**Files:**
- Modify: `edge_api/protocol.py`
- Modify: `personal_runtime/action_layer.py`
- Create: `personal_runtime/display_lifecycle.py`
- Test: `tests/test_protocol_v0.py`
- Test: `tests/test_display_lifecycle.py`

**Step 1: Write failing tests**

```python
def test_progress_frame_is_versioned_and_contains_only_safe_fields():
    frame = build_interaction_progress("terminal-edge-1", progress, correlation={})
    self.assertEqual(frame["type"], "interaction_progress")
    self.assertNotIn("tool_args", frame["progress"])
```

**Step 2:** Run the new tests and verify that `interaction_progress` is not yet a supported public frame type.

**Step 3: Implement the minimal contract**

```python
SAFE_PHASES = frozenset({"deliberating", "planning", "executing", "awaiting_action_result", "completing", "completed", "failed", "cancelled"})

{"type": "interaction_progress", "device_id": target, "progress": {
    "version": 1, "interaction_id": interaction_id,
    "interaction_turn_id": turn_id, "sequence": sequence,
    "phase": phase, "state": state, "occurred_at": timestamp,
    "presentation_hint": hint,
}}
```

**Step 4:** Re-run the focused tests and verify API-version, phase, sequence, and privacy assertions pass.

### Task 3: Route safe lifecycle projections through Runtime and Gateway

**Files:**
- Modify: `personal_runtime/runtime_orchestrator.py`
- Modify: `personal_runtime/gateway_server.py`
- Create: `personal_runtime/runtime_console_presenter.py`
- Test: `tests/test_runtime_orchestrator.py`
- Test: `tests/test_gateway_v0.py`
- Test: `tests/test_runtime_console_presenter.py`

**Step 1: Write failing tests** for normal user work, action batches, action-result continuation, provider failure, unauthorized participants, unsupported progress capability, disconnected targets, monotonic sequence, and body-free diagnostics.

**Step 2:** Run the selected tests and confirm the contract is absent.

**Step 3: Implement the minimal lifecycle**

```python
replies.extend(gateway.emit_interaction_progress(
    interaction=interaction, phase="deliberating", correlation=correlation,
))
```

Emit before Harness deliberation, before planning, after dispatch, while an action batch awaits exact results, before post-action continuation, and at terminal complete/fail. Resolve recipients from requester/outcome visibility plus explicit authorized participants; require `interaction.progress` capability; never wait for rendering or alter execution when no eligible Edge is connected.

**Step 4:** Send each accepted safe lifecycle reduction to `Runtime Console Presenter` as well as eligible Gateway recipients. The local presenter must render OpenHalo-owned human-readable activity state such as `正在理解来自桌面的请求` or `正在等待手机确认`; it may use only safe device display names, safe capability/result summaries, phase, sequence, and timing. It must not render prompt bodies, model/provider data, tool content, Hermes identity, or internal module names; it must neither await nor alter Runtime work.

**Step 5:** Record only phase, correlation, timing, sequence, recipient and delivery outcome in diagnostics; do not persist display prose, provider details, tool data, research content, or Hermes identity.

**Step 6:** Re-run focused Runtime/Gateway and Runtime Console tests.

### Task 4: Render the lifecycle in Terminal Edge

**Files:**
- Modify: `device_edge/cli/terminal_daemon.py`
- Test: `tests/test_terminal_daemon_m8.py`

**Step 1: Write failing tests** for progress phase text, stale-sequence rejection, phase replacement, terminal/failure cleanup, session-loss cleanup, and progress-capability announcement.

**Step 2:** Run the Terminal test module and confirm the new cases fail.

**Step 3: Implement a local progress reducer and presenter.** Both TTY and non-TTY paths append one concise progress line per accepted phase so fast real transitions remain inspectable. They clear only their active in-memory progress state before user input, final interaction output, failure, cancellation, or session loss; M20.3 may later replace this initial phase history with a formal status panel or timeline.

```python
if sequence <= self.progress_sequence_by_interaction.get(interaction_id, 0):
    return
self.render_progress_phase(phase)
```

**Step 4:** Teach the session loop to consume `interaction_progress` frames before ordinary action/result frames without interfering with acknowledgement or action-result correlation.

**Step 5:** Re-run Terminal tests.

### Task 5: Verify the complete server-side slice

**Files:**
- Test: `tests/test_protocol_v0.py`
- Test: `tests/test_display_lifecycle.py`
- Test: `tests/test_gateway_v0.py`
- Test: `tests/test_runtime_orchestrator.py`
- Test: `tests/test_terminal_daemon_m8.py`
- Test: `tests/test_runtime_console_presenter.py`

**Step 1:** Run all focused suites.

**Step 2:** Run the bounded server-safe focused suite through `bin/test`; do not
run unrestricted `unittest discover` on the shared server.

```bash
bin/test -m unittest -v \
  tests.test_interaction_progress \
  tests.test_terminal_daemon_m8 \
  tests.test_gateway_v0 \
  tests.test_runtime_orchestrator \
  tests.test_display_lifecycle \
  tests.test_protocol_v0 \
  tests.test_runtime_console_presenter \
  tests.test_hermes_adapter
```

**Step 3:** Start Runtime without any Edge and inspect that `Runtime Console Presenter` shows the human-readable active and settled activity states while the interaction continues normally. Then run a bounded local WebSocket acceptance with a Terminal Edge and inspect that progress frames are ordered, final `interaction_update` remains intact, and no progress payload/diagnostic contains forbidden private fields.

**Step 4:** Keep Android code, emulator work, and Android human acceptance out of this branch; hand the versioned progress contract and focused protocol tests to the local Android implementation work.
