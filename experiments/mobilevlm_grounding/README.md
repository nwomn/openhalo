# Image + low-level measurement grounding probe

This is the owner-authorized next Camera Edge research route. Existing Isaac
ROS user-state semantics remain failed; no ROS transport or Runtime acceptance
is inferred from this fixed-frame backend experiment.

`evidence.py` reuses the existing detector/pose TensorRT engines (640px,
confidence 0.35) in the isolated MobileVLM environment and preserves raw object
boxes and 17 keypoints with scores. Unlike the previous aggregated pose output,
raw per-point data is available. Values with confidence below 0.5 or coordinates
outside the image are not marked usable. Hash identity and saved-video PTS align
the exact pixels; this is not validation of live ROS timestamp synchronization.

The frozen comparison uses language NF4, FP16 vision/projector/head, official
v1 template, greedy decoding and a 48-token ceiling. A has the same image and
conservative prompt. B adds fallible measurements and their interpretation
limits. A/B order alternates across repetitions/cases. Detector, pose and VLM
remain co-resident, with serial computation. Warmup is separately recorded.

C checks the exact B text, with no further model call. It withdraws unsupported
specific relations/actions and unparsed text; retains bounded static captions
as `image_only_unverified`; and only marks directly corroborated presence as
such. Detector misses never prove absence, nor do boxes prove grip or gaze.
Retained image-only captions are not accepted observations. Raw text, every
withdrawal, truncation and total abstention remain visible. Withholding correct
food/hand actions is an information loss and must count against C's usefulness.

Four challenge frames include food, raised hand, the remote-control failure and
the low-head screen-attention failure. Four held-out frames are from greeting B
and a different eating timestamp, not previously fed to MobileVLM or used to
adjust this prompt/gate. These share scene/session context: they are not an
independent environment or a statistical accuracy benchmark. Exact references
are inspected before inference and never placed in the prompt.

Run on Jetson after copying this directory:

```sh
/home/jetson/openhalo-mobilevlm-v2-venv/bin/python benchmark.py \
  --cases /home/jetson/openhalo-mobilevlm-grounding/cases.json \
  --output /home/jetson/openhalo-mobilevlm-grounding/reproduce-v1 \
  --gate-version frozen-v1
```

Dependencies and pinned MobileVLM assets remain in `../mobilevlm_v2/`'s isolated
setup. Added measurement imports use existing ultralytics 8.4.24/TensorRT 10.7.0.
`python -m unittest discover -s experiments/mobilevlm_grounding` verifies the
claim-check boundaries. Do not interpret all-withdrawn output or verified person
presence alone as useful state-understanding success.

The frozen A/B run is complete and negative: B increased false held-object /
computer-relation claims and lost useful action information. C-v1 withdrew all
eight frames. `claims_v1_frozen.py` preserves that implementation, including its
documented overbroad matching defects. `claims.py` is the repaired diagnostic
v1.1: token boundaries avoid the `put` substring in `computer`, and static
holding-one's-hands-up is not treated as holding an object. Rechecking unchanged
B outputs still withdraws seven frames and verifies no claim. This repair was
made after observing results, so it is not a fresh held-out validation.

`summarize.py <results-directory>` preserves raw C-v1 and writes the diagnostic
check separately. The runner defaults to diagnostic v1.1 for future explicit
tests; use `--gate-version frozen-v1` only for historical reproduction. No new
model inference was needed for the parser repair.

## Direct-JSON missing control

The original B changed JSON plus surrounding explanatory prose together, so
its failure cannot reject every low-level/image combination. The owner-authorized
`replay_json.py` now supplies A, J (exact saved JSON only), and B (exact old
evidence text) in one paired run. It reuses each original B repetition's JSON,
verifies hashes/PTS/selection, preserves A's complete prompt and saves complete
rendered prompts with raw results. C is disabled. No real-frame measurements
are recomputed; a black synthetic frame only initializes co-resident TRT contexts.

```sh
python replay_json.py --previous-report /path/to/run-v1/report.json \
  --output /path/to/fresh-replay-directory
python summarize_replay.py /path/to/replay-directory \
  --original /path/to/run-v1/report.json
```

The eight reused frames produced targeted counts A=1/8, J=2/8, B=5/8. Direct
JSON did better than old B but did not establish a net benefit over A; no new
held-out evidence was obtained. The removal of 64 surrounding text tokens does
not isolate any single word as the cause. See the
[supplementary report](../../docs/ops/jetson-mobilevlm-direct-json-validation.md)
for full prompts, exact outputs, partial-credit limits and timings.
