# Qwen3.5 FlashHead fixed-video probes

Owner-authorized on 2026-09-14 through the side discussion; gate approval confirmed
by authenticated config HTTP 200 after the owner accepted the new repository gate.
Original stable Qwen3-VL Demo and Cosmos environments remain separate and retained.

- Model: `embedl/Qwen3.5-0.8B-FlashHead`
- Revision: `6208c90544971d154eefc047e6f84d05326fa031`
- Source: `/home/jetson/openhalo-specialist-expanded/fresh-2157/capture.mp4`
- Primary matched input: existing c14, source 28.5–35.5 s, uniform 16 indices
  from the existing 28-frame 4-fps intermediate, resized to 832x468 before the
  model processor. Reuse actual frame indices, prompt and 96-token limit.
- Existing comparison is community AWQ Qwen3-VL-2B. Cosmos lacks a c14/16-frame
  baseline; do not present its other-clip/12-frame timings as matched results.
- Quality review: gestures/order, hand count/finger count, held objects, ending
  state, repetitions/truncations and unsupported claims. References stay outside
  the prompt. Only source-supported actions/objects can be scored.
- Report read/preprocess through completed answer, separately from model loading
  and warm-up; include actual model frame dimensions/timestamps/tokens and system
  RAM/swap. No live camera or backend modification belongs to this probe.

`fetch_assets.py` downloads only the pinned repository using the existing Jetson
HF login, checks sizes and LFS SHA256, and keeps model assets outside Git. The
temporary reverse-SSH proxy is loopback-only and should close after downloads.
Model card says FP16; config declares BF16. Actual tensor dtypes must be inspected
and runtime dtype reported; this artifact is not W4A16.

Compatibility preflight: the existing cached image has vLLM 0.14.0+cu126,
Torch 2.9.1 and Transformers 4.57.6, with no qwen3_5 model implementation.
The published architecture is FlashHeadQwen3_5ForCausalLM, while 488 indexed
tensors include model.visual.* and model.language_model.*. Verify any runtime-only
architecture correction and full vision weight loading rather than silently
running a text-only route. Original checkpoint config must be retained unchanged.

Fixed-video validation is complete. Matched c14/480p/16-frame resident median
is 3.643 s, versus retained Qwen3-VL 4.454 s, but initial palm is omitted.
Phone naming works with false gesture/ending claims; screwdriver becomes syringe
with repeated truncated output (8.345 s). No live replacement is supported.
See [full report](../../docs/ops/jetson-qwen35-flashhead-validation.md).


## Isolated runtime recipe

Container `openhalo-qwen35-flashhead-20260914` reuses the cached NVIDIA image
`ghcr.io/nvidia-ai-iot/vllm@sha256:15b41320647ebbaa4547b96bbb027d4816e8cb1ee018fda3ebaba1c8056291ed`.
Mount the new `/home/jetson/openhalo-qwen35-flashhead` at `/work`, retained
Qwen root at `/comparison:ro`, and Cosmos root at `/baseline:ro`; NVIDIA runtime,
host network, 1 GiB shared memory, no camera device, no restart policy.

Install overrides with `PIP_CONSTRAINT=` and `pip --no-deps --no-cache-dir
--target /work/runtime-packages`. Invoke Python with
`PYTHONPATH=/work/runtime-packages`, leaving old containers untouched.

Verified core: Jetson AI Lab aarch64/Python 3.10 wheels for Torch 2.10.0,
torchvision 0.25.0, vLLM 0.19.0+cu126. Torch CUDA and `vllm._C` imports passed.
The downloaded vLLM 0.16.0 lacks Qwen3.5 and was not installed.
Overrides: flash-head 0.1.10, compressed-tensors 0.14.0.1,
flashinfer-python/cubin 0.6.6, opencv-python-headless 4.11.0.86,
xgrammar 0.1.32, protobuf 6.33.5. Transformers 4.57.6 and Triton 3.5.1
are inherited. Remove **only in the new container** the incompatible optional
flash-attn 2.8.3 (Torch 2.9 ABI) and flashinfer-jit-cache 0.5.3.
vLLM uses its own FlashAttention implementation after removal.

Run `prepare_runtime.py` to create symlinks plus a corrected config view;
retain original assets. Start with `benchmark.py --output /work/private/NEW_RUN`.
`--compiled` permits a separately labeled graph/compile probe, and `--case c11`
or `--case c12` selects retained phone or object-to-empty clips. Default is c14,
480p/16 frames, eager mode, BF16, thinking disabled, 96 output tokens.
Set `TRITON_PRINT_AUTOTUNING=1 TRITON_CACHE_AUTOTUNING=1` for transparent,
persistent one-time linear-attention tuning. Record host `tegrastats --interval
500` separately; do not leave a monitor running indefinitely.

FlashHead 0.1.10 directly calls `get_next_token` with `do_sample=False` and
bypasses ordinary sampling/penalties for intercepted tokens. Although requested
sampler parameters are recorded, this is approximate greedy decoding, not
identical decoding to the retained recommended-sampling Qwen3-VL run.

## 2B follow-up

The separately authorized `embedl/Qwen3.5-2B-FlashHead` probe is complete at
revision `17f56ded573393020f0db622e15a17c19ce0cbd5`. Reuse this isolated container
and runtime, with assets/results under `/work/variants/qwen35-2b`. The original
FlashHead loader was manually stopped under severe memory pressure before a
video reply. Successful runs opt into `share_flashhead_weight.py`: share the
existing CUDA BF16 vocabulary matrix, retain CPU FP32 centroid preparation,
avoid a duplicate 0.947 GiB GPU matrix. Stored checkpoint assets are unchanged.
This adapter is specific to the tested single-process full-vocabulary BF16
path; it asserts shape, dtype, CUDA location and storage identity.

After downloading with `fetch_assets.py --model MODEL --revision REVISION
--root /work/variants/qwen35-2b`, prepare and run inside the existing
experimental container with `PYTHONPATH=/work/runtime-packages`:

```sh
python /work/qwen35_flashhead/prepare_runtime.py --assets /work/variants/qwen35-2b/assets
TRITON_CACHE_AUTOTUNING=1 python /work/qwen35_flashhead/benchmark.py \
  --model-dir /work/variants/qwen35-2b/assets/runtime-model \
  --model-id embedl/Qwen3.5-2B-FlashHead \
  --revision 17f56ded573393020f0db622e15a17c19ce0cbd5 \
  --max-model-len 4096 --kv-cache-mib 192 --oom-score-adj 800 \
  --share-flashhead-weight --case c14 \
  --output /work/variants/qwen35-2b/private/NEW_RUN
```

Run c11 and c12 sequentially in fresh processes with distinct output paths;
record host telemetry. Do not run these concurrently on this device. With the
full model stopped, `python /work/qwen35_flashhead/check_weight_sharing.py`
checks a synthetic GPU fixture against the publisher's dense-copy construction:
32 selected tokens and all state tensors match, with shared vocabulary storage.
This is not full-checkpoint numerical equivalence.

2B c14/phone/tool medians were 12.486/9.514/9.116 s, with peak whole-device RAM
7473–7498/7620 MB and swap 2650–2837 MB. It restores the initial palm missed by
0.8B but still miscounts fingers, mislabels screwdriver as syringe and gives
unsupported ending claims. Retain the current live Qwen3-VL configuration.
See [2B report](../../docs/ops/jetson-qwen35-2b-flashhead-validation.md).
