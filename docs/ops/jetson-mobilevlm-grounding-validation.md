# MobileVLM image + same-frame measurement grounding

Date: 2026-09-12. Owner-authorized A/B/C experiment completed; this tested
concatenated-measurement plus rule-filter recipe failed the usefulness gate.
B worsened the measured critical errors; C removed almost all useful output.
This is not acceptance of the earlier failed Isaac ROS user-state route or
Runtime integration. It does not prove all future grounding designs impossible.

## Scope correction and supplementary control

The owner correctly identified that B changed measurement JSON and extra
surrounding prose together. The preceding failure applies only to that full
prompt/filter recipe; it cannot reject direct JSON or all grounded-image
combinations. The [supplementary direct-JSON control](jetson-mobilevlm-direct-json-validation.md)
is now complete with the exact saved measurements and original A text unchanged.
Its targeted count was J=2/8 versus paired A=1/8 and old-B replay=5/8: better
than old B on these images, but not a net improvement over A.
No effect is presumed for the word Fallible or removal of explanatory prose.

## Frozen protocol

- A: image + the conservative prompt from the preceding MobileVLM probe.
- B: identical image, model, prompt body and output budget, plus fallible
  same-frame detection/keypoint measurements and explicit interpretation limits.
- C: exact B response with deterministic per-clause checks; no second model call.

Language NF4 (168 linears), FP16 vision/projector/head, greedy generation,
official v1 template and 48-token ceiling are fixed. The first model inference
and detector/pose warmup are excluded. A/B order alternates, each frame is
replayed twice, and all three backends remain resident. B adds serial low-level
inference and longer prompt processing; its full timer includes saved-frame
decode, measurement, prompt/token/image preparation, generation and text decode.
C adds gate time. No live camera, ROS transport, event waiting or Runtime time
is included; this is not camera-to-answer P95 or continuous-stream acceptance.

The four challenge images are eating at 3 s, greeting A raised at 3.5 s and
hands-down at 7.5 s, plus the fresh low-head frame at 20 s. The four held-out
images are greeting B at 0/3.5/7.5 s and eating at 1.5 s. The latter were not
previously given to MobileVLM or used to tune this prompt/gate. They share the
same room/person/capture sessions, so this is a limited held-out-frame check,
not independent-scene accuracy. Exact references were inspected before model
output and never inserted into the prompt. Replays are not new accuracy cases.

## Actual low-level capability

The original Isaac ROS wrapper exposed detection boxes/confidence but collapsed
pose into counts/coverage/unknown and discarded raw keypoints. The new minimal
wrapper preserves 17 point coordinates/confidences and marks points usable only
at confidence >=0.5 and inside the image. It reuses the same existing
`yolo26n.engine` and `yolo26n-pose.engine`, 640px and detection confidence 0.35,
with ultralytics 8.4.24 and TensorRT 10.7.0. It directly invokes that backend;
the Isaac ROS graph is not running in this fixed-frame comparison.

Frame SHA256 and source PTS bind the same decoded pixels with zero pair skew.
This does not validate live timestamp synchronization. The prompt includes up
to six highest-confidence object boxes and two persons' nose/shoulder/elbow/wrist
measurements; raw evidence preserves all detections/points. No inconvenient
class is filtered out to improve a result. A preliminary measured false `tie`
detection on the hands-down frame confirms this backend is not ground truth.

No grip/contact, gaze-target, intention or temporal-motion measurement exists.
Detection misses do not prove absence; box overlap does not prove holding, and
head pose/screen proximity does not establish screen attention.

## Gate and scoring boundaries

The frozen `grounding-claims-v1` checker withdraws specific unmeasured relations,
temporal actions, unparsed text, misaligned evidence and truncated responses.
It can retain simple posture/expression captions as `image_only_unverified`;
that status explicitly does not mean corroborated or Runtime-admissible. Direct
person-presence wording requires a same-frame person detection for corroboration.

The checker is intentionally bounded, not a general semantic verifier. It can
withdraw correct food/eating/waving claims because independent measurements
cannot corroborate those relations. This loss must be scored, alongside false
claims and all-withdrawn responses. Retaining generic person presence or
returning all unknown is not success. Original text and every withdrawal are
saved separately. Five boundary tests cover misalignment, detection-vs-grip,
non-detection-vs-absence, image-only status and truncation.

Scoring is by unique frame: unsupported specific claims, useful target-state
retention (food/hand action for the action cases, posture for rest cases, low
head/forward lean for the fresh failure), and abstention. Generic seated/person
descriptions do not substitute for food/raised-hand recognition. Static retained
captions are not counted as validated state. Report challenge and held-out
results separately; no statistically meaningful accuracy percentage is implied.

## Results

Eight distinct frames each ran A and B twice (32 model executions after
warmup), with identical text across the repetitions. All weights matched and
168 language linears were quantized. No answer hit the token ceiling.

