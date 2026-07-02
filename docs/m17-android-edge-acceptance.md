# M17 Android Edge Acceptance

Status: M17 acceptance workflow baseline.

This document defines how to verify the first native Android `Device Edge`
without turning every development check into a full cross-device live test.

The acceptance model is intentionally layered:

```text
runtime-side simulated verifier -> real-device smoke verifier -> manual live chain acceptance
```

## Layer 1: Runtime-Side Simulated Verifier

Purpose:

- Verify `Personal Runtime` multi-edge routing and lineage logic.
- Keep the check fast and deterministic.
- Avoid depending on Android Studio, a phone, public network reachability, or a
  live cloud runtime.

Command on Windows:

```powershell
python bin\verify_m17_mobile_edge.py
```

Command on Unix-like environments:

```bash
bin/verify-m17-mobile-edge
```

What it verifies:

- A terminal-like source edge connects through public Edge API frames.
- An Android-like edge registers `notification.show` and `mobile.context`.
- Competing speaker and ambient-light surfaces register as available candidates.
- `mobile.context` observations are accepted.
- A terminal text intent routes to the Android-like edge as `notification.show`.
- Nonchosen surfaces record filtered candidate reasons.
- The Android-like edge returns `action_result`.
- Interaction lineage preserves source, target, participants, action, and result.

This layer is the default regression check for runtime changes that may affect
M17 routing, planning, action dispatch, or interaction lineage.

## Layer 2: Local Android Real-Device Smoke Verifier

Purpose:

- Verify the actual Android app can run as a real `Device Edge`.
- Cover Android-local behavior that runtime simulation cannot prove, such as
  app launch, adb visibility, UI diagnostics, Android network policy, and
  observation delivery from a real phone.

Prerequisites:

- A debug build of `device_edge/android_edge/` installed from Android Studio.
- USB debugging enabled and the phone visible in `adb devices -l`.
- The runtime URL in the app points at the intended runtime. Use the
  restart-heavy development runtime on `ws://<server-ip>:18765` for Android
  acceptance unless intentionally testing the long-running server runtime on
  `ws://8.153.37.167/openhalo/edge`.
- The runtime mode switch selects development runtime settings when off and
  persistent runtime settings when on.

Command:

```powershell
python bin\verify_m17_android_device.py --tap-connect --tap-observations
```

What it verifies:

- An Android device is online through adb.
- The Android edge app launches.
- The foreground service owns the Edge API session while the UI exposes
  diagnostics and control.
- The app connects to the configured runtime.
- The app sends the configured Edge API auth token in the `connect` frame while
  foreground diagnostics redact the token value.
- The app sends `mobile.context` observations.
- A live `notification.show` action visibly pops up through the Android urgent
  alert path. A notification that only appears after manually opening the
  notification shade does not satisfy M17.2 phone-alert acceptance.
- The verifier can read foreground diagnostic state through UI automation.
- After installing the instrumented app build, the verifier can also read
  structured `OPENHALO_EDGE_EVENT` logcat evidence, including foreground
  service state.

Use this layer for Android app changes and before manual M17 live acceptance.

## Layer 3: Manual Live Chain Acceptance

Purpose:

- Verify the real deployed chain across multiple live processes and devices.
- Confirm that a real source edge can cause the live runtime to route a
  governed action to the real Android phone edge.

Scenario:

```text
terminal edge -> public runtime -> Android phone edge
```

Expected flow:

1. Start or confirm the `Personal Runtime` on the server.
2. Start or confirm the Android edge app is connected to the runtime.
3. Start a terminal edge against the same runtime.
4. Send a normal user request that should surface as a private text reply.
5. Confirm the phone receives `notification.show`.
6. Confirm the phone returns `action_result` with status `ok`.
7. Inspect runtime state or diagnostics for source, target, participants,
   routed capability, and action result lineage.

During the manual action window, the Android verifier can wait for the phone
side of the action:

```powershell
python bin\verify_m17_android_device.py --require-action
```

If the verifier also needs to reconnect the app first:

```powershell
python bin\verify_m17_android_device.py --tap-connect --tap-observations --require-action
```

This layer is a milestone or human-acceptance check. It is not expected to run
on every local code edit.

## Current M17 Practice

Use the layers as follows:

- Runtime or planning change: run Layer 1.
- Android app change: run Layer 1 and Layer 2.
- M17 milestone acceptance: run Layer 1, Layer 2, then manual Layer 3.

Do not treat a purely simulated verifier as proof that the Android device is
healthy. Do not treat a phone smoke check as proof that runtime lineage is
correct. The two checks cover different risks and are meant to complement each
other.
