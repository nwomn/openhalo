# M17.10 Ambient Camera Edge Design

Status: design baseline with a bounded Camera Edge bootstrap implementation.
The selected hardware sample has passed basic stock-device bring-up, the
Edge-session dependency probe, real-device P-256 proof verification, and one
owner-Runtime pairing/authentication session. It has no sustained connection,
Observation, evidence, or media-transfer validation yet.

This document records the proposed first implementation shape for a fixed home/desk camera Edge. It is intentionally a bounded ambient-observation design, not a commitment to continuous raw camera or microphone streaming.

The repeatable owner-development procedure is in [MaixCAM Camera Edge
Development Runbook](../ops/maixcam-camera-edge-runbook.md). It stores no
dynamic LAN address, pairing code, private key, or device credential.

## 0. Hardware validation preparation

The first physical experiment is deliberately a fixed, mains-powered desk or
room camera, rather than a battery-powered wearable. This keeps the first
question architectural: can a normal Camera Edge capture bounded evidence and
participate in the governed Runtime loop? It does not start a custom PCB,
wearable, or product-packaging workstream.

The selected physical validation target is the received **Sipeed MaixCAM
standard kit**, using its integrated display, Wi-Fi, vendor camera, a
user-provided 64 GB TF card flashed with the official MaixCAM system image,
stable USB-C power supply, and a simple desk/room mount. Its camera pipeline,
local display, and MaixPy/Linux development route make it a hardware-validation
target; this is not a requirement that all future Camera Edges use this board
or run a general Linux distribution.

The display is a local, diagnostic status surface, not a second interaction
channel or an ungoverned video viewer. The first display contract is read-only
and limited to provisioning/pairing state, Runtime-session connectivity,
camera state, capture/evidence-transfer state, storage health, and a
privacy/capture-active indicator. It must not show raw camera content by
default or create a transport path outside the public Edge API.

The validation kit has arrived, but the no-card SKU needs a first system flash
through a card reader before it can boot. The immediate evidence target is only
a stock bring-up: flash the exact MaixCAM image onto the user-provided 64 GB TF
card, boot to the device UI, obtain a Wi-Fi IP address, install the vendor
runtime libraries, run a factory camera example, and reach the device from the
development host over the local network. No OpenHalo hardware integration,
Runtime capability, or acceptance evidence exists yet.

2026-08-23 user-reported stock validation passed: the device joined Wi-Fi,
connected to the development host, ran `hello_maix.py`, and showed a normal
camera preview. This is hardware/SDK evidence only; it does not prove a
Gateway session, pairing, capability announcement, Observation, or video
transfer. The next probe checks whether the device system can run the
WebSocket and P-256 dependencies required by the existing public Edge API.

2026-08-23 dependency-probe result: Python `3.11.6`, OpenSSL `3.1.4`, and
`websockets 10.4` are present. `cryptography` is absent, so a P-256 private key
could not be generated and the existing OpenHalo P-256 pairing client cannot
run on the device yet. The repository's current client dependency range is
`websockets >=12,<16` and `cryptography >=46,<47`; before installation, inspect
the device ABI and package-manager/build-tool availability rather than assuming
a compatible prebuilt wheel exists.

2026-08-23 installation-path result: the device reports `riscv64`, has
`pip 22.3.1`, and has neither `gcc` nor `rustc`. Direct inspection of the
official PyPI file lists for `cryptography 46.0.3` and `46.0.6` found no Linux
`riscv64` wheel, so the current dependency range would fall back to a source
build that this device cannot perform. Do not add a compiler/Rust toolchain as
the prototype default. Instead, first validate a narrow signer backend that
uses the device's existing OpenSSL command-line support for the required
P-256/prime256v1 key and ECDSA-SHA256 signature; it must still produce the
same PKCS#8, SPKI DER, and DER-signature wire values expected by the public
Edge API.

