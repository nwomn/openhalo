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
- Early cloud-model-backed proposal and reply generation
- Runtime grounding and memory plumbing
- Prompt/context inspection and proposal diagnostics

The project roadmap and milestone status live in [Project.md](Project.md).

## Quick Start

Use the repository root virtual environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Start the runtime:

```bash
.venv/bin/python -m personal_runtime.main \
  --host 127.0.0.1 \
  --port 8765 \
  --token dev-token
```

Start the host edge in another terminal:

```bash
.venv/bin/python -m device_edge.host.host_daemon \
  --url ws://127.0.0.1:8765 \
  --token dev-token \
  --device-id host-edge-1
```

Start the terminal edge in a third terminal:

```bash
.venv/bin/python -m device_edge.cli.terminal_daemon \
  --url ws://127.0.0.1:8765 \
  --token dev-token \
  --device-id terminal-edge-1
```

## Important Docs

- [Project.md](Project.md): project baseline, milestones, architecture direction, current status
- [docs/dev-env.md](docs/dev-env.md): local development and verification workflow
- [docs/plans/2026-06-16-runtime-architecture-design.md](docs/plans/2026-06-16-runtime-architecture-design.md): architecture baseline

## Notes

- The real model-provider path is still under active hardening.
- The roadmap currently places runtime-native credential/runtime-config work as milestone `M15`.
- This repository is evolving quickly; treat `Project.md` as the source of truth for current direction.
