# M17.11 Proxy Interaction Edge Baseline

Status: first contract and adapter slice implemented; real governed HID and
Gateway acceptance remain pending.

## Goal

Add a hardware-independent Edge that can observe and operate an unmodified
computer, tablet, phone, server, or appliance through an attached interaction
surface. ESP-KVM is the first adapter and bench reference, not the product
contract.

ESP-KVM is also not the required product firmware base. Its source tree and REST
surface are disposable bring-up tools: the product may keep selected capture or
HID drivers while removing unrelated services, or replace the firmware
entirely. Only the governed OpenHalo contract and accepted physical behavior are
stable across implementations.

## Architecture boundary

The normal path is mandatory:

`capture/input adapter -> Proxy Interaction Edge -> Edge Session Link -> Gateway -> Personal Runtime`

The proxy has its own paired identity. The controlled target and its interaction
surface are explicit attachment records; neither is silently treated as the
proxy device itself. Adapter credentials and raw frames remain Edge-local.

Runtime retains permission, Presence, exact provider selection, action request
correlation, result lineage, and audit. The adapter cannot call Runtime directly
or execute a Runtime proposal without an `action_request` delivered to its proxy
device identity.

## Target-facing connector profile

The intended product packaging exposes one full-function USB-C male target lead
for both observation and control. A target with native USB-C DisplayPort Alt
Mode and USB host support connects directly: DisplayPort flows from the target
to the Proxy Edge, while the Proxy Edge's USB HID device traffic flows back to
the target over the same cable.

Legacy computers remain supported through an active host-side aggregation
accessory. That accessory accepts one GPU HDMI or DisplayPort source plus one
USB-A or data-capable USB-C host connection, and exposes a full-function USB-C
female receptacle for the Proxy Edge target lead. It must synthesize the correct
DisplayPort Alt Mode, USB data-role, CC, and power behavior; a passive gender or
video-only adapter is not sufficient. The current split HDMI capture and
four-pin USB HID bench wiring remains the validation baseline until this
single-cable accessory is selected and physically accepted.

This connector profile is a product-surface direction, not a change to the
hardware-independent Proxy Interaction Edge contract. Other adapters may retain
separate physical video and input paths while exposing the same governed Edge
capabilities.

## Public contract

The baseline capability bundle is:

- `proxy.interaction.observe`
  - `proxy.target_attachment.v1`
  - `proxy.screen_frame.v1`
- `proxy.keyboard.input`
- `proxy.pointer.input`

Each attachment reports:

- `target_id`, `surface_id`, and `target_class`
- attachment state: `detached`, `attached`, `degraded`, or `incompatible`
- adapter identity/kind and physical requirements
- explicit availability for screen, audio, keyboard, pointer, virtual media,
  and power
- optional `native_device_id` for native/proxy provenance binding

Only available or degraded input facets are announced as action providers.
Every input action repeats the exact `target_id` and `surface_id`; the Edge
rejects a mismatch before invoking hardware.

Pointer coordinates are normalized to `[0, 1]` in the OpenHalo contract. The
ESP-KVM adapter alone converts them to its `0..32767` absolute-HID range. Text
input is currently bounded to 80 US-ASCII characters because that is the first
adapter's safe request limit; arbitrary Unicode input remains a later adapter or
clipboard capability.

## Screen evidence boundary

A fresh ESP-KVM still is fetched from `/api/v1/video/frame.jpg` only in MJPEG
mode. The JPEG is retained in a small bounded Edge-local frame store. Runtime's
ordinary observation receives only metadata and a body-free
`proxy-evidence://...` reference. This preserves the project rule that raw media
does not enter ordinary context or semantic memory.

The observation labels its source as `human_visible_pixels`. It must not be
interpreted as structured Android, Windows, BIOS, or application state. A later
governed understanding worker may resolve an authorized frame reference and
produce separately attributed visual inference.

## First ESP-KVM adapter

The adapter uses authenticated REST endpoints already present in the bench
firmware:

- `GET /api/v1/video/status`
- `GET /api/v1/system/usbprobe`
- `GET /api/v1/video/frame.jpg`
- `POST /api/v1/hid/move`
- `POST /api/v1/hid/click`
- `POST /api/v1/hid/key`
- `POST /api/v1/hid/type`

The firmware's agent API remains off by default and must be explicitly enabled
for a controlled bench. Credentials stay in the Proxy Edge process and are
never emitted in capability, observation, diagnostic, or action-result frames.

## Implemented acceptance evidence

- Independent proxy device identity and explicit target/surface relationship.
- Explicit compatible, incompatible, attached, detached, degraded, available,
  and unavailable states.
