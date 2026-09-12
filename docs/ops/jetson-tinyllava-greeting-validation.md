# TinyLLaVA-Video greeting-process probe — 2026-09-12

**Owner closeout at 19:45 local: failed; validation stopped.** The owner regards
this as the fastest useful semantic response among the tested candidates so far,
but still unacceptable. Retain evidence and the existing environment as a future
compromise option only if needed. No further testing, optimization or deployment
is scheduled by this decision. This comparison does not equate model replay
latency with end-to-end latency or low-level detector throughput.

The owner requested a fresh greeting-camera test and clarified that serialized
15-second capture/inference is unacceptable. A pre-maintained ring buffer with
under-10-second completed understanding is worth considering. This is a scoped
exploratory condition, not acceptance or replacement of the existing v2 target.
Failure to identify an off-camera screen is temporarily acceptable without
screen-position context.

**Result: useful but inconsistent process understanding; full-greeting replies
still exceed 10 seconds.** No Camera Edge or Runtime acceptance changed.

## Input and controls

The owner performed the requested rest → raise hand → wave → lower hand → rest
sequence. The first 24-second ring attempt lost the action before collection;
that is a capture scheduling failure, not a model result, and was not inferred.
A second capture with 90 two-second segment slots retained 73.353 seconds.
Segments were concatenated by modification time because splitmuxsink cycles
filenames. The retained recording contains two separate greeting bouts.

Selected inputs were fixed by visual inspection before inference:

| Input | Source interval | Visible process |
| --- | --- | --- |
| greeting-a | Retained recording 27–35 s | Hands down, raise, wave, lower; gaze down near the end |
| greeting-b | Retained recording 37–45 s | Hands down, raise, wave, lower, hands down |
| opening-only | greeting-a 0–5.5 s | Hands down, raise, wave; ends with waving hand still raised |
| closing-only | greeting-a 3.5–8 s | Starts waving, lowers hand, sits still; no initial raise from rest |

The exact 16 uniformly sampled input frames were also visually inspected.
Partial clips test whether descriptions track the observed start/end rather
than completing a stereotypical full greeting. They are correlated derivatives,
not independent scenes. The old eating clip was a warmup/non-greeting control.
All five inputs were replayed twice using deterministic generation; repeats do
not establish an accuracy rate or P95 latency.

The same blinded prompt was used for every input, without action labels:

> In one short sentence, describe the person's visible actions in order from the beginning to the end of the video. Mention the starting and ending states. Do not infer intent.

## Outputs and assessment

Each input returned identical text on its two replays:

| Input | Exact model output | Assessment | Warmed decode/preprocess to completed output |
| --- | --- | --- | --- |
| greeting-a | The person starts by looking forward, then raises their right hand to wave, and finally lowers their hand and looks forward again. | Captures raise → wave → lower. Final gaze claim misses the downward gaze near the end. | 11.140, 11.459 s |
| greeting-b | The person starts by looking forward, then raises their right hand, and finally lowers their hand and looks forward again. | Captures raise → lower, but omits visible waving. | 10.385, 10.418 s |
| opening-only | The person starts by looking forward, then looks to the side, and finally looks forward again. | Fails: omits the main raise/wave action and raised-hand ending. | 10.311 s; initial inference 14.096 s excluded |
| closing-only | The person starts by waving their hand, then lowers it, and finally sits still. | Matches the visible process and does not invent an initial raise. | 9.435, 8.951 s |
| Eating control | The person starts by eating a snack, then looks to the side, and finally looks forward. | No greeting hallucinated; detailed gaze sequence was not separately accepted. | 10.115 s; initial inference 13.781 s excluded |

The full-greeting action-sequence gate is only partly satisfied: A contains the
core sequence, B omits waving. The start/end control fails on opening-only and
succeeds on closing-only. This supports some temporal sensitivity but not
reliable process understanding across cache-window boundaries. No attention,
identity, intention or interruptibility accuracy is established.

## Timing and resource boundary

The model/runtime/quantization is the existing completing NF4 recipe described
in the [initial validation](jetson-tinyllava-video-validation.md): vision batch
4, last-position language logits, 16 frames, 512 visual tokens, 48-token output
cap. Both processes loaded 430 quantized linears with no checkpoint key mismatch.
Greeting outputs used 24–26 tokens; partial outputs used 18–20, without hitting
the cap. Model loading took 23.687 and 22.165 seconds, separately from replay.

All four warmed full-greeting responses took 10.385–11.459 seconds, so even
the measured replay subpath fails the owner's under-10-second consideration.
Closing-only responses fit that subpath at 8.951–9.435 seconds. This shorter
answer is not evidence that complete greetings meet the condition.

The benchmark times clip decoding/preprocessing through completed model output.
It excludes file selection, ffprobe frame-count/hash work, ring extraction,
event confirmation, queueing, cold loading, transport and Runtime. Offline
creation of each full 8-second crop separately took about 1.50 seconds; it is
not included in the table and is not an optimized ring extraction measurement.
Capture was stopped before loading the model: ring retention and inference
were exercised sequentially, not as a concurrent resident service. Therefore
no under-10-second end-to-end ring-buffer claim is established.

Whole-process peaks (including loading) were RAM 7464/7620 MB and swap 3566 MB
for the full probe, then RAM 7494/7620 MB and swap 3648 MB for the partial probe.
Swap was already in use; these are system peaks, not isolated model allocation.
No sustained/no-swap operation was demonstrated. Temporary capture, benchmark
and telemetry processes exited; no autostart or Runtime integration was added.

## Evidence

- [Full input/replay report](evidence/2026-09-12-tinyllava-greeting/full-report.json)
- [Full probe summary](evidence/2026-09-12-tinyllava-greeting/full-summary.json)
- [Partial input/replay report](evidence/2026-09-12-tinyllava-greeting/partial-report.json)
- [Partial probe summary](evidence/2026-09-12-tinyllava-greeting/partial-summary.json)
- [Full clip selection and hashes](evidence/2026-09-12-tinyllava-greeting/selected-clips.json)
- [Partial references and hashes](evidence/2026-09-12-tinyllava-greeting/partial-reference.json)

Raw camera media, exact-frame contacts, capture metadata, commands and logs stay
outside Git at `/home/jetson/openhalo-tinyllava-greeting-20260912-1930` on Jetson.
Host previews are under `D:\openhalo-tinyllava-assets`. No provider upload was
performed. Existing parent-thread runtime/source and other experiments were
reused without modification.
