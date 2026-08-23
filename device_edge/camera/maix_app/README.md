# OpenHalo Camera Edge Maix App

This is the minimal manually launched Maix App wrapper for the Camera Edge.
It owns one local camera + YOLO11 pipeline and reports only the debounced
`camera.person_presence.v1` semantic Observation to the OpenHalo Runtime.

The package intentionally does not contain an endpoint, pairing secret, or
private key. Before launching it, create this device-private file:

`/root/.openhalo-camera-edge/app-config.json`

Use `openhalo_camera_edge/app-config.example.json` as the shape. Do not copy a
real Runtime URL or identity material into this repository.

The initial App has no Display UI. It is manually launched from the Maix
Launcher and remains the sole camera/NPU owner until the Launcher or MaixVision
stops it. Do not configure boot auto-start until that manual lifecycle has
passed on the real device.

`app.yaml` packages the confirmed OpenHalo primary logo at
`assets/openhalo-logo-primary.png`; Maix Launcher reads its `icon` field rather
than using the system default icon.
