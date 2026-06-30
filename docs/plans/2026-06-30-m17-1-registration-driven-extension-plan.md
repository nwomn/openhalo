# M17.1 Registration-Driven Multi-Device Extension Rework Plan

Status: salvaged design baseline for a future reimplementation.

This document was recovered from the abandoned
`codex/m17-1-registration-extension` branch. The implementation on that branch
predated the module-boundary diagnostics and `RuntimeOrchestrator` baseline now
on `master`, so the code from that branch should not be treated as current.
Use this file as a requirements and acceptance-plan source when rebuilding
M17.1 on top of the current architecture.

**Goal:** Build the `M17.1` baseline that lets new device edges register capabilities and observations through the public Edge API, then lets the runtime validate, plan, and dispatch actions through a generic registry-driven execution path.

**Architecture:** Keep `Edge API v1 -> Gateway` as the physical boundary and keep `Presence Router` as the governance gate before execution. Add `Device Registry`, `Capability Registry`, and `Observation Registry` state, enforce strict registration at gateway ingress, then add `Execution Planning` after `Presence Router` so capability/provider selection is driven by registered metadata instead of device-type branches or fixed `intent -> capability` tables.

**Tech Stack:** Python 3.11 standard library, `unittest`, existing `edge_api` frame helpers, existing `RuntimeGateway`, existing runtime state persistence, existing terminal/host edge clients, existing chain inspection and verification scripts.

## Design Rules

- New devices may add capabilities and observations through public registration metadata.
- Unregistered observations are rejected by default; they are not silently stored as runtime state.
- Schema-mismatched observations are rejected by default.
- Existing terminal and host edges should keep working during the migration through bounded compatibility defaults.
- Capability names remain useful identifiers, but planning decisions must use registered metadata such as direction, affordances, modality, privacy, content capacity, side effect, trust, and schema.
- `Capability Resolver` is an internal sub-step of `Execution Planning`, not a replacement for `Execution Planning`.
- `Action Layer` receives a finalized action envelope or execution plan and does not decide semantic capability selection.
- Planner records must preserve enough candidate, filter, and rationale data for later replay and `M20` policy-learning candidates.

### Task 1: Extend public Edge API registration contracts

**Files:**
- Modify: `edge_api/protocol.py`
- Modify: `docs/edge-api.md`
- Test: `tests/test_protocol_v0.py`
- Test: `tests/test_edge_client_v0.py`

**Step 1: Write failing tests**

Add tests proving `build_capability_announce_frame()` accepts rich capability objects that include:
- `name`
- `direction`
- `kind`
- `affordances`
- `modality`
- `content_capacity`
- `privacy`
- `interruptiveness`
- `side_effect`
- `input_schema` or `result_schema`
- `observations` for observation-provider capabilities

Also add a test for a mobile-style registration payload:

```python
frame = build_capability_announce_frame(
    "phone-edge-1",
    [
        {
            "name": "notification.show",
            "direction": "runtime_to_edge",
            "kind": "action",
            "affordances": ["notify_user", "deliver_private_text"],
            "modality": "visual_text",
            "content_capacity": "short_text",
            "privacy": "personal",
            "interruptiveness": "medium",
            "side_effect": "user_visible",
            "input_schema": {
                "type": "object",
                "required": ["message"],
                "properties": {"message": {"type": "string"}},
            },
        },
        {
            "name": "mobile.context",
            "direction": "edge_to_runtime",
            "kind": "observation_provider",
            "observations": [
                {
                    "name": "mobile.screen_state",
                    "schema": {
                        "type": "string",
                        "enum": ["locked", "unlocked", "unknown"],
                    },
                    "semantics": ["device_activity"],
                    "privacy": "personal_device_state",
                    "freshness_seconds": 120,
                    "confidence": {"type": "edge_reported"},
                }
            ],
        },
    ],
)
```

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_protocol_v0 tests.test_edge_client_v0 -v
```

Expected: FAIL where the current API helpers and tests do not preserve or assert the richer contract.

**Step 3: Implement the public contract helpers**

Keep `edge_api.protocol` dependency-free. Preserve rich capability objects without normalizing away metadata. Add small validation helpers only for required public frame shape; do not import runtime internals.

**Step 4: Document the contract**

Update `docs/edge-api.md` so edge authors see:
- rich action capability examples
- observation-provider examples
- strict rule that observations must be registered before `observation_push`
- strict rule that action results must match registered runtime-to-edge capabilities

**Step 5: Run focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_protocol_v0 tests.test_edge_client_v0 -v
```

Expected: PASS.

### Task 2: Add runtime registries to state and persistence

**Files:**
- Modify: `personal_runtime/runtime_state.py`
- Modify: `personal_runtime/state_store.py`
- Modify: `personal_runtime/context_contracts.py`
- Test: `tests/test_runtime_state_v0.py`
- Test: `tests/test_runtime_persistence_v0.py`

**Step 1: Write failing tests**

