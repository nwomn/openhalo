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
- a reverse proxy exposes the public edge WebSocket endpoint when needed
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

## Current Production Edge Endpoint

The current Alibaba Cloud production runtime keeps the Python runtime private
and exposes the phone edge through nginx:

```text
Phone Edge -> ws://8.153.37.167/openhalo/edge -> nginx -> 127.0.0.1:8765
```

Use this URL for Android cleartext testing:

```text
ws://8.153.37.167/openhalo/edge
```

The Android edge must use the production token from:

```text
/etc/openhalo/runtime.env
```

Specifically, use the value of `OPENHALO_EDGE_TOKEN`. Do not use `dev-token`
against the production systemd runtime.

The nginx `listen 80 default_server` block must keep a special
`/openhalo/edge` location before the normal HTTP-to-HTTPS redirect:

```nginx
location /openhalo/edge {
    proxy_pass http://127.0.0.1:8765;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}
```

This keeps `8765` closed to the public internet while allowing Android devices
with cleartext traffic enabled to reach the runtime through nginx. Without the
`default_server` behavior, IP-based requests may be handled by another nginx
site and redirected to an unrelated domain.

When a stable OpenHalo domain is available, prefer a TLS endpoint:

```text
wss://<openhalo-domain>/openhalo/edge
```

At that point, move the same WebSocket `location` into the active TLS server
block for that domain and update Android builds to use `wss://`.

## Port Rule

Reserve ports by purpose:

- `8765`: long-running server runtime
- `18765`: development, Android acceptance, and restart-heavy experiments

If both are running on the same server, make sure development edges use
`ws://<server-ip>:18765` and production or always-on edges use the stable
endpoint that fronts `127.0.0.1:8765`.
