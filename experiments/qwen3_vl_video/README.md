# Qwen3-VL-2B video model probe

## Live camera demo

Open `http://192.168.0.30:8766` on the same trusted LAN. The page starts idle.
Click **开始摄像头分析** to load/warm Qwen (typically about one minute), then
open the CSI camera. It shows live preview, original model answers, completion
times, actual sampled 16-frame evidence and selectable answer history. The model
uses the unchanged English prompt; the page does not translate or rewrite answers.
An answer remains attached to its own input window, not to the current preview.

Each user-started session is capped at ten minutes; **停止** ends camera capture,
drains the tail when possible and releases the dedicated model container. The
page and completed results remain available. A new session starts a new private
run directory. Closing the browser alone does not stop capture; use Stop or wait
for the session cap. All images stay in local private storage, roughly 270 MiB
per ten-minute session with this scene; repeated sessions accumulate disk usage.
There is no automatic boot start, no audio and no Personal Runtime connection.

Host setup uses the existing container, CSI hardware and GStreamer OpenCV:

```sh
# Copy demo.py/demo.html/live_capture.py/live_benchmark.py/frame_ablation.py
# into /home/jetson/openhalo-qwen3-vl-video/scripts/ first.
sudo systemctl start nvargus-daemon
/usr/bin/python3 /home/jetson/openhalo-qwen3-vl-video/scripts/demo.py
```

`demo.py` listens on port 8766 and defaults to LAN access, matching the prior
VLM demo. It has no login and must not be exposed publicly. The page rejects
cross-origin control POSTs and cannot start a second session while one is active.
Use `--host 127.0.0.1` with an SSH tunnel for local-only access. An already running
probe container is rejected rather than sharing model resources with another run.
After finishing all demo use, the operator can stop the server and restore
`nvargus-daemon` to inactive. Camera access itself is released at session stop.

The first [live validation](../../docs/ops/jetson-qwen3-vl-live-validation.md)
completed 25 replies at median 4.868 s, with no delivered-frame handoff gaps or
buffer overflow; gesture/object transitions remain unverified. The demo adds
interactive preview overhead and does not inherit those performance claims without
measurement. Test with `python -m unittest discover -s experiments/qwen3_vl_video
-p 'test_*.py'` from the repository root.

## Offline model probe

Owner selected Qwen3-VL-2B-Instruct on 2026-09-13. The initial deployment uses
the community `cyankiwi/Qwen3-VL-2B-Instruct-AWQ-4bit` checkpoint, revision
`db40a251bdba88fafabf8f3176e7488ed523ab51`, based on the Qwen original.
This measures that quantized artifact on existing vLLM, not original BF16 or
the NVIDIA TensorRT Edge-LLM performance recipe. No FlashHead is used.

The bounded test is complete: 26 greedy replies across two resolutions plus
seven selected 720p recommended-decoding controls, all naturally stopped within
10 seconds. Temporal/ending-state errors remain; see the
[validation report](../../docs/ops/jetson-qwen3-vl-validation.md).

`fetch_assets.py` downloads only pinned assets and validates sizes and upstream
LFS SHA256. `prepare_runtime.py` preserves original assets and creates a symlinked
runtime view with Transformers 5 `rope_parameters` mapped to the equivalent
4.57.6 `rope_theta`/`rope_scaling` fields. Values are asserted before and after.
Checkpoint Python/YAML code is not executed.

`offline_benchmark.py` adapts the retained Cosmos direct-frame runner and imports
its unchanged neutral prompt from `../cosmos_video/benchmark.py`. It uses the
same frozen local clips, frame sampling and timestamps, greedy decoding and
96-token cap. Input/prefix caching is disabled. Reference labels never enter
the prompt. The source recording does not cover mouse or a confirmed greeting
wave; this is reused footage rather than a fresh generalization test.

