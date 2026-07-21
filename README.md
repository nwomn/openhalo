# OpenHalo

[简体中文](README.zh-CN.md)

OpenHalo is a presence-first personal agent runtime built around the chain:

`device -> context -> presence -> action`

Instead of treating chat as the center of the product, OpenHalo treats devices
as edges, the runtime as a long-lived personal backend, and presence as an
explicit governance layer for deciding when and how the system should surface
itself.

## Project Status

This is an alpha source repository, not a hosted public Runtime. Do not expose
a bearer-credential Runtime endpoint from these development instructions.
Public Runtime deployment still requires the tracked TLS/WSS and mobile
sensitive-screen governance work.

## What It Is

OpenHalo is currently an architecture-led runtime project with an implemented
baseline. The repository already includes:

- A long-running `Personal Runtime` backend with a WebSocket gateway
- A host-class `Device Edge`
- A resident terminal `Device Edge`
- A first Android phone `Device Edge` product UI
- Cross-edge action routing for early multi-edge validation
- Grounded proposal formation, prompt/context inspection, and model-provider diagnostics

## Working Architecture

- `Frontend / Device Edge`: device-resident runtime surfaces for sensing, interaction, local permissions, and low-latency actions
- `Backend / Personal Runtime`: long-lived cross-device runtime state, agent behavior, presence governance, and action orchestration

Core backend layers:

- `Gateway`
- `State / Context / Task`
- `Presence Router`
- `Agent Executor`
- `Action Layer`

## Deployment Shapes

OpenHalo is being built toward a small set of deployment scenes:

- **Standard personal deployment**: one public or home server runs `Personal Runtime + host edge`; a computer runs a desktop/terminal edge; an Android phone runs the phone edge APK.
- **Computer-hosted deployment**: one personal computer runs `Personal Runtime + host edge + desktop/terminal edge`; the Android phone connects to that computer-hosted runtime.
- **Future ambient deployment**: phones, computers, smart-home devices, sensors, and small edge-AI nodes participate as a low-presence personal environment, so OpenHalo can understand context and act through the least intrusive nearby surface.

All deployment scenes preserve the same boundary:

`Device Edge -> Edge API -> Gateway -> Personal Runtime`

The server, computer, and phone may be physically close or even colocated, but
edge traffic should still cross the Edge API boundary instead of importing
backend internals directly.

## Progress Toward Deployment

The deployment shapes above require three things to come together: a durable
runtime, real device edges, and installable product packaging. The current
implementation has moved beyond pure architecture planning, but it is not yet a
fully packaged three-end product.

| Deployment requirement | Current status | Remaining gap |
| --- | --- | --- |
| Personal Runtime | Implemented baseline with Gateway, state/context, proposal formation, Presence Router, action dispatch, grounding, diagnostics, and a private `~/.openhalo` command/config foundation | Release-manifest signing, automatic staged update, and broader production hardening |
| Server/host edge | Implemented host-class edge for runtime/host-device validation and local actions; the personal `openhalo` command supervises it with Runtime | Public-endpoint hardening and packaged deployment acceptance |
| Computer edge | Completed resident terminal edge with foreground user input and runtime-delivered messages | User-facing desktop packaging remains later work |
| Android phone edge | Completed first product UI slice: `Connect`, `Global Chat`, `Settings`, hidden diagnostics, preview APK, and accepted M17.5 screen-context observation baseline | Formal signing, distribution polish, mobile observation liveness, and sensitive-screen capture governance remain later work |
| Cross-edge interaction | Public Edge API registration, observations, events, actions, action results, and presence-governed routing are implemented | Broader real-device scenarios and richer capability coverage |
| Ambient/home edge ecosystem | Long-term direction: smart-home devices, sensors, and small edge-AI nodes become additional `Device Edge` participants | Bridge integrations, device profiles, safety policy, and low-presence ambient interaction design |
| Mobile observation depth | M17.5 accepted: Android can upload passive `mobile.screen_context` / `mobile.screen_capture_health` evidence and operators can verify it through the runtime context viewer | M17.7 owns liveness/wake recovery; M17.8 owns allowlist-first sensitive-screen capture governance |
| Product packaging | M22 personal-installation foundation: fixed-commit installer, global `openhalo`/`openhalo-edge` commands, private configuration, Runtime lifecycle, and Terminal pairing | Signed Release publishing, automatic staged update/rollback, Windows package, and full three-end acceptance |

The project roadmap and milestone status live in [Project.md](Project.md).

## Android Phone Edge

The first Android phone Edge product UI is complete as milestone `M17.4`.
It provides:

