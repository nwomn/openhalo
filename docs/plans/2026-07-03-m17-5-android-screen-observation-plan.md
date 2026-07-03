# M17.5 Android Screen Context Observation Plan

Status: design baseline for the next Android-edge observation milestone.

## Goal

`M17.5` extends the accepted Android `Device Edge` from daily-use connection and
notification handling into richer phone-side observation collection. The goal
is to let the phone edge observe and summarize current screen/use context, then
send normalized evidence to the runtime.

This remains an `M17` edge-capability milestone. It does not perform runtime
intent recognition. It prepares higher-quality observations for later `M18`
observation-driven intent sensing.

## Boundary

The Android edge may observe, summarize, redact, and upload evidence such as:

- current screen/window context
- recent accessibility events
- visible UI structure
- visible text summary
- interactive controls and affordances
- coarse screen kind
- user action observed
- privacy/sensitivity flags

The Android edge must not decide:

- what the user wants
- whether the runtime should intervene
- whether a passive observation is actionable intent
- which proposal or action should happen next

Those decisions belong to `Personal Runtime` in later `M18`, through the normal
snapshot, grounding, proposal-formation, and `Presence Router` path.

## Recommended Default Architecture

```text
Accessibility event
  -> debounce/coalesce
  -> accessibility node tree extraction
  -> optional screenshot/OCR fallback
  -> local redaction and summarization
  -> mobile.screen_context observation
  -> Edge API observation_push
  -> Gateway / Runtime observation ingest
```

The preferred default is not raw screenshot streaming. The phone should send a
structured observation first. Raw screenshots, if supported at all, should be an
explicit, short-lived, user-approved diagnostic or enhanced-analysis mode.

## Implementation Approach

### 1. AccessibilityService Baseline

Use an Android `AccessibilityService` as the default capture mechanism.

The service should listen for a bounded set of event types:

- click
- scroll
- text change
- focused element change
- window state change
- window content change
- interactive window change

The first implementation should rely on the accessibility node tree before
using screenshots. For each relevant event, extract a bounded tree summary:

- package name or package category
- root/window class
- event type
- visible text snippets after redaction
- focused/editable node metadata
- clickable/scrollable/selectable controls
- bounds for interactive controls
- content descriptions where present
- password/sensitive-node flags

### 2. Foreground And Background Capture Model

M17.5 must distinguish OpenHalo app visibility from screen-observation
availability.

```text
OpenHalo Activity foreground
  -> show live status, controls, recent observations, and manual test capture

OpenHalo Activity background, foreground service alive
  -> keep Edge API session alive
  -> AccessibilityService may still observe the current foreground app
  -> event-triggered observations may continue under user policy

Phone unlocked/bright with another app in foreground
  -> accessibility events can trigger node-tree extraction
  -> send bounded mobile.screen_context evidence

Phone unlocked/bright but idle
  -> low-frequency periodic summary only
  -> skip repeated full payloads when window hash/context is unchanged

Phone locked or screen off
  -> do not collect rich screen_context
  -> send only availability/capture-health evidence where useful
  -> do not screenshot or OCR
```

The key product value is that OpenHalo does not need to be the foreground
Activity for screen-context observation. With user-approved accessibility
access, the Android edge can observe the user's current foreground app while
the OpenHalo app itself is in the background.

Foreground/background state should be reported as evidence, not inferred as
intent. The first implementation should include it in `mobile.screen_context`
and/or a companion `mobile.screen_capture_health` observation.

Candidate state fields:

- `openhalo_app_visibility`: `foreground`, `background`, `unknown`
- `edge_service_state`: `foreground_service`, `stopped`, `unknown`
- `accessibility_service_state`: `enabled`, `disabled`, `restricted`,
  `unknown`
- `screen_state`: `unlocked`, `locked`, `screen_off`, `unknown`
- `capture_mode`: `accessibility_tree`, `accessibility_tree_plus_ocr`,
  `health_only`, `disabled`
- `can_observe_foreground_app`: boolean
- `background_capture_allowed`: boolean
- `capture_pause_reason`: `locked`, `screen_off`, `disabled_by_user`,
  `sensitive_context`, `denylisted_app`, `none`, `unknown`

