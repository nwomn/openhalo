# Specialist + cached ROI + full-image MobileVLM experiment

This is an isolated semantic comparison, using the existing pinned Jetson
MobileVLM NF4 loader from `../specialist_temporal/vlm_session.py`. No Runtime
adapter, camera service, model installation or live queue is introduced.

`prepare.py` freezes 18 timestamp-selected full images and specialist observations
from the prior recording, with only ROI captions already available at each
replay timestamp. It retains uncertain and wrong captions without correcting
them using the reference labels. Recent gesture changes cover the preceding
four seconds. A contact sheet is visually reviewed before any generation.

`benchmark.py` runs three arms twice per image with cyclic arm order:

- `image`: full image and the same short description question;
- `specialists`: full image, gated specialist candidates and recent changes;
- `cascade`: the same as specialists, plus a previously available ROI caption
  with age and explicit unverified status, if any.

No-cache cases have identical specialists/cascade prompts. The identical
uncertainty instruction is present in both context arms. This comparison can
isolate the added ROI text among seven selected cache-present cases, but the
image/context comparison also includes the context instruction. It is not a
separate test of every possible prompt format.

Remote reproduction (fresh input and output paths required):

```sh
# Copy this directory's Python files and the existing vlm_session.py to scripts/.
/home/jetson/openhalo-mobilevlm-v2-venv/bin/python \
  /home/jetson/openhalo-specialist-context/scripts/prepare.py \
  --root /home/jetson/openhalo-specialist-context/inputs-NEW
# Freeze a visual reference before inference. Labels are never included in prompts.
/home/jetson/openhalo-mobilevlm-v2-venv/bin/python \
  /home/jetson/openhalo-specialist-context/scripts/benchmark.py \
  --root /home/jetson/openhalo-specialist-context/inputs-NEW \
  --output /home/jetson/openhalo-specialist-context/run-NEW
```

The pinned source video, cached specialist report, prior ROI scheduling report
and model runtime must already exist on the Jetson. Source/input hashes and
exact prompts are preserved. Reused frames and deterministic repeats do not
establish independent accuracy. Timings measure only second-stage inference;
real stage-one contention, queueing and event-to-final-label latency are absent.

See [results and boundaries](../../docs/ops/jetson-specialist-context-validation.md).