2026-08-23 OpenSSL bootstrap implementation and physical verification passed:
`device_edge.camera.openssl_session` now creates a persistent prime256v1
PKCS#8 identity through the device's OpenSSL binary, derives its SPKI DER public
key, and emits the normal `edge.runtime.v2.auth` ECDSA-SHA256 proof without
depending on `cryptography`. The module was deployed to the MaixCAM over the
owner-authorized SSH development channel. The device created its persistent
identity, signed a canonical OpenHalo challenge payload, and the resulting
SPKI/signature pair was accepted by the repository's Gateway signature
verifier on the development host. This proves cryptographic wire compatibility
only: no pairing code, Runtime endpoint, WebSocket session, capability
announcement, Observation, or camera media was sent. The next step requires an
owner-selected Runtime endpoint and one-time pairing code.

2026-08-23 owner-Runtime pairing verification passed: the owner-selected
Runtime `ws://8.153.37.167:8765` was live (`openhalo 0.1.22`, listening on
`0.0.0.0:8765`). A newly issued five-minute one-time code was transferred only
to the authenticated MaixCAM process and was not recorded in this repository.
The persistent device key completed `connect -> auth_challenge -> auth_proof
-> connect_ok`; it then emitted the minimal `camera.health` capability
announcement before the bounded probe closed its WebSocket. The Runtime's
paired-device registry confirms an active, non-revoked `camera-edge-1` record
named `Desk Camera`, with the expected direct-IP audience and a current
authentication timestamp. This is pairing and public session evidence, not a
claim that the Runtime has a Camera Feature registry, a long-lived Camera Edge
service, camera Observations, retained evidence, or media transfer.

Immediately after pairing, the device opened a second WebSocket without a
pairing code, completed the same challenge/proof flow with the retained
identity, and emitted `camera.health` again. The Runtime retained the active
record and advanced its `last_authenticated_at` timestamp. This verifies that
the stored key, rather than the one-time code, is sufficient for later Camera
Edge authentication.

2026-08-23 health-only session verification passed: the new Camera Edge
service registers `camera.health` as an `observation_provider` with four
versioned, schema-validated health fields. A physical MaixCAM `--once` run
authenticated normally, did not initialize the camera (`capture_state` was
explicitly `not_checked`), atomically wrote the local status payload, and sent
one Observation batch. The owner Runtime persisted the registered capability
and all four values: connection `connected`, capture `not_checked`, storage
`ready`, and a bounded numeric free-space report. This is not a persistent
process, local display implementation, camera capture, Feature subscription,
Evidence, or raw-media test.

2026-08-23 explicit capture-probe verification passed: using the vendor Maix
SDK, the device opened the GC4653 sensor at 320x240, read exactly one frame in
memory, reported only success and dimensions to the owner development channel,
then released the multimedia driver. No image was saved, displayed, sent to
Runtime, or added to a diagnostic record. The service exposes this only behind
an explicit `--capture-probe` switch; normal health reporting retains
`capture_state=not_checked` and does not compete with MaixVision preview.

2026-08-23 display-adapter finding: a direct `maix.display.Display()` attempt
also initialized the vendor multimedia/sensor stack and kept the device's SSH
management path unresponsive longer than the bounded five-second rendering
window. The device later recovered and no display process remained. Do not use
that adapter as a "status-only" surface or ship it beside capture code. The
atomic local status JSON remains the current read-only status contract; a later
display design must first establish safe single-owner multimedia lifecycle.

2026-08-23 development-host reachability verification passed: ICMP and TCP/22
reached the device, while an unauthenticated SSH attempt was correctly denied.
No device credential was used and no device state was changed. An authenticated
but read-only dependency probe remains the next task.

The initial hardware-validation acceptance is limited to:

1. The device can establish a normal authenticated `Device Edge` session over
   the public Edge API and report camera, storage, and connection health.
2. It can create a bounded local video clip on a simple trigger and make that
   clip available only through a Runtime-governed evidence request.
3. It can retain a short, bounded local buffer or explicitly record the
   platform limitation; continuous raw-media upload is not a fallback.
4. The experiment records power, thermal, storage-write, network reliability,
   and capture-indicator/privacy-control findings before a custom board is
   considered.
5. The local display renders the bounded diagnostic-status contract without
   exposing raw camera content or becoming an independent control plane.

