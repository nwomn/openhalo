# Camera Edge Small-VLM Reproduction Plan

Status: research and reproduction candidates only. No model in this document
is accepted as a Camera Edge implementation, and no candidate connects to
Personal Runtime until it passes the existing Observation and evidence gates.

## Owner-confirmed next validation order

The owner explicitly corrected the next-route order after the direct-JSON
supplement. The earlier suggestion to advance the specialist-plus-MobileVLM
combination first is superseded. Route 1 now has a completed bounded specialist/temporal probe: a new one-minute
owner recording yielded three wave detections, while old-clip misses/fragmentation
and missing raise/lower and daily semantics still fail full Camera Edge usefulness.
Live P95 and Runtime remain unaccepted. The later [trained specialist expansion](../ops/jetson-specialist-expanded-validation.md) adds useful bounded static gesture categories, while the tested hand-ROI object classifier fails phone/screwdriver/empty-hand checks. These are concrete component results; the wider multi-specialist route remains incompletely tested. See the [initial geometric result](../ops/jetson-specialist-temporal-validation.md).
Route 2 now has a first [conditional ROI fallback replay](../ops/jetson-mobilevlm-roi-fallback-validation.md), following the owner's explicit unknown-trigger clarification. Neutral-prompt phone ROI results are useful in selected frames, but screwdriver errors, high-score bypass and continuous scheduling remain unresolved; the route is not accepted. The initial scheduling update
started no device experiment; the subsequent explicit request authorized route 1.

| Order | Route | Independent question | Evaluation boundary |
| --- | --- | --- | --- |
| 1 — bounded probe complete, not accepted | Multiple task-specific small models + temporal fusion | Can specialist observations independently support continuous state and action-change understanding? | No MobileVLM or other VLM semantic stage in this experiment |
| 2 — bounded ROI fallback replay complete, not accepted | Multiple task-specific small models + MobileVLM V2 | Do specialist observations improve image-based semantic understanding over the image-only baseline? | Begin after route 1 has its own recorded result; retain original image input and compare added value separately |

### Route 1: independent specialist and temporal validation

Select concrete specialists only after checking their available observations
and suitability for the known failure cases. The existing all-unknown
Isaac ROS semantic route is not an accepted base, and model/box execution is
not useful-state acceptance. Identify the material change from that failed
recipe before implementation; do not repeat it under a new ensemble name.

Use time-aligned specialist outputs with explicit observation quality and track
continuity, then fuse them over time into bounded states and action changes.
Record raw observations, state/event transitions and failures independently.
Evaluate state persistence, action onset/end/order, track loss/recovery and
misassociation, useful information retained, false transitions, abstention,
and full event-to-result delay/resource use. A stream of `unknown`, a sequence
of isolated boxes, or merely smooth tracks does not pass. The five-second
P95 event-label target remains unchanged; a small replay alone cannot establish
that P95 or sustained live reliability. Model choices and scheduling budgets
remain to be verified, not newly accepted by this order update.

### Route 2: later specialist-plus-image-VLM comparison

Owner disposition after the first conditional ROI replay: retain this combination
as valuable for further validation. The positive bounded phone/hand-description
results do not resolve screwdriver recognition, high-score bypass, structured
empty-hand output or continuous scheduling/live latency; no route acceptance.

Use the independently characterized specialist observations from route 1
without upgrading uncertain outputs into truth. Retain MobileVLM's image input.
Freeze and compare image-only versus image-plus-observation inputs, with added
wording and output validation treated as separate experimental variables where
needed. Measure unsupported claims, useful semantics retained, abstention and
co-resident end-to-end latency/memory. Preserve raw outputs before any filter.
This route is not mixed into route 1 and is not assumed useful from the previous
JSON-control results. Neither route changes Runtime admission or restarts
TinyLLaVA.

## Earlier reproduction history

2026-09-12 execution update: the owner selected TinyLLaVA-Video first, then
MobileVLM V2 as the low-latency comparison, with multi-specialist fusion later.
The initial TinyLLaVA check is now complete: its best tested Jetson recipe
described eating correctly on one owner-referenced clip but took 8.97-9.21 s
when warmed, with significant memory/swap pressure. The current recipe fails
minimum usability; no replacement route is accepted. See the
[validation report](../ops/jetson-tinyllava-video-validation.md).

MobileVLM V2 1.7B comparison is now complete. Conservative single-frame FP16
replies took 0.757-1.151 s; language NF4 took 1.399-1.789 s with lower memory
pressure on selected retained images. Fresh low-head frames still produced
unsupported screen-attention claims, and the two/four-image process probe
failed ordering. Keep it only as a fast single-frame research candidate; the
tested standalone route is not accepted. See the
[MobileVLM report](../ops/jetson-mobilevlm-v2-validation.md).

