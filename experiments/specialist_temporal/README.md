# Specialist temporal probe

Research-only Jetson CPU MediaPipe hand/face/body observations and deterministic
temporal fusion. No VLM, LLM, identity, gaze, eating or Runtime integration.

See [validation and limitations](../../docs/ops/jetson-specialist-temporal-validation.md).

The Jetson already provides `python3`, MediaPipe 0.10.18, OpenCV 4.10.0,
NumPy and `tegrastats`. Do not replace its NVIDIA PyTorch or install packages
to reproduce this probe. All writes must stay in a new experiment output path.

```sh
python3 -B -m unittest discover -s /home/jetson/openhalo-specialist-temporal/scripts -p test_fusion.py
python3 /home/jetson/openhalo-specialist-temporal/scripts/benchmark.py \
  --cases /home/jetson/openhalo-specialist-temporal/cases-fresh-v2.json \
  --output /home/jetson/openhalo-specialist-temporal/replay-NEW --hz 5
python3 /home/jetson/openhalo-specialist-temporal/scripts/refuse.py \
  --input /home/jetson/openhalo-specialist-temporal/replay-v1 \
  --output /home/jetson/openhalo-specialist-temporal/ablation-NEW.json
```

Copy these scripts to the private experiment directory before replaying. Output
paths must not exist. `benchmark.py` runs each video in a fresh set of model
instances, logs full keypoints outside Git and stores frame-level summaries.
`refuse.py` only replays frozen measurements; its result is a development-set
ablation, not a new evaluation or model performance benchmark.

Case JSON is a list of objects with `name`, absolute `video`, optional `start_s`,
`end_s`, `freeze_frame` and `observation_dropouts` (inclusive source-time pairs).
Freezing repeats the first selected pixels; dropouts clear observations before
fusion. Neither is a physical robustness test.

v1 rejected chest-height waves with a palm-above-chin prerequisite. Its source
and result are retained unchanged in the evidence directory. v2 removes that
prerequisite and labels only visible hand posture and image-plane oscillation.
It deliberately cannot label raising/lowering from appearance/disappearance.
Body outputs remain recorded for analysis; they do not rescue v2 hand evidence.

The association is a one-person/one-hand geometric heuristic. Multiple faces or
hands, lateral motion, tracking errors and missing hands cause abstention.
Local track IDs are not identities. A `.3 s` debounce can retain the previous
state temporarily, so consumers must inspect `raw_state` and `quality` too.
Face reacquisition and physical track continuity remain unaccepted.

## Trained-classifier extension

`expanded.py` and `crop_diagnostic.py` run separately in
`/home/jetson/openhalo-specialist-expanded/`. They do not modify the initial
hand/face/body probe. See [expanded results and reproduction](../../docs/ops/jetson-specialist-expanded-validation.md).
The extension adds trained static gesture and image classifiers; it contains no
biometric identity or learned hand-object-contact model. Object predictions and
2D overlap are recorded as unverified, with empty-hand controls preserved.
