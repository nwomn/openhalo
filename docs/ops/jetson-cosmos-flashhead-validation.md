# Cosmos-Reason2-2B Edge2-FlashHead Jetson validation

Date: 2026-09-13. Status: **bounded model-only validation completed; mixed semantic result**.

**Later memory follow-up:** temporary desktop/Argus/Ollama shutdown and moving
swap use from ZRAM to the existing SSD allowed true 12-frame 720p on five clips.
Four stopped replies took 6.151–7.683 s; one repeated/truncated. This supersedes
the initial run's 720p feasibility limit, while semantic reliability remains
mixed. [Memory cleanup and paired resolution results](jetson-cosmos-memory-resolution-followup.md).

The final practical recipe used 6–12 frames spanning each full clip, resized to
832x468 before model preprocessing (832x480 patch grid), about 480p. It completed
all 13 clips and three repeats each: 36 naturally stopped answers took
1.278–4.037 s, median 2.517 s. Three phone-front answers repeated until the
96-token cap. A 192-token follow-up still repeated and hit the cap at 5.461 s.
Truncation is not a complete usable answer, even below 10 seconds.

Gesture/held-object recognition and one gesture sequence are useful positive
evidence. Object transitions, ending states and internal consistency still fail.
This is **not a successful reproduction of the publisher's 12-frame 720p
benchmark**, and is not Camera Edge acceptance or long-running validation.

The owner selected the first candidate and proposed a recording containing empty
hands -> fist -> V -> thumbs-up -> wave -> phone -> mouse -> empty hands. Test
only the model, with minimal external construction. Record per-stage gesture,
held-object and ending-state outputs plus chronological transition results.
Useful completed model replies <=8 s are preferred; 8–10 s are tolerated.
Model-level timing does not establish long-running Camera Edge acceptance.

## Observed results

Each row below covers three identical deterministic answers. Repeats test local
stability, not independent accuracy. Laterality and decorative scene details are
not separate scored targets. Full English answers and manual per-axis notes are
in [summary.json](evidence/2026-09-13-cosmos-model/summary.json).

| Case / visible evidence | Full-reply seconds | Model result and limitation |
| --- | --- | --- |
| c01 phone front | 3.611–3.707 to cap | Phone recognized; repeated text, all three truncated. 192-token control also truncated. |
| c02 screwdriver, then lower | 3.689–4.037 | Screwdriver recognized; falsely says hand stays in position throughout. |
| c03 empty open palm, lower | 2.174–2.180 | Palm and no object recognized; ending lowering omitted. |
| c04 fist | 2.564–2.930 | Fist recognized. |
| c05 thumbs-up | 1.278–1.355 | Thumbs-up recognized. |
| c06 V | 1.767–1.797 | Peace/V sign and no held object recognized. |
| c07 phone back | 1.972–1.994 | Recognized as smartphone. |
| c08 screwdriver | 3.423–3.613 | Correctly names screwdriver, then contradicts itself by saying hand is empty. |
| c09 empty open palm | 2.181–2.189 | Palm recognized; explicit empty-hand conclusion omitted. |
| c10 palm → fist → thumbs-up → V | 2.835–2.862 | All four gestures and their order correct; beginning-to-lower ending omitted. |
| c11 phone front/back, then lower | 2.921–2.991 | Phone recognized, but invents thumbs-up and misses the transition/ending. |
| c12 screwdriver → empty palm → lower | 3.128–3.187 | Mentions palm and red/silver object as coexisting hands; fails the actual sequence and ending. |
| c13 hands outside clear view | 2.437–2.469 | Correctly says hands are not visible; no false empty-hand conclusion. |

The c10 output is: “Shows five fingers, then clenches into a fist, then gives a
thumbs-up, and finally makes a peace sign.” This supports that bounded sequence
claim only. The c11/c12 failures prevent a general temporal-understanding pass.
Mouse recognition and greeting-wave recognition remain untested by this footage.

## Final measured recipe and scope

- Direct local `LLM.generate`, one resident process, same neutral prompt, no
  reference answers/history/fusion supplied. Video only; no audio interpretation.
- BF16 selected by model configuration, INT4 Marlin language kernels, FlashHead
  lazily loaded on GPU and CUDA graphs active. Actual runtime log verifies activation.
- Context 4096, prefill batch 2048, fixed 512 MiB KV allocation; one request at a
  time. Prefix and multimodal processor caches disabled. No quantization/model
  weight edits and no host service/power-mode changes.
  The installed input-processor branch was checked: these two cache flags also
  assign request-specific multimodal IDs, preventing encoder reuse across repeats.
- Decode uniformly at most 12 frames across the entire clip. Explicit per-input
  metadata and processor flags disable resampling. Logged actual prompt visual
  token counts (390 per frame pair) and timestamps passed all 39 formal checks.
  The first video has 10 frames, shorter videos 6–9, long videos 12.
- Stopwatch includes reading, decoding, resizing, model preprocessing, GPU work
  and complete generated text. Prior clip extraction and model initialization
  are excluded. Final v5 initialization was 82.295 s; warm-up reply 4.126 s was
  retained separately and was truncated. This is not live capture/event latency.
- Observed telemetry window 12:42:08–12:44:00 reached 7361/7620 MB RAM, swap
  1334–2860 MB and maximum reported junction temperature 74.937°C. This bounded
  window is not a sustained thermal or tail-latency test.
- Raw outputs, config, input hashes, runtime log and telemetry are in
  [evidence](evidence/2026-09-13-cosmos-model/). Private source/video/frame sheets
  and model weights remain outside Git and were not uploaded for inference.

