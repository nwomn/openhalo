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

## 6. Publish one health-only snapshot

The first active M17.10 service sends only connection, capture-probe, and
storage health. It does not initialize the camera, alter a MaixVision preview,
record clips, or upload media:

```powershell
scp -i $cameraKey device_edge/camera/health_daemon.py "${cameraHost}:/root/openhalo_camera_edge/"
ssh -i $cameraKey $cameraHost "python3 /root/openhalo_camera_edge/health_daemon.py --url $runtimeUrl --once"
```

The bounded local status payload is written atomically to
`/root/.openhalo-camera-edge/status.json`. The later device-display adapter may
render only this payload; it must not become a raw camera viewer or control
plane.

After stopping any MaixVision preview, add `--capture-probe` to intentionally
open the sensor once, discard one in-memory 320×240 frame, close the sensor,
and report only `ready` or `unavailable` in the health Observation. It never
writes or uploads that frame:

```powershell
ssh -i $cameraKey $cameraHost "python3 /root/openhalo_camera_edge/health_daemon.py --url $runtimeUrl --once --capture-probe"
```

For a supervised, repeated health session, omit `--once` only after the one
snapshot has been verified and a deliberate process-supervision decision is
recorded. The current slice does not install a boot service.

## 7. Opt in to the shared local visual Feature pass

The local visual pass opens the MaixCAM sensor and YOLO11 pipeline once. It
derives person presence, configured object counts, configured person-region
occupancy, and a bounded camera availability/frame-dimension check from the
same sample. The existing `person_presence.v1` contract remains unchanged and
still requires repeated matching samples before changing state. The additional
Observations are:

```json
{"state":"present|absent|unavailable","count":1,"feature_version":"person_presence.v1"}
```

```json
{"state":"ready","objects":{"chair":1,"cup":0},"feature_version":"object_presence.v1"}
{"state":"ready","regions":{"desk":{"occupied":true,"count":1}},"feature_version":"region_occupancy.v1"}
{"state":"ready","camera_state":"ready","width":320,"height":240,"feature_version":"scene_quality.v1"}
```

`camera.person_presence_transition.v1` is emitted only after a confirmed
person state/count change and distinguishes `entered`, `left`,
`count_changed`, and `availability_changed`. The corresponding
`camera.region_occupancy_transition.v1` reports the same enter/leave/count/
availability changes for each configured region. Object labels are an
explicit allowlist and regions are normalized rectangles; neither camera
frames nor image references, bounding boxes, object geometry, face data, OCR
text, or other unconfigured labels leave the device. `unavailable` is distinct
from `absent`, so a sensor/model failure cannot be interpreted as an empty
room.

The current `scene_quality.v1` name covers capture availability and detector
dimensions only. It does not claim blur, exposure, or perceptual sharpness;
those metrics require a separately verified Maix image-quality API.

Stop MaixVision's preview first: this process becomes the sole owner of the
camera/NPU pipeline. Deploy all three required files and make a supervised
one-shot verification with one confirmation sample:

```powershell
scp -i $cameraKey device_edge/camera/openssl_session.py device_edge/camera/person_presence.py device_edge/camera/health_daemon.py "${cameraHost}:/root/openhalo_camera_edge/"
ssh -i $cameraKey $cameraHost "python3 /root/openhalo_camera_edge/health_daemon.py --url $runtimeUrl --once --person-presence --presence-confirm-samples 1"
```

For the manually launched Maix App, set the explicit allowlist and normalized
regions in `/root/.openhalo-camera-edge/app-config.json`:

```json
{
  "object_labels": ["chair", "cup"],
  "regions": {"desk": [0.15, 0.20, 0.85, 0.95]}
}
```

For the copied CLI daemon, the equivalent flags are repeatable:

```powershell
ssh -i $cameraKey $cameraHost "python3 /root/openhalo_camera_edge/health_daemon.py --url $runtimeUrl --visual-features --object-label chair --object-label cup --region desk:0.15,0.20,0.85,0.95"
```

For a manually supervised continuous session, retain the safer two-sample
default and use a one-second sample interval with a 30-second freshness
heartbeat:

```powershell
ssh -i $cameraKey $cameraHost "python3 /root/openhalo_camera_edge/health_daemon.py --url $runtimeUrl --person-presence"
```

Do not also start a separate `Display()` or camera script. A future local
display must be integrated into this same process and lifecycle.

## Troubleshooting

| Symptom | Likely cause and response |
| --- | --- |
| `Connection refused` or timeout | Recheck the Runtime with `openhalo status`, firewall/public-port reachability, and the exact selected `ws://`/`wss://` URL. |
| `pairing_code_expired` or `invalid_pairing_code` | Generate a new code; codes are intentionally one-time and short-lived. |
| `device_already_paired` | Use `reconnect`; revoke only if deliberately replacing the device identity. |
| `ModuleNotFoundError` for the bootstrap | Repeat the two-file deployment step; the device copy is intentionally separate from the repository checkout. |
| P-256/OpenSSL failure | Confirm `openssl version`; do not substitute a random key format or introduce a compiler toolchain. |
| Capture probe reports `unavailable` | Stop a conflicting MaixVision preview, then retry once. Do not turn this into a continuous retry loop. |
| Presence reports `unavailable` | Check that no MaixVision preview or other camera process owns the sensor; the Edge deliberately reports failure rather than `absent`. |

## What this does not verify

This runbook proves device access and the public Edge session boundary, plus a
bounded local visual Feature pass when section 7 has been accepted on the owner
Runtime. It does not prove a boot-supervised service, local display state,
Scene Profile/Feature Subscription governance, bounded evidence, face identity,
OCR, gesture/pose inference, audio addressing, or any raw-media policy. Those
remain explicit M17.10 work.
