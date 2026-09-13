# Qwen higher-frame evidence

One frozen seven-second clip, same checkpoint and prompt. `attempt-720p/`
contains two warm-up answers (12/16 frames), no formal answers, and the original
global-OOM log from processing 24 frames. 28 frames was not reached at 720p.
Its runner is archived separately from subsequent width-aware runner changes.

`run-720p/` contains two warm-ups and six formal requests (12/16 frames; context
8192 and KV 960 MiB). `run-480p/` contains four warm-ups and twelve formal
requests (12/16/24/28 frames; context 6144 and KV 768 MiB). Both completed runs
use `runner.py`, whose SHA256 matches the executed Jetson source in
`final-state.txt`. Each arm has a remeasured 12-frame baseline. Fixed seed 0;
three rotating-order repeats measure bounded consistency, not generalization.

`sampled-inputs.json` freezes the selected source indices. `reference.json` is
the earlier pre-inference reference; the full 28-frame sheet was also visually
reviewed this turn. `tegrastats.log` spans all attempts; per-run summaries filter
to formal-request windows only (Asia/Shanghai). Effective resolution assertions
and actual model token/timestamp checks passed for all formal outputs.

The 480p 28-frame answer matches this clip's four gestures and sequence in all
three repeats. Other profiles retain errors; full review is in the
[report](../../jetson-qwen3-vl-highframe-validation.md). Source recording, frame
previews and model weights stay outside Git. `SHA256SUMS.json` covers the other
evidence files recursively.
