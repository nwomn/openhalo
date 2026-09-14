# Mage-VL resident fixed-video retest

2026-09-14, owner-authorized after the [historical-run audit](jetson-mage-vl-audit-20260914.md).
**The new measurements still favor retaining Qwen3-VL.** Mage's codec selection
substantially reduces processing cost, but all tested complete-answer requests
remain above 10 seconds, gesture order is wrong, and screwdriver is called a
syringe. Phone visibility/ending wording is useful and better than several
earlier model replies. This is a result for the retained community GGUF/native
configuration, not a verdict on all Mage-VL implementations.

## What changed from the old test

- Same owner's frozen gesture, phone and screwdriver clips as the recent Qwen
  tests; same 16 rounded uniform source-frame indices, neutral prompt and
  96-token output cap. Reference labels never enter the prompt.
- Backbone and vision weights load once per profile. One language context is
  reused, with request memory cleared; no previous-answer context or prefix reuse.
- Direct native inference, without StreamMind sidecars, trigger threshold,
  periodic scheduling, UDP camera capture, FFmpeg live startup or UI delay.
- Actual source-frame IDs, timestamps and visual token counts are asserted
  from the native multimodal chunks before encoding. All 24 requests, including
  six warm-ups, passed; all 18 formal replies stopped naturally.
- Clip read/hash/decode/geometry/packing through the returned answer is timed.
  Initialization and prior clip extraction are separate. Native vision,
  language prefill and decoding times are also recorded.

Q4_K_M backbone and Q8 projector SHA256 were freshly verified against the
historical expected hashes: `e8959bb666872d10cd826e0f76542a89e39e81dec18b2563ec3d281abfdd9fb0`
and `8a9d784e666f8178bc805b5a157ac56e52a66be9eef5a73035c746461df1d231`.
No model download or replacement occurred. New standalone `resident` links the
existing patched llama.cpp libraries (base `a52077c4cabb4f3c0298329c9d2dd1324d5604cb`),
without changing old executables. Binary/library hashes are archived.

Context 8192, batch 1024, ubatch 256, four CPU threads, explicit CUDA flash
attention, full GPU layer offload and greedy decoding. Native logs show a
1152 MiB KV buffer. This is a distinct deployment configuration from Qwen's
vLLM/AWQ/sampling recipe. It is not full-checkpoint numerical parity with the
Microsoft BF16 implementation or an optimized-runtime speed limit.

## Two input profiles

| Profile | Source samples | Actual geometry | Visual tokens | Meaning |
| --- | --- | --- | ---: | --- |
| Full-frame control | Same 16 chronological frames | 832x468 RGB resized to 832x480 native grid | 6240 | All patches preserved; four four-frame bundles in one request |
| Codec-selected | Same 16 chronological frames | Package-selected 832x448 canvases | 1456 | H.264 bit-cost selection packs patches into four canvases in one request |

Both use lossless PNG payloads. The full-frame geometry adapter is explicit;
native preprocessing differs from Qwen even though selected source frames match.
The codec arm uses installed `codec-video-prep 0.2.5` and its real H.264/HEVC
bit-cost reader, not the old incremental pixel-difference proxy. Only the
sampler is temporarily pinned to the matched IDs; keyframe shifting is disabled.
Fixed grouping of 16 frames/four canvases isolates this bounded input budget.
All sixteen source IDs retain selected patches in each tested clip, but that
does not preserve all details from every frame. Patch counts and positions are
audited separately from mere source-sample coverage.

The codec package rounds geometry to 832x448 under the supplied pixel budget;
it must not be reported as identical 480p processing. Its 1456 tokens are 25%
of full dense tokens at that same 832x448 geometry; the comparison with the
6240-token control additionally includes the geometry difference. No claim of
bit-exact official preprocessing or fully optimized codec inference follows.

## Inputs and reviewed results

Original recording: `/home/jetson/openhalo-specialist-expanded/fresh-2157/capture.mp4`.
The retained 16-frame contact sheets were reviewed again during this turn.

| Clip | Reference | Full-frame median (range) | Codec median (range) |
| --- | --- | --- | --- |
| c14, source 28.5–35.5 s | Empty five-finger palm → fist → thumbs-up → V, ends V | 35.824 s (35.538–36.092) | 10.849 s (10.839–10.900) |
| c11, source 36–43 s | Phone front → illustrated back → lowered/out of view | 35.369 s (35.205–35.379) | 11.136 s (11.113–11.157) |
| c12, source 43–54 s | Screwdriver → lowered → empty five-finger palm → hand lowered/out of view | 34.927 s (34.540–35.115) | 10.626 s (10.590–10.640) |

Each profile has one warm-up then three formal repetitions per clip, with
one process retained across all three clips. Within each profile/clip the three
formal answers are identical. These reused inputs and deterministic repetitions
measure bounded consistency, not general accuracy or P95.

