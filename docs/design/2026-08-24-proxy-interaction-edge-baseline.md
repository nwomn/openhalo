# M17.11 Proxy Interaction Edge Baseline

Status: first contract, ESP-KVM adapter, host-run persistent-session
development harness, and governed Proxy Screen Profile/evidence protocol are
implemented and regression-covered. The initial native ESP-IDF component and
FreeRTOS state machine are now wired into the ESP-KVM Waveshare P4-WIFI6/C6
tree and compile cleanly. The first P4-WIFI6/C6 boot verifies the board task,
capture/HID, and C6 bring-up; public-Gateway session and real P4 screen-governance
acceptance remain pending.

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

## Deployment lifecycle

The normal Proxy Interaction Edge runs on the P4 controller itself. On every
power-up, the board-resident service starts the capture/HID adapter, restores its
P-256 identity and completed provisioning from board-local storage, waits for
real transport readiness, and reconnects to the Runtime. It does not require a
PC command or a fresh pairing code after a normal power loss.

An unprovisioned board enters a bounded local onboarding mode. A phone companion
or a local setup service supplies the Runtime endpoint and one-time pairing code;
the board completes P-256 pairing itself and retains only the resulting identity
and non-secret endpoint configuration. The one-time code is never retained.

`ProxyEdgeDaemon` is a Python development harness used to prove this public
session/adapter behavior against ESP-KVM before its native ESP-IDF equivalent is
accepted. It is not a product-side runtime component.

## Native ESP-IDF implementation slice

The ESP-KVM Waveshare P4 firmware now contains a thin `openhalo_edge` component
started after its existing `usb_hid_init()` and `capture_start()` calls. The
component has one FreeRTOS task and the fixed state sequence
`UNPROVISIONED -> WAIT_READY -> CONNECTING -> ONLINE -> BACKOFF`.

- Existing schema-driven ESP-KVM settings/NVS supply the selected `ws://` or
  `wss://` endpoint, an issuing CA PEM when TLS is selected, device/target/surface
  identity, target class, and a write-only
  one-time pairing code. The generic local settings page/hotspot remains the
  onboarding channel; no new browser control loop or Agent REST path is used.
- The P-256 device key is generated/restored in a separate board-local NVS
  namespace. After `connect_ok`, the task clears `oh_pair_code`; normal later
  boots use only the endpoint, device identifiers, and retained identity.
- `WAIT_READY` requires a routable selected Ethernet/Wi-Fi-station address, a
  locked HDMI capture with an initialized frame store, and an enumerated USB
  HID device. A setup AP or mere Wi-Fi association is explicitly not readiness.
  `CONNECTING` then performs the actual DNS/WebSocket connection (and TLS when
  `wss://` is selected) plus the OpenHalo challenge proof, so `ONLINE` is not
  reported before the selected transport succeeds.
- Availability metadata alone is not sufficient for a controllable proxy, but
  requesting a raw still before every input is not the normal control loop.
  Proxy screen control follows the Camera Edge pattern: Runtime confirms a
  surface-specific Screen Profile, selects only allowlisted/versioned screen
  Features, and receives structured low-cost observations from the Edge. The
  P4 keeps bounded, potentially relevant frames locally; a material screen
  change, a user inspection, or a governed verification step may cause Runtime
  to request one bounded evidence item through the normal Edge Session Link.
  Raw video is never continuously uploaded or retained remotely by default.
  Evidence transfer is size/rate/retention bounded, provenance/audit bound, and
  available only to the scoped Runtime/vision evaluation rather than general
  context memory. Keyboard/chord and absolute mouse move/click requests
  continue to use direct C APIs; a visually dependent action without the
  profile-required structured understanding or evidence is refused or
  escalated rather than executed blind.
- Disconnect/backoff destroys only the `esp_websocket_client`, uses bounded
  exponential retry, and re-announces the capabilities after reconnect. It does
  not reset capture, HID, the P4, or the C6.
- The Edge registers its bounded local evidence viewer before `WAIT_READY` so
  the existing capture pipeline allocates and publishes its encoded frame store.
  It releases that viewer again if provisioning is disabled. Registering only
  after `ONLINE` would deadlock readiness because an idle ESP-KVM encoder has no
  frame payload until it has a viewer.

## Screen Profile, Features, and Evidence

### Architecture status

The current hard Profile activation protocol below is a bounded host/runtime
experiment, not the durable Edge ingestion architecture.  The accepted
architecture baseline is [Edge Attention Profile Baseline](2026-08-30-edge-attention-profile-baseline.md): safe bounded base Observations remain
admissible without a Profile, while a future Attention Profile is a validated
overlay for additional registered Features, cadence, or local evidence policy.
Runtime Profile delivery and lease management are deferred and must not be
implemented as a prerequisite for the visual plus audio/microphone Edge closed
loop.

The Proxy Interaction Edge adopts the Camera Edge governance model, adapted to
a human-operated display. It is not a remote-video stream and it is not a
blind HID injector.

