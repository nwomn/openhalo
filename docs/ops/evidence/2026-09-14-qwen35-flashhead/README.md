# Qwen3.5 FlashHead fixed-video evidence

`summary.json` holds formal resident timing and request-window resource summaries.
`c14-matched-input-check.json` checks retained Qwen3-VL inputs and neutral prompt.
Each run directory has original config, engine construction time and raw JSONL.
`telemetry.txt` is host output including initialization and requests, not model-only RAM.
Setup logs preserve ABI/cache rejection, manually interrupted tuning and the memory
startup rejection. These are not formal model answers.

`benchmark-executed.py` preserves the runner used for all three inference runs.
The final source changes only the prepare-only contact-sheet label offset for
non-c14 clips; the corrected contact sheets are private and were reviewed.
No private images/videos, weights, tokens or user contact details are included.

`asset-manifest.json` lists pinned download sizes/hashes; checkpoint-check records
stored dtypes and original/runtime-only architecture labels. See the linked report
for scope, decoding differences, truncation and cold/resident timing limitations.
