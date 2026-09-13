# Specialist + ROI-cache + full-image MobileVLM validation

Date: 2026-09-13. Owner-requested next step: multiple specialist models with
MobileVLM V2 unknown-ROI supplementation, followed by MobileVLM V2 for a full
scene description. This experiment tests that exact semantic composition using
causal recorded inputs; it does not add a live second-stage scheduler or accept
Camera Edge / Personal Runtime integration.

Result: the exact tested composition did not establish a net semantic benefit.
It preserved phone recognition and removed some hallucinations, but introduced
other object/gesture errors and propagated wrong or semantically stale ROI
captions. This is a bounded result for the selected prompt/context recipe, not
a verdict against all specialist/VLM combinations or a withdrawal of the earlier
conditional-ROI component's useful phone evidence.

## Results

| Metric | Full image | Image + specialists | Image + specialists + ROI cache |
| --- | ---: | ---: | ---: |
| Phone correctly named | 4/4 | 4/4 | 4/4 |
| Screwdriver correctly named | 0/4 | 0/4 | 0/4 |
| Clear gesture explicitly named | 2/6 | 1/6 | 1/6 |
| Explicit empty-hand confirmation | 0/6 | 0/6 | 0/6 |
| Frames with target error | 5/18 | 5/18 | 6/18 |
| Second-stage inference median | 2.176 s | 1.941 s | 2.083 s |
| Second-stage inference P95 | 3.411 s | 3.610 s | 3.610 s |

Target error means a wrong held-object category, an invented held object on a
clear empty-hand frame, a wrong current gesture, or an unsupported current
hand/held-object claim on a no-visible-hand control. Absence of a target error
is not complete scene correctness. Generic descriptions do not count as exact
identification, and ambiguous background equipment is excluded. The review
retains other unsupported activity claims separately; these counts are not a
general-purpose accuracy estimate.

Among only the seven cache-present cases, adding ROI text to the specialist arm
removed one target error (case 3: pen/writing became generic pink object), added
two (13: generic object became syringe; 15: no hand claim became raised hands),
and left four unchanged under this binary target-error criterion. Case 9 changed
from an unsupported remote claim to an unsupported thumbs-up claim; it remained
wrong. No exact phone/screwdriver or gesture identification improved in this
cache subset.

Material paired examples:

- Cases 4/5: image-only invents a held object/phone on open hands; context arms
  describe raised hands. This is useful partial correction, not confirmed empty hands.
- Case 6: detector candidate `donut` at score 0.432 overrides an available
  `Closed_Fist` observation in the generated description. Image-only says raised
  hand; both context arms say holding a donut.
- Case 8: image-only names the visible V/peace sign; context arms say thumbs-up
  despite current `Victory` and a recent `Thumb_Up -> Victory` transition. The
  input contains the correct state, but the tested prompt does not make the model
  reliably distinguish current observations from history.
- Case 13: ROI text says syringe with needle. Image-only and specialists give
  generic object descriptions; the cascade repeats syringe with needle.
- Case 15: hands are no longer visible; the scheduler still allows a recent
  raised-hands caption during its brief observation-gap tolerance. The cascade
  repeats raised hands. Causal availability and a valid cache key do not prove
  that a caption remains semantically current.

All 18 image/arm pairs matched text across two repeats (54 matched pairs), with
no token-limit truncation. Peak RAM was 6970 MB; swap ranged 907-919 MB including
initialization/warmup. Source hashes, caption availability and no-cache prompt
identity checks passed. All experiment processes ended. The first-stage ROI
cost is excluded; these second-stage timings cannot be advertised as complete
pipeline latency or used to claim the five-second event-label target is met.

## Setup and frozen comparison

The first stage is the existing trained gesture/detection/ROI-classification
stack plus [asynchronous ROI cache](jetson-roi-singleflight-validation.md).
Eighteen timestamps were declared before second-stage generation on the same
approximately 90 s owner recording. Each input uses the latest prior replay
observation and its corresponding full frame. Seven inputs have a valid cached
ROI description already returned at that timestamp; later replies are excluded.
The remaining eleven inputs contain no ROI caption. Incorrect captions are
preserved as uncertain candidates, not corrected with reference labels.

Three arms share the full image, model weights/precision, greedy 48-token limit
and question: `Describe what the person is visibly doing and any object visibly
held, in one short sentence.`

| Arm | Second-stage input |
| --- | --- |
| image | Full image and question |
| specialists | Full image, gated hand-object candidates, stable gesture, detected objects, preceding 4 s gesture transitions and question |
| cascade | Same as specialists, plus available ROI caption with age and unverified status |

Both context arms have the identical instruction to check uncertain candidates
against the image. Low-score object classifications are represented as unknown;
high-score candidates are retained. Object/hand box overlap is only a candidate
relation. No-cache specialists/cascade prompts are byte-identical. The comparison
between those arms on the seven cache-present frames isolates added ROI text;
image versus context also changes the uncertainty instruction and JSON length,
so it cannot establish the value of every possible grounding prompt recipe.

Each arm runs twice on every frame, with cyclic arm order: 108 formal generations.
Model/context loading and one full-image warmup are excluded from timings.
The same pinned language-NF4, FP16 vision/projector/head MobileVLM loader and
resident specialist contexts are reused. First-stage computations are cached;
only the second-stage VLM runs during this benchmark. Thus stage-one contention,
queueing and complete event-to-answer latency are not measured. No model or
environment installation was performed.

## Visual reference and interpretation

Before generation, the 18-frame contact sheet was visually reviewed with the
owner's prior phone/screwdriver labels. Reference labels and scoring criteria
were saved separately and never included in prompts. The cases comprise eight
object frames (four phone and four screwdriver), six clear empty-hand gesture
frames (three palms, fist, thumb-up, V), and four no-visible-hand controls.
No-visible-hand is not a confirmed empty-hand label. A still image does not
establish waving, greeting intent or an ordered action sequence.

Scoring distinguishes exact held-object identification, explicit gesture naming,
explicit empty-hand confirmation, target errors and other unsupported scene or
activity claims. Generic object/hand descriptions are retained as partial
information, not counted as exact identification. Clothing color is excluded
because projector illumination varies. References and scoring use one reviewer
on reused development material; deterministic repeats are not independent
accuracy samples.

## Reproduction and evidence

- [Input manifest](evidence/2026-09-13-specialist-context/manifest.json) records
  image hashes, exact candidates, cache ages and source-report hashes.
- [Frozen reference](evidence/2026-09-13-specialist-context/reference.json).
- [Raw prompts, replies and timings](evidence/2026-09-13-specialist-context/report.json).
- [Manual review](evidence/2026-09-13-specialist-context/review.json) and
  [recomputed metrics](evidence/2026-09-13-specialist-context/summary.json).
- [Source and commands](../../experiments/specialist_context/README.md).

Full images stay on the Jetson under
`/home/jetson/openhalo-specialist-context/inputs-v1/media/`; no new recording or
raw image egress to a hosted model was performed. Runtime outputs are in
`/home/jetson/openhalo-specialist-context/run-v1`. The local inspection contact
sheet is outside the repository. The summarizer verifies archived source bytes,
causal caption availability, prompt identity for no-cache cases and repeat text.
