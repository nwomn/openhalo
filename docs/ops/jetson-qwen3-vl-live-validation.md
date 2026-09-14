# Qwen live-camera processing-paced probe

## Owner retention decision and Demo follow-up

At 2026-09-14 14:14, the owner designated this as the first "stable seamless
understanding" combination to retain: Orin Nano Super + IMX219 live capture +
Qwen3-VL-2B community AWQ, approximately 480p, 16 chronological frames per request,
with capture concurrent with inference and immediate handoff at completion.
This positive owner assessment establishes the working comparison baseline for
further live/backend experiments. It does not establish full Camera Edge, backend,
long-duration audiovisual or general semantic acceptance.

The later user-operated Demo run `demo-20260914-120829-229838` retained 1140
delivered frames over 141.645 s and returned 32 batches. All delivered sequences
were handed off exactly once, with contiguous windows and no overflow. Thirty-one
replies stopped naturally; one reached the 96-token output cap. Request times were
3.414–5.911 s, median 4.434 s. Maximum inter-request handoff gap was 17.62 ms.
For ongoing capture, median newest/oldest selected input age at completion was
4.491/8.949 s. These are new Demo evidence, separate from the original 25-request
two-minute probe below. Original generated claims have not all been visually
validated; no new semantic accuracy score is assigned.

The owner observed that changed actions could take about two batches to appear
in descriptions. The schedule explains why throughput differs from event latency:
an action waits for the currently running request to finish (approximately 0–T),
then its own batch needs approximately T to process. With roughly constant T and
correct recognition in the first eligible batch, the response delay is therefore
approximately T–2T, averaging 1.5T only if arrival phase is uniform. At T=4.434 s,
this corresponds to roughly 4.4–8.9 s and a conditional mean of 6.7 s, before
network/UI overhead (the page polls every 800 ms plus response time). Sparse
sampling or incorrect recognition can delay a correct answer beyond 2T or miss it
altogether. This is a scheduling derivation, not an annotated measurement of actual
action onset to first correct answer. No zero-lag claim follows from seamless handoff.

[Demo evidence](evidence/2026-09-14-qwen3-vl-demo/) preserves raw answers, capture
metadata, config, completion markers, the checked summary and SHA256 manifest.
Private images remain outside Git. The existing Demo and model environment are
retained; this save does not restart recording or change backend state.

## Future direction: event-triggered faster feedback

Owner confirmed this future direction at 2026-09-14 14:48 and asked to stop at
discussion, save and push all work. The retained seamless combination remains the
working baseline; no event-trigger implementation or new capture starts here.

Continue ordinary processing-paced video understanding when no significant event
occurs. On a significant change, form a chronological 16-frame candidate from the
buffer around the event, including before/during/after evidence. A trigger at the
first changed frame may contain too little post-event evidence, so any additional
observation wait belongs in the measured event-response latency.

Compare two scheduling choices in a future authorized experiment:

- Prioritize the event window after the current request: may improve evidence
  selection and recognition, but does not by itself remove the 0–T wait for the
  current request or its resulting T–2T scheduling latency.
- Interrupt an ordinary request for an important event: could approach one new
  inference duration plus detection, evidence-gathering and interruption overhead.
  This is a hypothesis, not a measured 4–5 second guarantee. The current synchronous
  worker has no lightweight cancellation path; the Demo's container Stop is not
  a usable low-latency preemption mechanism.

Additional parallel VLM requests cannot be assumed to improve latency on the
current resource-constrained Jetson. Trigger logic should flag potentially useful
changes without supplying unverified semantic labels as facts. Pixel motion is
not automatically a significant event. Merge/debounce repeated changes so that
ongoing motion cannot continually cancel requests before any answer completes.

Future evaluation must separately report event detection delay/false triggers,
event-window evidence quality, missed events and incorrect answers, interruption
cost and abandoned ordinary windows, resource usage and event-onset-to-first-correct
answer P50/P95 relative to the retained continuous baseline. Success means an
observed latency improvement with explicit semantic/coverage tradeoffs and bounded
resources, not merely a faster trigger notification or shorter model request.
Detailed detector and interruption choices remain open, as does backend validation.

## Original two-minute probe

2026-09-14. Owner authorized the first real CSI-camera test after retaining
the offline comparisons. This probe uses 16 chronological frames per request,
approximately 480p, and one resident Qwen AWQ engine. Each completed request
triggers an atomic handoff of the camera frames accumulated during that cycle.
Seven seconds is not a fixed live-window duration. No backend is used here.

## Protocol and acceptance boundary

- Existing IMX219 CSI camera, requested 1280x720 at 30 fps; Argus reports sensor
  mode 4 with nominal 60 fps (actual exposure cadence was not measured). GStreamer scales to
  832x468 and selects up to 8 fps before CPU JPEG capture. This is intentional
  temporal sampling, not retaining every sensor frame. No audio is captured.
- Host capture and container inference run concurrently. The capture owner keeps
  a 240-entry metadata buffer; JPEG evidence is stored on local disk for a bounded
  120-second recording. No private images or video are committed to Git.
- Buffer publication and handoff use the same lock. Publication timestamps define
  contiguous scheduling windows; separate frame-arrival timestamps expose delivery
  gaps. Neither timestamp is claimed to be a sensor exposure timestamp.
- Uniformly choose 16 frames from each handed-off batch. A final short batch can
  duplicate frames; unique frame count must be reported. Overflow fails explicitly.
- Qwen settings match the offline 480p comparison: context 6144, KV 768 MiB,
  recommended decoding, seed 0 and 96-token cap. Prompt remains the neutral
  gesture/held-object prompt, without expected action labels or prior answers.
- Model loading and an offline-footage warm-up precede camera start. The first
  live request waits for 36 captured frames (approximately 4.5 seconds). Subsequent
  windows follow actual completion times, without a fixed timer.