Jetson layout: `/home/jetson/openhalo-qwen3-vl-video` mounted at `/work`; the
existing Cosmos root mounted read-only at `/baseline`. Copy the shared
`benchmark.py` into `/work/cosmos_video/` for the remote prompt import.
Container: `openhalo-qwen3-vl-probe-20260913`, base image
`sha256:15b41320647ebbaa4547b96bbb027d4816e8cb1ee018fda3ebaba1c8056291ed`.
Private video and model weights remain outside Git.

```sh
docker exec openhalo-qwen3-vl-probe-20260913 python3 /work/scripts/prepare_runtime.py
docker exec openhalo-qwen3-vl-probe-20260913 python3 /work/scripts/offline_benchmark.py \
  --output /work/private/run-NEW --repeats 1 --compare-widths 832 1280 \
  --max-model-len 6144 --kv-cache-mib 768 --gpu-memory-utilization 0.40
```

Measure clip read/decode/resize through the complete answer, excluding model load
and prior clip extraction. A stopped answer within 8 seconds is preferred;
8–10 seconds is acceptable for screening. Truncation/repetition is not a pass.
Semantic validity must be reviewed separately; no live audiovisual or Runtime
acceptance follows from an isolated replay.

`--decoding qwen-recommended` selects temperature 0.7, top-p 0.8, top-k 20,
presence penalty 1.5, repetition penalty 1.0 and seed 0 for the follow-up.
The 96-token cap is retained. It improved selected empty-hand wording but did
not resolve temporal errors. The initial runner predates this optional switch;
its source and exact config are retained with the evidence.

## Fixed-clip frame-count follow-up

`frame_ablation.py` compares 12 uniformly spaced frames, 1 fps (7 frames) and
0.5 fps (4 frames) on one frozen seven-second gesture clip at 720p. Review
`--prepare-only` contact sheets and freeze `sampling_reference.json` before
inference. The reference is not loaded by the runner. One warm-up per profile
and three rotating-order fixed-seed repeats preserve the same engine and prompt.
Actual prompt timestamps/token counts are asserted, including odd-frame padding.
`summarize_sampling.py --run <results>` computes timings and consistency.

The measured medians were 7.472, 4.719 and 3.076 seconds respectively. Every
profile still made gesture-sequence errors; see the
[sampling report](../../docs/ops/jetson-qwen3-vl-sampling-validation.md).
The private source clip is prepared from the original recording at 28.5–35.5 s,
using `ffmpeg -ss 28.5 -i <source> -t 7 -an -vf fps=4 -c:v libx264 -preset fast
-crf 18 -threads 2 -pix_fmt yuv420p <new-c14.mp4>`. Runtime path is
`/work/private/sampling-cases-v1/c14.mp4`. Use fresh output directories:

```sh
docker start openhalo-qwen3-vl-probe-20260913
docker exec openhalo-qwen3-vl-probe-20260913 python3 /work/scripts/frame_ablation.py \
  --prepare-only --output /work/private/sampling-inputs-NEW
# Review the sampled images and reference before starting inference.
docker exec openhalo-qwen3-vl-probe-20260913 python3 /work/scripts/frame_ablation.py \
  --output /work/private/sampling-run-NEW
docker stop openhalo-qwen3-vl-probe-20260913
```

Higher-frame follow-up uses `--profiles uniform12 uniform16 uniform24 uniform28`.
The first 720p attempt with context 12800 / KV 1536 MiB hit kernel OOM during
24-frame warm-up. Complete the bounded 720p comparison using profiles 12/16,
context 8192 / KV 960 MiB, and a separate 480p comparison using width 832,
profiles 12/16/24/28, context 6144 / KV 768 MiB. Each arm includes a remeasured
12-frame baseline. See the
[higher-frame report](../../docs/ops/jetson-qwen3-vl-highframe-validation.md).
The runner records effective processor dimensions and checks dynamic visual
token counts; it supports `--repeats` and rotates over the selected profiles.
