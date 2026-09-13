# Cosmos video model-only probe

Owner selected `embedl/Cosmos-Reason2-2B-W4A16-Edge2-FlashHead` on
2026-09-13 11:47. This is an isolated model test, not a streaming service or
Runtime integration. Model access and verified weight download are complete;
the isolated inference image and FlashHead plugin are installed. The bounded
13-clip replay is complete; see [results](../../docs/ops/jetson-cosmos-flashhead-validation.md).

Later [memory cleanup and resolution follow-up](../../docs/ops/jetson-cosmos-memory-resolution-followup.md)
ran five paired 12-frame cases at ~480p and 720p without OOM. Four 720p answers
stopped in 6.151–7.683 s, one truncated. The temporary headless/SSD-swap bench
state and restoration commands are documented in that report.

```sh
docker start openhalo-cosmos-probe-20260913
docker exec openhalo-cosmos-probe-20260913 python3 /work/scripts/offline_benchmark.py \
  --output /work/private/new-resolution-results --case-ids c02 c08 c10 c11 c12 \
  --repeats 1 --compare-widths 832 1280 --max-model-len 6144 --kv-cache-mib 768 \
  --gpu-memory-utilization 0.40
docker stop openhalo-cosmos-probe-20260913
```

## One owner recording

The owner's originally requested sequence was:

1. Empty hands, visibly open.
2. Fist.
3. V gesture.
4. Thumbs-up.
5. Wave hello, with actual side-to-side motion.
6. Hold the phone.
7. Put down the phone and hold the mouse.
8. Put down the mouse and return to visibly empty hands.

Suggested recording: about 5 seconds per stage, with hands and objects fully
visible, plus a short initial/final margin. Do not speak the action labels into
the model's input. This probe sends video only; audio is excluded from inference.
The owner instead supplied an existing recording at
`/home/jetson/openhalo-specialist-expanded/fresh-2157/capture.mp4`.
No new recording was started. It is 89.920 seconds, 1280x720, 60 fps.
Visual inspection confirms phone front/back, screwdriver, empty palm, fist,
thumbs-up and V. Mouse and a confirmed greeting wave are not covered.
`prepare_cases.py` freezes 13 neutral clips and separate reference descriptions.

Inspect the actual video before assigning ground truth or intervals. Planned
actions are not proof of what the camera captured. Save the private source and
frame previews outside Git. Freeze intervals before viewing model answers.

The supplied video yielded nine state/object clips, three transition clips and
one hands-out-of-view control. A still raised palm is not proof of waving.
For temporal evidence, compare full transition windows, not just their final
frames. Keep filenames neutral (c01, c02, etc.) and keep reference answers in a
separate file that the runner does not load.

## Simple runner

`offline_benchmark.py` is the active single-process resident-model runner.
It uses the same neutral prompt/cases and saves each raw complete reply. The
initial HTTP-server approach failed its startup memory check (3.8 GiB available
versus 4.84 GiB requested), so the model-only test removes that service overhead.
The final recipe uses the model's default BF16 precision, context 4096 and fixed
512 MiB KV cache. It directly supplies uniformly decoded frames and timestamps
with resampling explicitly disabled. Frames are resized to 832x468 (approximately
480p after model patch alignment). The 720p attempt ran out of memory and must not
be confused with the completed run. No unrelated host application was stopped.

```sh
docker start openhalo-cosmos-probe-20260913
docker exec openhalo-cosmos-probe-20260913 python3 /work/scripts/offline_benchmark.py \
  --output /work/private/new-results
docker stop openhalo-cosmos-probe-20260913
```

`benchmark.py` is a standard-library client to a local vLLM server. It reads each
clip, constructs a video data URL and records complete-response wall time, raw
reply, usage and stop reason. It does not perform recognition or temporal fusion
outside the model. It and `serve.py` retain the earlier unsuccessful HTTP-server
setup for diagnosis; they are not the measured final route. FlashHead activation
was verified in the successful single-process runtime log.

