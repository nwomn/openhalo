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

## Prepare The Phone

Recommended phone setup:

- Android developer options enabled.
- USB debugging enabled.
- Wireless debugging optional, only when the local computer and phone are on a
  suitable trusted network.
- Notification permission available for Android 13+ testing.
- Ability to review battery optimization / background restriction settings.

## Debugging Expectations

Use Android Studio for:

- Installing debug builds on the phone.
- USB or trusted local wireless debugging.
- Logcat.
- Interactive UI debugging.
- Foreground service and notification permission checks.

Do not expose `adb` directly to the public internet. If remote debugging is ever
needed, use a trusted private network and treat it as a temporary debugging aid,
not the primary M17 development path.

## Useful References

- Android Studio installation: <https://developer.android.com/studio/install>
- Run apps on a hardware device: <https://developer.android.com/studio/run/device>
- Android Debug Bridge: <https://developer.android.com/tools/adb>
- Foreground services: <https://developer.android.com/develop/background-work/services/foreground-services>
- Notification runtime permission: <https://developer.android.com/develop/ui/views/notifications/notification-permission>
- Android background restrictions: <https://developer.android.com/develop/background-work/background-tasks/bg-work-restrictions>