Non-goals for this experiment are on-device VLM inference, continuous cloud
recording, a wearable/battery design, and custom PCB fabrication. On
2026-08-23 the owner explicitly authorized this bounded M17.10 implementation
slice; it does not make the milestone accepted or authorize the later raw-media,
Feature/Scene-Profile, or Runtime-understanding work.

## 1. Architecture position

The camera is a normal `Device Edge`, not a backend-owned camera adapter and not a second agent runtime. Its physical path is:

```text
Camera sensors
  -> local Edge processing and bounded evidence buffer
  -> Edge API
  -> Edge Session Link
  -> Gateway
  -> Personal Runtime
```

`Personal Runtime` remains authoritative for:

- scene/profile confirmation and change governance;
- feature subscription policy, privacy, permissions, and retention;
- high-level video/audio understanding;
- evidence correlation, Presence, and action decisions.

The camera Edge is responsible for local capture, low-cost feature extraction, candidate-event detection, and bounded pre/post-event evidence buffering. A Runtime model may be local or a governed remote provider, but the camera Edge does not directly depend on a model provider.

## 2. Core vocabulary

The implementation must keep these objects separate:

| Object | Meaning | Owner |
| --- | --- | --- |
| `Feature` | A registered, versioned extractor or detector capability, such as person presence or VAD | Runtime capability/feature registry |
| `Observation` | One timestamped, schema-valid structured result from a Feature | Edge, with Runtime provenance |
| `Event` | A bounded temporal change inferred from one or more Observations | Edge proposes; Runtime evaluates |
| `Evidence` | A bounded video/audio segment that supports an Event or a Runtime query | Edge stores/captures; Runtime governs retrieval |
| `Understanding` | Runtime model interpretation of Observations plus Evidence | Personal Runtime |

The Edge should emit typed, schema-validated observations rather than asking a small model to freely generate arbitrary JSON. Model-assisted extraction, if later needed, must still terminate at a registered Feature schema.

## 3. Scene and feature subscription flow

The intended setup flow is:

```text
Camera Edge registers
  -> Runtime inspects capability and initial bounded evidence
  -> Runtime proposes or confirms a Scene Profile
  -> user confirms or edits the profile when needed
  -> Runtime selects allowlisted Features
  -> Runtime sends a versioned Feature Subscription
  -> Edge continuously emits structured Observations
```

A first profile might be:

```text
scene: living_room
placement: fixed_camera
features:
  - person_presence
  - person_entered
  - object_present
  - door_state
  - speech_activity
  - known_person_candidate   # only with explicit enrollment and consent
```

The Runtime may propose a profile from an initial scene sample, but one model guess must not permanently become a fact. The user or an explicit policy must be able to confirm, edit, pause, or revoke the profile.

Feature subscriptions are selected from a capability/feature registry and include a feature identifier, version, parameters, output schema, sampling/debounce policy, privacy class, and expiry/revision information. The Runtime must not ask the Edge to execute arbitrary model-generated code or an unregistered monitoring task. Adding a new Feature requires registry, version, permission, and compatibility checks.

## 4. Local Edge responsibilities

The first Edge implementation can use small, bounded components for:

- person/object detection and tracking;
- region entry/exit and coarse state changes;
- object appeared/disappeared detection;
- VAD and optionally bounded local ASR;
- authorized known-person candidate matching;
- a local circular video buffer and optional audio buffer.

These components are detectors, not the source of high-level meaning. For example, `person_presence=true` is useful immediate evidence; deciding that a delivery person left a package, that two people are arguing, or that an action is needed belongs to Runtime understanding and Presence governance.

Each Observation should include at least:

```json
{
  "type": "person_presence",
  "schema_version": "1",
  "observed_at": "2026-08-05T12:00:00Z",
  "value": {"present": true, "count": 1},
  "confidence": 0.94,
  "source": {"device_id": "camera-edge-1", "feature_version": "..."},
  "privacy": {"raw_media_included": false},
  "expires_at": "2026-08-05T12:00:10Z"
}
```

The exact wire schema remains an implementation task, but the contract must support freshness, confidence/uncertainty, provenance, privacy classification, and expiry. A feature that cannot produce a meaningful result should report an explicit unavailable/degraded state rather than silently appearing absent.