Add tests proving runtime state can persist and restore:
- device registry entries with `device_id`, `device_type`, `role`, and trust/profile fields when present
- capability registry entries keyed by provider device and capability name
- observation registry entries keyed by provider device, provider capability, and observation name

Also prove existing simple capability strings still restore to the existing `devices[device_id]["capabilities"]` set for compatibility.

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_runtime_state_v0 tests.test_runtime_persistence_v0 -v
```

Expected: FAIL because state currently stores only device payloads and capability-name sets.

**Step 3: Implement registry storage**

Add minimal standard-library data structures. Keep them serializable through `to_dict()` / `from_dict()`:

```python
self.capability_registry = {}
self.observation_registry = {}
```

Use stable keys such as:

```text
capability_registry[device_id][capability_name]
observation_registry[device_id][provider_capability][observation_name]
```

Do not add a database or migration framework in this slice.

**Step 4: Preserve migration compatibility**

When older state lacks registry fields, restore empty registries and keep old `devices` behavior intact.

**Step 5: Run focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_runtime_state_v0 tests.test_runtime_persistence_v0 -v
```

Expected: PASS.

### Task 3: Register rich capabilities and observation schemas in Gateway

**Files:**
- Modify: `personal_runtime/gateway_server.py`
- Modify: `personal_runtime/runtime_state.py`
- Test: `tests/test_gateway_v0.py`

**Step 1: Write failing tests**

Add gateway tests proving:
- rich capability objects are persisted in `capability_registry`
- observation schemas nested under a capability are persisted in `observation_registry`
- existing terminal/host simple-string capability announcements still work
- capability names still appear in `devices[device_id]["capabilities"]` for existing routing during migration

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_gateway_v0 -v
```

Expected: FAIL because gateway currently calls `_capability_name()` and drops all rich metadata.

**Step 3: Implement registration handling**

On `capability_announce`:
- register the capability name for backward compatibility
- store the full rich capability metadata when provided
- register nested observations when `observations` exists
- infer bounded defaults for simple strings only for existing terminal/host compatibility

Compatibility defaults should be narrow:
- `notification.show` defaults to runtime-to-edge user-visible short text
- `text.input` defaults to edge-to-runtime user text
- `runtime.control` defaults to runtime-to-edge runtime-scoped control
- host observation capabilities may register known existing observation names only where current code already emits them

**Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_gateway_v0 -v
```

Expected: PASS.

### Task 4: Enforce strict observation registration and schema checks

**Files:**
- Modify: `personal_runtime/gateway_server.py`
- Modify: `personal_runtime/context_contracts.py`
- Test: `tests/test_gateway_v0.py`
- Test: `tests/test_roundtrip_v0.py`

**Step 1: Write failing tests**

Add tests proving:
- `observation_push` with an unregistered observation name returns a public `error` frame and does not append to `state.observations`
- `event_push` carrying `payload.observations` follows the same rule
- schema mismatch returns a public `error` frame and does not append to `state.observations`
- registered observations with valid schema are normalized and persisted
- existing host and terminal observation flows still pass after their compatibility registrations are in place

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_gateway_v0 tests.test_roundtrip_v0 -v
```

Expected: FAIL because gateway currently accepts any observation with the expected flat payload fields.

**Step 3: Implement strict validation**

Before `_extract_runtime_observations()` records anything:
- verify the source device registered the source capability
- verify each observation name is registered under that provider capability
- validate primitive schema support for the first slice: `type`, `enum`, required object properties where needed
- reject the whole batch if any observation is invalid

Return public `error` frames with stable fields such as:

```json
{
  "type": "error",
  "code": "unregistered_observation",
  "message": "Observation is not registered for this device capability.",
  "device_id": "phone-edge-1",
  "capability": "mobile.context",
  "observation": "mobile.screen_state"
}
```

**Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_gateway_v0 tests.test_roundtrip_v0 -v
```

Expected: PASS.

### Task 5: Add Execution Planner and Capability Resolver modules

**Files:**
- Create: `personal_runtime/execution_planner.py`
- Modify: `personal_runtime/action_layer.py`
- Modify: `personal_runtime/gateway_server.py`
- Test: `tests/test_execution_planner.py`
- Test: `tests/test_gateway_v0.py`

**Step 1: Write failing planner unit tests**

