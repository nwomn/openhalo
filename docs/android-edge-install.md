# Android Edge Local Install Guide

Status: M17 local development setup baseline.

This document defines the local Android Studio setup for developing the native
Android `Device Edge`. It is only about local tooling and phone setup. The M17
Android edge design is tracked separately in
`docs/plans/2026-06-30-m17-android-edge-design.md`.

## Intended Local Workflow

- Open the full `openhalo/` repository in Codex or another project-aware editor.
- Open only `openhalo/device_edge/android_edge/` in Android Studio once the
  Android project is scaffolded.
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

The current local Android baseline now includes:

- An Android Studio project scaffold under `device_edge/android_edge/`.
- Package name `dev.openhalo.android.edge`.
- Kotlin + Jetpack Compose Gradle project generation through Android Studio.
- A successful first debug install and launch on a USB-connected Android phone.
- A foreground diagnostic app surface that can connect to a configured runtime,
  start the foreground presence service, send `mobile.context` observations,
  execute `notification.show`, and expose recent Edge API activity for local
  verification.

This means the repository is now past the "tooling only" stage for M17 local
setup. The local Android path has been exercised through project creation,
Gradle sync, device recognition, debug install, and app launch.

## Prepare The Phone

Recommended phone setup:

- Android developer options enabled.
- USB debugging enabled.
- Wireless debugging optional, only when the local computer and phone are on a
  suitable trusted network.
- Notification permission available for Android 13+ testing.
- Ability to review battery optimization / background restriction settings.

Quick local verification steps:

- Confirm the phone is visible to Android Debug Bridge with `adb devices -l`.
- Accept the phone-side USB debugging trust prompt when it appears.
- Prefer a data mode such as file transfer if the phone is not detected
  immediately.

## Debugging Expectations

Use Android Studio for:

- Installing debug builds on the phone.
- USB or trusted local wireless debugging.
- Logcat.
- Interactive UI debugging.
- Foreground service and notification permission checks.

## First Sync And First Run Notes

On a fresh local Android Studio setup, the first Gradle sync and first run may
take noticeably longer than later runs because Android Studio and Gradle need
to download Android, Kotlin, and Compose dependencies.

You may also encounter a local proxy-authentication prompt such as
`Proxy Authentication: 127.0.0.1` during dependency resolution:

- If the machine intentionally uses a local proxy for Gradle traffic, provide
  the proxy credentials configured for that local proxy.
- If the machine does not intentionally require that proxy for Android Studio,
  cancel the prompt and let the normal local network path continue.

Successful first-run indicators:

- Android Studio device selector shows the connected phone model.
- Gradle sync completes successfully.
- `Run` installs the debug build to the phone.
- The launcher activity opens on the connected device.
- The app can connect to the runtime URL and show `Connection: connected`.
- The app shows `Service: foreground` while the Android edge session is active.
- The runtime mode switch can choose development runtime defaults or persistent
  runtime defaults. Local persistent runtime URL/token values should come from
  ignored Android `local.properties`, not tracked source. The current
  persistent runtime endpoint is `ws://8.153.37.167/openhalo/edge`.
- The app token field matches the runtime edge token; for development helpers
  this defaults to `dev-token`, while long-running server runtime tokens should
  match the server's `OPENHALO_EDGE_TOKEN` without exposing the secret in
  diagnostics.
- Runtime-delivered `notification.show` actions are treated as effective phone
  alerts on Android: the edge uses the urgent alert presenter so the message can
  visibly pop up instead of requiring the user to manually search the
  notification shade.
- `Send Observations` records a recent `mobile.context` observation.

Do not expose `adb` directly to the public internet. If remote debugging is ever
needed, use a trusted private network and treat it as a temporary debugging aid,
not the primary M17 development path.

## M17 Verification Workflow

M17 verification is layered rather than one large cross-device test:

1. Runtime-side simulated verifier for routing, candidate filtering, action
   result handling, and interaction lineage:

   ```powershell
   python bin\verify_m17_mobile_edge.py
   ```

2. Local real-device smoke verifier for Android app launch, connection, and
   observation delivery:

   ```powershell
   python bin\verify_m17_android_device.py --tap-connect --tap-observations
   ```

3. Manual live-chain acceptance for the full server-runtime-to-phone action
   path. During the manual action window, the device verifier can wait for a
   real phone-side `notification.show -> ok`:

   ```powershell
   python bin\verify_m17_android_device.py --require-action
   ```

See `docs/m17-android-edge-acceptance.md` for the full acceptance model.

## Useful References

- Android Studio installation: <https://developer.android.com/studio/install>
- Run apps on a hardware device: <https://developer.android.com/studio/run/device>
- Android Debug Bridge: <https://developer.android.com/tools/adb>
- Foreground services: <https://developer.android.com/develop/background-work/services/foreground-services>
- Notification runtime permission: <https://developer.android.com/develop/ui/views/notifications/notification-permission>
- Android background restrictions: <https://developer.android.com/develop/background-work/background-tasks/bg-work-restrictions>