## 5. Event and evidence path

To preserve useful responsiveness without continuously uploading media, the Edge uses two related paths:

```text
Feature change
  -> immediate candidate_event Observation/Event
  -> Runtime updates compact state quickly

Feature change
  -> Edge freezes bounded pre-event ring buffer
  -> Edge records bounded post-event interval
  -> Runtime requests or receives authorized Evidence
  -> Runtime video/audio model returns Understanding
  -> Runtime records understanding.ready or a bounded failure state
```

The initial buffering target is a configurable 5–10 second pre-event ring plus a finite post-event clip. The exact duration, frame rate, audio inclusion, size limit, and retention are policy values rather than hard-coded assumptions. Raw media remains on the Edge by default and is uploaded only for an accepted/authorized evidence request, an explicitly configured event policy, or a user-initiated inspection.

`candidate_event` is not automatically an accepted event and must not directly trigger an action. Runtime decides whether the candidate is relevant, whether more evidence is needed, and whether the result should enter the normal observation/proposal/Presence path.

The understanding lifecycle should be inspectable:

```text
pending_understanding
  -> understanding_ready
  -> understanding_failed
  -> evidence_unavailable
```

An event can remain useful as structured evidence even when its video is unavailable or model understanding fails. The Runtime records timestamps, model/provider version, confidence, provenance, and evidence references for every returned Understanding.

## 6. Runtime query and model boundary

Runtime may use the public Edge API to request, subject to policy:

- structured Features or Observations for a bounded time window;
- additional details for a known Observation;
- the short Evidence associated with an Event;
- an authorized audio or video segment when the current context justifies it.

These requests still travel through `Edge Session Link <-> Gateway`; Runtime must not bypass the Gateway or access camera internals directly.

Complex interpretation stays in Personal Runtime, including:

- cross-frame event explanation and summarization;
- relations between people, objects, regions, and time;
- combined video/audio interpretation;
- semantic identity reasoning beyond an authorized candidate signal;
- deciding whether an observation warrants an Interaction Proposal.

The model output remains a Runtime candidate/understanding. It cannot bypass privacy checks, Presence Router, action validation, or the normal result/audit path.

## 7. Privacy, retention, and failure boundaries

- Raw camera and microphone data are local by default; structured observations should be minimized and bounded too.
- Identity features, face embeddings, voice, and raw audio/video are sensitive and require explicit authorization, retention, and deletion behavior.
- `known_person_candidate` is opt-in and must not be treated as an unconditional identity assertion.
- Edge and Runtime both need bounded queues, expiry, deletion, and backpressure behavior.
- A disconnected or overloaded Edge reports health/availability and does not cause Runtime to infer that no person or event exists.
- Evidence upload is bounded, resumable or explicitly failed, and correlated to the originating Event.
- All accepted observations and understandings retain safe provenance without copying raw sensitive media into diagnostics by default.

## 8. Implementation sequence and non-goals

The first implementation sequence should be:

1. Register a fixed camera Edge and expose a small Feature Registry.
2. Implement one or two structured Features, such as `person_presence` and region entry/exit.
3. Add freshness-aware Observations, candidate Events, and local ring-buffer retention.
4. Add Runtime Feature Subscription and bounded Feature/Evidence queries.
5. Add Runtime video understanding and the `pending_understanding` lifecycle.
6. Validate the full Gateway boundary, privacy controls, retention, and human acceptance with a real fixed-camera scenario.

The initial owner-authorized slice implemented step 1 as a persistent
health-only session: it registers `camera.health`, sends connection,
capture-probe, and storage health Observations, and atomically maintains a
bounded local status payload. `capture_state=not_checked` is intentional: that
health-only mode must not seize the sensor while MaixVision is previewing it.

