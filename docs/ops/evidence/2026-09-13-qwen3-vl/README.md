# Qwen3-VL-2B AWQ Jetson evidence

2026-09-13 model-only replay. `run-v1` contains 26 formal greedy answers and
two warm-ups; `run-v2-decoding` contains seven selected 720p controls and one
warm-up. Each stores raw outputs, exact engine config, initialization time,
runtime log, input/timing summary, runner and formal-window telemetry summary.
`tegrastats.log` spans both runs and initialization; use the per-run summaries
for formal-window statistics. Dates in telemetry are Asia/Shanghai; raw start
times are Unix seconds.

The first runner snapshot was reconstructed from the retained Cosmos runner and
the same Qwen path/model adaptations after the optional decoding switch was
added; its engine config and outputs are the original recorded files. The
second runner is copied from the executed source. The neutral prompt is imported
unchanged from `experiments/cosmos_video/benchmark.py` and appears in each config.

`asset-manifest.json` records downloaded file size/SHA256 and upstream LFS hashes.
`runtime-config-adaptation.json` records the equivalent RoPE schema mapping.
`SHA256SUMS.json` covers all evidence files except itself. The model and recording
remain on Jetson outside Git. No credentials or private media are included.

Input checks compare all ten matching initial Cosmos clip/resolution pairs and
all seven greedy/control pairs. Semantic findings are reviewed against the
retained video references in the [report](../../jetson-qwen3-vl-validation.md),
not inferred from natural stopping or a latency threshold.