```text
Proxy Edge registers screen Feature capability
  -> Runtime confirms a target/surface Screen Profile
  -> Runtime sends a versioned allowlisted Feature Subscription
  -> P4 emits compact freshness/change/action-effect Observations
  -> candidate event, owner inspection, or governed verification needs evidence
  -> Runtime requests one bounded item from the P4-local evidence buffer
  -> scoped Runtime vision returns expiring structured Understanding
  -> Action Layer admits or refuses the next HID action under that policy
```

The initial registry should be deliberately small: capture health and
availability; frame freshness and material-change state; and action-correlated
screen-change state. Each result includes its feature/version, timestamp,
freshness, uncertainty, provenance, and expiry. A P4 digest or change detector
can report that pixels changed; it cannot truthfully infer arbitrary GUI text,
buttons, errors, or task state. Those cases are `unknown`/`evidence_needed`,
not a fabricated semantic Observation.

The selected Screen Profile defines the allowed feature identifiers, sampling
and debounce policy, privacy class, retention and evidence limits, and its
revision/expiry. It must not let Runtime send arbitrary detector code to the
board. The Edge maintains only a small policy-bounded local rolling frame
buffer. A `candidate_event` is an input to Runtime evaluation, not authority to
act. On an authorized evidence query, Runtime receives a bounded frame (or a
bounded action-correlated pre/post pair) over the authenticated Edge Session
Link, keeps the bytes out of ordinary durable context, and records the returned
visual Understanding with its evidence reference and expiry. Exact P4-native
feature schemas, buffer duration, and the production Runtime vision provider
remain implementation work and require compatibility review before they are
claimed as firmware behavior.

The first host/runtime protocol slice now implements the Profile and wire
boundaries: `proxy.screen.profile.configure` validates a target/surface-bound,
expiring allowlist; `proxy.screen.features` emits capture-health, digest-based
change, and action-effect Observations only when a Profile is active; and
`proxy.screen.evidence.read` queues a byte-limited `evidence_transfer` only
after its corresponding action result. Gateway accepts the transfer only when
that result is present, supplies the bytes to a transient injected vision
evaluator, records only safe audit metadata, and sends an expiring
`understanding_update`. Profile and Understanding frames additionally carry a
short monotonic lease for boards without a trusted wall clock; the RFC3339
expiry remains the Runtime audit value. Runtime without such an evaluator fails
closed as `understanding_failed`. When a Profile says `require_understanding`, the Edge
rejects keyboard/pointer input without the matching current authorization. This
is host/runtime protocol acceptance. The P4 native component now implements the
same bounded JPEG ring, Profile-selected Feature emission, authorized transfer,
and monotonic Understanding lease; a configured production vision provider and
the end-to-end Runtime-dispatched visual-control acceptance remain outstanding.

This is source integration with compile evidence, not acceptance evidence.
After GitHub HTTPS recovered, the declared `third_party/microlink` submodule was
restored at its locked revision. On 2026-08-29, ESP-IDF 6.1-rc1 built the
Waveshare P4-WIFI6 profile (`CONFIG_KVM_WIFI=y`) cleanly with the onboard C6
dependencies `esp_hosted` and `esp_wifi_remote` retained, plus
`esp_websocket_client` 1.8.0. The resulting `espkvm.bin` is 1,804,432 bytes;
the smallest 4 MiB app partition has 57% free. Flash, real public-Gateway
pairing/action/reconnect, and board-local key-at-rest review remain required
before claiming board execution or recovery success.

The first board boot is verified: the corresponding P4-WIFI6 image loaded on
the received ESP32-P4 rev 1.3, the C6 SDIO firmware negotiated a matching 3.0.6
host/co-processor session, the AP/DHCP path, TinyUSB HID, and 1280x720 C790
capture started, and `openhalo_edge` logged its task start after capture/HID
initialization. The initial board image was deliberately unprovisioned; the
subsequent live configuration uses the owner's public `ws://` Runtime endpoint,
which needs no CA. `wss://` remains supported but requires an issuing CA PEM.
No pairing/action/reconnect outcome is claimed until the target USB HID device
has enumerated and the board reaches `CONNECTING`.

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
- The development `ProxyEdgeDaemon` owns a persistent WebSocket session: a first run
  may pair its persisted P-256 identity with a one-time code, then it
  authenticates, announces current capabilities, publishes attachment state,
  and reconnects with the already paired identity. An adapter probe failure
  withdraws keyboard/pointer capability rather than treating WLAN association
  as readiness. A successful governed action is followed by a body-free fresh
  screen Observation carrying its originating `action_request_id`; raw JPEGs
  remain Edge-local. Focused contract/daemon coverage passes 14 tests.
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
- The first persistent-session development harness uses ESP-KVM as a replaceable capture/HID
  adapter and bring-up firmware. It does not make ESP-KVM's web console, Agent
  REST API, or unrelated services part of the OpenHalo product contract. Only
  after the public OpenHalo session is accepted will selected required drivers
  and recovery behavior be retained in a trimmed/replaced Proxy Edge firmware.
- Upstream ESP-KVM exposes its real-time keyboard/pointer channel as `WS /ws`.
  Its relative HID capability is therefore not assumed to be available through
  the temporary Agent REST adapter. The next relative-pointer slice must add a
  narrowly authenticated WebSocket adapter or a deliberately selected firmware
  endpoint, then bind its calibration profile to the same target/surface.
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
