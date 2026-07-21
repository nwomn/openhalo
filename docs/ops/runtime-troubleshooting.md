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
openhalo-edge setup --url wss://<runtime-domain>/openhalo/edge --pairing-code <one-time-code>
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

## Edge Connects But Does Not Reply

The default `runtime-config.toml` is a placeholder, so a paired Edge can
connect and submit input before the Runtime has a working model/provider
configuration. Edit `~/.openhalo/runtime-config.toml`, or import an approved
private configuration, then restart the Runtime:

```bash
openhalo setup --runtime-config /path/to/runtime-config.toml
openhalo stop
openhalo start
openhalo logs --lines 100
```

The pairing and saved device credential remain valid across this restart; do
not pair again unless the credential was revoked or replaced. `openhalo doctor`
checks that local configuration files exist, but it does not validate provider
credentials, upstream connectivity, or model access.

## Public Endpoint And Transport

The Runtime defaults to loopback on `127.0.0.1:8765`. A remote Edge must use a
reverse-proxy endpoint such as `wss://<runtime-domain>/openhalo/edge`; the
proxy forwards WebSocket upgrades to the loopback port. Do not point a remote
Edge at `ws://<runtime-host>:8765` under the normal personal deployment.

When another device connects through an untrusted network, use TLS-protected
`wss://`. Trusted local development or an explicitly trusted test proxy may use
`ws://<runtime-host>/openhalo/edge`. The installer does not provision the
reverse proxy, DNS, TLS certificate, or firewall rules.

The current detached personal Runtime does not start automatically after a
machine reboot. Run `openhalo start` after reboot and use `openhalo status` to
confirm it is running.

Do not put a one-time pairing code or device credential in shell history,
source control, or tickets. Use `openhalo devices` for safe metadata and
`openhalo revoke <device-id>` to invalidate a device.
