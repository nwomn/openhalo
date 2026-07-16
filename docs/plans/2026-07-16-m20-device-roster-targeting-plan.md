# M20 Device Roster Targeting Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` for each implementation task.

**Goal:** Give Hermes a bounded, Runtime-owned device roster so it can make the
semantic target choice for governed Device Edge actions using current device
identity, availability, and capabilities.

**Architecture:** `Personal Runtime` remains the source of truth for devices,
capabilities, and live session availability. Each Harness turn receives a
compact `device_roster` projection through its existing grounding/prompt
contract. Hermes chooses an exact `target_device_hint` from that roster; the
Runtime validates that choice through normal Presence and execution planning
without keyword-based target rewriting.

**Tech Stack:** Python 3.12, existing RuntimeState/Gateway registries,
HermesHarnessRunner, standard-library `unittest`.

**Execution constraint:** Work on `codex/m20-harness-foundation` in the main
workspace. Do not create a worktree. Android changes remain local to the
Android development checkout until this Runtime contract is accepted.

## Contract

`device_roster` is a bounded inference input, not an Edge API replacement and
not a second device store. It contains one item per registered device:

```json
{
  "device_id": "android-edge-782d0247",
  "device_type": "android-phone",
  "role": "interactive_surface",
  "online": true,
  "action_capabilities": [
    {
      "name": "notification.show",
      "affordances": ["notify_user", "deliver_private_text"],
      "modality": "visual_text",
      "privacy": "personal",
      "content_capacity": "short_text",
      "interruptiveness": "medium"
    }
  ]
}
```

The model receives `request_source_device_id` alongside the roster. It must
select only an exact roster `device_id` when it proposes a target. It reasons
over the user request and roster semantics; no Runtime keyword heuristic may
replace a valid model choice. `Presence Router` and `Execution Planning` still
reject offline, unsupported, schema-invalid, or policy-disallowed actions.

## Tasks

### Task 1: Prove the roster contract

**Files:**
- Modify: `tests/test_runtime_memory.py`
- Modify: `tests/test_prompt_context.py`

1. Add a failing grounding test with an online Android phone and an online
   Terminal. Assert that the projected roster preserves device ID, type, role,
   online state, and only runtime-to-edge action capabilities.
2. Add a failing prompt-context test. Assert the roster and request source are
   present in a dedicated `device_roster` section, while recent memory and raw
   edge evidence remain separate.
3. Run the two tests and observe failure before production code changes.

### Task 2: Build and inject the roster

**Files:**
- Modify: `personal_runtime/runtime_memory.py`
- Modify: `personal_runtime/prompt_context.py`
- Modify: `personal_runtime/runtime_orchestrator.py`

1. Extend `build_model_grounding_bundle` with current online device IDs and a
   request source ID.
2. Project registered state into a stable, bounded roster. Do not include raw
   observations, action-result bodies, or client-supplied executable data.
3. Pass the same roster-producing inputs into normal, action-result,
   post-observation, and observation-driven Harness inputs.
4. Add the roster to prompt context and the behavior contract, including the
   explicit distinction between semantic model selection and Runtime
   validation/governance.

### Task 3: Constrain Hermes target choice

**Files:**
- Modify: `personal_runtime/hermes_adapter.py`
- Modify: `tests/test_hermes_adapter.py`

1. Add a failing fake-agent test that captures the JSON user message and
   system message for a phone/Terminal roster.
2. Assert the complete roster reaches Hermes and the system contract requires
   an exact roster target ID, selecting the requesting surface only when the
   request semantically asks for it.
3. Update the system instruction. Keep `target_device_hint` model-owned; do
   not add keyword routing or a Runtime override.

### Task 4: Regression and human retry

**Files:**
- Modify: `Project.md`

1. Run focused runtime-memory, prompt-context, Hermes-adapter, execution, and
   Gateway tests, then full discovery.
2. Restart the development Runtime so the fresh roster contract is loaded.
3. With an Android phone already connected and registered, send a natural
   Terminal request to deliver text to the phone. Pass only when the Harness
   action intent names the Android device, the phone executes
   `notification.show`, the correlated phone `action_result` returns, and the
   requesting Terminal receives a final execution outcome.
4. Record the decision boundary and the failed prior acceptance as a negative
   case: semantic target selection requires a roster and must not be replaced
   by keyword routing.

### Task 5: Preserve the explicit requester outcome contract

**Files:**
- Modify: `personal_runtime/interaction_pool.py`
- Modify: `personal_runtime/gateway_server.py`
- Modify: `personal_runtime/hermes_adapter.py`
- Modify: `personal_runtime/runtime_orchestrator.py`
- Modify: `personal_runtime/execution_planning.py`
- Modify: `personal_runtime/prompt_context.py`

1. Register normal user events as `explicit_user_intent` with a requesting
   device and outcome obligation. Register passive observation and agent
   initiative interactions without either field.
2. Pass a bounded `action_result_context` into post-action Harness calls.
   Hermes must produce a requester acknowledgement when a cross-device user
   action settles, while passive evidence and initiative have no such rule.
3. When the Hermes post-action result is `no_intervention` or
   `provider_failure`, synthesize a narrowly authorized Runtime fallback to
   the exact requester. It must traverse Presence and Execution Planning; it
   is not a direct Gateway dispatch.
4. Prove that incomplete fallback metadata is rejected, passive/initiative
   interactions receive no completion update, and the Terminal-to-Android
   scenario produces the Terminal outcome action after the phone result.

### Task 6: Keep source semantics Runtime-owned and remove global cooldown

**Files:**
- Modify: `personal_runtime/hermes_adapter.py`
- Modify: `personal_runtime/presence_router.py`

1. Normalize the Harness output source to the Runtime interaction phase rather
   than `hermes`: normal user turns are `sense_first`, initiative remains
   `agent_initiative`, and re-entry uses `post_action` or
   `post_observation`.
2. Remove the fixed global intervention-history cooldown. The current runtime
   is not yet intervention-saturated; terminal activity, context ambiguity,
   capability, privacy, permission, and explicit policy remain the active
   governance constraints.
3. Prove a recent allowed intervention no longer suppresses an initiative,
   while Hermes-backed normal and post-action proposals expose semantic source
   values and retain Hermes only in harness metadata.