- **Gesture, full-frame, 38 tokens:** “5 fingers, then 1 finger, then 2 fingers,
  then 1 finger, then 2 fingers”; empty ending is stated. Initial five-finger
  palm and empty state have support, but fist and the actual four-state order
  are not recovered. End two fingers is compatible with V but not sufficient
  to rescue the incorrect sequence.
- **Gesture, codec, 28 tokens:** “3 fingers, then 2 fingers, then 1 finger,
  then 2 fingers, then 3 fingers”. Finger counts, order and ending are wrong;
  no explicit empty-hand state. Compression did not improve this clip's quality.
- **Phone, full-frame, 31 tokens:** holds phone, raises it, shows its back, then
  lowers it. Useful broad sequence without an invented empty ending, but initial
  front-to-back rotation is not explicitly described.
- **Phone, codec, 33 tokens:** raises phone with illustrated case, then lowers
  it and the phone is no longer visible. The ending is appropriately visibility
  bounded, not an assertion of visibly empty hands. Front-to-back transition
  remains omitted.
- **Tool, full-frame/codec, 24/20 tokens:** both call the screwdriver a syringe,
  then describe raising a hand with extended fingers. Some change toward open
  palm is captured, but object identity is wrong and empty state/ending is not
  fully described. The full-frame answer correctly says five fingers here.

Original English replies and finish reasons are retained in JSONL. None is a
96-token truncation; completion does not imply semantic correctness.

## Time and memory interpretation

| Codec profile | Median input preparation | Median native inference | Peak whole-device RAM | Inherited swap range |
| --- | ---: | ---: | ---: | ---: |
| c14 | 1.297 s | 9.542 s | 6596/7620 MB | 802–887 MB |
| c11 | 1.263 s | 9.875 s | 6612/7620 MB | 882–883 MB |
| c12 | 1.502 s | 9.124 s | 6604/7620 MB | 804–881 MB |

The codec native portion alone falls within 10 s, but input-to-answer totals
do not. It is inappropriate to omit the measured preparation to declare the
owner's complete-answer latency bound passed. Independent component medians
need not sum to the median total.

For the full-frame profile, preparation takes medians 2.621–2.771 s and native
processing 32.129–33.132 s. Even eliminating the entire file/PNG packing overhead
would not bring that profile near 10 seconds. Codec c14 median stages are vision
3.988 s, prefill 3.600 s, decode 1.794 s, versus full-frame 17.386/12.683/2.734 s.
Its large speed improvement is real for these configurations; geometry, output
length and patch content also change, so it is not an isolated sparsity ablation.

Full-frame RAM peaks by c14/c11/c12: 6849/6891/6890 MB; inherited swap spans
781–794 MB across formal requests. Both profiles fit without OOM or killing
unrelated processes. The 500 ms tegrastats samples use one-second interval
padding because timestamps have second precision; short peaks may be missed.
Values are whole-device occupancy, not model-only allocations or proof of live
camera headroom. Sequential profiles share host cache/swap history.

Engine initialization takes 8.720 s (full) and 8.376 s (codec), excluded from
resident timing; these are process starts using retained assets/caches, not
fresh installation benchmarks. First full request is 36.020 s; first codec
request 11.701 s. All resources and raw stages remain separately archived.

## Comparison and disposition

Retained Qwen3-VL AWQ c14/16 at approximately 480p takes 4.454 s median and
recovers all four broad gesture states in order, but calls five fingers four.
The Mage full-frame control shares selected source frames but uses twice as
many visual tokens and a different native runtime; the codec arm shares source
sample IDs but uses selected patches and slightly different geometry. Neither
Mage arm improves the tested combination of latency and gesture quality.

Do not compare these phone/tool values with historical Qwen or Cosmos 12-frame
numbers as though they were matched 16-frame results. No new Qwen, Cosmos, live
camera or backend run was performed. No full Microsoft reference-logit parity,
long-video event recall, different GGUF quantizations or further kernel/context
optimization was tested.

The owner-retained Qwen3-VL Demo remains the preferred tested route. Mage's
codec speed benefit and better bounded phone-ending wording are retained as
component evidence; the tested Mage replacement does not pass the owner's
complete-answer/quality screen. This is more informative than the old mixed
cold-start/live-delay measurements, without claiming every alternative is ruled
out.

Inference processes and the experiment monitor are stopped. Old binaries,
models and Demo are preserved; HTTP 200 was verified. Post-run available RAM
5648 MiB, swap used 798 MiB, disk free 1.2 GiB. No partition modification,
deletion of old assets or new package installation occurred.

[Reproduction](../../experiments/mage_retest/README.md),
[evidence and hashes](evidence/2026-09-14-mage-retest/).
