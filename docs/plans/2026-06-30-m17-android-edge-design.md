# M17 Native Android Device Edge Design

Status: M17 design baseline draft.

## Goal

Build the first real mobile `Device Edge` for OpenHalo as a native Android app.
The Android edge should join the existing presence-governed runtime model
through the public Edge API rather than becoming a terminal companion or a
backend-specific shortcut.

## Milestone Split

The first implementation milestone for this Android direction is `M17.2:
Native Android Presence Edge`.

`M17.2` should stay deliberately bounded:

- Maintain a stable Edge API session from the phone when Android foreground or
  background policy permits it.
- Register the phone as a real edge with low-risk mobile context observations.
- Execute `notification.show` as the first phone-side action.
- Provide a foreground diagnostics UI and adb-verifiable smoke evidence.
- Preserve multi-edge routing and interaction lineage when another edge starts
  an interaction and the runtime chooses the phone as the intervention surface.

The broader Android/mobile edge direction is larger than `M17.2`. Later
milestones may turn the phone into a richer mobile Sensor/Action Edge with
screen-use context, optional camera or microphone capture, voice command input,
environmental audio observations, location or motion context, and richer
foreground command surfaces. Those capabilities are recorded here as direction,
not as blockers for accepting the initial Presence Edge baseline.

## Architecture Position

The Android app is a `Frontend / Device Edge` participant. It owns Android-local
permissions, sensing, foreground UI, background service behavior, notification
execution, and local diagnostics.

The backend continues to see only public Edge API frames:

```text
Android Device Edge -> Edge API v1 WebSocket -> Gateway -> Personal Runtime
```

The Android edge must not import Python backend modules, depend on internal
runtime state objects, or reuse terminal-edge implementation details as its
product model.

## Local Edge Responsibilities

The Android edge should cover both foreground and background surfaces on one
phone device:

- Background edge service for connection, registration, observations, reconnect,
  and notification action delivery.
- Foreground app UI for user input, runtime replies, diagnostics, and manual
  test flows.
- Local action executor for `notification.show` and in-app reply rendering.
- Local capability runtime that maps Android platform state into normalized
  Edge API observations.
- Local permission handling for notifications, background behavior, and later
  sensor access.

Android background execution should be treated as constrained availability, not
as guaranteed presence. Restrictions should be reported as observations where
they affect runtime routing or presence decisions.

## Initial Capability And Observation Candidates

Initial capability candidates:

- `mobile.context`
- `mobile.input`
- `notification.show`
- `mobile.reply.render`
- `mobile.prompt_user`

Initial observation candidates:

- `mobile.screen_state`
- `mobile.app_visibility`
- `mobile.notification_permission`
- `mobile.power_state`
- `mobile.connection_state`
- `mobile.background_restriction`

These names are candidates until the Android edge design and Edge API examples
are finalized. If a value should affect runtime presence or planning, prefer a
generic observation vocabulary that can apply beyond Android-specific APIs.

## Debug And Inspection Requirements

The debug app should expose enough diagnostics to avoid relying only on Logcat:

- Build version, build time, and git commit if available.
- Runtime URL currently in use.
- Device ID.
- Connection state.
- Last sent public Edge API frame.
- Last received public Edge API frame.
- Last public API error.
- Registered capabilities.
- Recent observations sent.
- Recent action requests and action results.

M17 acceptance should be inspectable from both the Android app UI and runtime
chain inspection output.

The current acceptance workflow is layered and documented in
`docs/m17-android-edge-acceptance.md`: runtime-side simulation verifies
multi-edge planning and lineage, adb-based real-device smoke verification checks
the Android app and phone state, and full live server-to-phone action delivery
remains a manual milestone acceptance step.

## Non-Goals

- Do not use terminal edge as the phone edge entry point.
- Do not add phone-specific backend shortcuts.
- Do not commit generated APK files to the repository.
- Do not treat Android background execution as guaranteed availability.
- Do not rely on Google/Firebase services for the first M17 runtime path unless
  a later decision explicitly adds that dependency.

