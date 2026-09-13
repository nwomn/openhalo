# Memory cleanup / resolution evidence

`raw.jsonl` has two warm-ups followed by five clip pairs (832x468 and 1280x720),
one formal request per resolution per clip. All have 12 frames. `config.json`,
`runner.py`, `benchmark.py` and `runtime.log` capture the same resident engine,
fixed prompt and settings. `load.json` records initialization separately.

`summary.json` records the checked pairs and telemetry restricted to formal
request wall-clock timestamps. All paired clip hashes match the original
`2026-09-13-cosmos-model/references.json`; within each pair, source hashes,
metadata and actual prompt timestamps match, with visual token counts 2340/5280.
No altered frame selection or missing-frame tradeoff was used to fit 720p.

Memory/slab snapshots and `previous-oom.log` preserve the prior kernel OOM and
before/after cleanup state. Large kmalloc-256 allocation persists; the logs do
not establish its allocation stack or prove a specific kernel bug. The service
and swap changes are temporary and documented in the follow-up report.

The prepared model container and telemetry stopped after the run. No raw video,
frame images, weights or authentication credentials are included. The measured
runner's SHA256 matches its Jetson copy:
`06141092e7b0daed9f4c37dbbb2de80f15fd4e207aa32f4163004a2f5a81e666`.

`SHA256SUMS.json` records the evidence bytes; Git preserves their line endings.
