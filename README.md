# OpenHalo

[简体中文](README.zh-CN.md)

OpenHalo is a presence-first personal agent runtime built around the chain:

`device -> context -> presence -> action`

Instead of treating chat as the center of the product, OpenHalo treats devices as edges, the runtime as a long-lived personal backend, and presence as an explicit governance layer for deciding when and how the system should surface itself.

## What It Is

OpenHalo is currently an architecture-led runtime project with an implemented baseline. The repository already includes:

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

The project has moved beyond pure architecture planning. The current baseline already supports:

- Real local runtime + edge process validation
- A formal terminal-edge interaction surface
- A first-version Android phone Edge surface with `Connect`, `Global Chat`, and `Settings`
- Early cloud-model-backed proposal and reply generation
- Runtime grounding and memory plumbing
- Prompt/context inspection and proposal diagnostics

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
- This repository is evolving quickly; treat `Project.md` as the source of truth for current direction.
