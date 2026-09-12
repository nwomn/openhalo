# Jetson unknown ROI asynchronous deduplication validation

Date: 2026-09-12. Scope: owner-authorized isolated scheduling experiment,
following the [conditional ROI probe](jetson-mobilevlm-roi-fallback-validation.md).
This is recorded-video replay with actual MobileVLM calls. It does not accept
Camera Edge, live event-label P95, object identity, or Personal Runtime integration.

## Implemented contract

- One MobileVLM request can run at a time. Further observations replace the
  latest candidate; they do not enter a FIFO request queue.
- The candidate key is an anonymous local hand continuity epoch plus appearance
  revision. It is not a recognized object class or person identity. Hands are
  associated by maximum bounding-box IoU; IoU below 0.1 or a gap over 0.65 s starts
  a new epoch. At most one hand candidate is selected per sampled frame.
- Object classifier top-1 score below 0.7 means unknown. Gesture uncertainty
  does not trigger this worker; high-confidence classification errors still bypass it.
- A reply can enter the cache only if its key remains current, a supporting
  observation is at most 0.65 s old, and the request is at most 5 s old.
- Completed nonempty captions without token truncation or literal unknown/unclear
  are cached for up to 10 s. Cache status is `unverified_model_caption`:
  `accepted=true` in the raw report means accepted by the scheduler, not correct.
- Unusable replies have a 2/4/8 s capped retry cooldown. A changed candidate
  invalidates the cache and resets the cooldown. Old in-flight work still occupies
  the backend until completion; it is then discarded before the latest candidate
  can run. The 5 s age gate is not cancellation or recovery from a hung worker.

## Controlled comparison

Both runs replay the same approximately 90 s recording and 416 cached specialist
observations at their original wall-clock offsets. Of these, 146 selected hand
observations have object score below 0.7. That count is the hypothetical
one-call-per-selected-unknown-frame baseline, not an actually executed 146-call
VLM experiment. Both runs retain real model generation, video ROI decoding,
single-worker scheduling and resource sampling.

The existing language-NF4 MobileVLM stack, FP16 vision/projector/head, prompt
`Describe this image briefly.`, greedy 48-token generation, and all scheduler
settings remain fixed. Gesture/detector/classifier contexts are resident and
warmed, but their observations are cached; their continuous GPU workload is
absent. One full-image warmup is excluded from request counts and latency.

V1 compares blurred 16x16 RGB ROI pixels against the revision anchor using mean
absolute distance >=0.12. Its 20 actual requests all became stale before use.
This is a preserved failed appearance recipe, despite reducing dispatch count.

V2 changes only the appearance comparison to an L1-normalized HSV histogram
(8x4x4 bins), Bhattacharyya distance >=0.35 against the revision anchor. This
diagnostic threshold was chosen before that run; no threshold sweep was run.
V2 is an adaptive same-recording ablation, not a fresh accuracy holdout.

## Results

| Measurement | V1 pixel comparison | V2 histogram comparison |
| --- | ---: | ---: |
| Selected unknown observations | 146 | 146 |
| Actual VLM requests | 20 | 15 |
| Reduction vs per-observation dispatch | 86.3% | 89.7% |
| Maximum in-flight requests | 1 | 1 |
| Captions admitted to unverified cache | 0 | 7 |
| Cache-reuse events | 0 | 41 |
| Stale replies discarded | 20 | 8 |
| Model reply median / P95 | 2.038 / 2.288 s | 2.055 / 2.265 s |
| Maximum replay lag | 0.134 s | 0.156 s |
| RAM peak | 6857 MB | 6835 MB |
| Swap observed range | 903-1024 MB | 912-1015 MB |

The requested non-repeating in-flight behavior works in both real-worker
replays. V2 also demonstrates cache reuse with continuous observations. The
114 pending-suppression events and 41 cache events in V2 include short periods
holding a recent observation between detections; they are not distinct input
frames and should not be added to the 146-frame baseline.

Seven cached captions are not seven correct classifications. In V2, request 10
(37.88 s source frame) names a cell phone but also mentions a projector; request
12 (45.24 s) incorrectly calls the screwdriver a syringe with a needle. Request
14 (51.52 s) describes raised hands without establishing a confirmed empty-hand
state. All raw text is retained. No semantic accuracy improvement is established
by this scheduling experiment.

All eight synthetic scheduler tests passed. Recorded request intervals confirm
no backend overlap, and source hashes matched. Both replay jobs ended; no
background service, model installation, camera capture or Runtime change was made.
Resource logs include initialization/warmup, while request timing excludes them.

## Evidence and reproduction

- [Raw v1](evidence/2026-09-12-roi-singleflight/run-v1.json),
  [raw v2](evidence/2026-09-12-roi-singleflight/run-v2.json), and
  [recomputed comparison](evidence/2026-09-12-roi-singleflight/summary.json).
- [Eight scheduler contract tests](evidence/2026-09-12-roi-singleflight/tests.json)
  cover deduplication, latest-only replacement, disappearance/reentry, cooldown,
  cache expiry, late replies, known/missing observations and unmatched completion.
  These tests supply synthetic keys and completions, not visual ground truth.
- Raw resource logs and the exact v1 runner snapshot are archived alongside
  the reports. `summarize.py` checks source hashes and non-overlapping request
  intervals before recomputing statistics.
- [Runner and commands](../../experiments/specialist_temporal/README.md).
  Remote outputs: `/home/jetson/openhalo-roi-singleflight/run-v1` and `run-v2`.
  Original video stays on the Jetson at the source path recorded in the prior
  specialist report; the runner verifies its SHA256 before replay.

## Remaining limits

Owner discussion, 2026-09-13: retain the cascade as a useful candidate while
separating dispatch efficiency from recognition accuracy. The 89.7% figure is
fewer calls than a hypothetical per-unknown-observation baseline, not measured
whole-system speedup or energy savings. No enabled/disabled accuracy comparison
has been performed. Avoiding a held-object claim does not confirm an empty hand.
Free-form VLM descriptions extend the vocabulary beyond the specialist's fixed
class list, but a broader reliable object-recognition range has not been validated.
Cached captions remain candidate explanations, including incorrect ones.

Color distribution does not establish object identity: similarly colored
replacement objects can retain a key, while crop/background/occlusion changes
can invalidate a useful reply. True in-hand swaps, multi-hand association and
physical loss/recovery need independently labeled fresh validation. An anonymous
hand track is not proof that its held object is unchanged. A cached generic
caption can also mention a gesture that has since changed.

Caching does not repair semantic hallucinations. This experiment still cannot
reliably confirm empty hands or screwdrivers; it adds no calibrated confidence
for VLM prose and no structured factual acceptance. Request-level model timing
is not live event-to-correct-label latency. Long-running resource stability,
live specialist contention, timeout recovery and Runtime admission remain open.