- `Connect`: the default connection/status surface
- `Global Chat`: phone-originated `mobile.input` through the public Edge API
- `Settings`: runtime URL, device name, permission/background controls, cache/reset actions, and a hidden developer diagnostics entry

A preview APK is published through GitHub Releases:

- [v0.17.4-mobile-edge-preview](https://github.com/nwomn/openhalo/releases/tag/v0.17.4-mobile-edge-preview)

This APK is a debug-signed preview artifact for early installation and testing.
Formal release signing, updater/distribution polish, and packaged three-end
delivery are tracked as later productization work.

## Install A Personal Runtime

For a Linux server or personal computer with Git and Python 3.11+, install a
published fixed commit. Use the same 40-character commit ID in both
placeholders:

```bash
curl -fsSL https://raw.githubusercontent.com/nwomn/openhalo/<commit>/scripts/install.sh | bash -s -- --ref <commit>
export PATH="$HOME/.local/bin:$PATH"
openhalo setup
openhalo start
openhalo pair
```

The installer makes `openhalo` available from `~/.local/bin`, creates no
Runtime data until `setup`, and keeps personal configuration, state, and paired
device credentials in `~/.openhalo`. Add `~/.local/bin` to your login-shell
configuration once if it is not already on `PATH`. `openhalo start` also
manages the colocated Host Edge. `openhalo pair` prints a one-time pairing code
for the phone or computer Edge; its saved device credential means the Edge does
not need the code again.

For a remote Edge, configure the server's reverse-proxy URL, for example
`wss://<runtime-domain>/openhalo/edge`, and enter the pairing code there. The
Runtime itself stays on `127.0.0.1:8765`; do not point remote Edges at that
loopback port. A public pairing or device-credential endpoint requires `wss://`.

To install only the Terminal Edge on another computer:

```bash
curl -fsSL https://raw.githubusercontent.com/nwomn/openhalo/<commit>/scripts/install.sh | bash -s -- --edge-only --ref <commit>
export PATH="$HOME/.local/bin:$PATH"
openhalo-edge setup --url wss://<runtime-domain>/openhalo/edge --pairing-code <one-time-code>
openhalo-edge
```

Normal Runtime control is `openhalo status`, `openhalo logs --lines 100`, and
`openhalo stop`. Full proxy, update, and troubleshooting instructions are in
[docs/runtime-deploy.md](docs/runtime-deploy.md).

## Development Quick Start

The local development loop uses one development runtime on port `18765`, plus
local host/terminal edges and an emulator or phone edge.

Use the repository root virtual environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Start a development runtime:

```bash
bin/run-runtime-dev
```

The Runtime starts its colocated `host-edge-1` automatically. Start the terminal
edge in a second terminal:

```bash
.venv/bin/python -m device_edge.cli.terminal_daemon \
  --url ws://127.0.0.1:18765 \
  --token dev-token \
  --device-id terminal-edge-1
```

The development helper uses port `18765` so an installed personal Runtime can
use port `8765`. See [docs/runtime-deploy.md](docs/runtime-deploy.md) for the
owner-facing install, setup, pairing, and lifecycle commands.

## Important Docs

- [Project.md](Project.md): project baseline, milestones, architecture direction, current status
- [docs/dev-env.md](docs/dev-env.md): local development and verification workflow
- [docs/runtime-deploy.md](docs/runtime-deploy.md): personal Runtime install, pairing, and lifecycle commands
- [docs/android-edge-install.md](docs/android-edge-install.md): Android phone Edge setup and install notes
- [docs/m17-android-edge-acceptance.md](docs/m17-android-edge-acceptance.md): Android Edge verification ladder
- [docs/design/mobile-edge-ui/mobile-edge-ui-spec.md](docs/design/mobile-edge-ui/mobile-edge-ui-spec.md): phone Edge product UI design baseline
- [docs/ops/runtime-troubleshooting.md](docs/ops/runtime-troubleshooting.md): production runtime and edge-connection troubleshooting
- [docs/plans/2026-06-16-runtime-architecture-design.md](docs/plans/2026-06-16-runtime-architecture-design.md): architecture baseline
- [CONTRIBUTING.md](CONTRIBUTING.md): contribution and local verification rules
- [SECURITY.md](SECURITY.md): private vulnerability reporting policy
- [LICENSE](LICENSE): MIT license

## Notes

- The real model-provider path is still under active hardening.
- The first Android phone Edge product UI is usable, but broader packaging and distribution are still evolving.
- Source collaboration is available under MIT; private vulnerability reporting must be enabled in the repository Security settings before public release.
- Keep this README's implementation-progress table current when a milestone is completed, accepted, or re-scoped.
- This repository is evolving quickly; treat `Project.md` as the source of truth for current direction.
