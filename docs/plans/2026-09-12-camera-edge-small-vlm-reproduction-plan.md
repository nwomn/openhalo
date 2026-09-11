# Camera Edge Small-VLM Reproduction Plan

Status: research and reproduction candidates only. No model in this document
is accepted as a Camera Edge implementation, and no candidate connects to
Personal Runtime until it passes the existing Observation and evidence gates.

## Research question

Can a continuously running Isaac ROS fast path plus a small visual-language
model provide useful event and world-state understanding on the Jetson Orin
Nano Super 8GB, while meeting bounded latency, memory, thermal, and energy
budgets?

The experiment is about deployment and system design. The use of a known model
or a standard quantizer is not itself a novelty claim.

## Candidate baselines

| Candidate | Relevant property | Reproduction reference |
| --- | --- | --- |
| MobileVLM 1.4B / 2.7B | Mobile-oriented VLM; the paper reports Jetson Orin inference measurements | [paper](https://arxiv.org/abs/2312.16886), [code](https://github.com/Meituan-AutoML/MobileVLM) |
| MobileVLM V2 1.7B / 3B | Improved small-model baseline and training recipe | [paper](https://arxiv.org/abs/2402.03766), [code](https://github.com/Meituan-AutoML/MobileVLM) |
| TinyLLaVA 3.1B | Small-scale LMM design-space baseline across vision encoder, connector, language model, and data | [paper](https://arxiv.org/abs/2402.14289) |
| TinyLLaVA-Video approximately 3.6B | Video-level group resampler for reducing temporal visual-token redundancy | [paper](https://arxiv.org/abs/2501.15513), [code](https://github.com/ZhangXJ199/TinyLLaVA-Video) |
| Existing Mage-VL Q4_K_M + Q8 projector | OpenHalo's current real-camera and continuous-stream reference path | [validation](../ops/jetson-mage-vl-validation.md) |

The first pass must record whether each candidate has a usable ARM64/CUDA or
llama.cpp/TensorRT path. A paper-level model result is not treated as a local
deployment result until the exact weights, projector, tokenizer, runtime, and
hardware are recorded.

## Architecture reference: edgeVLM

[edgeVLM](https://arxiv.org/abs/2508.12638) is a reference for a cloud-edge
context-transfer design. Its useful idea for OpenHalo is to treat delayed,
high-quality model output as historical context that can guide a faster small
model, instead of waiting for the large model on every request.

The OpenHalo mapping is:

```text
Isaac ROS detector/tracker/temporal features
  -> fast local state and change signals
  -> bounded ROI/event window
  -> local small VLM or delayed Mage-VL result
  -> structured, uncertainty-bearing world-state candidate
  -> ordinary Edge Observation and later Runtime admission
```

This is a research reference, not permission to let model prose bypass the
existing Gateway, ContextFact, evidence, or Presence boundaries.

## Quantization study

[Rethinking Small VLM Quantization](https://arxiv.org/abs/2607.08029) is the
reference for separating the visual encoder, projector, and language backbone
when measuring edge performance. The reproduction matrix should vary these
components independently where the runtime permits:

- language backbone: FP16, Q8, Q6, and Q4 where available;
- projector: FP16 and Q8 first, then lower precision only if supported;
- vision encoder: its native precision versus an INT8 or TensorRT variant;
- input: fixed resolution, fixed crop policy, fixed visual-token budget, and
  fixed output-token budget.

Each cell records cold-start and resident-process behavior separately:

- model load time, first-token latency, steady-state token rate, and
  event-to-result P50/P95;
- peak and steady RAM, swap, GPU utilization, temperature, and power when
  available;
- structured-output validity, semantic correctness, unsupported-claim rate,
  and `unknown` behavior;
- model invocation count, visual-token count, retained evidence bytes, and
  raw-media egress.

INT4 is therefore a memory variable, not an assumed latency improvement.

## Fair reproduction protocol

1. Start with a fixed, owner-labeled image and short-event corpus. Do not use
   changing live input for the first model comparison.
2. Keep resolution, crop, prompt, schema, seed, temperature, context length,
   output limit, and warmup policy fixed across candidates.
3. Compare an always-on VLM baseline with the event-triggered hybrid path.
4. Run resident-process tests long enough to expose thermal throttling,
   allocator growth, cache effects, and recovery behavior.
5. Keep model output as local evaluation evidence until a candidate passes the
   normal Camera Edge contract and Runtime admission tests.

## Initial comparison groups

- `fast-only`: Isaac ROS structured features without VLM reasoning;
- `vlm-only`: periodic full-frame VLM requests;
- `event-vlm`: Isaac ROS change/ROI selection followed by a VLM request;
- `event-vlm-context`: event VLM plus bounded temporal/context transfer;
- `event-vlm-quantized`: the best latency/quality point from the component
  quantization matrix.

The acceptance target remains the v2 design target of event-label completion at
P95 <= 5 seconds. This plan does not change that target or accept the current
Mage-VL 14-16 second continuous delay as real-time behavior.
