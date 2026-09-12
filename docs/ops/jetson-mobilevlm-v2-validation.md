# MobileVLM V2 1.7B Jetson validation

Date: 2026-09-12. Status: bounded reproduction completed. Single-image response
speed is promising, but hallucination and failed temporal ordering prevent
accepting this as a standalone Camera Edge route. TinyLLaVA-Video remains closed.

| Tested configuration | Warm measured latency | Finding |
| --- | --- | --- |
| FP16, original single-image prompt | 1.093-2.589 s | Food/eating useful; false held objects in non-eating frames |
| FP16, conservative single-image prompt | 0.757-1.151 s | Fewer false objects; full-frame hands-down still claims a remote |
| Language NF4, same conservative prompt | 1.399-1.789 s | Useful selected single-frame states with more memory headroom |
| FP16, chronological two/four-image input | 1.482-4.151 s | Wrong ordering / invented third frame; long outputs truncated |
| Language NF4, four fresh low-head frames | 1.890-2.303 s | Unsupported claim of looking at a computer screen |

These are small replay ranges, not event-level P95. Capture, event confirmation,
Runtime and cold model load are excluded. The original five-second event-label
requirement remains unaccepted.

## Reproduction

- Device: Jetson Orin Nano Super 8GB, existing MAXN_SUPER profile.
- [Official source](https://github.com/Meituan-AutoML/MobileVLM), revision
  `688fdec914810485c8766da96c63d9d2ce15f750`.
- [Official V2 checkpoint](https://huggingface.co/mtgv/MobileVLM_V2-1.7B), revision
  `9a5b623a83feae6a6b2ecad7a843334ccc119ce1`.
- Original checkpoint: 3,348,457,261 bytes; SHA256
  `cd16648451c84831f317dbcc59e9c8d323235bde2dd2ecdaadb67808a25132e9`.
  Windows download and transferred Jetson copy verified. Lossless safetensors
  conversion retained 616 tensors, including 391 vision-tower keys, with
  3,348,242,432 bytes of tensor data in eight shards.
- CLIP config/processor: `openai/clip-vit-large-patch14-336` revision
  `ce19dc912ca5cd21c8a653c79e251e808ccabcd1`. The V2 checkpoint contains vision
  weights; no extra full CLIP checkpoint is loaded.
- Separate venv `/home/jetson/openhalo-mobilevlm-v2-venv`; NVIDIA PyTorch
  `2.5.0a0+872d972e41.nv24.08`, CUDA 12.6, NVIDIA torchvision
  `0.20.0a0+afc54f7` preserved. Transformers 4.33.1, tokenizers 0.13.3,
  accelerate 0.27.2, huggingface-hub 0.25.2, safetensors 0.4.5, timm 0.9.12.
- Runtime copy changes only dummy vision construction to use config before the
  outer checkpoint loads. The runner refuses missing/unexpected/mismatched keys.
  HF 4.33 also needs its FSDP probe disabled when the NVIDIA torch build reports
  distributed support unavailable. The first load attempt exposed this API
  compatibility error; it produced no semantic result.

The [host wrapper](../../experiments/mobilevlm_v2/README.md) records raw outputs,
per-stage latency, token truncation, CUDA allocations and tegrastats. Private
media and weights live under `/home/jetson/openhalo-mobilevlm-v2/` and the local
`D:\openhalo-mobilevlm-assets` directory, outside Git.

## Input and measurement boundaries

Four frames were selected before reading model outputs, from retained camera
recordings: eating at 3 s; greeting A at 0 s (rest), 3.5 s (open hand raised),
and 7.5 s (hand no longer raised, looking roughly forward). Each has a full 1280x720 view and a fixed
crop `[160,40,1140,720]`, chosen to retain the upper body and hands.
The owner previously confirmed the eating and greeting actions; the frame-level
references also use visual inspection. No new action was requested here.

The fixed prompt asks for the visible action and handled object in one short
sentence without guessing intent or identity. Labels, filenames and previous
answers are withheld. Official v1 prompt template, aspect padding, 336px CLIP
input and LDPNetV2 projector are preserved. Greedy generation uses a 48-token
ceiling. Each case has three replays in one resident process. Only the first
inference is cold; case repetitions are not independent accuracy samples.

Timing covers image-file decode/preprocessing and generation through the last
output token. It excludes model load, live capture, event/window selection,
Runtime and final text decoding. A single-image caption—even one saying
“waving”—cannot establish raise/wave/lower process understanding. These small
replays cannot establish a reliable event-level P95 or sustained stability.

## Results

The first FP16 run completed all 24 replays of four frames and their crops.
All checkpoint keys matched. Eating full-frame replies warmed at 1.417-1.569 s;
all eight input variants ranged from 1.093 to 2.589 s when warm. The model
recognized food/eating and the raised-hand image as waving, but invented a
phone, remote control or white held object in every non-eating variant. Fixed
cropping did not remove that failure under the initial object-oriented prompt.
Full-window peaks were RAM 7397/7620 MB, swap 2998 MB and temperature 61.062 C.

One revised prompt was then fixed for all inputs: ask what the person is visibly
doing, require clear evidence, prohibit invented objects/actions/intentions, and
prohibit held-object claims when hands are invisible. Across 16 replays, warm
latency was 0.757-1.151 s. Food-holding, waving and seated-state descriptions
were useful; full-frame hands-down still hallucinated a remote control. Its crop
said sitting and smiling. This is prompt/composition sensitivity, not proven
semantic reliability. Full-window RAM peaked at 7474 MB and swap at 2886 MB.

The initial and conservative prompts have different output lengths; faster
conservative replies are not a model-kernel speedup. Two repetitions of the
same pixels do not establish accuracy. No five-second event-level acceptance
follows from these single-frame timings.

### NF4 memory comparison

Quantizing language linears only with bitsandbytes 0.48.2 (the previously
smoke-verified CUDA 12.6/SM87 library, copied into the new venv) completed all
16 conservative-prompt replays. Warm replies took 1.399-1.789 s, slower than
FP16 but with CUDA peak allocation approximately 1.683 GB versus 3.490 GB.
Full-window RAM peaked at 6298 MB and swap at 942 MB. System swap includes
pre-existing pages; these runs are not proof of zero swapping or steady-state
memory isolation. The selected inputs no longer produced nonexistent held
objects; food/eating, waving and seated descriptions remained useful. This
small change in answers is not proof that quantization improves accuracy.

### Ordered-image process check: failed

A separate FP16 exploratory input used the upstream multiple-image path with
one `<image>` marker per chronologically labeled frame and vision microbatch 1.
This adds no video training or temporal module. Frames 0, 3.5, 4.5 and 7.5 s
were supplied for a complete greeting, with two-frame opening and closing
controls. The added 4.5 s frame was visually inspected before inference.

- Complete greeting: claimed the first frame already had a raised hand and
  invented the wrong raise/lower order. It reached the 48-token ceiling;
  warm generation plus preprocessing was 4.151 s, an incomplete wrong answer.
- Opening (rest -> raised): replied only that the person was waving,
  at 1.482-1.485 s; no explicit transition understanding.
- Closing (raised -> down): initially described lowering, then invented a
  third frame and raising again despite receiving only two frames. It hit
  the 48-token limit at 3.538-3.544 s.

Each input was replayed twice with identical text. The tested ordered-image
route fails process understanding; its truncated timings are not useful
completed-response latencies. This does not invalidate the measured single
image speed, but it prevents accepting MobileVLM as the full temporal route.

### Fresh-camera check

A 59.949 s IMX219 1280x720/60fps recording started at
2026-09-12 20:10:29 +08:00 and ended normally. Frames at 5, 20, 35 and 50 s
were chosen uniformly before inference. Visual inspection showed a seated
person leaning forward with head/gaze lowered; hands and any manipulated
object were not clearly visible. No owner action reply had arrived by closeout,
so this is an assistant-inspected visible-state check, not owner-labeled intent
or screen-attention validation. The owner's earlier eating label was not reused.

Language NF4 with the unchanged conservative prompt replayed each fresh frame
twice. It consistently claimed looking at a computer screen, at 1.890-2.303 s
when warm. Screen attention is not supported by these images, so these replies
are not counted as correct actionable state observations. Peak RAM was 6160 MB
and system swap 1113 MB. Capture and inference were sequential: no concurrent
live pipeline or end-to-end freshness result was established.

## Disposition and evidence

Retain the isolated model as a fast single-frame research candidate. The tested
standalone caption/multi-image route does not meet reliable Camera Edge state
and process understanding requirements. This check does not establish temporal
memory, screen context, multi-person accuracy, low-light robustness, long-run
stability, camera-to-answer P95, or Runtime acceptance. No further prompt search,
service deployment, or replacement-model trial was started.

All five inference runs loaded with zero missing/unexpected/mismatched keys;
NF4 applied to 168 language linears. Model load was 10.701-11.924 s, measured
separately. First inference ranged from 2.597 to 7.946 s across recipes and was
excluded from warm ranges. No token-limit-hit answer is accepted as completed.
Temporary capture/inference/telemetry processes exited. Existing models,
TinyLLaVA environment, power profile and system PyTorch were retained.

Reproduction data: [asset manifest](evidence/2026-09-12-mobilevlm-v2/asset-manifest.json),
[frame reference](evidence/2026-09-12-mobilevlm-v2/reference.json),
[FP16 raw results](evidence/2026-09-12-mobilevlm-v2/fp16-run/report.json),
[conservative FP16](evidence/2026-09-12-mobilevlm-v2/fp16-conservative/report.json),
[NF4 raw results](evidence/2026-09-12-mobilevlm-v2/nf4-conservative/report.json),
[process failure](evidence/2026-09-12-mobilevlm-v2/fp16-sequence/report.json),
[fresh-frame raw results](evidence/2026-09-12-mobilevlm-v2/nf4-fresh/report.json).
Each successful run includes summary JSON and full-window tegrastats. Raw media
was not added to Git or uploaded to an inference service.


Subsequent owner-authorized work: the [same-frame grounding A/B/C probe](jetson-mobilevlm-grounding-validation.md) completed separately and failed its usefulness gate. This does not change the single-image reproduction measurements above.
