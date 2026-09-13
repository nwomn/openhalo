# Qwen3-VL fixed seven-second frame-sampling comparison

Later [higher-frame follow-up](jetson-qwen3-vl-highframe-validation.md) retains
this failed-sequence result and adds a bounded improvement: 480p with 28 frames
described the same gesture sequence correctly in three fixed-seed repeats at
7.398–7.572 s. Increasing frame count was not monotonically better.

2026-09-13. Owner authorized testing whether fewer frames improve response time
while preserving useful action understanding. This follow-up tests Qwen only;
Cosmos is not rerun and no Cosmos speedup is inferred from these measurements.

## Fixed input and variables

The source is the owner's existing `fresh-2157/capture.mp4`, interval
28.5–35.5 seconds. A frozen 7.000-second 1280x720 clip (`c14.mp4`) contains
28 frames at 4 fps. It shows one empty hand changing from open palm to fist,
thumbs-up and V. The ending sampled state is V. Source media and previews remain
outside Git. This interval and visual reference were frozen before inference.

| Profile | Sampling within the same 7 s clip | Selected frames |
| --- | --- | --- |
| uniform12 | Uniform indices from first through last decoded frame | 12 |
| fps1 | 0, 1, 2, 3, 4, 5, 6 s | 7 |
| fps0.5 | 0, 2, 4, 6 s | 4 |

All three sampled contact sheets were visually reviewed before generation.
All four gesture states are present in every profile. The four sparse samples
happen to align with the four held gestures; this favorable sampling phase
cannot establish recall for fast, short or differently timed actions.
The periodic profiles end at 6 s, while uniform12 reaches 6.75 s; the V state
is visible at both endpoints. This is a sampling-policy comparison, including
its natural phase/coverage effects, not merely discarding redundant frame bytes.

The resident Qwen AWQ model, schema adaptation and vLLM container are unchanged
from the [previous validation](jetson-qwen3-vl-validation.md). One engine uses
720p input, context 6144, 768 MiB KV, prefill 2048 and disabled input/prefix
caching. Prompt unchanged. All profiles use temperature 0.7, top-p 0.8, top-k 20,
presence penalty 1.5, repetition penalty 1.0, seed 0 and 96-token cap.
There is one warm-up per profile, then three formal repeats in rotating order:
12/7/4, 7/4/12, 4/12/7. Model initialization is excluded from reported latency.

Every request reads/hashes the same file, decodes all 28 source frames, selects
the profile's frames and resizes to the same 1280x720 input. Timing includes
that preparation and model preprocessing/inference through complete returned
text. Clip extraction, live collection and Runtime are excluded. Separate
preparation times and output-token counts are recorded. Outputs may have different
lengths, so total-response speedup is not a pure visual-kernel benchmark.

The runner records selected indices separately from processor metadata and
asserts actual prompt timestamps and visual-token counts. The processor groups
video frames in pairs; the odd 7-frame profile needs last-frame padding, which
must be reflected in actual model input rather than reported as seven unpadded
frames of work. Three same-seed repeats check run consistency, not independent
generalization or stochastic robustness.

## Results

All nine formal requests stopped naturally without OOM or truncation. Each
profile produced the same text over its three fixed-seed repeats. Every source
hash, selected-index, actual timestamp and visual-token assertion passed.

| Profile | Complete-answer range | Median | Reduction vs 12 frames | Visual tokens | Output tokens |
| --- | --- | --- | --- | --- | --- |
| 12 frames | 7.434–7.569 s | 7.472 s | baseline | 5280 | 60 |
| 1 fps, 7 frames | 4.694–4.887 s | 4.719 s | 36.8% | 3520 | 37 |
| 0.5 fps, 4 frames | 3.049–3.083 s | 3.076 s | 58.8% | 1760 | 50 |

Read/decode/resize medians were 0.154–0.170 s. The actual model input contained
6, 4 and 2 temporal frame pairs respectively; 7 selected frames were padded
with a duplicate final frame. Reduced visual input and changed answer lengths
both contribute to the measured complete-response difference.

| Profile | Semantic review of the repeated answer |
| --- | --- |
| 12 frames | Palm and fist present, then two fingers/V; thumbs-up omitted and a two-handed V invented. No held object correctly reported. Full sequence fails. |
| 1 fps | Palm, fist and final V reported; thumbs-up omitted and clapping invented. No held object correctly reported. Full sequence fails. |
| 0.5 fps | Palm then thumbs-up only; fist and final V omitted even though both sampled images show them. No held object correctly reported. Full sequence fails. |

**Fewer frames measurably reduced response time in this controlled Qwen test,
but none of the three profiles gave a fully correct action account.** The sparse
four-frame result is less complete. Its omissions cannot be attributed to absent
gesture images: all four states were present in the inspected input. Neither
12 frames nor 1 fps is accepted as reliable full-sequence understanding here.
The 1 fps setting is a faster configuration for further model-level evaluation,
not a validated general continuous-understanding profile. This does not show
that all missed events in other videos would remain sampled at 1 fps.

Formal-window telemetry peaked at 7426/7620 MB RAM, 1115–1444 MB SSD swap and
68.5 C reported junction temperature. All jobs and the container are stopped;
no new download, proxy, camera capture or host configuration change occurred.
Final available RAM was 5095 MiB; root disk about 9.2 GiB free. The previous
temporary lean host state and both model environments are retained.

[Runner and frozen reference](../../experiments/qwen3_vl_video/) and
[raw evidence](evidence/2026-09-13-qwen3-vl-sampling/) preserve configuration,
sample indices, original responses, telemetry and checksums. No overall Camera
Edge, sustained pipeline or Runtime acceptance changed.
