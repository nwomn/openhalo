# Mage-VL historical-run audit

Later the same day, the owner authorized a resident retest, now
[completed with full-frame and real codec-bit-cost profiles](jetson-mage-vl-retest-20260914.md).
The following audit remains the record of what the earlier runs established.

2026-09-14. The owner retains Qwen3-VL as the preferred tested combination and
questions whether the earlier Mage-VL numbers represent a correct run. This
audit rereads the retained Jetson source and raw logs; it does not start a new
model, camera session, download or rebuild.

**Finding: native image and streaming execution occurred, but the retained
measurements do not establish a fair model-only comparison with the current
Qwen3-VL benchmark, or a faithful end-to-end reproduction of the official
proactive recipe.** Keep the owner's earlier rejection of the tested live
implementation. Do not generalize that rejection to all Mage-VL deployments.

## What did run

The current Jetson checkout still reports author revision
`f0df1fe6f13095a359ff38c7749279d5d6a8c60f` and llama.cpp base
`a52077c4cabb4f3c0298329c9d2dd1324d5604cb`. The recorded Q4_K_M backbone and
Q8 projector paths agree with the retained assets and historical integrity
checks. Native source loads the backbone, vision encoder, EPFE and classifier
on GPU; stream logs record timestamped vision tokens, logits and real answers.
This is not evidence of a silently substituted text-only or CPU-only run.

The Jetson CUDA patch adds explicit F32/F16-to-F32 binary-operation dispatch
instead of treating the F16 operand as float. Its intent matches the observed
type/assertion failure. A successful build and inference do not establish
numerical parity with Microsoft's implementation: no retained full-model
reference-logit/embedding comparison was found in the inspected artifacts.

The single-image synthetic raw command uses GPU offload, context 1024, maximum
80 output tokens, `--no-warmup` and `--image-max-tokens 196`. Its 9.9977-second
wall time measures process invocation including model loading. Earlier
8–16-second single-image numbers are not resident inference latencies. The
input was also not the later hand-gesture recording used for Qwen.

## Live latency was an end-to-end proxy

Audited run: `/home/jetson/mage-vl-live-genctx-20260911-113517`.
It has 15 submitted groups (indices 0–14), 14 completed responses and 56 gate
rows. The bounded launcher exits 124; the final submitted group has no answer.

| Metric from retained raw data | Minimum | Median | Maximum |
| --- | ---: | ---: | ---: |
| Native total | 4.046 s | 4.125 s | 5.740 s |
| Submit to response | 4.047 s | 4.126 s | 5.744 s |
| Displayed live-delay metric | 14.090 s | 15.036 s | 16.238 s |
| Submit elapsed minus nominal source end | 8.346 s | 10.871 s | 12.191 s |
| Generation stage, including new context/prefill | 2.079 s | 2.142 s | 3.220 s |

Median stage measurements: vision 1.897 s, EPFE 6.20 ms, classifier 24.53 ms.
The first nominal four-second group was submitted at elapsed 12.346 s and
answered at 18.090 s: the displayed delay was 18.090 minus 4 = 14.090 s.
It is incorrect to label all 14.090 s as model inference.

The wrapper's delay is `elapsed_since_producer_launch - source_end_seconds`;
the producer derives source time from sampled-frame index divided by requested
FPS. It runs ffprobe before starting FFmpeg. This is not camera-PTS/monotonic
clock alignment. Startup, probing, buffering, preprocessing, backlog and time
origin mismatch are not independently instrumented. Therefore the residual
8.35–12.19 s cannot be attributed wholly to any one of them, nor treated as
precisely measured real-world action latency. Subtracting it does not prove
that an improved live pipeline will deliver four-second action feedback.

## Triggering was forced, not validated

The retained Demo launcher requests `--threshold 0.0`,
`--interval-segments 1`, 1 sampled FPS, four minimum frames per group,
`--readiness-threshold 0`, `--max-pixels 262144`, and only 16 output tokens.
All audited groups have four samples, approximately 672x384 canvases and 1008
visual tokens per group. This is not the current 480p/16-frame/96-token Qwen
task. The tiny output cap does not provide a complete-action-description test.

Every observed gate probability is below the default 0.5:
range 0.00001198274–0.01589111, zero of 56 above 0.5. Yet logs say `speak`
because native code compares probabilities against the configured zero
threshold. Periodic generation is separately enabled. Under an unchanged
default gate with periodic generation disabled, these observed scores would
not trigger descriptions. These statements concern the observed logits, not
an unperformed alternate live run or proof that the gate is broken.

The outputs include nine `no change`/`no changes`, two `None`, and three short
scene/action phrases. No synchronized retained scene reference was scored in
this audit. Such output is not proof of successful event detection or temporal
understanding; routine-scene silence may also be appropriate.

## Streaming state and preprocessing differ from the broad promise

Native `generate_shared` creates and frees a new language context for every
trigger, evaluates only the current group's chunks and cached vision embeddings,
then greedily generates at most the configured cap. Model weights remain
resident and vision embeddings are shared between gate and generation, but
the generation context and prior answers are not carried across groups. EPFE
is recurrent across groups; its state feeds the classifier, not the decoder's
past dialogue. Thus the old runner does not demonstrate cross-window narrative
memory merely because it contains a stateful StreamMind gate.

The incremental producer also uses decoded-frame absolute pixel differences as
a proxy for codec importance, followed by four-canvas patch packing with source
positions. It is not a bit-exact implementation of official codec-derived
motion/residual or neural rate-map selection. At just four source frames for
four canvases, this test does not demonstrate the advertised many-frame token
compression benefit. The official model describes codec-aware token selection
and event-gated generation; the community runner is a separate implementation.
[Microsoft model description](https://huggingface.co/microsoft/Mage-VL),
[community runtime](https://github.com/JohnTDI-cpu/mage-vl-gguf).

The wrapper permits only one group in native inference at a time, but while
waiting it does not drain producer events. The incremental producer can keep
writing bundle files until pipe backpressure occurs. `pending_segments=0` is
hard-coded in this path; stale-drop options are used in the separate segmented
path. Those logs do not prove bounded end-to-end backlog or gap-free real-time
consumption.

## Corrected disposition and next discriminating test

The earlier conclusion remains valid for the owner's observed experience:
that concrete low-resolution forced-commentary Demo was not satisfactory.
The stronger claim that Mage-VL itself needs 14–16 seconds or is intrinsically
worse than Qwen3-VL is not supported by these mixed measurements.

A useful later retest is the same retained gesture/phone/tool recording with
the current neutral prompt and 96-token complete-answer cap, explicit checked
frame/timestamp/token mapping, resident model timing separated from cold load,
and direct generation without the proactive gate/UDP capture wrapper. Keep
Mage's own preprocessing recorded; a 16-frame target must not be silently
reduced to four samples or assumed memory-feasible. Only after this establishes
model usefulness should a separate default-gate/forced-generation and capture
latency experiment be considered. This audit authorizes no new route acceptance
and makes no new Mage latency or quality prediction.

[Archived audit inputs and arithmetic](evidence/2026-09-14-mage-vl-audit/).
Earlier [validation record](jetson-mage-vl-validation.md) remains historical.
