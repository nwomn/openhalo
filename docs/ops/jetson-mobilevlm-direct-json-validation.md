# MobileVLM direct-JSON supplementary control

Date: 2026-09-12. Owner explicitly authorized this missing control after
identifying that the previous B prompt changed JSON and surrounding prose
together. That previous result rejects its concrete prompt/filter recipe only.
No effect is presumed for the word `Fallible` or the removal of explanatory text.

## Controlled change

Same original eight images, same pinned MobileVLM assets/source, language NF4
(168 linears), FP16 vision/projector/head, official v1 conversation, greedy
generation, 48-token budget, same complete original A conservative prompt:

```text
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding.
```

- A: original image plus that unchanged prompt.
- J: original image plus the exact previously saved B JSON, followed by that
  unchanged prompt. Only B's added surrounding prose is removed.
- B replay: original image plus the exact previously saved B evidence text
  (JSON and all extra prose), followed by the same unchanged original prompt.

The evidence remains immediately after the image marker and before the original
A prompt. JSON is sliced from the saved B prompt, not regenerated/reserialized:
all numbers, uncertainty fields, key/element order, selection and formatting
are retained. For each frame/repetition, J and B reuse the matching old B entry.
The extractor verifies frame SHA256, source PTS, zero pair skew and the original
top-six-box / two-person keypoint selection against stored raw measurements.

No real-frame detector/pose measurements are recomputed. The same TensorRT
engines are kept co-resident; a synthetic black image initializes their contexts
before timing and its result never enters a prompt. All three arms use cached
evidence, with cyclic/reversed execution order and two repetitions per image.
Model warmup is excluded. Timing covers saved-frame decode through text reply;
it excludes low-level measurement extraction, live capture, ROS and Runtime.
It must not be labeled a newly measured live joint-pipeline latency.

C filtering is disabled entirely. The previous eight images are already exposed
test samples; replay does not create another held-out test. The original split
labels are retained only to identify prior subsets. We keep the previous
specified critical held-object/computer-relation count and coarse food/hand
information count, not a new or exhaustive accuracy metric.

## Results: direct JSON improves over old B, but does not beat A here

The completed paired run produced 48 raw model replies (8 frames x 3 arms x 2
repetitions). A and B reproduced their respective earlier texts on every frame
and repetition. J was also text-stable across repetitions. No output was
truncated, no C filter ran, and no abstention occurred.

| Metric | A: original image prompt | J: exact JSON only | B: old JSON + extra prose |
| --- | --- | --- | --- |
| Targeted unsupported held-object/computer-relation claims | 1/8 | 2/8 | 5/8 |
| Clear useful food/raised-hand information, same four action frames | 4/4 | 2/4, plus one partial hand-position description | 2/4 |
| Warm saved-frame-to-text time | 1.493-2.335 s | 1.605-2.400 s | 1.550-1.862 s |
| Median time | 1.783 s | 1.920 s | 1.678 s |
| Text input tokens, before visual-token replacement | 87 | 201-733 | 265-797 |
| Output tokens | 10-16 | 9-16 | 8-11 |

The original challenge subset's targeted count is A=1/4, J=1/4, B=2/4; the
previously held-out subset is A=0/4, J=1/4, B=3/4. These are now replay subsets,
not fresh holdouts. Counts target the same specific errors and are not exhaustive
accuracy. B's shorter response length partly explains its lower measured time;
latency here excludes recomputing measurements, unlike the original live-backend
B timing. Full-window peak RAM was 6636 MB, system swap 1159 MB, temperature
60.718 C; initialization was 12.096 s plus separately recorded warmup.

### Per-frame raw findings

| Frame | J raw output | Targeted error / retained information |
| --- | --- | --- |
| challenge-food | The person is eating a piece of food. | Useful food information |
| challenge-raised | The person is waving at the camera. | Useful coarse hand/wave information; not process proof |
| challenge-remote | The person is sitting down and smiling. | Old B remote claim removed |
| challenge-screen | The person is sitting at a desk and looking at a computer screen. | Unsupported screen attention remains |
| heldout-b-rest | The person is sitting down and looking at the camera. | Old B remote claim removed; gaze not independently validated |
| heldout-b-raised | The person is holding a hand in front of their face. | More position information than B, but not explicit raised-hand/wave; partial credit separate |
| heldout-b-down | The person is sitting down and smiling. | Old B remote claim removed |
| heldout-food | The person is holding a remote control. | Visible food still mislabeled; B had said phone |

J removes three of B's targeted false-object assertions, while retaining the
screen-target error and a false object on the food frame. It therefore performed
better than that old B recipe on this replay, but not better than the paired A
baseline. It has not established a net benefit from adding these measurements,
or an acceptable Camera Edge route. This conclusion is limited to the exact
JSON/placement/model/frames tested, not every way of using low-level evidence.

The removed surrounding text accounts for 64 tokenizer tokens in every case.
This comparison changes that whole explanation/length package. It cannot
identify the word Fallible, any other individual phrase, or prompt length alone
as the cause of the semantic differences. No such causal claim is made.

## Complete prompt inspection

All 48 complete prompts were audited: after removing only each arm's expected
evidence insertion, each equals the same full A conversation string. JSON
SHA256 and frame/PTS checks passed. The complete per-frame A/J/B strings are
published in [actual-prompts.md](evidence/2026-09-12-mobilevlm-direct-json/actual-prompts.md),
with identical repetitions deduplicated for readability. The raw report retains
every repetition separately.

For example, this is the **actual entire J prompt** for the low-head frame,
including the official conversation template and unchanged original A text:

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
{"detections":[{"id":"d0","label":"tv","confidence":0.6066,"bbox":[0.0,0.0016,0.2592,0.4821]},{"id":"d1","label":"person","confidence":0.3821,"bbox":[0.5876,0.732,0.9036,0.9961]}],"poses":[]}
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

No labels such as eating or the expected scene description were added to this
prompt. The JSON is the same saved selection from the prior B record.

Evidence: [raw replies and full prompts](evidence/2026-09-12-mobilevlm-direct-json/report.json),
[latency/input-length summary](evidence/2026-09-12-mobilevlm-direct-json/summary.json),
[per-frame assessment](evidence/2026-09-12-mobilevlm-direct-json/assessment.json).
The temporary inference/telemetry processes exited; no services were deployed.

## Reproduction

`experiments/mobilevlm_grounding/replay_json.py` performs the paired replay;
`replay_prompts.py` extracts and verifies exact saved JSON. Run in the existing
isolated Jetson environment:

```sh
/home/jetson/openhalo-mobilevlm-v2-venv/bin/python replay_json.py \
  --previous-report /home/jetson/openhalo-mobilevlm-grounding/run-v1/report.json \
  --output /home/jetson/openhalo-mobilevlm-grounding/run-direct-json
```

Use a fresh output directory for any explicitly requested repetition. No
camera service, Runtime integration or TinyLLaVA experiment is started here.