| Measure | A: image only | B: image + measurement | C: checks on B |
| --- | --- | --- | --- |
| Critical unsupported held-object / computer-relation claims | 1/8 frames | 5/8 frames | 0/8, by withdrawal |
| Useful coarse food/raised-hand information in the four action frames | 4/4 | 2/4 | v1: 0/4; repaired diagnostic: 1/4, image-only unverified |
| Full abstention / all claims withdrawn | 0/8 | 0/8 | v1: 8/8; repaired diagnostic: 7/8 |
| Independently corroborated retained state claims | Not an admission check | Not an admission check | 0 |
| Warm saved-frame processing time | 1.586-2.452 s | 1.684-2.048 s | Original gate adds negligible rule time; not a new VLM pass |

The critical-error metric is limited to the targeted nonexistent held objects
and unestablished computer gaze/spatial relations, not exhaustive accuracy.
Other uncertain expression/gaze details are not all adjudicated. Coarse
raised-hand recognition includes a plausible waving description supported by
the owner's greeting context; it is not process-order correctness. The held-out
set shares source sessions and cannot establish broad generalization.

The critical-error split was challenge A=1/4 versus B=2/4, and held-out A=0/4
versus B=3/4. For food/hand cases, challenge A/B preserved 2/2, while held-out
A preserved 2/2 and B 0/2. No prompt changes were made between splits.

### Exact contrasts

| Frame | A | B | Consequence |
| --- | --- | --- | --- |
| Previously false-remote frame | Smiling / camera-facing | Holding a remote | Adding evidence reintroduces the false object |
| Fresh low-head frame | Looking at computer screen | In front of computer | Changes wording but still lacks visible support; misses low-head state |
| Held-out rest and down frames | Seated descriptions | Holding a remote | Two new false held-object assertions |
| Held-out food frame | Holding food | Holding a phone | Correct food information replaced by a false object |
| Held-out raised hand | Hands up | Holding a hand | Ambiguous, fails useful raised-hand description; not counted as a definite nonexistent-object error |

B did preserve food and raised-hand information in the two challenge action
frames. A post-filter cannot count deleting those correct claims as success.

### Measurement limits and resources

No returned wrist keypoint reached the frozen usable threshold, including the
obvious raised-hand images. The low-head frame yielded no pose. Boxes included
fallible TV and tie detections, but none established grip, food contact or gaze.
Thus the chosen low-level backend did not provide the missing decisive evidence.
The longer numerical prompt may also affect the small model, but this run did
not isolate prompt length/representation as the cause; no causal claim is made.

Detector plus pose measurement took 37.120-48.655 ms, median 47.352 ms, while
co-resident with the VLM. Total median A=1.887 s and B=1.799 s reflects different
answer lengths: A generated 10-16 tokens versus B 8-11. It is not a speedup from
adding measurements. Text-input tokens rose from 87 to 265-797 (excluding
replacement visual tokens). Both backends were serially exercised in one
process, not simultaneously saturated by a 60fps live stream.

Full-window RAM peak was 6593/7620 MB, swap 1075 MB and temperature 58.75 C.
System swap includes pre-existing pages. The model/engine construction phase
was 11.987 s, with further warmup separately recorded. This demonstrates bounded
co-residency, not sustained memory behavior or camera-to-answer P95.

### Gate implementation repair, separately reported

The preserved C-v1 checker was overbroad: `holding their hands up` matched the
held-object rule, and the substring `put` also matched `computer`. After the
frozen result, diagnostic v1.1 added token boundaries, explicitly separated
static hands-up from holding an object, and explicitly withdrew unmeasured
computer spatial relations. The original raw C-v1 evidence was not overwritten.

Rechecking the unchanged B responses on Jetson with v1.1 retained just one
hands-up caption, labeled `image_only_unverified`; seven frames remained fully
withdrawn, and no claim was independently corroborated. This is a post-result
implementation repair, not another untouched held-out validation. It does not
rescue the route. Seven boundary tests now pass. `claims_v1_frozen.py` retains
the original implementation for reproduction.

## Disposition and evidence

Stop this bounded recipe here as failed: direct numeric/box/keypoint prompt
augmentation worsened useful output in the held-out frames, and rule filtering
could only remove almost everything. Preserve the raw evidence and wrapper.
A materially different measurement/representation design would need its own
new test; do not repeat this recipe or claim a solved fast semantic base.
TinyLLaVA stays stopped. No Camera Edge service, Runtime admission or live ROS
stream was started. Temporary inference and telemetry processes exited.

Reproduction: [wrapper](../../experiments/mobilevlm_grounding/README.md).
Evidence: [raw A/B/C-v1](evidence/2026-09-12-mobilevlm-grounding/report.json),
[summary](evidence/2026-09-12-mobilevlm-grounding/summary.json),
[manual assessment and metric limits](evidence/2026-09-12-mobilevlm-grounding/assessment.json),
[pre-inference reference](evidence/2026-09-12-mobilevlm-grounding/reference.json),
[diagnostic gate repair](evidence/2026-09-12-mobilevlm-grounding/diagnostic-gate-v1.1.json).
Raw camera media remains outside Git and no image was sent to a cloud model.
