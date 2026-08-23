# MaixCAM Camera Edge Development Runbook

This runbook preserves the current owner-development path for the fixed
MaixCAM Camera Edge. It covers device access, deployment, pairing, and a
one-shot reconnect check. It does not turn on recording, upload camera media,
or make the experimental device a production service.

The architecture boundary remains:

```text
MaixCAM Device Edge -> Edge Session Link -> Gateway -> Personal Runtime
```

## Security boundary

- Treat the MaixCAM's LAN address as dynamic; obtain it from MaixVision or the
  owner router each time rather than storing it in Git.
- Keep the developer private SSH key outside this repository. Its public key
  may be placed in the device's `authorized_keys` with forwarding and PTY
  restrictions appropriate for the owner workflow.
- Never put a pairing code, SSH private key, device private key, Runtime token,
  or device credential in source control, logs, chat transcripts, or shell
  history. The pairing CLI below accepts the code only on standard input.
- Use the exact Runtime URL selected at pairing for reconnect. Direct owner
  `ws://<server-ip>:8765` is supported but not encrypted; use an owner-managed
  `wss://` URL when transport confidentiality is required.

## 1. Verify the device is reachable

On the development host, substitute the current private LAN address and the
owner's dedicated key path:

```powershell
$cameraHost = "root@<maixcam-lan-ip>"
$cameraKey = "$env:USERPROFILE\.ssh\openhalo_maixcam_ed25519"

ssh -i $cameraKey $cameraHost "python3 --version; openssl version"
```

Expected baseline: Python 3.11, OpenSSL 3.1, and the vendor `websockets`
package. Do not attempt to install `cryptography` or a compiler toolchain on
the current `riscv64` image; use the OpenSSL-backed bootstrap instead.

## 2. Deploy the Camera Edge bootstrap

From the repository root:

```powershell
ssh -i $cameraKey $cameraHost "install -d -m 700 /root/openhalo_camera_edge /root/.openhalo-camera-edge"
scp -i $cameraKey device_edge/camera/openssl_session.py device_edge/camera/maixcam_cli.py "${cameraHost}:/root/openhalo_camera_edge/"
ssh -i $cameraKey $cameraHost "python3 /root/openhalo_camera_edge/maixcam_cli.py --help"
```

The first pair or reconnect creates the device-local P-256 identity at
`/root/.openhalo-camera-edge/devices/<device-id>/identity.p256.pk8.der`. Do
not copy this file off the device or commit it.

## 3. Create a one-time Runtime pairing code

On the owner Runtime host, first confirm it is live, then generate a short
code in a private terminal:

```bash
openhalo status
openhalo pair --ttl-seconds 300
```

The command prints a secret code. Do not paste it into a ticket, commit it, or
pass it as a command-line argument. Use it once in the next step.

## 4. Pair the Camera Edge

Set the exact owner Runtime URL and pipe the code directly into the device
command. The following PowerShell pattern reads the JSON response without
printing the code:

```powershell
$runtimeHost = "<owner-runtime-ssh-host>"
$runtimeUrl = "ws://<owner-runtime-public-ip>:8765"
$pairing = (ssh $runtimeHost "openhalo pair --ttl-seconds 300" | ConvertFrom-Json).pairing_code

[Text.Encoding]::UTF8.GetBytes($pairing) |
  ssh -i $cameraKey $cameraHost "python3 /root/openhalo_camera_edge/maixcam_cli.py --url $runtimeUrl pair --pairing-code-stdin"
```

Successful output contains only safe metadata: `state=paired`, device ID,
display name, and public-key fingerprint. The initial capability is
`camera.health`; it is not permission to capture or upload media.

## 5. Verify a no-code reconnect

This uses the retained P-256 identity and should not create or reveal a new
pairing code:

```powershell
ssh -i $cameraKey $cameraHost "python3 /root/openhalo_camera_edge/maixcam_cli.py --url $runtimeUrl reconnect"
ssh $runtimeHost "openhalo devices"
```

Expect an `authenticated` result on the device and an active, non-revoked
record for `camera-edge-1` on the Runtime. If a device is intentionally
revoked, run `openhalo revoke camera-edge-1` on the Runtime and repeat the
pairing step with a new code.

## Troubleshooting

| Symptom | Likely cause and response |
| --- | --- |
| `Connection refused` or timeout | Recheck the Runtime with `openhalo status`, firewall/public-port reachability, and the exact selected `ws://`/`wss://` URL. |
| `pairing_code_expired` or `invalid_pairing_code` | Generate a new code; codes are intentionally one-time and short-lived. |
| `device_already_paired` | Use `reconnect`; revoke only if deliberately replacing the device identity. |
| `ModuleNotFoundError` for the bootstrap | Repeat the two-file deployment step; the device copy is intentionally separate from the repository checkout. |
| P-256/OpenSSL failure | Confirm `openssl version`; do not substitute a random key format or introduce a compiler toolchain. |

## What this does not verify

This runbook proves device access and the public Edge session boundary only.
It does not prove a persistent service, local display state, camera health
Observation, Scene Profile/Feature Subscription governance, bounded evidence,
or any raw-media policy. Those remain explicit M17.10 work.