### 3. Async Capture, Processing, And Upload Pipeline

M17.5 must not do heavy work inside the `AccessibilityService` callback path.
Accessibility events can arrive in bursts, and blocking that callback on OCR,
tree summarization, JSON building, disk writes, or WebSocket upload risks
making the phone edge laggy or unreliable.

Use a split pipeline:

```text
AccessibilityService callback
  -> lightweight event envelope
  -> bounded in-memory queue
  -> debounce/coalesce worker
  -> node-tree/screenshot capture worker
  -> redaction/summarization worker
  -> observation upload worker
  -> Edge API send queue
```

Callback-thread responsibilities:

- read only minimal event metadata
- record event type, package/window hint, timestamp, and source node id if safe
- enqueue a lightweight capture request
- return quickly

Background-worker responsibilities:

- wait for UI stabilization after bursts
- collapse repeated content-change/scroll events into one latest-state capture
- extract node tree and optional screenshot/OCR under rate limits
- redact and summarize
- build bounded `mobile.screen_context` payloads
- hand observations to the existing Edge API session send path

Backpressure rules:

- use a bounded queue, not an unbounded event backlog
- prefer latest-state semantics for screen context; drop stale pending captures
- keep the newest capture request per package/window where possible
- never enqueue per-character text-change uploads
- apply a global minimum capture interval
- apply a stricter minimum screenshot/OCR interval
- skip rich capture when CPU/battery/network state is constrained
- emit `mobile.screen_capture_health` when events are dropped or capture is
  throttled

Suggested first-slice defaults:

- event queue size: 16-32 lightweight requests
- UI settle delay: 300-800 ms
- min node-tree capture interval: 1-2 seconds
- min screenshot/OCR interval: 5-10 seconds
- max interactive elements per payload: 20-50
- max visible text summary length: 500-1000 characters

The correctness model should be "latest useful screen context", not "lossless
event log". M17.5 observations are context evidence, so dropping stale captures
is acceptable and preferable to blocking the phone edge.

### 4. Interactive Element Indexing

Borrow the useful part of `android-use`: turn the accessibility tree into an
indexed, compact element list. This is useful even without a vision model.

Example shape:

```json
{
  "interactive_elements": [
    {"index": 1, "role": "text_input", "text": "", "bounds": [0, 1850, 900, 2020]},
    {"index": 2, "role": "button", "text": "Send", "bounds": [910, 1850, 1080, 2020]}
  ]
}
```

For OpenHalo this list is observation evidence, not an instruction for the
runtime to click anything.

### 5. Optional Screenshot And OCR Fallback

Use accessibility screenshots only as a supplement:

- when node text is missing or poor
- when the current app is mostly canvas/image/webview
- when the user explicitly enables screen-context capture
- after sensitivity checks pass

OCR may use an on-device recognizer such as ML Kit Text Recognition. OCR output
should be merged with accessibility-node text, deduplicated, redacted, and
bounded before upload.

Screenshots must not be uploaded by default. If a future mode allows image
upload, it must record:

- why the upload was needed
- whether the screenshot was redacted
- whether it was thumbnail/full-resolution
- retention policy
- user-visible permission state

### 6. Event-First Upload Policy

Use event-triggered upload as the primary path and periodic upload only as a
fallback.

Recommended timing:

- wait 300-800 ms after a UI event before extracting context
- debounce/coalesce bursts of click/scroll/content-change events
- set a minimum screenshot interval, such as 2-5 seconds
- avoid per-character uploads during typing; upload after an input pause
- send only lightweight heartbeat/hash state when the screen is unchanged
- pause screen extraction when locked, screen-off, or disabled by user policy
- keep upload asynchronous from capture; if upload lags, collapse pending
  observations to the latest context plus capture-health metadata

Periodic upload should be limited to unlocked/bright/active windows and should
use a coarse cadence such as 10-30 seconds unless a user explicitly enables a
more detailed debug mode.

### 7. Privacy And Safety Defaults

The default mode should be conservative:

