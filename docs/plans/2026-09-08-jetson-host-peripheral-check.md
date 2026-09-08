# Jetson host and peripheral check — 2026-09-08

Scope: owner-authorized storage inventory, fan diagnosis, camera and audio smoke tests. This record covers the initial steps 1–4, during which no disk cleanup/resize, package installation, fan policy change, or model execution occurred. The owner subsequently authorized the separate [step-5 VLM experiment](2026-09-08-jetson-vlm-demo-validation.md); the overall initial check is now closed.

## Storage inventory

Root filesystem: 172 GiB total, 140 GiB used, 25 GiB available (86%). Main directory usage (nested entries must not be added together):

| Directory | Usage | Contents identified |
| --- | --- | --- |
| /usr | 59 GiB | System and installed software |
| /usr/share/ollama | 37 GiB | Pre-existing Ollama directory; no models run |
| /usr/local | 12 GiB | Includes CUDA 12.6 (3.9 GiB), libraries (7.9 GiB) |
| /var | 42 GiB | Includes Docker, logs, caches, swap file |
| /var/lib/docker | 20 GiB | Existing Docker data |
| /var/log | 6.7 GiB | Logs |
| /home/jetson | 35 GiB | Existing vendor/development files |
| /home/jetson/workspaces/isaac_ros-dev | 16 GiB | Isaac ROS workspace |
| /home/jetson/.cache | 7.9 GiB | Existing caches |
| /opt | 4.1 GiB | Includes NVIDIA software (3.6 GiB), ROS |

Preserved all existing files. Approximately 3.5 MiB of test artifacts added under `/home/jetson/openhalo-hardware-check-20260908` on the Jetson.

## Fan and bounded CPU load

`jtop.service` is active; its startup log explicitly records manual fan profile selection. Saved `/usr/local/jtop/config.json` contains manual profile and speed [80, 0], but live jtop reports 34.51% and sysfs PWM is 88/255. These differ; the saved startup value must not be treated as current speed. `nvfancontrol.service` is inactive, consistent with manual jtop control. Fan tachometer is approximately 2073 RPM. No policy changed.

A 15-second, six-worker OpenSSL SHA-256 CPU load (1024-byte block, hard timeout) with a 20-second tegrastats window showed six CPUs at 100% / 1728 MHz in the initial load samples, peak CPU temperature 55.656 C and peak board-reported input power 7606 mW. The first OpenSSL invocation had a per-block rather than total duration and was interrupted; no OpenSSL processes remained after tests. Fan PWM stayed 88. This is bounded CPU evidence only, not automatic fan regulation or sustained GPU/thermal acceptance.

## Camera

`/dev/video0`: CSI `vi-output, imx219 9-0010`, tegra-video driver, RG10 Bayer. Enumerated modes: 3280x2464@21, 3280x1848@28, 1920x1080@30, 1640x1232@30, 1280x720@60. No 3840x2160 mode enumerated.

Argus -> nvvidconv -> software x264 -> MP4 captured 150 frames at requested 1080p30. File `camera-1080p30.mp4`: 1920x1080 H.264, 150 decoded frames, duration 4.984333 seconds, approximately 2.6 MiB. Source timestamps were strictly increasing, intervals 17–63 ms, with one interval above 50 ms. FFmpeg null-output validation reported two non-monotonic DTS warnings at its output timebase; do not claim perfect cadence or zero dropped frames.

Extracted two-second preview was visually inspected: blurred gray-purple/noisy image without a recognizable scene. Capture/encoding is live, but usable image quality is NOT accepted. Lens cover, scene illumination, focus and then capture/ISP settings require follow-up. A user question was sent to verify the physical scene.

## Audio

C-Media USB Audio Device, USB ID 0d8c:0012, ALSA card 2. Native capture: S16_LE mono, 44.1/48 kHz. Native playback: S16_LE stereo, 44.1/48 kHz. Speaker playback is enabled at 49%; microphone capture enabled at 34%, AGC enabled. No mixer settings changed.

Recorded `microphone.wav` through hw:2,0: five seconds, 48 kHz mono, 240000 samples, peak absolute sample 22975, RMS 458.58 (int16 scale). Non-silent capture established; intelligibility not verified. Generated a two-second, 660 Hz low-amplitude tone and aplay completed on plughw:2,0. Physical audibility/speaker quality awaits owner confirmation. No recording was sent to an external service.

## Follow-up with owner feedback

The owner reports no lens cover and a very close camera-to-face distance. A subsequent 90-buffer 1080p capture (`camera-recheck.mp4`) completed; its two-second preview was visually inspected and shows a recognizable close-up face/background, with visible noise and soft detail. This establishes actual imaging, superseding the first preview's lack of recognizable content; root cause of that first view is not established. Camera quality at intended room distance and cadence remain unaccepted. Kernel logs distinguish successful imx219 9-0010 from a failed probe at the other 10-0010 address; do not attribute the latter to the working camera. Exposure/gain after the first capture were 29999 us and 170/171.

The owner describes the speaker attached to a USB-C voice module and initially could not hear the very low-amplitude tone. USB output was the default, unmuted at about 49%. A second two-second 660 Hz tone, generated with a higher sample amplitude while keeping mixer settings unchanged, completed on the same USB sound card; the owner explicitly confirmed hearing it at 21:17. Basic physical speaker playback is now confirmed. Microphone non-silent capture remains confirmed, but speech intelligibility was not assessed.

## Read-only inventory of reusable inference assets

Follow-up inventory found Ollama 0.11.4 active but `ollama ps` empty; no model was loaded or run. Its existing model directory `/usr/share/ollama/.ollama/models` accounts for approximately 37 GiB. Installed candidates include qwen2.5vl:3b (3.2 GB), llava-phi3:3.8b (2.9 GB), gemma3:4b (3.3 GB), minicpm-v:8b (5.5 GB), llava:7b (4.7 GB), and several text models. Read-only `ollama show` confirms vision capability and Q4_K_M quantization for the first three. These are candidate assets, not validated memory/latency profiles.

Ultralytics 8.4.24, ONNX Runtime GPU 1.20.0, local YOLO11n/YOLO26n .pt/.onnx/.engine files and Yahboom examples exist under `/home/jetson/ultralytics`. TensorRT engine compatibility has not been tested. Docker images include Open WebUI, Label Studio, Yahboom ROS Melodic, CUDA 12.1.1 base and hello-world; they are not evidence of a ready Jetson multimodal inference container. Bounded home-directory searches found no Mage-VL/StreamMind runtime or standalone GGUF weights; this is not an exhaustive whole-disk absence claim. No package/model downloads or inference were performed.

## Final acceptance boundary

Storage inventory and fan diagnosis complete. Camera capture/recognizable imaging, microphone non-silent capture, and owner-confirmed speaker playback are established with the limitations above. Model inference was subsequently tested in the linked step-5 record. Camera Edge v2 end-to-end acceptance remains pending; no further optimization is scheduled in this initial check.
