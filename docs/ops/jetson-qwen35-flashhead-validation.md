# Qwen3.5-0.8B FlashHead fixed-video validation

2026-09-14. The owner authorized this probe through the side discussion and
accepted the separate Hugging Face gate. Authenticated access changed from 403
to 200. This is a bounded model-only replay on the existing Orin Nano Super,
not a live-camera replacement or backend acceptance.

**Result: the checkpoint runs, but this tested configuration does not establish
an improvement over the retained Qwen3-VL combination.** It is modestly faster
on the matched gesture input while omitting a gesture; phone and tool/empty
transitions remain unreliable. Retain the existing live Demo.

## Model and runtime

- `embedl/Qwen3.5-0.8B-FlashHead`, pinned revision
  `6208c90544971d154eefc047e6f84d05326fa031`.
- All 14 files verified, 1,805,674,764 bytes. Actual safetensors contain 452 BF16
  tensors and 36 F32 tensors, including 153 visual tensors. The model card's
  FP16 description does not match those stored dtypes. This is not W4A16.
- The published `FlashHeadQwen3_5ForCausalLM` architecture label is incompatible
  with the intended full multimodal path. A separate runtime config selects
  `FlashHeadQwen3_5ForConditionalGeneration`; weights and original config remain
  unchanged. Vision and language weights loaded successfully; FlashHead was
  observed as an active module and lazily loaded from the tied embedding.
- New isolated container reuses the cached NVIDIA image layers, overriding
  Torch 2.10.0, torchvision 0.25.0, vLLM 0.19.0+cu126 and flash-head 0.1.10.
  Existing vLLM 0.14 and inspected 0.16 lack Qwen3.5. Setup logs preserve the
  resolved optional FlashAttention ABI and FlashInfer cache-version failures.
  Only the new container had those incompatible optional packages removed.
- BF16 execution, eager mode, one request at a time, context 6144, KV 768 MiB,
  prefill 2048, no prefix/processor cache, no audio or previous-answer context.
  The final startup utilization check is 0.30; explicit KV allocation overrides
  percentage-based KV sizing. This is not a hard 30% memory cap.
- Thinking disabled through the model's template; neutral retained prompt and
  96-token output cap. Requested sampling fields match the old benchmark, but
  FlashHead 0.1.10 intercepts logits and directly selects approximate greedy
  tokens. Normal temperature/top-p/presence-penalty behavior is bypassed for
  those tokens. This is a comparison of deployable configurations, not a
  controlled FlashHead-only or architecture-only ablation.

