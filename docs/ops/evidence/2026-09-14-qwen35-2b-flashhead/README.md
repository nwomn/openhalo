# Qwen3.5-2B FlashHead evidence

2026-09-14 owner-authorized fixed-video probe; see
[report](../../jetson-qwen35-2b-flashhead-validation.md).

- `asset-manifest.json`, `source-config.json`, `weight-preflight.json`: pinned
  model assets and actual tensor metadata; no checkpoint payload or credentials.
- `unshared-stopped.log`, `benchmark-executed.py`: original loader attempt,
  manually stopped under memory pressure before a real video answer.
- `benchmark-shared-executed.py`, `share_flashhead_weight.py`: exact successful
  runner and opt-in vocabulary-sharing adapter.
- `c14-shared`, `phone-shared`, `tool-shared`: config, engine load, raw warm-up
  and three formal answers, plus verified shared-storage metadata. Associated
  logs retain model-load and actual-input checks.
- `experiment.tegrastats`: whole-device 500 ms telemetry spanning setup and
  formal runs. `summary.json` filters request intervals with one-second padding;
  swap includes inherited pages, and timings exclude engine initialization.
- `matched-input-check.json`: 0.8B input/prompt/cap equality, with c14 Qwen3-VL
  matching traced through the retained 0.8B check. Runtime settings differ.
- `check_weight_sharing.py`, `weight-sharing-check.log`: synthetic GPU numerical
  and storage regression; not a full-checkpoint equivalence claim.
- `SHA256SUMS`: hashes of all other files in this directory, relative paths.

Private recordings, sampled contact sheets, downloaded weights and HF tokens
are excluded. No partition/GPT repair or expansion was performed. APT cache
cleanup was the only newly authorized deletion; prior experiments remain intact.
