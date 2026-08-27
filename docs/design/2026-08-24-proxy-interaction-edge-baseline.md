# M17.11 Proxy Interaction Edge Baseline

Status: first contract and adapter slice implemented; real governed HID and
Gateway acceptance remain pending.

## Goal

Add a hardware-independent Edge that can observe and operate an unmodified
computer, tablet, phone, server, or appliance through an attached interaction
surface. ESP-KVM is the first adapter and bench reference, not the product
contract.

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

## Still required for M17.11 acceptance

- Run the proxy as a paired long-lived Edge against the public Gateway and prove
  `connect_ok`, capability registration, observation persistence, Presence,
  governed action dispatch, result audit, disconnect, reconnect, and revocation.
- Resolve the current four-pin USB enumeration gap and prove keyboard plus pointer
  actions on the Xiaomi Pad 6S Pro.
- Add governed fresh-frame retrieval/understanding without exposing raw media to
  ordinary Runtime context.
- Measure `capture -> decision -> HID -> post-action capture` latency and bind the
  resulting observation to the originating action.
- Exercise one native-Edge-unavailable or pre-boot/recovery scenario.
- Extend or explicitly keep unavailable virtual media, power, and optional audio
  capabilities based on the selected adapter profile.
