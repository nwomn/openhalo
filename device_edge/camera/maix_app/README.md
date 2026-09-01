# OpenHalo Camera Edge Maix App

This is the minimal manually launched Maix App wrapper for the Camera Edge.
It owns one local camera + YOLO11 pipeline and reports bounded semantic
Observations to the OpenHalo Runtime. `camera.person_presence.v1` remains the
backward-compatible person state; the same local sample can also provide an
explicit object-label allowlist, normalized person-region occupancy, capture
availability/frame dimensions, and debounced person/region transitions.

The package intentionally does not contain an endpoint, pairing secret, or
private key. Before launching it, create this device-private file:

`/root/.openhalo-camera-edge/app-config.json`

Use `openhalo_camera_edge/app-config.example.json` as the shape. Set
`object_labels` only to labels you intend to admit and set `regions` as
normalized `[x1, y1, x2, y2]` rectangles. Do not copy a real Runtime URL or
identity material into this repository.

The visual pass never sends camera frames, bounding boxes, or other detection
geometry. Its `scene_quality.v1` result is deliberately limited to camera
availability and detector dimensions; it is not a blur/exposure score.

## Single-owner capture loop

The App now constructs one `CameraEdgeService` event loop. Only its
`MaixCameraCaptureOwner` opens the camera. Each captured NV21 frame is consumed
locally by the H.264/MP4 segment recorder and (at its configured sampling
interval) the YOLO Feature worker. The Gateway/session code receives only
semantic observation frames and textual action results; it never receives a
frame or video segment.

Set `media_memory_enabled` to `true` only after the owner has opted into local
continuous recording. It enables a local Hot Ring and the two registered
actions: `media.provider.configure` and `media.memory.query`. Runtime supplies
the configured provider profile in memory after connection; a recent query is
understood locally against selected Hot Ring MP4 segments and returns Markdown
only. The example uses a 2-second segment at 1 Mbps so a selected provider
request stays bounded. The provider call remains asynchronous relative to the
capture loop.

This package path is tested for import and configuration construction, but has
not yet passed real-MaixCAM MP4 segment sealing or provider-video acceptance.

The initial App has no Display UI. It is manually launched from the Maix
Launcher and remains the sole camera/NPU owner until the Launcher or MaixVision
stops it. Do not configure boot auto-start until that manual lifecycle has
passed on the real device.

`app.yaml` packages the confirmed OpenHalo primary logo as the
`128×128` RGBA asset `assets/openhalo-logo-primary.png`; Maix Launcher reads
its `icon` field rather than using the system default icon.
