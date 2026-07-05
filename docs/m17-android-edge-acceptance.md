# M17 Android Edge Acceptance

Status: M17 Android edge testing workflow baseline.

This document defines the current verification workflow for the native Android
`Device Edge`. The workflow is optimized for stable day-to-day development:
most checks should run below the black-box adb layer, while adb remains a small
installed-build smoke test.

## Current Testing Workflow

Use this order for Android edge work:

```text
unit tests -> Compose UI tests -> instrumentation/UI Automator -> adb installed-build smoke -> manual live-chain acceptance
```

This replaces the older verifier-first workflow. Do not treat
`bin/verify_m17_android_device.py` as the main UI automation layer.

## 1. Unit Tests

Purpose:

- Verify pure Android-edge behavior without a phone, emulator, Android Studio,
  public network reachability, or a live runtime.
- Keep high-churn logic fast and deterministic.

Target coverage:

- Edge API frame builders such as `mobile.input`, `mobile.context`, and action
  result frames.
- `mobile.screen_context` capability registration and observation frame shape.
- Screen-context summarization, redaction, bounded visible text, indexed
  interactive elements, and the default `raw_screenshot_uploaded=false`
  privacy contract.
- Reconnect/backoff policy and connection health state transitions.
- Runtime config persistence boundaries.
- Bounded notification/event history formatting.
- Diagnostic state to UI-model mapping once that mapping is factored out.

Expectation:

- Any new Android edge behavior that can be expressed without Android framework
  side effects should land here first.

## 2. Compose UI Tests

Purpose:

- Verify app-internal UI flows with stable semantics instead of screen-text
  scraping or coordinate clicking.
- Run the normal app UI automation on an Android Studio emulator or a dedicated
  test device, not on the user's daily phone.

Required practice:

- Add stable `testTag` or accessibility-friendly semantics before adding UI
  tests for important controls and state surfaces.
- Prefer tags for controls whose visible copy may change.

Recommended stable surfaces:

- `openhalo.home.tab`
- `openhalo.notifications.tab`
- `openhalo.diagnostics.tab`
- `openhalo.start`
- `openhalo.stop`
- `openhalo.command.input`
- `openhalo.command.send`
- `openhalo.status.connection`
- `openhalo.status.service`
- `openhalo.status.reconnect`
- `openhalo.notification.history`
- `openhalo.notification.detail`

Target coverage:

- Home status rendering for connected, disconnected, reconnecting, and
  needs-setup states.
- Start/stop control state.
- Phone-originated text command entry and send button behavior.
- Notification history and detail navigation.
- Diagnostics navigation and stable display of recent Edge API state.

Current emulator command:

```powershell
powershell -ExecutionPolicy Bypass -File .\bin\test_m17_android_emulator.ps1 -AvdName OpenHalo_M17
```

This script reuses an existing Android Studio AVD. It does not create or
download an emulator image. It builds unit-test and debug/test APK artifacts,
installs only to the selected `emulator-*` serial, runs the Compose
instrumentation test class, and fails if instrumentation output reports
failures even when `adb shell am instrument` exits successfully.

If no emulator is already online, the script starts the existing AVD named by
`-AvdName`. If physical adb devices are attached, the script ignores them and
continues to target only the emulator serial.

Current emulator coverage:

- Daily home shell: title, connection status, service status, reconnect status,
  Start/Stop controls, command input, and disabled empty Send state.
- Phone command affordance: entering text enables Send through Compose
  semantics rather than adb text or coordinate scraping.
- Top-level app navigation: Home, Notifications, and Diagnostics are reachable
  through stable tags.
- Notification history/detail: persisted notification events render in the
  Notifications view and expose the stored detail body.
- Diagnostics state display: updated connection/service/error/recent
  observation/recent action state is visible in the Diagnostics view.
- Config persistence: runtime mode, runtime URL, device ID, and token configured
  state round-trip through Android shared preferences.
- History retention: mobile event history remains newest-first and bounded.
- Service intent contracts: start, stop, send-observations, and submit-text
  intents preserve the expected action names and payload extras.
- Android health helpers: full-screen alert and battery/background status helper
  calls return usable state strings in instrumentation.

This is a functional coverage matrix for the app surface. It complements, but
does not replace, line/branch coverage for pure Kotlin logic.

## 3. Instrumentation And UI Automator

Purpose:

- Verify real Android/device behavior that unit and Compose tests cannot prove.

Target coverage:

- Foreground service lifecycle.
- Accessibility service enablement and screen-context observation toggle.
- Notification runtime permission behavior.
- Full-screen alert availability and alert activity behavior.
- Battery/background restriction settings affordances.
- System settings intents.
- App interactions with Android notification surfaces.

Use instrumentation or UI Automator when the flow crosses from the app into the
Android system. Do not model these flows primarily through Python XML scraping.