- Record request-to-complete-answer latency separately from oldest/newest input
  age at completion. A fast reply is not necessarily a fresh or correct answer.
- Verify every captured sequence is handed off once, no buffer overflow, and
  actual prompt timestamps plus 3120 visual tokens per 16-frame request. Millisecond
  timestamps are represented using a virtual 1000 Hz index clock in processor
  metadata; this does not represent the physical camera frame rate.
- Compare measured memory, swap, compute, complete-answer latency and semantic
  outputs. Preserve truncations and failures. Two minutes is a bounded concurrency
  probe, not long-duration operation or full Camera Edge acceptance.

Implementation: `experiments/qwen3_vl_video/live_capture.py` (host OpenCV with
GStreamer), `live_benchmark.py` (existing vLLM container). Two local unit checks
cover concurrent handoff sequence/timestamp coverage and explicit overflow.

## Execution and results

Preflight reached the Jetson, confirmed IMX219 and the retained model environment.
Initial available memory was 4839 MiB, SSD swap used 558 MiB, and root disk had
8.9 GiB available. The idle desktop and Ollama remained stopped. Argus was started
temporarily for the camera. Model load plus offline warm-up took 62.196 seconds.
The first capture launch failed before opening the camera because the container
created a root-owned output directory. Changing only this run directory to the
host user's ownership allowed capture to start; the retained worker was already
warm. The reusable worker now inherits directory ownership from its parent.
Both the failed startup log and executed source are retained.

The owner confirmed at 11:51 that the camera recorded their own live actions,
not a video displayed on a screen. The recording was bounded to approximately
two minutes, with a measured frame-arrival span of 120.040 seconds.

| Measurement | Result |
| --- | --- |
| Delivered capture frames | 966, average 8.039 fps |
| Formal requests | 25, all naturally stopped within 8 seconds |
| Request-to-complete-answer | 4.319–5.686 s; median 4.868 s; sample P95 5.587 s |
| Processing-paced window duration | 4.325–5.703 s; median 4.887 s |
| Previous completion to next request start | median 7.45 ms; maximum 16.78 ms |
| Delivered-frame handoff coverage | every sequence 0–965 handed off exactly once; no overflow |
| Frame-arrival gaps | median 132.9 ms; maximum 137.2 ms |
| Final tail | request 24 used 8 distinct captured frames, duplicated to 16 |
| Oldest selected input age when answer returned | median 9.720 s; maximum 11.073 s |
| Newest selected input age during ongoing capture | median 4.914 s; maximum 5.703 s |
| Newest selected input age including capture-ended tail | maximum 8.123 s |
| Whole-device RAM | 6820–7249 / 7620 MB; median 7010 MB |
| Whole-device SSD swap in use | 1022–1307 MB |
| GPU utilization samples in request windows | average 83.9%; maximum 99% |
| Mean utilization across CPU cores and samples | 26.2% |
| VDD_IN | average 20.10 W; maximum 23.50 W |
| Maximum reported junction temperature | 75.25 C |

Resource statistics use 247 tegrastats samples aligned to formal request windows;
they are whole-device values, not the model's allocation or wall-outlet power.
The monitor has finite sampling resolution. Used swap does not quantify page-in
traffic. The GPU engine remained resident between requests; no parallel Qwen
workers or growing inference queue were used.

The capture output intentionally selects approximately 8 fps and the model selects
16 frames per batch. Complete delivered-sequence handoff coverage does not mean
that all sensor frames were retained or that every event was understood. Actual
selected timestamps and 3120 visual tokens were asserted for all 25 requests.
Publication timestamps prevent an in-flight JPEG write from crossing backwards
over a handoff boundary. JPEG files remained in the private Jetson run directory
(approximately 54 MiB); the active ring contains bounded metadata rather than a
large decoded-frame backlog.

## Semantic review and interpretation

All 25 replies describe holding/interacting with a smartphone. Nine visual audit
frames spanning 0–120 s confirm the persistent phone and visible hand-position
changes; this supports the coarse phone-held description, not every generated
detail. Several replies infer scrolling/typing/tapping and assert unchanged or
two-handed holding throughout their window. Those details have not been verified
frame by frame and must not be promoted to validated events. The neutral prompt
remained unchanged and no reference action list was supplied to the model.

No palm/fist/thumb/V transition sequence, mouse switch or empty-hand transition
was established in the reviewed samples. Consequently this run supports a bounded
real-camera concurrency/latency result and useful coarse phone recognition, not
reliable gesture transitions, cross-window continuity or full daily semantics.
There was no backend connection or audio processing. Independent windows do not
inherit the previous model answer.

The live median 4.868 s is approximately 9% above the prior offline 16-frame
median 4.454 s, but scene, window duration and answer length differ. This is not
a controlled measurement attributing that difference solely to camera overhead.
Most importantly, the demonstrated complete-answer time and input age are distinct:
continuous capture avoids scheduled gaps but does not produce zero-lag understanding.

## Cleanup and evidence

Capture completed and the final buffer was drained. The Qwen container and this
run's tegrastats monitor were stopped; Argus was restored to inactive. No boot
configuration or backend was changed; the user's OpenClaw service remained running.
After cleanup available RAM was 4965 MiB and swap used 613 MiB. This is a measured
post-run snapshot, not a promise about later host state.

[Evidence](evidence/2026-09-14-qwen3-vl-live/) retains config, raw answers, capture
metadata, actual executed source, monitor logs, startup failure, summary and
checksums. Private JPEGs/contact sheets remain outside Git. The reusable runner
adds the startup ownership fix; the archived executed worker preserves the earlier
source. Local checks cover concurrent handoff integrity and overflow handling.
