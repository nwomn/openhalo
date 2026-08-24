# M24 Cellular Camera Edge Product Hardware Design

Status: future independent product-hardware milestone. Not active for
implementation.

## 1. Purpose and boundary

`M24` defines the production fixed-camera `Device Edge` that can connect
without relying on a deployment site's Wi-Fi or Ethernet. It follows the public
Edge contract validated by the MaixCAM-based `M17.10` slice, but is a distinct
milestone with separate hardware, carrier, certification, and field-operations
acceptance.

The received MaixCAM remains a v1 scene, local-feature, privacy, and protocol
validation platform. It is not a production-hardware reference and its
Wi-Fi-only bearer is not a product requirement.

## 1.1 Product integration and cost baseline

M24 begins from a **MaixCAM-class low-cost local-vision base**: sufficient
on-device camera/ISP/NPU capability for bounded local Features, rather than a
high-end video-monitoring appliance. The later product is an integrated PCB and
purpose-designed enclosure derived from that class of platform; it is not a
resold MaixCAM development kit. The exact SoC, camera, memory, and retained
peripherals remain a procurement decision.

The exploratory per-unit price model includes recurring and per-unit costs such
as cellular additions, manufacturing, warranty, certification allocation, and
sales/channel costs. It deliberately excludes one-time integrated-PCB,
enclosure-design, and hardware-R&D expenditure from current per-unit sales-cost
calculations. This accounting choice is a product-exploration assumption, not a
claim that the excluded work has no investment or recovery requirement.

## 1.2 Exploratory price baseline

The provisional direct-sale price ladder is:

| SKU | Provisional price | Connection ownership |
| --- | ---: | --- |
| Physical-SIM basic | ¥299 | User chooses and pays the carrier plan |
| eSIM | ¥349 | User chooses and pays the compatible carrier plan |
| Dual-mode | ¥399 | User chooses and pays either compatible plan |

These are target prices, not supplier quotes or launch commitments. They assume
a MaixCAM-class cost discipline, user-paid connectivity and shipping, no default
power adapter or mount, a feature-constrained local-vision product, and enough
scale for the physical-SIM basic SKU to hold its complete per-unit cost near or
below ¥190. They must be revisited with real quotes, the selected certification
route, expected sales channel, and target volume before implementation.

## 2. Product connectivity shape

```text
Camera / local compute
  -> Cellular modem/baseband + [eUICC/eSIM SKU | physical-SIM SKU | dual-mode SKU] + RF/antenna
  -> user-selected carrier cellular network
  -> Edge Session Link <-> Gateway
  -> Personal Runtime
```

eSIM/eUICC holds a subscriber profile; it does not replace the cellular modem,
RF design, antenna, carrier arrangement, or power budget. The selected hardware
must provide all of those elements as one supportable product system.

Cellular access is solely a transport bearer. It does not alter the existing
P-256 device identity or pairing/revocation flow, and it never creates a direct
path into Personal Runtime internals. All cross-boundary traffic remains on
`Edge Session Link <-> Gateway` and remains subject to Gateway validation,
Runtime privacy rules, Presence, action governance, and audit.

## 3. User-owned connectivity

OpenHalo supplies cellular-capable hardware and a clear local provisioning
surface; it is not a carrier and does not default to selling, preloading, or
billing mobile data. The user selects, activates, and pays a compatible
carrier SIM/eSIM plan directly.

The product line must offer both embedded eUICC/eSIM and removable physical-SIM
connection modes. They are equal v2 user-facing choices: users select one
according to carrier availability, price, or deployment preference; physical
SIM is not merely a compatibility fallback. An individual SKU may be eSIM-only,
physical-SIM-only, or dual-mode; the final SKU matrix is a cost and market
decision, not a protocol split. The selected modem and its Local Profile
Assistant must support the chosen carrier's eSIM provisioning flow. The phone
companion may configure APN and relay an eSIM activation QR/code through a
local setup channel (for example BLE, USB, or temporary local Wi-Fi). The Edge
must have a permitted bootstrap path to download the profile, such as temporary
phone tethering. No carrier lock or OpenHalo-controlled SIM profile is a
requirement.

## 4. Initial traffic and privacy posture

The production default traffic profile is intentionally narrow:

- versioned structured Observations;
- heartbeat, liveness, connection, and device diagnostics;
- bounded local buffering during an outage; and
- explicitly authorized, bounded evidence transfer when policy permits.

Continuous raw camera or microphone uplink is disabled by default. The device
must define retention and expiry behavior for buffered material so reconnect
does not turn a network outage into unbounded delayed surveillance upload.

## 5. Scope and acceptance

M24 must select and validate a production-reference compute/camera platform,
cellular modem/baseband class, an eSIM/physical-SIM SKU matrix that covers both
connection modes,
antenna/RF layout, power and thermal budget, supported regions, and applicable
certification route. It must provide user-safe APN/SIM configuration,
carrier-permitted eSIM activation where available, network-loss diagnostics,
and field recovery without collecting the user's carrier credentials or acting
as a traffic-billing intermediary.

Acceptance requires a representative cellular-connected device to complete
P-256 pairing, reconnect after cellular loss/recovery, publish a schema-valid
structured Camera Observation, and preserve the default no-continuous-media
policy. Transport-independent Edge-session/reconnect and offline-buffer-expiry
behavior require automated coverage.

## 6. Deliberate non-goals

M24 does not reopen `M17.10` scene, capability, or MaixCAM validation; select
a carrier, modem vendor, or deployment region in advance of product design; or
make continuous raw-media streaming the default camera behavior.
