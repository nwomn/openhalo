# Mage-VL resident fixed-video retest

Completed results: [2026-09-14 report](../../docs/ops/jetson-mage-vl-retest-20260914.md).
Full-frame medians are 35.824/35.369/34.927 s; codec-selected medians are
10.849/11.136/10.626 s for gesture/phone/tool. Codec canvas geometry actually
resolves to 832x448 and 1456 visual tokens. Every source frame is represented
by selected patches in these three cases, with all native timestamp checks
passed. Gesture and tool errors persist; retain the Qwen3-VL combination.

Owner-authorized 2026-09-14 following the historical-run audit. This uses the
retained JohnTdi Q4_K_M backbone and Q8 vision projector on Jetson, with the
existing patched native libraries. No new model download, camera session,
StreamMind sidecar, Runtime connection or change to the retained Qwen Demo.

`resident.cpp` loads the two models and one language context once. Each input
line contains tab-separated MAGECV1 bundle paths for one request. Request KV
memory is cleared, embeddings freshly encoded and prefetched, and greedy
generation stops on EOG or 96 output tokens. Output includes native frame IDs,
timestamps, visual/prompt token counts, stage timings and finish reason. The
runner uses context 8192, batch 1024, ubatch 256, four CPU threads, CUDA flash
attention and full GPU layer offload. Only its own OOM score is increased.

`benchmark.py` checks pinned clip hashes and selects the same 16 rounded uniform
indices as the Qwen3-VL/Qwen3.5 tests. It runs one warm-up and three formal
repetitions per clip in one resident process. The neutral prompt and cap match;
chat serialization, visual encoding, quantization and greedy decoding differ.
Wall timing includes read/hash/decode/geometry/packing and native reply; engine
loading and original clip extraction are separate. Input construction is
repeated, not cached. This is bounded replay consistency, not held-out accuracy.

- `--profile full`: full patches for all 16 frames, no codec sparsification.
  Initial 832x468 RGB frames are resized to native 832x480 and stored losslessly
  inside four four-frame bundles in one request. There are 6240 visual tokens
  versus Qwen's 3120; this is a matched selected-frame comparison, not identical
  preprocessing or the best Mage compression recipe.
- `--profile codec`: installed codec-video-prep 0.2.5 H.264/HEVC bit-cost selection
  packs one 16-frame group into four canvases. Only its frame sampler is
  temporarily pinned to the matched indices; keyframe shifting is disabled.
  Default codec decoding/patch selection and native source positions are used,
  with fixed grouping and PNG output. Selected patches may exclude some sampled
  frame IDs; actual represented IDs and token counts are checked and reported.
  This differs from the old live producer's pixel-difference proxy. It is still
  the community preprocessing/runtime path, not full Microsoft numerical parity.

The experiment root is `/home/jetson/openhalo-mage-retest`, outside old model
environments. Compile against existing libraries, without modifying them:

```sh
g++ -std=c++17 -O3 -DGGML_BACKEND_SHARED -DGGML_SHARED -DLLAMA_SHARED \
  -I/home/jetson/mage-llama/include -I/home/jetson/mage-llama/ggml/include \
  -I/home/jetson/mage-llama/tools/mtmd resident.cpp \
  -L/home/jetson/mage-llama/build/bin \
  -Wl,-rpath,/home/jetson/mage-llama/build/bin \
  -lmtmd -llama -lggml -lggml-base -o resident
/home/jetson/mage-vl-gguf/.venv-codec/bin/python benchmark.py \
  --root /home/jetson/openhalo-mage-retest/NEW_RUN --profile full
```

Run profiles sequentially, collecting bounded host `tegrastats --interval 500`.
Keep generated bundles/canvases private; archive JSONL, config, logs, model and
binary hashes, source snapshots, resource summaries and checksum manifests.
Do not present full-frame results as reproducing sparse-token speedups or
truncated output as a valid complete answer.