Input manifest (private file, real clips must exist):

```json
[{"id":"c01","video":"/home/jetson/openhalo-cosmos-video/private/c01.mp4"}]
```

```sh
python3 benchmark.py --cases /path/to/cases.json --output /path/to/new-results
```

The configured engine uses one sequence, context 4096 and disabled prefix and
multimodal processor caches. The installed vLLM 0.14.0 decoder and transformers
4.57.6 processor passed the standalone input check. The separate chat path did
not retain all those arguments, so final validation additionally inspects actual
model prompt visual-token counts and timestamps. At most 12 frames are sampled
uniformly across the entire interval, and HF resampling is disabled. Longer
clips therefore have a lower effective sampling rate than 4 fps. Original
indices/fps and paired model timestamps are saved in private input-check.json.
The actual 12-frame c10/c12 sheets retain all referenced gesture/object changes.
Run `summarize.py docs/ops/evidence/2026-09-13-cosmos-model` from the repository
root to recheck the 39 input hashes, frame-pair token counts and timestamps.

Final v5: 36 stopped answers at 1.278–4.037 s; three phone-front answers hit the
96-token limit through repetition. A 192-token control still repeated/truncated.
Gesture sequence c10 passed order, but object transitions and ending states did
not reliably pass. All repeated texts were identical. The stopped environment is
retained; the download tunnel and measurement processes are now closed.

The warm-up reply is preserved separately. Each case is repeated three times;
repeats measure stability, not independent accuracy. Full usable reply <=8 s is
preferred, 8–10 s is within the owner's screening tolerance, >10 s fails it.
Timeouts and truncated/wrong replies are not passes. Report per-stage gesture,
object, empty-hand accuracy and transition order; do not claim general accuracy
from this one person/recording.

## Preflight 2026-09-13

- Jetson SSH works, L4T 36.4.3, NVIDIA torch 2.5.0a0 nv24.8; vLLM and FlashHead absent.
- RAM 7619 MB total, 4462 MB available at first check; root 9.2 GiB free.
- Windows and Jetson had no cached HF login. Windows model config request returned
  HTTP 401 `GatedRepo`. Jetson direct network request failed; this is not a model failure.
- At owner request, login/download should occur on Jetson. A temporary SSH reverse
  tunnel binds Jetson `127.0.0.1:17897` to the existing Windows `127.0.0.1:7897`
  proxy. HF home returned HTTP 200 through it; restricted config still returned 401.
  It opens no public proxy port. Credentials must stay in the Jetson user's HF cache.
- Exact NVIDIA image tag exists:
  `ghcr.io/nvidia-ai-iot/vllm:0.14.0-r36.4-tegra-aarch64-cu126-22.04`, digest
  `sha256:2a90817f4d760094a25c546126a48aa8e8ae4fae1ae41bf72445fbc2c8bc2a7f`.
  Its compressed layers total 9,550,279,368 bytes. The owner subsequently approved
  removing seven named inactive Ollama models; `ollama rm` completed and free
  space rose from 9.2 to 37 GiB. No partition or system upgrade was performed.
  Direct Docker pull stalled on large layers, so the same digest is being streamed
  through the loopback proxy using verified official crane 0.22.1 into `docker load`.
- The owner completed Jetson HF login and repository consent. All 18 model files
  at revision `9e4e46b4accf298a34d6db02ba637e9ecc175b6c` were downloaded on Jetson
  and size/SHA256 checked (2,896,043,275 bytes). FlashHead 0.1.10 wheel is staged.
  This proves asset availability, not successful model load or inference.
- The Windows isolated HF CLI installation completed before the user changed
  preference; it is unused under `D:\openhalo-cosmos-assets\hf-cli-env`.

The temporary tunnel PID/log are under `D:\openhalo-cosmos-assets`. Keep it only
while needed for the authorized login/download; stop that specific process when
finished. Never record tokens in repo, manifests, shell command arguments or logs.
