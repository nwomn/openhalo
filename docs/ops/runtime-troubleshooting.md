# Personal Runtime Troubleshooting

Use the owner-facing commands first. They operate on the same private
`~/.openhalo` home used by the installed Runtime and never require service-unit
or deployment-directory paths.

```bash
openhalo status
openhalo doctor
openhalo logs --lines 100
```

## Runtime Does Not Start

Run setup once, then inspect the editable provider configuration:

```bash
openhalo setup
openhalo doctor
openhalo logs --lines 100
```

`openhalo setup` creates `~/.openhalo/runtime-config.toml`. Add the approved
provider endpoint, API key, and model there. The Runtime default is
`127.0.0.1:8765`; use `openhalo setup --host ... --port ...` only when the
local bind must change.

## Terminal Edge Cannot Connect

Check that this computer has been paired:

```bash
openhalo-edge status
```

If it needs setup, create a one-time code on the Runtime host and use it once
on this computer:

```bash
openhalo pair
openhalo-edge setup --url ws://<runtime-host>:8765 --pairing-code <one-time-code>
```

The saved per-device credential is private and is intentionally not printed by
`openhalo-edge status`. A revoked or replaced device must be paired again.

## Runtime Is Stale Or Stopped

```bash
openhalo stop
openhalo start
openhalo status
```

The command only signals a PID whose process command identifies it as an
OpenHalo Runtime. A stale PID is removed rather than treated as authority to
terminate another process.

## Public Endpoint And Transport

The Runtime defaults to loopback. When another device connects through an
untrusted network, supply a TLS-protected `wss://` endpoint to
`openhalo-edge setup`. Trusted local development may use `ws://`.

Do not put a one-time pairing code or device credential in shell history,
source control, or tickets. Use `openhalo devices` for safe metadata and
`openhalo revoke <device-id>` to invalidate a device.
