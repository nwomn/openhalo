# Qwen3-VL-2B-Instruct model-only Jetson comparison

2026-09-13. Owner selected this candidate after retaining Cosmos Edge2-FlashHead
as worth trying while seeking better alternatives. Same supplied recording,
neutral prompt, frozen chronological clip intervals and model-only scope.

## Artifact and runtime

- Base model: [Qwen/Qwen3-VL-2B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct).
- Tested artifact: community [cyankiwi AWQ-4bit](https://huggingface.co/cyankiwi/Qwen3-VL-2B-Instruct-AWQ-4bit),
  revision `db40a251bdba88fafabf8f3176e7488ed523ab51`.
  The 2,229,344,344-byte safetensors file matches upstream SHA256
  `d93e72c830fddcfc872bbeb37b60c99815b6e3add8af4bf6dd6b75a41724e646`.
  AWQ recipe uses symmetric INT4 group size 32 on language linear layers,
  leaving vision, embeddings and LM head unquantized; runtime format is
  compressed-tensors. This probe does not isolate quantization quality loss.
- Jetson Orin Nano Super: L4T 36.4.3, 7619 MiB RAM, existing 8 GiB SSD swap.
  The previous temporary desktop/Argus/Ollama stop and ZRAM-off state remains;
  OpenClaw is retained. Initial available memory 4834 MiB, root disk about 12 GiB.
- Separate container `openhalo-qwen3-vl-probe-20260913`, NVIDIA vLLM image
  `sha256:15b41320647ebbaa4547b96bbb027d4816e8cb1ee018fda3ebaba1c8056291ed`;
  PyTorch 2.9.1, Transformers 4.57.6, vLLM 0.14.0, compressed-tensors 0.13.0.
  No FlashHead or TensorRT Edge-LLM. No OS upgrade or prior model deletion.
- Preserved upstream files and made a separate symlinked runtime model directory.
  Converted only Transformers 5 RoPE schema to the installed 4.57.6 schema:
  `rope_parameters` becomes `rope_theta=5000000` and `rope_scaling` with
  interleaved MRoPE and section `[24,20,20]`; assertions verify preserved values.
  No checkpoint code or recipe YAML is executed.

## Protocol and limits

The [runner](../../experiments/qwen3_vl_video/README.md) reuses the Cosmos neutral
prompt and 13 frozen clips. Widths 832 and 1280, original aspect ratio, up to
12 uniformly sampled frames over the complete interval with explicit timestamps
and further HF frame sampling disabled. Same engine uses BF16 activations,
INT4 language weights, context 6144, fixed 768 MiB KV, prefill 2048, one sequence,
greedy decoding and 96-token cap. Processor/prefix caching is off. Warm-up once
per resolution; one formal request per case/resolution in the initial replay.

Timing includes reading, decoding and resizing the pre-extracted local clip,
model preprocessing and inference until return. It excludes model initialization,
previous clip extraction, live capture and Runtime. A truncated reply does not
count as a complete answer, regardless of elapsed time. Input hashes, frame
indices, actual visual tokens and model prompt timestamps must be checked before
comparing with the five matched Cosmos resolution cases.

The reused recording contains palm/fist/thumb-up/V, phone, screwdriver and
lowering/empty-hand transitions. It does not cover mouse or a confirmed greeting
wave. Repeated or selected clips do not establish fresh-video generalization,
long-running audiovisual responsiveness or Camera Edge acceptance. Existing
TensorRT Edge-LLM research timing is a different runtime and workload.

## Initial greedy replay

All 26 formal requests (13 clips at each resolution) stopped naturally without
OOM or token-cap truncation. This is one request per clip/resolution, not a
repeatability or P95 test. Actual input sizes are 6–12 frames; the longer action
clips have 12. The five matched Cosmos cases passed exact checks for clip SHA256,
decoded shape, frame metadata, visual-token count and actual prompt timestamps.
Twelve-frame inputs produce 2340 visual tokens at ~480p and 5280 at 720p.

| Input | Complete replies | Minimum–maximum | Median | Within 8 s / 10 s |
| --- | --- | --- | --- | --- |
| ~480p, 6–12 frames | 13/13 | 1.600–3.788 s | 3.270 s | 13/13 / 13/13 |
| 720p, 6–12 frames | 13/13 | 3.421–8.003 s | 6.739 s | 12/13 / 13/13 |

These are completed-answer timing counts, not semantic pass counts.

| Reference case | Observed semantic result |
| --- | --- |
| Phone front/back (c01/c07) | Correct object at both resolutions; initial Cosmos phone-front repetition was absent in this run. |
| Screwdriver (c02/c08) | Correct object at both resolutions; c02 still wrongly describes the state as unchanged and misses lowering. |
| Palm/fist/thumb/V (c03–c06) | Names the gesture, but repeatedly adds a false/contradictory non-empty-hand claim. 480p c06 invents both hands making V; 720p names one visible hand. |
| Empty palm (c09) | 480p correctly says no object; 720p says the hand is not empty. |
| Palm → fist → thumb → V (c10) | Both resolutions retain the broad order and stop, unlike the matched Cosmos 720p truncated reply; both call the initial palm four fingers. Not a fully correct detailed account. |
| Phone raise/show/lower (c11) | Both recognize raising/lowering but infer placing it down and visibly empty hands after it leaves view. Ending-state evidence remains insufficient. |
| Screwdriver → empty palm → lower (c12) | Both conflate sequential states with screwdriver in one hand and palm in another; 720p implies lowering makes the hand empty. |
| Hands out of view (c13) | Both refrain from naming a held object or confirming empty hands. |

Compared with the matched Cosmos cases, this recipe completes more consistently
and retains the broad gesture order at 720p. It does not establish superior overall
semantic reliability: empty-hand contradictions and object-transition errors
remain. This applies to the tested quantized artifact and prompt/decoding recipe.

## Recommended-decoding control

Because greedy decoding produced systematic empty-hand wording failures, an
additional 720p control replays c03, c06, c09, c10, c11, c12 and c13 using the
Qwen model card's visual-generation settings: temperature 0.7, top-p 0.8, top-k 20,
presence penalty 1.5 and repetition penalty 1.0, with seed 0. The neutral prompt,
inputs, engine configuration and 96-token cap remain fixed. These are deliberately
selected follow-up cases, not an independent holdout or multi-seed estimate.
All seven formal control replies stopped naturally in 3.739–7.881 s (median
6.586 s), without OOM or truncation. All seven input pairs exactly match the
greedy run. The c03/c06/c09 non-empty-hand contradictions disappear; c09 now
correctly states that no object is held. However, c03 still misses lowering and
adds a possible signalling intention, c10 still says four initial fingers,
c11 replaces a false empty-hand ending with an unsupported held-throughout
claim, and c12 still invents different hands for sequential object/palm states.
This shows a decoding-sensitive wording problem, not a solved temporal task.

## Disposition, resources and retained evidence

**Retain as another trial/comparison candidate: it meets the model-level latency
screen in these runs, but has not demonstrated a reliable semantic replacement
for Cosmos.** Recommended decoding is worth carrying into further comparisons
because it improved the selected empty-hand failures; independent inputs and
multiple seeds are needed before treating this as a robust improvement.

Formal-window telemetry: initial run RAM peak 7401/7620 MB, SSD swap
1176–2039 MB, maximum reported junction temperature 75.0 C; decoding control
RAM peak 7448/7620 MB, SSD swap 703–1725 MB, maximum junction 74.187 C.
Memory headroom remains small in this temporary model-only host configuration.
These short tests do not establish sustained thermal, memory or live P95 behavior.

All inference, telemetry and the temporary loopback download proxy are stopped.
The Qwen container, downloaded weights and prior Cosmos environment are retained.
Final available RAM was 5117 MiB; root disk about 9.2 GiB free. Previous temporary
service/ZRAM settings remain as documented in the
[Cosmos cleanup report](jetson-cosmos-memory-resolution-followup.md).

[Evidence bundle](evidence/2026-09-13-qwen3-vl/) preserves raw answers, configs,
runtime logs, telemetry, source hashes and summary/input checks. The recording,
sampled images and weights are kept outside Git. No media was uploaded for
external inference, no new capture occurred, and no Runtime acceptance changed.
