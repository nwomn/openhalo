# MobileVLM V2 1.7B Jetson probe

Bounded Camera Edge experiment, separate from the closed TinyLLaVA environment.
No Runtime admission or service installation. Raw camera media stays outside Git.

The official MobileVLM source is pinned to
`688fdec914810485c8766da96c63d9d2ce15f750`; the checkpoint is
`mtgv/MobileVLM_V2-1.7B@9a5b623a83feae6a6b2ecad7a843334ccc119ce1`.
Download metadata and SHA256 checks accompany each evaluation.

1. Run `fetch_assets.py --dest <private-assets-directory>` on a host with access
   to Hugging Face, then transfer `model/`, `clip/`, and `asset-manifest.json`.
2. On Jetson, create a separate Python 3.10 venv with `--system-site-packages`
   to preserve NVIDIA PyTorch. Install with `--no-deps --no-cache-dir`:
   `transformers==4.33.1 tokenizers==0.13.3 accelerate==0.27.2`
   `huggingface-hub==0.25.2 safetensors==0.4.5 timm==0.9.12 einops==0.8.0`.
   Existing NVIDIA torchvision and sentencepiece are required. Do not install
   upstream training requirements or replace NVIDIA torch.
3. Run `prepare_runtime.py --source <pinned-clone> --output <fresh-runtime>`.
   The sole source patch constructs the dummy CLIP tower from local config;
   actual vision weights must match the outer V2 checkpoint without missing keys.
4. Run `convert_checkpoint.py --assets <assets>` to verify transfers and write
   lossless safetensors shards using memory-mapped `weights_only` loading.
5. Run `benchmark.py --runtime <runtime> --assets <assets> --image <image>`
   `--image <another-image> --output <fresh-results> --repeats 3`.
   Defaults: FP16, upstream v1 conversation template and pad/336px processor,
   greedy generation, 48-token ceiling. Action references and filenames are
   not inserted in the prompt. Each inference re-reads and preprocesses its image.
6. Run `summarize.py <results>` and assess raw outputs against independently
   selected references. Warm timings exclude the first inference, model load,
   capture/event selection and Runtime. Replays are not independent accuracy
   cases or a reliable P95 estimate. An output reaching its token ceiling is flagged.

Optional `--nf4` quantizes only language linears with bitsandbytes; it requires
an independently verified SM87/CUDA 12.6 build. Optional `--last-token-logits`
avoids unused prefill output projections and is inference-only. Report each
changed recipe separately, including any semantic differences.

A useful single-frame caption is not evidence of temporal process understanding.
The five-second event-label requirement and previous failed-route dispositions
remain unchanged.

For the separately reported process probe, replace the `--image` arguments
with `--sequences <manifest.json>` and supply a chronological prompt. The JSON
contains a list of objects with `name` and ordered absolute `images` paths.
The runner uses one image marker per frame and vision microbatch 1. This is an
experimental multiple-image input to the image-trained model; its tested
raise/lower ordering failed. Token-limited results are never counted as complete.

See [the validation report](../../docs/ops/jetson-mobilevlm-v2-validation.md)
for single-frame speed, hallucination, memory and temporal-understanding limits.
