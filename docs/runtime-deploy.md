# Personal Runtime Installation

OpenHalo has one owner-facing Runtime installation model. The commands and
personal data belong to the person installing it; normal operation does not
require a service user, a unit file, or a repository checkout.

## Install A Fixed Build

The installer accepts a complete Git commit ID, never a mutable branch name.
Replace both placeholders with the same published 40-character commit:

```bash
curl -fsSL https://raw.githubusercontent.com/nwomn/openhalo/<commit>/scripts/install.sh | bash -s -- --ref <commit>
```

It creates versioned program files under `~/.local/share/openhalo/releases/`
and makes `openhalo` and `openhalo-edge` available from `~/.local/bin`.
Ensure that directory is on the login-shell `PATH` before using the commands.
The installer changes only program files; it does not create, reset, or delete
your personal Runtime data.

On a computer that only needs the Terminal Edge command, add `--edge-only`:

```bash
curl -fsSL https://raw.githubusercontent.com/nwomn/openhalo/<commit>/scripts/install.sh | bash -s -- --edge-only --ref <commit>
```

## Set Up The Runtime

```bash
openhalo setup
```

This creates one private owner directory:

```text
~/.openhalo/
  config.json               Runtime and Terminal Edge configuration
  runtime-config.toml       Editable model/provider configuration
  runtime/state.json        Runtime state
  runtime/pairing.json      Hashed pairing records and device metadata
  runtime/runtime.pid       Runtime process identity
  logs/runtime.log          Runtime output
```

The directory and credential-bearing files are owner-only. Edit
`~/.openhalo/runtime-config.toml` to add the provider and model details before
starting a model-backed Runtime. To import an already prepared configuration
instead, use:

```bash
openhalo setup --runtime-config /path/to/runtime-config.toml
```

The default Runtime bind is `127.0.0.1:8765`. Change it at setup time with
`--host` and `--port`; keep the restart-heavy development path on `18765`.

## Run And Inspect

```bash
openhalo --version
openhalo start
openhalo status
openhalo logs --lines 100
openhalo doctor
openhalo stop
```

`openhalo --version` and `openhalo-edge --version` report the package version
and active immutable release's short commit ID. A repository development run
reports `dev` instead of claiming an installed release.

`openhalo start` launches the Runtime and its managed Host Edge as an internal
per-user background process. Repeating `start` does not create a second
Runtime. `stop` only signals a process whose command line identifies it as the
OpenHalo Runtime; a stale PID is discarded rather than risking an unrelated
process.

## Pair Devices

Create a short-lived one-time code on the Runtime host:

```bash
openhalo pair
```

Use it exactly once when setting up an Edge. Inspect only safe metadata or
revoke a device at any time:

```bash
openhalo devices
openhalo revoke <device-id>
```

Terminal Edge setup persists the Runtime URL and its device-specific credential
in the same `~/.openhalo/config.json` home. It does not require entering an IP
address or token again:

```bash
openhalo-edge setup --url ws://<runtime-host>:8765 --pairing-code <one-time-code>
openhalo-edge
```

Use a TLS-terminated `wss://` URL when the pairing or device credential crosses
an untrusted network. Local development and explicitly trusted test paths may
use `ws://`.

## Updating

Program releases and `~/.openhalo` data are separate. The fixed-build installer
selects its program release through an atomic `current` link, leaving prior
release directories available for a later rollback path. It never installs from
a branch checkout and never resets personal data as an update side effect.

The present installer is the bootstrap/update path while release publishing is
being established: install a newer published fixed commit with the same command
above. Automatic `openhalo update` and signed Release manifests remain the next
M22 packaging slice; they will stage and health-check a new release before
switching `current` and will refuse unsupported persistent-state migrations.

## Development Runtime

Use the repository development helper only for restart-heavy implementation and
acceptance work:

```bash
bin/run-runtime-dev
```

It uses port `18765` and repository-local `.runtime` files. It is independent
from the installed personal Runtime and should not be used as the product
installation path.