- do not upload raw screenshots
- redact password fields and sensitive nodes
- treat secure windows as blocked evidence
- support app allowlist/denylist
- mark payment/login/banking/credential contexts as sensitive or blocked
- cap visible text length and element count
- expose a clear user-facing enable/pause control
- record `raw_screenshot_uploaded=false` in normal observations

Any future automation or action path must remain out of scope for M17.5.

## Observation Contract Draft

Candidate observation name:

```text
mobile.screen_context
```

Candidate payload:

```json
{
  "trigger": "accessibility_event",
  "event_kind": "view_clicked",
  "source": "accessibility",
  "openhalo_app_visibility": "background",
  "edge_service_state": "foreground_service",
  "accessibility_service_state": "enabled",
  "screen_state": "unlocked",
  "interaction_state": "active",
  "capture_mode": "accessibility_tree",
  "can_observe_foreground_app": true,
  "background_capture_allowed": true,
  "capture_pause_reason": "none",
  "capture_queue_depth": 0,
  "events_coalesced": 4,
  "events_dropped": 0,
  "capture_throttled": false,
  "package_category": "messaging",
  "screen_kind": "chat_thread",
  "user_action_observed": "tapped_text_input",
  "visible_text_summary": "Chat screen with message list, text input, and send button.",
  "ui_affordances": ["message_list", "text_input", "send_button"],
  "interactive_elements": [
    {"index": 1, "role": "text_input", "label": "", "sensitive": false},
    {"index": 2, "role": "button", "label": "Send", "sensitive": false}
  ],
  "sensitivity": "normal",
  "raw_screenshot_uploaded": false,
  "confidence": 0.76
}
```

This payload describes what was observed. It must not include a field named
`intent`, `user_need`, or `should_intervene`.

## External References And Borrowed Lessons

`languse-ai/android-use` is useful as a reference for converting Android UI
XML/accessibility structure into indexed interactive elements that can be
reasoned about without requiring a vision model. OpenHalo should borrow the
element-indexing idea, not the ADB-driven automation loop.

`Mangi-11/FuckAndes` is useful as a reference for event-triggered, low-overhead
screen-entry integration on OEM Android systems. OpenHalo should borrow the
event-first and low-power posture, not the Xposed/root/system-hook technique as
the default implementation path.

## Non-Goals

- Do not implement runtime intent sensing in M17.5.
- Do not upload raw screenshots by default.
- Do not build an ADB-driven phone automation agent.
- Do not rely on Xposed/root/system-server hooks as the normal Android edge
  path.
- Do not let the phone edge decide whether to intervene.
- Do not add automatic clicking, swiping, or app-control behavior.

## Acceptance Criteria

- The Android edge exposes an explicit user-controlled screen-context
  observation mode based on `AccessibilityService`.
- The edge can produce `mobile.screen_context` observations from accessibility
  events and node-tree snapshots without requiring raw screenshot upload.
- The design distinguishes OpenHalo app visibility from capture availability:
  the Activity may be backgrounded while the foreground service and
  AccessibilityService still allow event-triggered observation of the user's
  current foreground app.
- Locked or screen-off states pause rich screen-context extraction and emit
  only availability/capture-health evidence where useful.
- Accessibility callbacks remain lightweight: capture, OCR, redaction,
  summarization, and upload run asynchronously behind bounded queues with
  coalescing, throttling, and stale-capture dropping.
- Observations include trigger metadata, interaction state, screen kind,
  bounded text summary, UI affordances, indexed interactive elements,
  foreground/background capture state, sensitivity flags, confidence, and
  provenance.
- Event-triggered observation upload is debounced/coalesced, with periodic
  upload used only as a fallback when the screen is active and unchanged.
- Sensitive contexts are blocked or redacted by default, including password
  fields, secure windows, and configured app denylist entries.
- Runtime ingestion treats `mobile.screen_context` as passive evidence, not as
  direct intent or a command.
- Automated tests cover node-tree extraction, element indexing, redaction,
  bounded payload size, event debounce/coalescing, queue backpressure, stale
  capture dropping, and runtime rejection or passive storage of malformed
  screen-context observations.
- Human acceptance demonstrates that a real phone can enable the feature,
  interact with several normal apps, and produce useful bounded observations
  without uploading raw screenshots or triggering runtime interventions.