Owner closeout, 2026-09-12: the tested Qwen2.5-VL 3B, Mage-VL/StreamMind,
Isaac ROS feature, and Isaac ROS temporal-feature-to-small-LLM routes failed
minimum usability. The owner already tested the proposed real-scene cases and
reports all relevant state/semantic outputs as `unknown`. Existing Isaac ROS
components are therefore not an accepted semantic fast path, and Mage-VL is a
failed-usability comparison baseline. The combinations below are hypotheses,
not selected replacements. Any reproduction must identify a concrete change
addressing the known latency/semantic failure and evaluate useful outputs on
the tested scenarios, rather than counting `unknown` or execution alone as
success or requesting the same unchanged scene tests again by default.

## Grounding prompt controls: tested recipes only

The original B combined JSON and extra explanatory wording. The subsequently
authorized direct-JSON J control is now complete on the same eight replayed
frames: targeted errors A=1/8, J=2/8, B=5/8. J removes several old-B errors but
still invents screen attention and a held remote on food imagery. It has not
shown a net benefit over A. Keep this conclusion scoped to the exact recipes;
it does not reject every low-level/image combination or identify a single word
as the cause. No new holdout or Runtime acceptance follows.
[Complete supplementary prompts/results](../ops/jetson-mobilevlm-direct-json-validation.md).

### Original explained-JSON recipe

The authorized first recipe completed its A/B/C test. Adding fallible numeric
measurements increased targeted false-object/computer claims from 1/8 to 5/8;
held-out food/hand information was lost. The repaired output gate still withdrew
all claims on 7/8 frames and independently corroborated none. It is not accepted
and no unchanged rerun is scheduled. This is the tested concatenation/filter
recipe's failure, not a universal conclusion about grounded VLM systems.
[Full evidence](../ops/jetson-mobilevlm-grounding-validation.md).

### Preserved protocol

The owner authorized a bounded A/B/C comparison on 2026-09-12. A uses the
image and one fixed conservative prompt; B adds same-frame, uncertainty-bearing
boxes/keypoints from the existing TensorRT measurement backend; C validates
individual claims in the exact B response. It never replaces image input with
numeric-only small-LLM interpretation. Full-ROS live admission is not part of
the fixed-frame probe. Keep the prior all-unknown semantic failure unchanged.

Freeze the prompt, 48-token ceiling, language NF4 and gate rules before held-out
inference. Retain raw responses and withdrawn claims, and measure unsupported
claims, useful-state retention, abstention, serial co-resident latency and RAM.
Detection misses cannot prove absence; proximity cannot prove holding or gaze.
An all-unknown or information-empty output does not pass. No Runtime work.

## Research question

First, can multiple task-specific small models plus temporal fusion provide
useful continuous state and action-change understanding on Jetson Orin Nano
Super 8GB within the latency/resource budget, independently of a VLM? Later,
does combining those specialist observations with MobileVLM V2 improve image
semantics enough to justify its additional cost?

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

## Later-stage architecture reference: edgeVLM

[edgeVLM](https://arxiv.org/abs/2508.12638) is a reference for a cloud-edge
context-transfer design. Its useful idea for OpenHalo is to treat delayed,
high-quality model output as historical context that can guide a faster small
model, instead of waiting for the large model on every request.

The following mapping is a later-stage research reference, not the next
independent specialist/temporal experiment:

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

## VLM comparison protocol (route 2 only)

1. Start with a fixed, owner-labeled image and short-event corpus. Do not use
   changing live input for the first model comparison.
2. Keep resolution, crop, prompt, schema, seed, temperature, context length,
   output limit, and warmup policy fixed across candidates.
3. Compare an always-on VLM baseline with the event-triggered hybrid path.
4. Run resident-process tests long enough to expose thermal throttling,
   allocator growth, cache effects, and recovery behavior.
5. Keep model output as local evaluation evidence until a candidate passes the
   normal Camera Edge contract and Runtime admission tests.

## Later VLM comparison groups (route 2 only)

- `specialist-only`: the separately measured route-1 result, with its actual
  uncertainties preserved rather than assuming a validated Isaac ROS fast path;
- `vlm-only`: periodic full-frame VLM requests;
- `event-vlm`: Isaac ROS change/ROI selection followed by a VLM request;
- `event-vlm-context`: event VLM plus bounded temporal/context transfer;
- `event-vlm-quantized`: the best latency/quality point from the component
  quantization matrix.

The acceptance target remains the v2 design target of event-label completion at
P95 <= 5 seconds. This plan does not change that target or accept the current
Mage-VL 14-16 second continuous delay as real-time behavior.
