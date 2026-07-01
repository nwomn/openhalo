# Personal Runtime Startup

This document separates OpenHalo runtime startup into two operational modes:
development/runtime acceptance and long-running server operation.

## Development Runtime

Use the development helper when testing Android, terminal, or host edges against a
runtime that may be restarted often:

```bash
bin/run-runtime-dev
```

The helper defaults to:

- `OPENHALO_DEV_RUNTIME_HOST=0.0.0.0`
- `OPENHALO_DEV_RUNTIME_PORT=18765`
- `OPENHALO_DEV_EDGE_TOKEN=dev-token`
- `OPENHALO_DEV_STATE_PATH=.runtime/android-openai-dev-state.json`
- `OPENHALO_DEV_DIAGNOSTIC_LOG_PATH=.runtime/android-openai-dev-diagnostics.jsonl`
- `OPENHALO_DEV_RUNTIME_CONFIG_PATH=config/runtime-config.openai-local.toml`

The deliberate default port is `18765`, not `8765`. Keep `8765` available for
the long-running Personal Runtime while using `18765` for development and
manual acceptance. Android development builds can point at:

```text
ws://<server-ip>:18765
```

For local-only terminal or host edge checks, override the bind host:

```bash
OPENHALO_DEV_RUNTIME_HOST=127.0.0.1 bin/run-runtime-dev
```

Then connect local edges to `ws://127.0.0.1:18765`.

## Long-Running Server Runtime

For a server runtime that should survive SSH disconnects and process failures,
run the Personal Runtime under systemd instead of an interactive shell.

The recommended baseline is:

- systemd owns process lifetime and restart behavior
- the runtime binds `127.0.0.1:8765`
- a reverse proxy exposes the public `wss://...` edge endpoint when needed
- state lives under `/var/lib/openhalo`
- diagnostics live under `/var/log/openhalo` or journald
- the shared edge token is read through `--token-env OPENHALO_EDGE_TOKEN`

Use the example files:

```text
deploy/systemd/openhalo-runtime.service.example
deploy/systemd/openhalo-runtime.env.example
```

Suggested server layout:

```bash
sudo useradd --system --home /opt/openhalo --shell /usr/sbin/nologin openhalo
sudo mkdir -p /opt/openhalo /etc/openhalo /var/lib/openhalo /var/log/openhalo
sudo chown -R openhalo:openhalo /opt/openhalo /var/lib/openhalo /var/log/openhalo
sudo chmod 750 /etc/openhalo
```

Copy the repository to `/opt/openhalo`, install its `.venv`, copy the env file
to `/etc/openhalo/runtime.env`, and set a real token:

```bash
sudo cp deploy/systemd/openhalo-runtime.env.example /etc/openhalo/runtime.env
sudo chmod 600 /etc/openhalo/runtime.env
```

Install the service:

```bash
sudo cp deploy/systemd/openhalo-runtime.service.example /etc/systemd/system/openhalo-runtime.service
sudo systemctl daemon-reload
sudo systemctl enable --now openhalo-runtime
sudo systemctl status openhalo-runtime
```

Check logs:

```bash
sudo journalctl -u openhalo-runtime -f
```

## Port Rule

Reserve ports by purpose:

- `8765`: long-running server runtime
- `18765`: development, Android acceptance, and restart-heavy experiments

If both are running on the same server, make sure development edges use
`ws://<server-ip>:18765` and production or always-on edges use the stable
endpoint that fronts `127.0.0.1:8765`.