Reproduction code and dependency details: [experiment README](../../experiments/qwen35_flashhead/README.md).
Primary package/model references: [checkpoint](https://huggingface.co/embedl/Qwen3.5-0.8B-FlashHead),
[FlashHead source](https://github.com/embedl/flash-head),
[Jetson AI Lab wheels](https://pypi.jetson-ai-lab.io/jp6/cu126/).

## Inputs and review

Original private recording is
`/home/jetson/openhalo-specialist-expanded/fresh-2157/capture.mp4`, SHA256
`c5b1e31ee2cad15472fc20996adc3f2ff898ff018eb1b2b5c0af063195d97728`.
Reuse frozen 4-fps intermediate clips. Uniform16 uses rounded linspace indices;
read/decode/resize produces 16 RGB frames at 832x468. The processor produces
832x480, 3120 visual tokens and eight chronological frame-pair timestamps.
Every reply passed actual visual-token and timestamp checks. A startup warning
about a two-frame maximum originates in vLLM's dummy-input profiler; the real
request assertions confirm all sixteen sampled frames were encoded.

The actual sampled contact sheets were reviewed, with labels kept outside the
prompt. They remain private under the Jetson experiment root.

| Clip | Source interval | Visible reference |
| --- | --- | --- |
| c14 | 28.5–35.5 s | One empty hand: five-finger palm, fist, thumbs-up, V; ends V |
| c11 | 36–43 s | Raises phone, shows front then back, lowers it; hands leave view, so visible empty ending is unconfirmed |
| c12 | 43–54 s | Shows/rotates screwdriver, lowers it, shows empty five-finger palm, lowers hand; final hands leave view |

The c14 input matches the retained Qwen3-VL 480p/16-frame run in source hash,
frame indices, dimensions, visual tokens and timestamps. Its neutral prompt
text and output limit also match; model chat templates and decoding differ.
New phone/tool 16-frame results have no old 16-frame baseline. An extra phone
12-frame run used rounded linspace, unlike the old floored 12-frame selections;
its speed must not be presented as an exactly matched old-model comparison.
Cosmos has no retained c14/16-frame result and is not assigned one here.

## Resident results

One warm-up per profile, then three seed-0 repetitions, with rotating profile
order when two profiles were present. Timing includes clip read/hash/decode/
resize and model preprocessing through the returned answer. Prior extraction,
initialization, live capture, UI and Runtime are excluded. Repeated same-input
results measure bounded consistency, not general accuracy or event latency.

| Configuration | Median / range | Output | Reviewed result |
| --- | --- | --- | --- |
| Retained Qwen3-VL AWQ, c14/16 | 4.454 / 4.431–4.487 s | 48 tokens, natural stop | All four gesture states in order, but five fingers called four |
| Qwen3.5 FlashHead, c14/16 | 3.643 / 3.622–3.770 s | 31 tokens, natural stop | Omits initial palm; fist→thumbs-up→V and empty ending correct; no finger-count claim |
| Qwen3.5 FlashHead, c11/16 | 3.666 / 3.665–3.670 s | 32 tokens, natural stop | Phone recognized, false thumbs-up, front/back change omitted, unsupported visibly-empty ending |
| Qwen3.5 FlashHead, c12/16 | 8.345 / 8.310–8.565 s | 96 tokens, all truncated | Screwdriver called syringe; repeats waving, misses object→empty-palm transition and ending |
| Qwen3.5 FlashHead, c11/12 supplementary | 5.374 / 5.300–5.573 s | 59 tokens, natural stop | Phone recognized, vague/redundant holding sequence, unsupported empty ending |

The matched c14 returned answer is about 0.81 s sooner, but also 17 tokens
shorter and semantically less complete. This does not establish an intrinsic
18% compute speedup. The tool run's 8.35 s is **time to truncation**, not time to
a completed valid answer; it does not satisfy the owner's complete-answer
screening criterion. All three formal repetitions share the same text within
each configuration. The tool warm-up differs slightly in wording but has the
same failure. Fewer phone frames produced a longer answer and higher latency,
so frame count alone does not determine end-to-end time.

## Memory and cold/resident separation

Host tegrastats samples every 500 ms. These are whole-device RAM and inherited
swap, not isolated model allocation. Per-request intervals have a one-second
boundary pad because tegrastats timestamps have second precision. Phone profiles
share a resident process and allocator state; their peaks are not independent
minimum-memory measurements. Sampling can miss shorter peaks.

| Formal run | Whole-device RAM peak / total | Swap range |
| --- | --- | --- |
| c14/16 | 7212 / 7620 MB | 1654–1681 MB |
| c11/16 | 7351 / 7620 MB | 1322–1402 MB |
| c11/12 | 7351 / 7620 MB | 1253–1402 MB |
| c12/16 | 7296 / 7620 MB | 1158–1268 MB |

This smaller parameter count has not demonstrated ample live-camera memory
headroom. Earlier roughly 5.8 GB readings were startup/tuning, not the full
request peak. The existing live Qwen measurements were from different runs and
workloads and are not a controlled memory comparison.

The first successful engine construction took 278.045 s, after earlier setup
attempts had populated some compilation cache. Its first c14 request took
27.412 s; subsequent requests took 3.622–3.770 s. Cached later engine construction
took 41.764 s (phone) and 43.063 s (tool); first phone-12 request 19.766 s,
subsequent phone-16 warm-up 4.246 s, first tool request 19.772 s. These cold/first
request times remain separate from formal resident timing. Initial setup also
included a manually interrupted autotuning attempt and one startup free-memory
threshold rejection. No formal run hit OOM, but that does not prove sustained
live stability.

## Disposition and evidence

Bounded fixed-video validation is complete. Do not replace the retained live
Qwen3-VL combination on this evidence. The tested checkpoint/runtime has useful
phone naming and partial gesture order, but no demonstrated overall semantic
upgrade. Compiled/CUDA-graph optimization, ordinary non-FlashHead decoding,
larger holdout evaluation, live buffer contention, audio and Runtime integration
were not tested. No claim about all Qwen3.5 variants follows from this probe.

Experimental inference container, bounded telemetry and temporary loopback proxy
were stopped. Original Demo HTTP endpoint still returned 200. Device after
cleanup: no running Docker containers, 4849 MiB available RAM,
784 MiB swap used, 3.3 GiB filesystem free. Downloaded assets and the isolated
runtime are retained for reproduction; old model environments remain intact.

[Raw answers, configs, logs, hashes, matching check and resource summary](evidence/2026-09-14-qwen35-flashhead/).
[Retained Qwen comparison](jetson-qwen3-vl-highframe-validation.md).
This record adds completed experimental evidence; it changes no Camera Edge,
M17.10, backend or owner acceptance status.
