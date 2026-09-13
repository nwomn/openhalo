# Qwen3-VL higher-frame-count follow-up

2026-09-13. Owner requested increasing frame count to test whether action
understanding improves. Same frozen seven-second `c14.mp4` (source 28.5–35.5 s),
neutral prompt, AWQ checkpoint, recommended decoding, seed 0 and 96-token cap
as the [sampling follow-up](jetson-qwen3-vl-sampling-validation.md).
Reference remains one empty hand: five-finger palm -> fist -> thumbs-up -> V,
ending in V. The complete 28-frame contact sheet was visually checked again.
All four states and the transitions are present. Labels remain outside prompts.

Profiles uniformly select 12, 16, 24 or all 28 frames from the same frozen
4 fps clip. All profiles span timestamps 0–6.75 s within the 7 s interval.
28 frames is all of this intermediate clip, not all frames of the original
60 fps recording. The existing reference and source/clip hashes are retained.

## Resource boundary and comparison design

The initial attempt kept 720p and enlarged context to 12800 with 1536 MiB KV
to accommodate 28 frames. Warm-ups returned for 12 and 16 frames; the kernel
then killed the experiment Python process while it was processing 24 frames.
The 2026-09-13 15:09:40 kernel log explicitly reports global OOM and PID 158316.
There are no formal results from that attempt and no 28-frame result. This
records a failure of this host/configuration, not an intrinsic universal frame
limit of the model or Jetson.

Two bounded comparisons follow, each with its own remeasured 12-frame baseline:

- 720p: 12 versus 16 frames, context 8192 and KV 960 MiB.
- Approximately 480p: 12/16/24/28 frames, context 6144 and KV 768 MiB.

Within each comparison only sampling changes. The smaller-resolution comparison
answers whether denser temporal input helps under a feasible memory budget; it
must not be used as a resolution-matched 720p improvement. All other model and
decoding settings remain fixed. Natural-length answers may have different token
counts, so timing includes both input processing and response length effects.
One warm-up per profile and three fixed-seed repeats in rotating profile order
test bounded consistency, not fresh-video or multi-seed generalization.

Actual timestamps and visual-token counts are asserted against installed video
processor resizing. Selected indices and post-processor metadata are recorded
separately. A higher total-pixel load may trigger model-side resizing; effective
frame dimensions are recorded so this cannot silently masquerade as constant
resolution. The tested completed comparisons must retain identical effective
dimensions within each resolution arm.

## Results

The completed 720p comparison returned six naturally stopped formal answers:

| Frames | Median | Range | Semantic result across three same-seed repeats |
| --- | --- | --- | --- |
| 12 | 7.463 s | 7.459–8.106 s | Palm -> fist -> two fingers/V; thumbs-up omitted, two-handed V invented. |
| 16 | 9.476 s | 9.420–9.578 s | Initial hand -> fist -> thumbs-up -> two fingers in order; initial five fingers called four, and false non-empty-hand claim remains. |

Sixteen frames recovers the missing thumbs-up and improves the broad order on
this clip, at approximately 27% higher median complete-response latency. All
16-frame formal replies remain below 10 s, but exceed 8 s. Each profile repeats
the same answer. Full semantic correctness is still not established.

The completed 480p comparison returned twelve naturally stopped formal answers:

| Frames | Median | Range | Semantic result across three same-seed repeats |
| --- | --- | --- | --- |
| 12 | 4.178 s | 4.164–4.283 s | Broad order and final V correct; initial five fingers called four. |
| 16 | 4.454 s | 4.431–4.487 s | Broad order correct; initial five fingers called four. |
| 24 | 6.138 s | 6.028–6.306 s | Initial palm omitted; fist/thumb/V described but two-handed V invented. |
| 28 | 7.545 s | 7.398–7.572 s | Five-finger open right hand -> fist -> thumbs-up -> right-hand peace sign; no held object. Matches this clip's gesture sequence and sampled ending state. |

All profiles produced one distinct answer over three fixed-seed repeats.
Actual effective dimensions remain 1280x704 for every completed 720p request,
and 832x480 for every completed 480p request. Visual-token counts are 5280/7040
for 720p 12/16, and 2340/3120/4680/5460 for 480p 12/16/24/28. Input SHA256,
frame indices, actual timestamps and expected token checks passed throughout.

**There is a bounded improvement: 480p with 28 frames correctly describes this
selected gesture sequence in all three repeats, within 8 seconds.** Increased
sampling is not monotonically better: 24 frames performs worse than 16 here.
Frame count also changes selected timestamps and the model's frame pairing;
this does not isolate a universal causal benefit of each added frame.
The stronger 28-frame result is evidence for retaining that configuration for
further comparisons, not proof of general action, object-transition or ending-state
reliability. The original repeated clip and seed remain shared; there is no new
independent input or sustained audiovisual test. Cosmos was not rerun.

## Resources and retained state

Formal-window telemetry:

| Comparison | Peak RAM | SSD swap range | Maximum reported junction |
| --- | --- | --- | --- |
| 720p 12/16 | 7407/7620 MB | 1935–2321 MB | 69.718 C |
| 480p 12/16/24/28 | 7349/7620 MB | 1682–2048 MB | 74.5 C |

The initial 720p OOM is separately preserved; it is not hidden in successful-run
statistics. All inference/telemetry jobs and the Qwen container are stopped.
No driver/OS change, asset deletion, reboot, new capture or media upload occurred.
Final available RAM was 5146 MiB and root free disk about 8.9 GiB. Both model
environments and the previous temporary lean host configuration remain.

[Raw evidence and checksums](evidence/2026-09-13-qwen3-vl-highframes/) include
the OOM attempt, both formal comparisons, frozen reference, executed runners,
input indices, telemetry and summaries. Overall Camera Edge acceptance is unchanged.