- Body-free screen observation with bounded Edge-local JPEG retention.
- Exact proxy device, target, and surface checks before keyboard/pointer calls.
- Action-result preservation of request, interaction, and interaction-turn
  correlation.
- Native/proxy provenance link through optional `native_device_id`.
- ESP-KVM probe, still-frame, key, pointer, session-auth, and normalized-coordinate
  adapter boundaries.
- ESP-KVM `agent_api` state is part of capability probing; disabled agent access
  makes screen and HID unavailable. A USB enumeration trace is only degraded
  HID evidence until an actual governed action succeeds.
- Real bench evidence confirms an authenticated `1280x720` JPEG still can be
  fetched after enabling the upstream Agent REST API. A post-lock fetch still
  displayed the prior/external tablet canvas, so lock-screen semantics and HDMI
  freeze/presentation behavior remain an explicit target-compatibility gap.
- A temporary isolated-bench profile with ESP-KVM `Require login` disabled also
  survived restart and returned changed JPEG frames without credentials. This is
  a bring-up convenience, not a deployment default: every network participant
  can otherwise read the screen and invoke the enabled HID REST endpoints.
- Real Xiaomi Pad 6S Pro bench evidence accepts HDMI observation plus relative
  USB-HID movement, button hold, continuous drag, release, and a visually proven
  post-action line on the same note surface. The current absolute-pointer path
  remains unsuitable for the tablet's rotated external display.
- Real Windows desktop bench evidence accepts the split GPU-HDMI plus USB-HID
  transport and a same-surface keyboard loop. In Windows duplicate mode, a KVM
  pre-frame showed Notepad with `OPENHALO-SAFE-135`, Agent REST typed a newline
  plus `OPENHALO-DUPLICATE-1142`, and the KVM post-frame visibly showed both
  lines. This result does not depend on target process or window-title state.
- The same duplicate-mode desktop profile accepts absolute pointer placement. A
  KVM-observed click at adapter coordinates `x=3456,y=3095` moved the Notepad
  caret onto the first line, and the following `MOUSE-` input appeared at that
  location in the post-action KVM frame.
- After a 30-second no-viewer interval, the first requested JPEG returned in
  about 1.4 seconds and already contained a just-injected HID marker; the second
  frame agreed. A one-frame retry remains defensive for display-mode changes,
  where a prior first request returned the immediately preceding frame once.
- A controlled upstream-firmware restart restored the ESP32-C6 AP and WLAN
  association but left P4 HTTP availability intermittent even after manual WLAN
  reassociation. This is recorded as reference-stack evidence, not a requirement
  to repair ESP-KVM before continuing Proxy Interaction Edge development.
- A later Waveshare P4 rev 1.3 / C6 `3.0.6` bench build enabled P4 internal
  pull-ups on SDIO CLK/CMD/D0--D3 before ESP-Hosted initialisation, supplementing
  the board's 51k external pull-ups. At 4-bit 40 MHz streaming, three P4/C6
  resets followed by explicit WLAN reassociation each recovered DHCP and HTTP;
  ten further reassociation cycles completed thirty page requests, and a
  100-request page burst transferred about 22 MB without error. Windows did not
  autojoin in the first eight seconds after one P4 reboot despite a visible SSID,
  but explicit reassociation succeeded. This is controlled single-client
  reference-stack transport evidence, not an accepted long-duration, multi-client
  or product-firmware recovery guarantee.
- For the first desktop profile, the capture output must duplicate the operator's
  primary desktop or otherwise be the explicitly governed target surface.
  Extended multi-monitor mode is degraded until surface selection, foreground
  focus, virtual-desktop pointer mapping, and destructive-shortcut safeguards are
  explicit. A window being visible on one screen is not evidence that it owns
  keyboard focus.

## Still required for M17.11 acceptance

- Run the proxy as a paired long-lived Edge against the public Gateway and prove
  `connect_ok`, capability registration, observation persistence, Presence,
  governed action dispatch, result audit, disconnect, reconnect, and revocation.
- Add the governed relative-pointer/calibration contract needed by the accepted
  Xiaomi Pad 6S Pro hardware path.
- Add governed fresh-frame retrieval/understanding without exposing raw media to
  ordinary Runtime context, implementing the accepted one-retry freshness policy
  and action-bound post-observation behavior.
- Measure `capture -> decision -> HID -> post-action capture` latency and bind the
  resulting observation to the originating action.
- Define and accept recovery against the selected Proxy Edge firmware and
  transport; upstream ESP-KVM AP/P4 recovery behavior is nonbinding.
- Select and validate the active legacy-computer aggregation accessory, including
  video capture, USB HID return, hot-plug recovery, and independent Edge power
  through the intended single target-facing USB-C lead.
- Extend or explicitly keep unavailable virtual media, power, and optional audio
  capabilities based on the selected adapter profile.
