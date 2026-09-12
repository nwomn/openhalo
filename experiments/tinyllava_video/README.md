# TinyLLaVA-Video bounded Jetson validation

This is a local-only Camera Edge v2 experiment. No model prose is admitted to
Runtime, no capability is registered, and no camera media is uploaded to a
provider. The owner selected this candidate after the previous four v2
implementations failed minimum usability.

2026-09-12 result: **the tested recipe fails minimum usability on latency**.
It described eating correctly on one owner-referenced clip, but its best warmed
completed response took 8.97-9.21 seconds, excluding capture and Runtime.
[Results and evidence](../../docs/ops/jetson-tinyllava-video-validation.md).

## Exact candidate

- Source: `https://github.com/ZhangXJ199/TinyLLaVA-Video`, revision
  `44e162fa0ce6ea5f166cbfc6c1130465f82fd81a`.
- Checkpoint: `Zhang199/TinyLLaVA-Video-Qwen2.5-3B-Group-16-512`, revision
  `490db36363bae6e6653e2ad09d2041a4a9a33f29`; 3,629,878,336 BF16 parameters.
- Preserve 16 uniformly sampled frames, original SigLIP 384 preprocessing,
  original Group Resampler (512 tokens), and `qwen2_base` prompt template.
- Initial language-only NF4/FP16-vision recipe hit OOM. The completing recipe
  uses NF4 double quantization for supported language, vision and connector
  linears, retaining embeddings, language output head, SigLIP pooling head
  and normalization in FP16. Its quantization-quality cost is not measured.
- Vision frame microbatching bounds activation memory without dropping frames.
- First gate: a useful description of the owner's actual scene. Second gate:
  completed result within the existing five-second budget. Repeated outputs
  from one clip establish invocation behavior, not multi-scene accuracy or P95
  acceptance. Timings here exclude live capture, event confirmation and Runtime.

## Assets and isolation

On the Windows download host:

```powershell
python experiments/tinyllava_video/fetch_assets.py --dest D:\openhalo-tinyllava-assets
```

`fetch_assets.py` pins the model revision, resolves and records the processor
config revisions, downloads only inference assets, and checks size/SHA256.
Copy these assets once to `/home/jetson/openhalo-tinyllava-video/assets/`; verify
the transferred files against `asset-manifest.json`. The Jetson runtime runs
offline. Do not put weights or private camera clips in Git.

The Jetson environment is `/home/jetson/openhalo-tinyllava-video-venv`, created
with `--system-site-packages` to retain NVIDIA PyTorch 2.5.0a0 nv24.08/CUDA 12.6.
Inference dependencies installed locally with `--no-deps` were Transformers
4.40.1, tokenizers 0.19.1, accelerate 0.27.2, huggingface-hub 0.25.2,
bitsandbytes 0.48.2, safetensors 0.4.5, einops 0.8.0 and einops-exts 0.0.4;
sentencepiece 0.2.0 was already present. Do not install upstream's full training
dependency list or replace the board's NVIDIA torch build.

The bitsandbytes wheel failed its NF4 CUDA probe. The working local backend was
built from revision `b48ecdb3c7fe7bc0c467a015177258b35dfbc3ce` (tag 0.48.2):

```bash
cmake -S . -B build-jetson -DCOMPUTE_BACKEND=cuda \
  -DCOMPUTE_CAPABILITY=87 -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc
cmake --build build-jetson -j 2
```

Only the isolated environment's `libbitsandbytes_cuda126.so` was replaced;
the original wheel library was preserved with suffix `.wheel-original`.
A 256-by-256 NF4 linear-layer CUDA inference returned finite values afterward.

## Run

Create a fresh inference-only copy with `prepare_runtime.py`. It verifies the
upstream revision and omits eager training/dataset imports; model and prompt
implementations remain upstream. The benchmark explicitly passes quantization
kwargs because upstream's normal loader builds them but omits them from its
`from_pretrained` call.

```bash
VENV=/home/jetson/openhalo-tinyllava-video-venv
EXP=/home/jetson/openhalo-tinyllava-video
$VENV/bin/python $EXP/prepare_runtime.py \
  --source /home/jetson/openhalo-tinyllava-video-src --output $EXP/runtime
timeout --signal=TERM --kill-after=10s 240s $VENV/bin/python -u $EXP/benchmark.py \
  --runtime $EXP/runtime --assets $EXP/assets --video /absolute/path/to/clip.mp4 \
  --output $EXP/results-new --repeats 3 --quantize-vision \
  --vision-batch 4 --last-token-logits --cuda-memory-fraction 0.55
$VENV/bin/python $EXP/summarize.py $EXP/results-new
```

Use a new result directory per configuration. The benchmark records raw model
text, input hashes/frame indices, prompt, loading-key checks, actual quantized
layer count, stage latency, and CUDA allocation. `tegrastats.log` records system
RAM/swap, GPU, power and thermal behavior. Inductor compilation concurrency is
limited to one; the CUDA allocator has a configurable memory ceiling. The
telemetry child terminates if its parent dies. A hard kill can still leave an
unfinished report; explicitly annotate it from process/kernel evidence.

`--last-token-logits` projects only the last hidden position into vocabulary
logits, which is sufficient for generation and avoids unused prefill logits.
It must not be used for training/loss computation. The batch-4/last-token
configuration matched the batch-1 baseline's answer on this clip; this is not
a general equivalence test across all inputs. Both configurations remain too
slow for the five-second target.

Owner labels belong in a separate reference artifact and must not be included
in the model prompt. The 2026-09-12 clip was reported by the owner as looking at
the screen while eating; the exact selected frame sequence should be inspected
before evaluating more specific claims about food, screen visibility or motion.
