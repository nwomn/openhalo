# Qwen3.5-2B FlashHead fixed-video validation

2026-09-14, Orin Nano Super. The owner authorized this model-only replay and
accepted its separate Hugging Face gate. **The tested 2B configuration is not a
better replacement for the retained live Qwen3-VL combination:** it restores
the initial palm omitted by 0.8B, but miscounts fingers, retains object/ending
errors, and exceeds the 8–10 s complete-answer screening bound on gestures.

## Setup and disk authorization

Pinned [embedl/Qwen3.5-2B-FlashHead](https://huggingface.co/embedl/Qwen3.5-2B-FlashHead)
revision `17f56ded573393020f0db622e15a17c19ce0cbd5`. All 14 assets were verified,
4,638,752,149 bytes total. The 4,548,221,488-byte checkpoint has 596 BF16 and 36
F32 tensors, including 297 visual tensors; this is not a quantized W4A16 model.
Weight SHA256: `aa33250c4fc64891ddfaba3a314fd9542ea371843c387178b425fbcc5ed680b1`.

The owner declined partition/GPT changes and explicitly approved `apt-get clean`.
Only APT package downloads were cleaned: cache 2.3 GiB to 92 KB, available disk
3.3 to 5.6 GiB before model download. No existing models, recordings, logs or
Docker environments were deleted. Read-only inspection found about 62 GiB
unallocated after the root partition and inconsistent/corrupt backup GPT metadata;
repair and expansion were not performed. After the experiment, root free space
was 1.2 GiB; the retained assets leave little room for additional installations.

Reuse the isolated [0.8B runtime](jetson-qwen35-flashhead-validation.md):
Torch 2.10.0, vLLM 0.19.0+cu126, flash-head 0.1.10, BF16, eager mode, one
request at a time. Original downloaded config remains unchanged; the runtime
view corrects the published text-only architecture label to
`FlashHeadQwen3_5ForConditionalGeneration`. Context is reduced to 4096 and KV
to 192 MiB for 2B (0.8B used 6144/768 MiB). No audio, history, prefix or
processor cache. Thinking is disabled, with the retained neutral prompt and
96-token cap. FlashHead selects approximate greedy tokens and bypasses ordinary
sampling/penalties; its recorded sampling fields are not equivalent to the old
Qwen3-VL sampler. This compares usable configurations, not architecture alone.

## Memory workaround and its verification

The first attempt with the original FlashHead loader loaded 4.25 GiB of model
weights but suffered severe memory pressure while constructing its extra dense
vocabulary layer. Whole-device RAM approached the physical limit and swap
exceeded 5.4 GB; SSH responsiveness deteriorated. The experimental container was
**manually killed** before any real video reply or successful engine-load
measurement. This is not a demonstrated kernel OOM. The log's periodic
`Timeout (0:03:00)` is a diagnostic stack dump, not an automatic timeout verdict.

The successful runs use the opt-in process-local `--share-flashhead-weight`
adapter. It reuses the already loaded CUDA BF16 vocabulary weight while retaining
the publisher's CPU FP32 centroid/normalization preparation and original
FlashHead token selection. It avoids a duplicate 1,017,118,720-byte GPU matrix
(about 0.947 GiB) and the associated large FP32 CPU dense copy. Every process
verified shared storage at shape 248320 x 2048. No stored weights, quantization,
old containers or global memory settings were changed. The runner sets only its
own `oom_score_adj=800` so a memory failure preferentially sacrifices the probe.

A separate small GPU fixture compared the adapter with the publisher's
FP32-copy construction: all state tensors were bitwise equal, all 32 tested
hidden states selected identical tokens, and vocabulary storage was shared.
This supports the memory-only intent of the adapter; it does not establish
full-checkpoint output equivalence. These are results with a custom runtime
adapter, not an unmodified publisher recipe.

## Inputs and results

Reuse the owner's existing recording and the same frozen clips, 16 rounded
uniform indices, prompt and cap as the 0.8B run. Actual inputs are 832x468 RGB;
the processor encodes 832x480, 3120 visual tokens and eight chronological paired
timestamps. Hashes, frame selections, effective sizes and timestamps match the
0.8B evidence; c14 also matches the retained Qwen3-VL 16-frame input. Real-input
assertions passed despite the dummy profiler's two-frame warning. Labels were
reviewed against the selected private frames and kept outside the prompt.

One warm-up, then three formal calls per clip. Times include clip read/hash/
decode/resize and preprocessing through returned text, excluding engine load,
prior clip extraction, camera capture, UI and backend. All nine formal replies
stopped naturally, with identical text within each clip. Latency falls across
some repetitions; three calls after one warm-up do not establish stationary
steady-state performance, P95, live latency or general accuracy.

| Clip and visible reference | 2B median (range) | Tokens | Reviewed 2B result |
| --- | --- | --- | --- |
| c14, 28.5–35.5 s: empty five-finger palm → fist → thumbs-up → V | 12.486 s (10.294–13.624) | 84 | Four broad states/order and final V correct; five fingers called four. Explicit empty state only at beginning. All three calls exceed 10 s. |
| c11, 36–43 s: phone front → illustrated back → lowered, hands leave view | 9.514 s (9.045–11.672) | 69 | Phone/back drawing recognized; falsely starts with drawing already visible, substitutes closer/away for rotation, unsupported visibly-empty ending. One call exceeds 10 s. |
| c12, 43–54 s: screwdriver rotated → lowered → empty palm → lowered | 9.116 s (8.262–9.670) | 45 | Screwdriver called syringe; open palm described as a stop sign, misses object-to-empty order, claims empty ending although final hands leave view. |

The c12 empty palm is visible during the clip, so the output contains a partly
supported state but places it imprecisely at the ending. No greeting-wave intent
is established by this reference. Full English answers are retained in JSONL.

| Matched 480p/16-frame c14 configuration | Median | Tokens | Gesture result |
| --- | --- | --- | --- |
| Retained Qwen3-VL-2B AWQ | 4.454 s | 48 | All four states/order and empty ending; five called four |
| Qwen3.5-0.8B FlashHead | 3.643 s | 31 | Omits initial palm; remaining order and empty ending correct |
| Qwen3.5-2B FlashHead with shared weight | 12.486 s | 84 | Restores initial palm, still five called four; no overall upgrade over retained Qwen |

2B generates longer gesture/phone answers and has a larger model under tighter
memory pressure. These data cannot assign its latency increase to any one cause.
For matched phone/16, 0.8B took 3.666 s but invented thumbs-up; 2B avoids that
specific error without correctly recovering the transition. For tool/16, 0.8B
took 8.345 s to a repeated 96-token truncation; 2B stops naturally at 45 tokens
but keeps the syringe error. Time to truncation is not a valid completed-answer
baseline and neither tool answer satisfies the semantic task.

Cosmos has **no retained c14/16 baseline**. Historical 480p/12-frame phone/tool
medians were 2.923/3.187 s: the phone answer invented a gesture; the tool answer
used vague object/two-hand descriptions rather than the full transition. Those
other selections use floored 12-frame indices and cannot establish a matched
speed or memory ranking against the new 16-frame run. See the
[Cosmos report](jetson-cosmos-flashhead-validation.md).

## Resources, initialization and disposition

Host tegrastats interval 500 ms; per-request intervals padded one second because
timestamps have second precision. Values are whole-device RAM and inherited
swap, not isolated model allocation; sampling may miss shorter peaks.

| Formal run | Peak RAM / total MB | Swap range MB | Engine construction | First request |
| --- | --- | --- | --- | --- |
| c14 | 7473 / 7620 | 2721–2837 | 44.745 s | 32.720 s |
| c11 | 7498 / 7620 | 2670–2775 | 44.084 s | 25.563 s |
| c12 | 7481 / 7620 | 2650–2761 | 42.369 s | 23.868 s |

Engine construction used caches populated by earlier attempts; it is not a fresh
installation cold start. Even after weight sharing, RAM remains near the device
ceiling. The earlier 0.8B formal runs peaked at 7212–7351 MB with 1158–1681 MB
swap. These separate sessions are not a controlled minimum-memory comparison,
but neither establishes comfortable concurrent-camera headroom.

The bounded probe is complete. Preserve the owner-retained Qwen3-VL live Demo;
this 2B configuration offers no demonstrated overall quality/latency improvement.
No compiled-mode optimization, full-checkpoint equivalence, fresh holdouts,
live camera, audio or Runtime experiment was conducted with 2B. This does not
rule out other runtimes or quantized Qwen3.5 variants.

Experimental inference container, bounded telemetry and temporary loopback proxy
are stopped. No Docker containers remained running; the host Demo returned HTTP
200. Post-cleanup available RAM was 5919 MiB, swap used 971 MiB, root free space
1.2 GiB. Assets/runtime and prior experiments remain retained. No Camera Edge,
M17.10, backend or replacement acceptance status changed.

[Evidence and checksums](evidence/2026-09-14-qwen35-2b-flashhead/),
[reproduction scripts](../../experiments/qwen35_flashhead/README.md).