After testing, the container and its telemetry process were stopped and the
temporary proxy tunnel closed. Weights and the prepared stopped container remain
for reproducibility. Root free space is about 12 GiB. Prior experiments remain.

## Reproduction assets

- Model: `embedl/Cosmos-Reason2-2B-W4A16-Edge2-FlashHead` at
  `9e4e46b4accf298a34d6db02ba637e9ecc175b6c`; 18 listed files, 2,896,043,275 bytes.
- Configuration confirms `FlashHeadQwen3VLForConditionalGeneration` and
  `flash_head_cache_dir=flash_head_assets`.
- NVIDIA runtime image: `ghcr.io/nvidia-ai-iot/vllm:0.14.0-r36.4-tegra-aarch64-cu126-22.04`,
  digest `sha256:2a90817f4d760094a25c546126a48aa8e8ae4fae1ae41bf72445fbc2c8bc2a7f`.
- Jetson L4T 36.4.3; base NVIDIA PyTorch and prior experiments preserved.
- Private experiment root: `/home/jetson/openhalo-cosmos-video`.
- [Scripts and protocol](../../experiments/cosmos_video/README.md).

## Confirmed preparation

The owner completed HF login on Jetson and accepted the selected repository's
access conditions. Initial 401/403 access failures were resolved: authenticated
config download succeeded. Credentials remain in the Jetson account's normal
HF cache, not in repository files or process arguments.

Jetson direct HF access timed out. A temporary loopback-only reverse SSH proxy
tunnel restored connectivity using the existing Windows proxy; download clients
and output files run on Jetson. Direct Docker pull reached GHCR but stalled on
large layers. The identical manifest digest was streamed through the proxy
using official crane 0.22.1 into `docker load`, without changing daemon settings.
The crane arm64 archive was checked against the release checksum
`898c0cff975f898a33e8c4580bdafb0e7c02c7faa33374e946762f97c4ab7110`.

At 11:58 the owner explicitly authorized removing seven inactive Ollama models:
`deepseek-r1:7b`, `qwen3:8b`, `minicpm-v:8b`, `llava:7b`, `gemma3:4b`,
`llava-phi3:3.8b`, `phi4-mini:3.8b`. All seven were removed using `ollama rm`.
Root free space increased from approximately 9.2 GiB to 37 GiB. The before-list
is preserved in the private experiment directory. MobileVLM/TinyLLaVA environments,
recordings and evidence were retained. All 18 model files subsequently completed
size/SHA256 verification; total download time was 254.83 s. The private
`assets/asset-manifest.json` records each file. FlashHead 0.1.10 was installed.
Runtime image import and plugin installation completed. The imported arm64 image
ID is `sha256:15b41320647ebbaa4547b96bbb027d4816e8cb1ee018fda3ebaba1c8056291ed`
(22,294,086,873 bytes); temporary import data was released, leaving about 12 GiB.
Container `openhalo-cosmos-probe-20260913` uses NVIDIA runtime and a bind mount of
the private experiment root, with no restart policy. Installed versions are
PyTorch 2.9.1, vLLM 0.14.0+cu126, transformers 4.57.6 and FlashHead 0.1.10.
CUDA reports Orin; host power mode is MAXN_SUPER. No host Python upgrade occurred.

Startup attempts are retained independently. The HTTP server failed its memory
gate (3.8 GiB free versus 4.84 requested). Single-process 0.60 utilization narrowly
failed (4.44 versus 4.46 GiB); 0.58 loaded weights but explicitly forced FP16
conflicted with the FlashHead BF16 cluster parameters during profiling. The
next default-precision attempt hit a changed free-memory gate. These are setup
failures, not semantic results. A fourth attempt used default BF16, context 6144,
prefill batches 2048 and fixed 768 MiB KV. Its phone-front responses took
5.771–5.994 s after 13.707 s warm-up. That chat path did not preserve the intended
frame count: 2731 prompt tokens are consistent with six processed frames, rather
than the ten decoded frames checked separately. It must not be reported as a
12-frame result. On the next 12-frame clip the kernel logged a global OOM kill
of the experiment Python process at 12:37:24. The final v5 recipe therefore uses
explicit decoded-frame inputs and reduced spatial size, as described above.
The 720p route remains unvalidated on this current host configuration.

## Actual supplied recording and frozen cases

The owner supplied `/home/jetson/openhalo-specialist-expanded/fresh-2157/capture.mp4`:
89.919667 s, H.264, 1280x720, 60 fps. No new recording was started. Visual review
of source contact sheets and each selected clip's start/middle/end confirms phone
front/back, screwdriver, open palm, fist, thumbs-up and V. A mouse and confirmed
greeting wave are not covered. Do not infer the requested sequence occurred.

`prepare_cases.py` created 13 whole-frame video-only clips under private
`cases-v1`, retaining full interval duration at 4 fps. Reference descriptions and
source intervals are separate from the neutral model-input manifest. Nine clips
cover visible gestures/objects; three longer clips cover gesture order, phone
front/back/lowering and screwdriver-to-open-palm transitions; the last checks
hands outside clear view. This is reused study footage, not an independent holdout.

The initial standalone `check_inputs.py` passed all 13 decoder/HF processor checks
with explicit resampling disabled. That check did not establish that the separate
chat path applied the same arguments. For 12 decoded
frames the processed grid is `[6,44,80]`, with 5280 visual tokens. Source frame
indices and paired timestamps match. Actual sampled c10/c12 sheets retain all
referenced gesture/object changes; those private sheets were visually reviewed.

Final v5 checks additionally inspect actual model prompt tokens and timestamps;
syntax checks, evidence hash/pair-count/timestamp validation and three-repeat
consistency checks passed. No general accuracy or full Camera Edge pass is inferred.
