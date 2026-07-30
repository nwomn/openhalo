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

It creates immutable program files under
`~/.local/share/openhalo/releases/<commit>/`, atomically selects one through
`~/.local/share/openhalo/current`, and makes `openhalo` and `openhalo-edge`
available from `~/.local/bin`. Ensure that directory is on the login-shell
`PATH` before using the commands. The installer changes only program files; it
does not create, reset, or delete your personal Runtime data in `~/.openhalo`.

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

The default Runtime bind is `127.0.0.1:8765`. This private loopback port is
not a remote Edge endpoint. Leave that default in place for a normal server
deployment; change `--host` or `--port` only for a deliberate local-network or
development topology. Keep the restart-heavy repository development path on
`18765`.

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
process. `start` returns only after the Gateway has created its private ready
marker, so a reported running process has started listening for Edge sessions.

The detached Runtime survives shell exit while the machine remains up. It is
not a system service and does not yet start itself again after a machine reboot;
run `openhalo start` after reboot until per-user restart supervision is added.

## Expose A Remote Edge Endpoint

For a server Runtime, terminate the public endpoint in a reverse proxy and
forward WebSocket upgrades to the loopback Runtime. Remote Edges use the proxy
URL, not `ws://<runtime-host>:8765`:

```text
wss://<runtime-domain>/openhalo/edge
```

For an explicitly trusted test path, the corresponding non-TLS URL is:

```text
ws://<runtime-host>/openhalo/edge
```

For example, an nginx location needs the normal WebSocket upgrade forwarding:

```nginx
location /openhalo/edge {
    proxy_pass http://127.0.0.1:8765;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
}
```

DNS, TLS certificates, firewall rules, and reverse-proxy provisioning remain
the server owner's responsibility; `openhalo setup` and the installer do not
create them. A public endpoint that carries a pairing code or device credential
must use TLS (`wss://`).

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
openhalo-edge setup --url wss://<runtime-domain>/openhalo/edge --pairing-code <one-time-code>
openhalo-edge
```

Use a TLS-terminated `wss://` URL when the pairing or device credential crosses
an untrusted network. Local development and explicitly trusted test paths may
use `ws://`, but remote connections still go through the proxy path rather than
the loopback Runtime port.

## Updating

Program releases and `~/.openhalo` data are separate. The fixed-build installer
selects its program release through an atomic `current` link, leaving prior
release directories available for a later rollback path. It never installs from
a branch checkout and never resets personal data as an update side effect.

The fixed-commit installer remains the bootstrap path for a new machine. Once
that installed version contains the updater, normal owner updates use GitHub
Releases rather than a branch or a manually supplied commit:

```bash
openhalo update --check
openhalo update
```

`update --check` reads the latest published non-prerelease GitHub Release for
`nwomn/openhalo` and reports whether its exact commit differs from the active
release. `update` accepts a Release only when it contains all three assets:

- `openhalo-<tag>.tar.gz`
- `release-manifest.json`
- `SHA256SUMS`

The manifest and checksum file must name the same archive, digest, tag, and
40-character commit. OpenHalo stages the verified archive into the private
release root, leaving `current`, `previous`, and `OPENHALO_HOME` untouched
until the candidate is installed successfully. For a running Runtime, it stops
the old process, switches the `current` link atomically, and waits for the
candidate Gateway ready marker. If that start fails, it switches back to the
prior release and restarts the old Runtime. A failed download or staging step
does not stop the active Runtime.

Restore the previously selected program release explicitly with:

```bash
openhalo rollback
```

Updates and rollback only operate from an installed immutable release; a
repository development command is not an installer. The current Release trust
boundary is GitHub HTTPS plus the matching SHA-256 manifest and checksum asset.
It verifies the published OpenHalo source archive, but candidate environment
creation still resolves the package dependencies declared by that archive; a
locked, hash-verified dependency wheelhouse is not implemented yet. Treat that
as a supply-chain hardening gap alongside Release-manifest signing and key
rotation. Persistent-state migration is also future work: releases must
currently preserve compatible `OPENHALO_HOME` state, and the updater never runs
or silently invents a migration.

### Publish A Runtime Release

Maintain a stable GitHub Release manually until CI publishing is introduced.
Create a tag pointing at an exact 40-character commit, then build and upload
the three required assets to the GitHub Release with the same tag:

```bash
python3 scripts/build_release.py \
  --tag v<version> \
  --commit <40-character-commit> \
  --output ./dist/release
gh release create v<version> \
  ./dist/release/openhalo-v<version>.tar.gz \
  ./dist/release/release-manifest.json \
  ./dist/release/SHA256SUMS
```

The builder uses `git archive` at the exact supplied commit and writes the
archive name, tag, commit, and SHA-256 into `release-manifest.json`. Do not
upload a Runtime archive to an Android-only preview Release: `openhalo update`
will reject releases without the complete Runtime asset set.

## Development Runtime

Use the repository development helper only for restart-heavy implementation and
acceptance work:

```bash
bin/run-runtime-dev
```

It uses port `18765` and repository-local `.runtime` files. It is independent
from the installed personal Runtime and should not be used as the product
installation path.
