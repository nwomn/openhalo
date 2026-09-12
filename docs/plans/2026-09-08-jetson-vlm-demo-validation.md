# Jetson VLM demo — bounded implementation validation

Current disposition (2026-09-12): the owner classifies the tested Qwen2.5-VL
3B direct-image implementation as a failed Camera Edge technology route
against minimum usability, owing to latency and insufficient output quality.
The execution and demo checks below are retained as historical component
evidence, not evidence of a usable route awaiting routine acceptance.

The owner requested a clean camera-window example with asynchronous Qwen2.5-VL annotations and startup-configured ablations. Implementation: `experiments/jetson_vlm/`. This supersedes the earlier request to stop before model validation, within this standalone demo only.

Final status: initial check closed at owner direction. Basic model executability is established; interactive semantic quality, accurate localization, sustained performance and Runtime integration are not accepted. No continued optimization is scheduled.

## Validation performed

- Four unit tests passed on local Python 3.12 and Jetson Python 3.10: display factor does not change model payload; grounding adds coordinates to the task; malformed coordinates are rejected without silent repairs; incomplete streams fail explicitly.
- Local compile check and git diff whitespace check passed.
- Actual Jetson CSI 1280x720/30 preview opened and browser accessibility state showed the page, camera element, correct caption configuration, live 30 FPS capture metric and analyzing status. Subsequent browser screenshot/state tool calls timed out, so full rendered-overlay visual QA is not claimed. Latest preview transport uses finite latest-JPEG requests to avoid accumulating stream requests, while keeping an optional MJPEG endpoint.
- Actual local Ollama qwen2.5vl:3b returned parsed caption and grounded results, with no downloaded models or new dependencies. This is model-output/protocol validation; it does not establish label truth or coordinate accuracy.

| Input/task | Request | Total request seconds | First content seconds | Output tokens | Prompt processing seconds |
| --- | --- | --- | --- | --- | --- |
| live CSI / caption | 1 | 45.224 | 41.328 | 47 | 33.593 |
| live CSI / caption | 2 | 29.907 | 26.513 | 46 | 26.180 |
| same fixed image / grounded | 1 | 33.280 | 25.045 | 114 | 24.644 |
| same fixed image / grounded | 2 | 9.753 | 0.645 | 114 | 0.196 |

These are smoke checks with unequal inputs, not a caption-vs-grounding ablation. Repeated fixed-image cache reuse explains much of the fourth row's improvement. First streamed content can be a JSON delimiter rather than a usable label. The first caption request included 7.322 seconds loading; the others had roughly 0.07–0.14 second loading. Live capture remained about 30 FPS. Still-image replay originally encoded a full 1920x1080 image each cycle and ran around 16 FPS; this is not a CSI throughput result.

Ollama 0.11.4 reported 5.6 GB loaded model allocation with 58%/42% CPU/GPU and context 2048; model disk size does not represent runtime memory. One sample showed 389 MiB swap in use. No full-GPU or real-time latency claim is made.

## Architecture and limitations

### Resource check after owner stopped optimization, 22:04–22:05

At inspection the demo was paused, Ollama had unloaded the model, system memory was 3.3 GiB used/3.8 GiB available and swap retained 530 MiB. One same-configuration grounded live-camera request was explicitly bounded by resuming then immediately pausing subsequent requests. No model parameters or software were changed. Request 4 completed in 43.452 s (load 4.461 s, prompt processing 30.098 s, generation 8.561 s), capture 30.04 FPS. Analysis remains paused afterward.

One-second tegrastats samples were filtered to the request interval (44 samples): system RAM peak 6681/7620 reported MB (~6.52 GiB of 7.44 GiB), swap peak 674 MiB (144 MiB above the pre-request snapshot), mean CPU utilization across six cores 79%, peak 100%, GPU sampled utilization average 10.98% and peak 99%. These are whole-device figures, not additive CPU RAM plus dedicated GPU VRAM. Ollama reports loaded size 5.6 GB and 58%/42% CPU/GPU allocation; that ratio is model placement, not utilization. One process snapshot showed runner RSS ~2.0 GiB, demo RSS ~216 MiB and nvargus-daemon RSS ~181 MiB; RSS is not a complete unified-memory attribution.

