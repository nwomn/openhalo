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

Do not expose `adb` directly to the public internet. If remote debugging is ever
needed, use a trusted private network and treat it as temporary debugging aid.

## Successful Run Indicators

- Android Studio device selector shows the connected phone model.
- Gradle sync completes successfully.
- `Run` installs the debug build to the phone.
- The launcher activity opens on the connected device.
- The app can connect to the runtime URL and show `Connection: connected`.
- The app shows `Service: foreground` while the Android edge session is active.
- The runtime mode switch can choose development runtime defaults or persistent
  runtime defaults.
- Local persistent runtime URL/token values come from ignored Android
  `local.properties`, not tracked source.
- The current persistent runtime endpoint is
  `ws://8.153.37.167/openhalo/edge`.
- The app token field matches the runtime edge token. Development helpers use
  `dev-token`; long-running server runtime tokens should match the server's
  `OPENHALO_EDGE_TOKEN` without exposing the secret in diagnostics.
- Runtime-delivered `notification.show` actions use the urgent alert presenter
  so messages can visibly pop up instead of requiring notification-shade search.

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