## 4. adb Installed-Build Smoke

Purpose:

- Prove that an installed build can launch and participate as a real
  `Device Edge`.
- Collect a small, robust evidence bundle from a physical phone.

Command:

```powershell
python bin\verify_m17_android_device.py --tap-start --require-daily-ui --timeout-seconds 30
```

What this smoke check may verify:

- A device is visible through adb.
- The installed app launches.
- The foreground service is running.
- The app reaches `Connection: connected`.
- The app sends connect, capability announcement, and `mobile.context`
  observation frames, preferably confirmed through structured
  `OPENHALO_EDGE_EVENT` logcat evidence.
- The daily-use surface exposes a small set of visible health markers such as
  Home, Notifications, Diagnostics, Android Health, and reconnect state.

What this smoke check should not become:

- The primary test for command input, rich scrolling, keyboard behavior,
  notification detail navigation, or Compose state transitions.
- A replacement for stable Compose semantics or instrumentation tests.

If an adb smoke flow starts needing extensive scrolling, coordinate tuning,
keyboard handling, or repeated Compose control interaction, move that coverage
down into Compose tests or instrumentation tests.

## 5. Manual Live-Chain Acceptance

Purpose:

- Verify the real deployed chain across multiple live processes and devices.
- Confirm that a real source edge can cause the live runtime to route a governed
  action to the real Android phone edge.

Scenario:

```text
terminal edge -> public runtime -> Android phone edge
```

Expected flow:

1. Start or confirm the `Personal Runtime` on the server.
2. Start or confirm the Android edge app is connected to the same runtime.
3. Start a terminal edge against the same runtime.
4. Send a normal user request that should surface as a private text reply or
   phone notification.
5. Confirm the phone receives the runtime-delivered action.
6. Confirm the phone returns `action_result` with status `ok`.
7. Inspect runtime or edge diagnostics for source, target, participants,
   routed capability, and action result lineage.

During a manual action window, the adb smoke verifier may wait for the phone
side of the action:

```powershell
python bin\verify_m17_android_device.py --require-action --timeout-seconds 45
```

This is a milestone or human-acceptance check. It is not expected to run on
every local edit.

## 6. M17.5 Screen-Context Observation Acceptance

Purpose:

- Verify that the phone can observe current foreground-app screen context as
  passive evidence while OpenHalo itself is not the foreground Activity.
- Confirm the feature remains user-controlled, redacted, bounded, and free of
  raw screenshot upload by default.

Scenario:

```text
Android foreground service + AccessibilityService -> public runtime observation ingest
```

Expected flow:

1. Install the debug APK and connect the Android edge to the target runtime.
2. In Settings, enable `屏幕上下文`.
3. Open `无障碍观察`, enable the OpenHalo accessibility service, and return to
   the app.
4. Confirm developer diagnostics show `mobile.screen_context` in registered
   capabilities and a non-empty Screen Context state.
5. Background OpenHalo, interact with several normal apps such as chat,
   browser, and settings, then return to OpenHalo diagnostics or inspect
   runtime state/logs.
6. Confirm `mobile.screen_context` observations arrive through the normal Edge
   API with `source=accessibility`, `capture_mode=accessibility_tree`,
   indexed `interactive_elements`, bounded `visible_text_summary`, sensitivity
   metadata, provenance, and `raw_screenshot_uploaded=false`.
7. Confirm sensitive or locked/screen-off cases produce blocked/redacted or
   health-only evidence rather than rich text or screenshots.
8. Confirm no runtime action, reply, or proactive intervention is triggered by
   these observations during M17.5 acceptance.

Current automated coverage:

- `EdgeApiFramesTest` covers `mobile.screen_context` capability registration,
  redaction/blocking behavior, default no-screenshot provenance, and indexed
  interactive elements.
- `M17AndroidEdgeComposeTest` covers the settings toggle and accessibility row
  as user-facing controls.
- `GatewayTests.test_mobile_screen_context_observation_is_passive_evidence`
  covers passive runtime storage without intervention.

## Current Practice By Change Type

- Runtime routing/planning change: run runtime-side Python tests and
  `python bin\verify_m17_mobile_edge.py`.
- Android pure logic change: run unit tests for the touched behavior.
- Android Compose UI change: run Compose UI tests over stable tags/semantics.
- Android emulator workflow change: run
  `powershell -ExecutionPolicy Bypass -File .\bin\test_m17_android_emulator.ps1 -AvdName OpenHalo_M17`.
- Android system/device behavior change: run instrumentation or UI Automator
  tests, then the adb installed-build smoke check.
- Milestone acceptance: run the relevant unit/Compose/instrumentation tests,
  the runtime-side verifier, the adb installed-build smoke check, and manual
  live-chain acceptance.

Do not preserve the old practice of using adb UI-text scraping as the main
optimization or interaction-test workflow.