During the request, board-reported VDD_IN mean was 11.676 W, peak 16.435 W; CPU temperature peaked at 65.593 C and GPU temperature at 66.468 C. Post-request fan readback was 2152 RPM / PWM 88. These one-second bounded samples can miss short peaks and do not establish sustained thermal acceptance. Raw tegrastats/vmstat evidence is retained on Jetson under `runs/20260908-215342-342332/resources-request4.log` and `vmstat-request4.log`. No optimization follows this check per owner direction.

### Owner experience feedback, 21:57

The owner reports roughly 30 seconds per understanding result, incorrect boxes, and descriptions that are too simple. The current preset does not meet the intended interactive semantic experience. This feedback is about the tested pipeline, not a model-family capability ceiling: the prompt explicitly limits output to three labels of at most 20 Chinese characters, and measured execution uses mixed CPU/GPU allocation. Grounding accuracy is independently unsatisfactory. Follow-up comparisons should isolate execution placement, caption task/prompt richness, and localization rather than change them together. No follow-up optimization or new model selection is accepted by this feedback alone.

Capture owns one latest frame; one worker performs inference; HTTP serves frames and state; browser renders captions/SVG. There is no retry/fallback chain, automatic coordinate repair, model replacement, tracker or action execution. Errors stop further model requests and remain visible. Live boxes use the analyzed historical frame's coordinates with a visible age and TTL; the original frame is shown alongside for comparison. They do not track moving subjects.

Three presets isolate caption+subtitles, grounded+boxes, grounded+subtitles. A grounded display-only change produces identical model requests. Model timings do not measure browser draw cost. Runs store configuration, model identity, image SHA256, prompt/schema and request timing/output/error records. New video is not recorded by default.

Device directory: `/home/jetson/openhalo-vlm-demo`. During the experiment the LAN preview ran at `http://192.168.0.30:8765`; it is stopped at closeout to release the camera. Restart using the README commands when another experiment is wanted. No system service/autostart or fan/storage settings were changed. Camera Edge v2 room-scene quality, sustained thermals/cadence, full ablation and Runtime integration remain pending.

## 2026-09-09 simplification review

Removed the unused optional MJPEG endpoint and the configuration serialization wrapper. Annotations now appear only on their analyzed snapshot, removing the unsupported assumption that historical coordinates still describe the live scene and eliminating overlay TTL configuration. Snapshot requests must match the result ID; the browser loads that snapshot before painting its annotations. Capture/inference separation, task/display ablations and measurement logs remain necessary to the experiment. This local revision does not extend the prior physical acceptance.

## 2026-09-09 deployment smoke check

Deployed the simplified source through the new public-key SSH alias `jetson` to `/home/jetson/openhalo-vlm-demo`. Previous source is backed up at `/home/jetson/openhalo-vlm-demo-before-20260909-1108.tar.gz`. Local/remote SHA256 matches for app.py, config.py and index.html; served HTML matches the local file. All four existing tests and Python compilation pass on Jetson.

Started `python3 app.py --config presets/boxes.json --host 0.0.0.0 --requests 1`. Run `runs/20260909-110833-642169` completed one real CSI grounded request: 48.192 s request, 48.212 s frame-to-result, 39.477 s first content, 4.534 s loading, 34.530 s prompt processing, 8.776 s generation, 115 output tokens. Capture was 29.888 FPS at completion, with no camera/model error. These single-request figures do not establish comparative performance or label/grounding accuracy.

HTTP verification confirmed changing live JPEG bytes, a valid result-1 snapshot, rejection of a mismatched snapshot ID (404), and removal of MJPEG (404). In-app and Chrome browser automation timed out, so rendered annotation placement and visual quality remain unverified. Preview is left running at `http://192.168.0.30:8765`; model analysis automatically paused after the one request. The Continue button allows another single request. No system autostart was installed.
