# Cosmos model-only evidence

Primary measured run: `raw-v5.jsonl`, `config-v5.json`, `load-v5.json`,
`runtime-v5.log`. One warm-up plus 13 clips x 3 formal repeats, 96-token cap.
`raw-v6-length.jsonl` / `config-v6-length.json` change only the length cap to
192 and select c01 for one warm-up plus one measured diagnostic reply.

`summary.json` combines verified timing/input metadata with explicitly manual,
per-axis semantic notes. Reproduce checks using `experiments/cosmos_video/summarize.py`.
`runner-v5.py` is the exact runner used; its imported prompt is captured in
`prompt-source.py` (copy to benchmark.py when replaying the snapshot standalone).
The final runner decodes 6–12 frames across the whole clip, resizes to 832x468
and explicitly disables resampling. Actual prompt tokens confirm 832x480 model
patch alignment and original timestamps. Odd frame counts pad the last frame.
`cache-check.txt` is the installed vLLM input processor's relevant branch:
with both prefix caching off and processor cache size zero, request-specific
multimodal identifiers prevent cross-request encoder-embedding reuse as well.

`references.json` contains manually reviewed source intervals and clip hashes.
No source video, frames, weights or credentials are included. References are
never passed to inference. `asset-manifest.json` records the pinned model files.
`decoder-hf-check.json` is the earlier standalone 720p check, not the final
inference configuration. `raw-v4-partial.jsonl` is the earlier chat-path phone
output before OOM on the next clip; do not combine its timings with v5.

`tegrastats-v5-v6.log` covers both runs and intervening idle/startup time. The
report's 12:42:08–12:44:00 bounded window includes the primary v5 replay.
These are reused personal clips and deterministic repeats, not fresh holdouts
or long-running Camera Edge acceptance. See the linked validation report for
the full setup failures and unresolved semantic limits.

`SHA256SUMS.json` checks the evidence file bytes; Git preserves their line endings.
