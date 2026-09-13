# Fixed seven-second Qwen frame-sampling evidence

One reused clip (source 28.5–35.5 s), 720p, unchanged model/prompt/decoding and
engine configuration. Three profiles: 12 frames, 1 fps (7 frames) and 0.5 fps
(4 frames). `raw.jsonl` contains three warm-ups and nine formal requests in
rotating order. `summary.json` reports complete-answer timings and repeated
text; semantic review is in the linked report, separate from natural stopping.

`sampled-inputs.json` was generated before inference and the private contact
sheets were inspected. `reference.json` was frozen before model output and never
loaded by the runner. All four gestures are visibly sampled even at 0.5 fps;
that favorable phase does not validate coverage for other timing. Source video
and private contact sheets are excluded from Git. `final-state.txt` includes
the source video and executed runner SHA256. `runner.py` is the executed source.

The recorded original indices distinguish seven selected frames from the
processor's padded eight-frame input. Actual visual-token/timestamp assertions
passed for every request. `tegrastats.log` spans initialization and inference;
`telemetry-summary.json` filters to formal-request windows (Asia/Shanghai).
`SHA256SUMS.json` hashes all other files in this directory.

[Full report](../../jetson-qwen3-vl-sampling-validation.md).
