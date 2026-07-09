# Runtime Troubleshooting

This runbook helps diagnose production `Device Edge -> Personal Runtime`
connection failures.

## Current Production Shape

```text
Android Edge
-> ws://8.153.37.167/openhalo/edge
-> nginx
-> 127.0.0.1:8765
-> openhalo-runtime.service
```

The runtime itself should stay bound to `127.0.0.1:8765`. Public edge traffic
should enter through nginx.

## Server Access

From the local Windows development machine, use the user-level SSH alias:

```powershell
ssh aliyun_server
```

The alias resolves to the Alibaba Cloud runtime host `8.153.37.167` as `root`
with the local private key configured outside this repository. Prefer this
alias for server-side runtime inspection so commands stay stable if the key path
or user-level SSH config changes.

For a direct non-interactive check:

```powershell
ssh aliyun_server "systemctl status openhalo-runtime --no-pager"
```

## Fast Status Checks

```bash
systemctl status openhalo-runtime --no-pager
systemctl status nginx --no-pager
ss -ltnp | rg '(:80|:443|:8765)'
```

Expected:

- `openhalo-runtime` is `active`.
- `nginx` is `active`.
- Python listens on `127.0.0.1:8765`.
- nginx listens on public `80` and, when TLS is configured, `443`.

## Logs To Watch

Runtime service log:

```bash
journalctl -u openhalo-runtime -f
```

Runtime structured diagnostics:

```bash
tail -f /var/log/openhalo/runtime-diagnostics.jsonl
```

One-shot local form:

```powershell
ssh aliyun_server "tail -n 80 /var/log/openhalo/runtime-diagnostics.jsonl"
```

nginx access log:

```bash
tail -f /var/log/nginx/access.log
```

Android local evidence:

```bash
adb logcat
```

## Screen Context Receipt Check

To verify whether the production runtime is receiving Android screen-context
frames from the phone edge:

```powershell
ssh aliyun_server "python3 - <<'PY'
import json, datetime
state_path = '/var/lib/openhalo/runtime-state.json'
now = datetime.datetime.now(datetime.UTC).replace(microsecond=0)
data = json.load(open(state_path, encoding='utf-8'))
screen = [
    item for item in data.get('observations', [])
    if item.get('name') in ('mobile.screen_context', 'mobile.screen_capture_health')
]
print('server_now_utc', now.isoformat().replace('+00:00', 'Z'))
print('screen_normalized_count', len(screen))
for item in screen[-8:]:
    value = item.get('value') if isinstance(item.get('value'), dict) else {}
    print(json.dumps({
        'name': item.get('name'),
        'observed_at': item.get('observed_at'),
        'capture_mode': value.get('capture_mode'),
        'screen_kind': value.get('screen_kind'),
        'pause_reason': value.get('capture_pause_reason'),
        'raw_screenshot_uploaded': value.get('raw_screenshot_uploaded'),
    }, ensure_ascii=False))
PY"
```

Pass evidence for M17.7.1 should show recent `mobile.screen_context` or
`mobile.screen_capture_health` observations from the Android edge, normally
seconds old during active unlocked phone use, with
`raw_screenshot_uploaded=false`.

## Interpret Common Symptoms

### No nginx log entry

The phone is not reaching the server. Check the Android URL, network, Alibaba
Cloud security group, and whether the app is allowed to use cleartext traffic.

Current cleartext URL:

```text
ws://8.153.37.167/openhalo/edge
```

### nginx returns 301

The request hit the wrong nginx server block or the generic HTTP redirect.
For IP-based cleartext testing, the nginx `listen 80 default_server` block must
include `/openhalo/edge` before the redirect to HTTPS.

### nginx returns 101, runtime has no connect_ok

The WebSocket upgraded, but the runtime did not complete protocol connect.
Check runtime journal and diagnostics.

### diagnostics show unauthorized

The edge sent a `connect` frame with the wrong token.

Production token source:

```text
/etc/openhalo/runtime.env
```

Use `OPENHALO_EDGE_TOKEN`; do not use `dev-token` against production.

### journal shows KeyError for android-edge

Example:

```text
KeyError: 'android-edge-...'
```

The Android edge likely sent `capability_announce`, `observation_push`, or
another post-connect frame before the runtime registered that `device_id`.

The required order is:

```text
connect
wait for connect_ok
capability_announce
observation_push / event_push / action_result
```

This is also a backend hardening gap: the gateway should return a structured
public error for unknown devices instead of allowing a `KeyError` to escape.

### provider probe fails with network unreachable

The server needs the local proxy environment for OpenAI access:

```text
HTTPS_PROXY=http://127.0.0.1:7890
HTTP_PROXY=http://127.0.0.1:7890
ALL_PROXY=http://127.0.0.1:7890
```

Confirm these are present in `/etc/openhalo/runtime.env` and inherited by the
running service process.

If the variables are present but provider requests still fail with errors such
as `SSL_ERROR_SYSCALL` or `UNEXPECTED_EOF_WHILE_READING`, verify the selected
proxy node itself. A local proxy can accept the CONNECT tunnel while the chosen
upstream node still cannot reach `api.openai.com`.

Useful checks:

```bash
tr '\0' '\n' < /proc/$(systemctl show -p MainPID --value openhalo-runtime)/environ \
  | grep PROXY

curl -I --proxy http://127.0.0.1:7890 https://api.openai.com/v1/models

curl -sS http://127.0.0.1:9090/proxies/<proxy-group-name> | jq '{name, now, type}'
```

If `curl` shows `HTTP/1.1 200 Connection established` followed by a TLS reset or
timeout, the runtime is reaching the local proxy but the selected node is
failing. Switch the proxy group to a node that reaches OpenAI and rerun the
provider probe.

## Smoke Tests

Verify nginx reaches the runtime through public cleartext WebSocket:

```bash
sh -c '. /etc/openhalo/runtime.env; cd /opt/openhalo; \
sudo -u openhalo env OPENHALO_EDGE_TOKEN="$OPENHALO_EDGE_TOKEN" \
/opt/openhalo/.venv/bin/python -c '"'"'
import asyncio, json, os, websockets

async def main():
    async with websockets.connect("ws://8.153.37.167/openhalo/edge") as ws:
        await ws.send(json.dumps({
            "type": "connect",
            "device": {
                "device_id": "public-ip-ws-smoke",
                "device_type": "desktop-cli"
            },
            "auth": {"token": os.environ["OPENHALO_EDGE_TOKEN"]}
        }))
        print(json.loads(await ws.recv())["type"])

asyncio.run(main())
'"'"''
```

Expected output:

```text
connect_ok
```

Verify model-provider access as the service user:

```bash
sudo -u openhalo \
  env HTTPS_PROXY=http://127.0.0.1:7890 \
      HTTP_PROXY=http://127.0.0.1:7890 \
      ALL_PROXY=http://127.0.0.1:7890 \
  /opt/openhalo/bin/verify-model-provider \
  --runtime-config-path /etc/openhalo/runtime-config.toml
```

Expected: `ok: true`.
