# Android Edge Local Install Guide

Status: M17 local development setup baseline.

This document defines the local Android Studio setup for developing the native
Android `Device Edge`. The detailed Android edge testing workflow lives in
`docs/m17-android-edge-acceptance.md`.

## Intended Local Workflow

- Open the full `openhalo/` repository in Codex or another project-aware editor.
- Open only `openhalo/device_edge/android_edge/` in Android Studio.
- Keep Android-specific source code under `device_edge/android_edge/`.
- Run and debug the Android app from the local computer.
- Keep the Alibaba Cloud server focused on the OpenHalo `Personal Runtime`.

Use the same local checkout for Codex and Android Studio:

```text
~/dev/openhalo/                          <- open this in Codex
~/dev/openhalo/device_edge/android_edge/ <- open this in Android Studio
```

## Install Android Studio

Install Android Studio from the official Android Developers site:

- <https://developer.android.com/studio>
- Install guide: <https://developer.android.com/studio/install>

Recommended local setup:

- A recent stable Android Studio release.
- JDK bundled with Android Studio unless the Android project later pins a
  separate JDK.
- Android SDK Platform for the target SDK selected by the project.
- Android SDK Build-Tools installed through Android Studio.
- Android SDK Platform-Tools for `adb`.
- Kotlin and Gradle support from the standard Android Studio installation.
- At least one physical Android phone available for testing.

## Current Verified Local Baseline

The current local Android baseline includes:

- An Android Studio project under `device_edge/android_edge/`.
- Package name `dev.openhalo.android.edge`.
- Kotlin + Jetpack Compose.
- A successful debug install and launch on a USB-connected Android phone.
- A foreground-service Android edge that can connect to the runtime, announce
  capabilities, send `mobile.context`, execute `notification.show`, expose a
  status-first daily surface, and keep recent activity history.

## Prepare The Phone

Recommended phone setup:

- Android developer options enabled.
- USB debugging enabled.
- Wireless debugging optional, only on a trusted private network.
- Notification permission available for Android 13+ testing.
- Ability to review battery optimization and background restriction settings.

Quick local verification:

```powershell
adb devices -l
```

Accept the phone-side USB debugging trust prompt when it appears. Prefer a data
mode such as file transfer if the phone is not detected immediately.

## Debugging Expectations

Use Android Studio for:

- Installing debug builds on the phone.
- USB or trusted local wireless debugging.
- Logcat.
- Interactive UI debugging.
- Foreground service and notification permission checks.

## Runtime Connection Acceptance

For a public Runtime, configure the Android edge with its TLS endpoint:

```text
runtime_url = wss://<openhalo-domain>/openhalo/edge
```

Get a short-lived pairing code from the Runtime administrator. The first
connection exchanges that code for a device-specific credential, which the Edge
stores locally with the Runtime URL. Do not configure a public Android Edge
with `OPENHALO_EDGE_TOKEN` or a cleartext `ws://` endpoint.

Android uses the pairing contract on both development and public Runtime paths;
it never falls back to the Runtime shared token. Development pairing may use a
trusted local `ws://` Runtime, while public pairing requires `wss://`.

In the app, set the Runtime URL under Settings, select `Device pairing`, and
enter the one-time code. The code is used only for that connection attempt and
is never stored. After `connect_ok`, the app synchronously stores the returned
device credential in private app storage, excludes that storage from Android
backup and device-transfer, and never displays either secret in diagnostics.
Changing the Runtime URL or device ID, using `Reset connection`, or receiving a
revoked device-credential rejection clears the stored credential and requires a
new pairing code.

The Android edge must follow this frame order:

```text
connect
wait for connect_ok
capability_announce
observation_push / event_push / action_result
```

`capability_announce` registers capabilities on an already connected device; it
does not create the device. If `connect` returns `error` or the socket closes
before `connect_ok`, the Android edge should not send capabilities or
observations on that session. Log the failure locally and retry only after the
URL/credential problem is fixed.

Useful acceptance signals:

- Android logcat shows `connect_ok` before capability or observation frames.
- nginx access log shows `GET /openhalo/edge HTTP/1.1" 101` with an Android
  client such as `okhttp`.
- runtime diagnostics show a `Gateway/dispatch_reply` entry with
  `reply_type=connect_ok` for the Android `device_id`.
- runtime state contains the Android `device_id` after the successful connect.

If nginx shows `101` but runtime later logs `KeyError: '<android-device-id>'`,
the edge likely sent `capability_announce` before a successful authenticated
`connect`. Recheck the device credential and make sure the Android code waits
for `connect_ok`.

## First Sync And First Run Notes

## Successful Run Indicators

- Android Studio device selector shows the connected phone model.
- Gradle sync completes successfully.
- `Run` installs the debug build to the phone.
- The launcher activity opens on the connected device.
- The app can connect to the runtime URL and show `Connection: connected`.
- The app shows `Service: foreground` while the Android edge session is active.
- The runtime mode switch can choose development runtime defaults or persistent
  runtime defaults.
- No Runtime IP or URL is bundled as an Android default. A developer may set a
  local Runtime URL in ignored Android `local.properties` or in the app's
  Settings; Android authentication always comes from device pairing.
- Persistent Runtime configuration uses a `wss://` endpoint and a locally
  stored device-specific credential. A local test Runtime may use `ws://`, but
  it must issue the same one-time pairing code and device credential.
- Runtime-delivered `notification.show` actions use the urgent alert presenter
  so messages can visibly pop up instead of requiring notification-shade search.

Do not expose `adb` directly to the public internet. If remote debugging is ever
needed, use a trusted private network and treat it as temporary debugging aid.

## Current Test Workflow

Use the current Android edge testing workflow, not the old adb-first flow:

```text
unit tests -> Compose UI tests -> instrumentation/UI Automator -> adb installed-build smoke -> manual live-chain acceptance
```

Practice:

- Unit-test pure Kotlin behavior such as frame creation, reconnect/backoff,
  config/history persistence boundaries, and diagnostics mapping.
- Add Compose `testTag` or accessibility semantics before writing UI tests for
  important controls.
- Use Compose UI tests for app-internal daily-use flows such as status, command
  input, notification history, and diagnostics navigation.
- Prefer the Android Studio emulator for this automated UI layer. The current
  local emulator helper reuses the existing `OpenHalo_M17` AVD and installs
  only to the selected `emulator-*` serial:

```powershell
powershell -ExecutionPolicy Bypass -File .\bin\test_m17_android_emulator.ps1 -AvdName OpenHalo_M17
```

- Use instrumentation/UI Automator for device and system behavior such as
  notification permission, full-screen alert permission, foreground service
  lifecycle, system settings intents, and notification surfaces.
- Keep the Python adb verifier as installed-build smoke only.

Installed-build smoke command:

```powershell
python bin\verify_m17_android_device.py --tap-start --require-daily-ui --timeout-seconds 30
```

Runtime-side multi-edge routing verifier:

```powershell
python bin\verify_m17_mobile_edge.py
```

Manual live-chain acceptance remains a milestone/human check. See
`docs/m17-android-edge-acceptance.md` for the full workflow.

## Useful References

- Android Studio installation: <https://developer.android.com/studio/install>
- Run apps on a hardware device: <https://developer.android.com/studio/run/device>
- Android Debug Bridge: <https://developer.android.com/tools/adb>
- Foreground services: <https://developer.android.com/develop/background-work/services/foreground-services>
- Notification runtime permission: <https://developer.android.com/develop/ui/views/notifications/notification-permission>
- Android background restrictions: <https://developer.android.com/develop/background-work/background-tasks/bg-work-restrictions>