On 2026-08-23 the owner authorized the first bounded Feature, implemented as
an opt-in `camera.person_presence` capability with the registered Observation
`camera.person_presence.v1`. One process owns `maix.camera.Camera()` and
`maix.nn.YOLO11()`; it filters to the built-in `person` class, confirms a state
only after a configurable number of matching local samples (two by default),
and emits `{state, count, feature_version}` plus a model confidence. It never
writes a frame, sends image bytes, keeps a bounding box, exposes another class
label, or enables face/OCR/gesture inference. `unavailable` is an explicit
state rather than a false `absent` result. This is a device-authorized Feature
implementation, not yet Runtime Scene-Profile/Feature-Subscription governance
or full M17.10 acceptance.

The first physical Feature run on 2026-08-23 authenticated to the owner
Runtime, registered `camera.person_presence`, and persisted a schema-valid
`camera.person_presence.v1` Observation with `state=unavailable` and
`count=null`; the Runtime recorded it as ordinary low-salience evidence. The
MaixCAM's camera/ISP pipeline then timed out even with the previously working
minimal capture configuration after a stale experimental `status_display.py`
process had been terminated. This was deliberately not counted as a
`present`/`absent` acceptance result.

After the owner rebooted the MaixCAM, a repeated one-shot Feature run completed
the local Camera -> YOLO11 -> P-256 Edge Session Link -> Gateway -> persisted
Observation path. The Runtime stored `camera.person_presence.v1` from
`camera-edge-1` as `{state: "absent", count: 0, feature_version:
"person_presence.v1"}` at `2026-08-23T09:48:17.464423Z`; the device logs also
confirmed normal vendor multimedia release. This is narrow physical acceptance
for the Feature's `absent` state and safe `unavailable` failure state, not an
identity claim, a `present`-scene evaluation, a supervised service, or full
M17.10 acceptance. Do not restart vendor services or install a boot daemon
without a separate owner decision.

The next owner-authorized packaging step is a minimal, manually launched Maix
App with ID `openhalo_camera_edge`. It will package the existing local-only
Feature files with a `main.py` entrypoint, read only a device-private Runtime
configuration and retained P-256 identity, and own the camera/NPU until the
Maix Launcher or MaixVision stops it. It intentionally has no `Display()` UI,
no system service, and no boot auto-start in this validation stage. Only after
manual Launcher lifecycle acceptance may the owner choose Maix's App-level
auto-start mechanism.

The minimal package was generated with `maixtool` and installed through the
device's `app_store_cli` on 2026-08-23. The follow-up `0.1.1` package embeds
the confirmed OpenHalo primary logo and is installed with
`icon=assets/openhalo-logo-primary.png` and `exec=main.py` in
`/maixapp/apps/app.info`; the packaged PNG exists on the device. This is
metadata/install evidence only until the owner visually confirms it in the
Launcher. Its device-private configuration exists with restrictive permissions,
and no App auto-start entry exists. A
direct SSH invocation of that installed entry is explicitly not a valid App
lifecycle acceptance: while the MaixVision/Launcher multimedia environment was
still active, the vendor SDK reported `vi_sdk_enable_chn ... Out of memory` and
then crashed in its own multimedia path. The process exited and did not emit an
Observation. The next test must therefore be user-launched from the physical
Maix Launcher, which owns the App lifecycle; do not retry foreground App start
through SSH or set boot auto-start before that test passes.

The owner then launched `openhalo_camera_edge` manually from the physical
Launcher. The App stayed active and Runtime persisted two fresh semantic-only
`absent` Observations 30 seconds apart, including the latest at
`2026-08-23T10:17:06.958198Z`. The owner then stood in view: Runtime persisted
repeated `{state: "present", count: 1}` Observations, latest at
`2026-08-23T10:22:24.248688Z` with confidence `0.859375`. This accepts the
minimal App's Launcher-managed lifecycle, retained camera/NPU ownership,
periodic Feature freshness path, and basic absent-to-present transition. It is
not an identity, multi-person, distance, or accuracy evaluation. The
intentionally UI-less App presents a black screen in this version; that is not
a camera failure. A single-process local
status UI, and a deliberate App-level boot-auto-start decision remain separate
work.

The first slice does not require continuous cloud video, full open-vocabulary detection, unrestricted face recognition, a general-purpose Edge agent, or packaged ambient-home hardware. Packaging and provisioning remain later product work under M22.