Create tests for:
- legacy `action_capability="notification.show"` hint resolves only against registered compatible capabilities
- unregistered legacy hints produce a no-action or rejected planning outcome instead of dispatch
- private short text chooses a registered personal text surface over public audio
- public audio is filtered when presence blocks `public_audio`
- ambient light is filtered when `content_required=true` and `content_capacity=none`
- fallback candidates are recorded when a valid lower-scoring surface remains

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_execution_planner tests.test_gateway_v0 -v
```

Expected: FAIL because there is no planner module and gateway dispatch still calls `build_planned_action()` directly from proposal data.

**Step 3: Implement planner data shapes**

Add small dataclasses or plain dict helpers for:
- `PlanningRequirements`
- `CapabilityCandidate`
- `ExecutionPlan`

Keep the first slice simple and serializable.

**Step 4: Implement hard filtering**

Filter candidates by:
- device online state
- direction
- capability schema compatibility
- privacy boundary
- interruptiveness boundary
- side-effect allowance
- content capacity
- trust or permission tier
- required response support when present

Do not implement model-assisted reranking in M17.1.

**Step 5: Implement deterministic scoring**

Score surviving candidates using simple explainable factors:
- affordance match
- modality match
- presence preferred participant
- source surface fallback
- recent availability where current state exposes it

Every score adjustment should produce a short reason string.

**Step 6: Thread planner into gateway**

Replace direct normal-path calls from proposal to `build_planned_action()` with:

```text
proposal -> Presence Router -> Execution Planner -> Action Layer
```

Keep legacy proposal action hints as advisory inputs.

**Step 7: Run focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_execution_planner tests.test_gateway_v0 -v
```

Expected: PASS.

### Task 6: Record planning lineage for replay and later policy learning

**Files:**
- Modify: `personal_runtime/runtime_state.py`
- Modify: `personal_runtime/gateway_server.py`
- Modify: `personal_runtime/chain_inspection.py`
- Test: `tests/test_runtime_state_v0.py`
- Test: `tests/test_chain_inspection.py`

**Step 1: Write failing tests**

Add tests proving intervention or interaction records include:
- proposal requirements or legacy action hint
- presence decision
- planner candidate list
- filtered candidates with reasons
- chosen primary action
- fallback candidates when present
- registry entry references
- relevant observation evidence references

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_runtime_state_v0 tests.test_chain_inspection -v
```

Expected: FAIL because planning records do not exist.

**Step 3: Persist planning records**

Store planning data inside recorded interventions first; only add a separate `execution_plans` list if intervention records become too large or awkward.

**Step 4: Expose inspection output**

Update chain inspection so manual acceptance can read:
- registered candidate capabilities
- selected action
- rejection reasons
- fallback candidates

**Step 5: Run focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_runtime_state_v0 tests.test_chain_inspection -v
```

Expected: PASS.

### Task 7: Add mobile-style external-edge acceptance coverage

**Files:**
- Modify: `tests/test_roundtrip_v0.py`
- Modify: `tests/test_gateway_v0.py`
- Modify: `docs/dev-env.md`
- Create: `bin/verify-m17-1-registration-extension`
- Test: `tests/test_dev_env_scripts.py`

**Step 1: Write failing end-to-end tests**

Add a raw public-API simulation with:
- `terminal-edge-1` as the source edge
- `phone-edge-1` registering `notification.show` and `mobile.screen_state`
- `speaker-edge-1` registering `speaker.play_audio`
- `desk-light-edge-1` registering `light.pulse`

Drive a text interaction that requires private short text and prove:
- phone notification is chosen
- speaker is rejected because public audio is not allowed
- light is rejected because it cannot carry text
- interaction lineage and planning rationale are recorded

Also drive an unregistered observation push and prove it is rejected.

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_roundtrip_v0 tests.test_gateway_v0 tests.test_dev_env_scripts -v
```

Expected: FAIL until registry, planner, and verifier are implemented.

**Step 3: Add bounded verification script**

Create `bin/verify-m17-1-registration-extension` that runs a focused local scenario and prints:
- registered devices
- registered capabilities
- registered observations
- accepted observation batch
- rejected unregistered observation
- planner selected action
- rejected candidate reasons

Support `--dry-run` like other verifier scripts.

**Step 4: Document manual acceptance**

Update `docs/dev-env.md` with the verifier command and expected acceptance signals.

**Step 5: Run focused tests**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_roundtrip_v0 tests.test_gateway_v0 tests.test_dev_env_scripts -v
```

Expected: PASS.

### Task 8: Verify M17.1 and update project status conservatively

**Files:**
- Modify if accepted: `Project.md`

**Step 1: Run targeted automated verification**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_protocol_v0 tests.test_edge_client_v0 tests.test_runtime_state_v0 tests.test_runtime_persistence_v0 tests.test_gateway_v0 tests.test_roundtrip_v0 tests.test_execution_planner tests.test_chain_inspection tests.test_dev_env_scripts -v
```

Expected: PASS.

**Step 2: Run bounded manual acceptance**

Run:

```bash
bin/verify-m17-1-registration-extension --dry-run
bin/verify-m17-1-registration-extension
```

Expected: PASS and printed evidence includes strict observation rejection plus planner selection rationale.

**Step 3: Run full regression**

Run:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Expected: PASS.

**Step 4: Update project status only after acceptance**

If all verification passes and human acceptance is completed, update `Project.md` to mark `M17.1` completed and accepted. Do not mark broader `M17` complete; phone/mobile and other real edge surfaces remain later work on top of this baseline.
