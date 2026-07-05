# OpenHalo

[简体中文](README.zh-CN.md)

OpenHalo is a presence-first personal agent runtime built around the chain:

`device -> context -> presence -> action`

Instead of treating chat as the center of the product, OpenHalo treats devices
as edges, the runtime as a long-lived personal backend, and presence as an
explicit governance layer for deciding when and how the system should surface
itself.

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

## Current Status

The project has moved beyond pure architecture planning. The current baseline
already supports:

- A real local `Personal Runtime` with WebSocket Edge API traffic
- A host-class edge and resident terminal edge
- A first-version Android phone Edge surface with `Connect`, `Global Chat`, and `Settings`
- Public Edge API registration, observation, event, action, and action-result frames
- Model-backed proposal formation with prompt/context inspection and provider diagnostics
- Presence-governed action routing across more than one edge surface

Implementation progress is intentionally tracked at a product-slice level:

| Area | Current status |
| --- | --- |
| Runtime core | Implemented baseline with Gateway, state/context, proposal formation, Presence Router, action dispatch, grounding, and diagnostics |
| Terminal edge | Completed first resident terminal edge with foreground user input and runtime-delivered messages |
| Host edge | Implemented host-class edge for runtime/host-device validation and local actions |
| Android phone edge | Completed first product UI slice: `Connect`, `Global Chat`, `Settings`, hidden diagnostics, and preview APK |
| Mobile observation depth | Planned next Android milestone (`M17.5`), focused on screen/use-context evidence rather than intent decisions |
| Product packaging | Planned later milestone (`M21`), covering installable three-end delivery and stronger release packaging |

The project roadmap and milestone status live in [Project.md](Project.md).

## Deployment Shapes

OpenHalo is being built toward a small set of deployment scenes:

- **Development loop**: one local development runtime on port `18765`, plus local host/terminal edges and an emulator or phone edge.
- **Standard personal deployment**: one public or home server runs `Personal Runtime + host edge`; a computer runs a desktop/terminal edge; an Android phone runs the phone edge APK.
- **Computer-hosted deployment**: one personal computer runs `Personal Runtime + host edge + desktop/terminal edge`; the Android phone connects to that computer-hosted runtime.

All deployment scenes preserve the same boundary:

`Device Edge -> Edge API -> Gateway -> Personal Runtime`

The server, computer, and phone may be physically close or even colocated, but
edge traffic should still cross the Edge API boundary instead of importing
backend internals directly.

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

## Quick Start

Use the repository root virtual environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Start a development runtime:

```bash
bin/run-runtime-dev
```

Start the host edge in another terminal:

```bash
.venv/bin/python -m device_edge.host.host_daemon \
  --url ws://127.0.0.1:18765 \
  --token dev-token \
  --device-id host-edge-1
```

Start the terminal edge in a third terminal:

```bash
.venv/bin/python -m device_edge.cli.terminal_daemon \
  --url ws://127.0.0.1:18765 \
  --token dev-token \
  --device-id terminal-edge-1
```

The development helper uses port `18765` so a long-running server runtime can
keep port `8765`. See [docs/runtime-deploy.md](docs/runtime-deploy.md) for the
systemd-backed server startup path.

## Important Docs

- [Project.md](Project.md): project baseline, milestones, architecture direction, current status
- [docs/dev-env.md](docs/dev-env.md): local development and verification workflow
- [docs/runtime-deploy.md](docs/runtime-deploy.md): development versus server runtime startup
- [docs/android-edge-install.md](docs/android-edge-install.md): Android phone Edge setup and install notes
- [docs/m17-android-edge-acceptance.md](docs/m17-android-edge-acceptance.md): Android Edge verification ladder
- [docs/design/mobile-edge-ui/mobile-edge-ui-spec.md](docs/design/mobile-edge-ui/mobile-edge-ui-spec.md): phone Edge product UI design baseline
- [docs/plans/2026-06-16-runtime-architecture-design.md](docs/plans/2026-06-16-runtime-architecture-design.md): architecture baseline

## Notes

- The real model-provider path is still under active hardening.
- The first Android phone Edge product UI is usable, but broader packaging and distribution are still evolving.
- Keep this README's implementation-progress table current when a milestone is completed, accepted, or re-scoped.
- This repository is evolving quickly; treat `Project.md` as the source of truth for current direction.
