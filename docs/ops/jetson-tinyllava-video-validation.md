# TinyLLaVA-Video on Jetson: 2026-09-12 validation

**Disposition: the tested configurations fail Camera Edge v2 minimum usability.**
The model produced a useful eating description for one owner-referenced clip,
but the best warmed replay took 8.97-9.21 seconds. This exceeds the five-second
target even before live capture, event confirmation, transport or Runtime.
No v2 milestone or general scene accuracy is accepted.

## Input and semantic result

The owner reported: "looking at the screen while eating." A fresh CSI IMX219
mode-4 clip was captured locally at 1280x720, with 360 frames over 5.992833
seconds. The clip SHA256 is
`50fd596d9d98ddd604633bc639c5cf3f2fd237cbcfc72d9067fa6cf8ee72b121`.
A preview showed a person holding food. Raw video and preview stay outside Git
and were not uploaded to a model provider.

The prompt asked for a short visible action/change description without guessing
intent or identity. It did **not** contain the owner's activity label. Both
successful configurations returned the same 17-token answer on all three
replays each:

> The person is eating a snack, and the background remains unchanged throughout the video.

This supports useful recognition of eating in this clip. It does not establish
screen-directed attention, temporal action transitions, multi-scene accuracy,
identity, or intent. Six replays of one clip are not six independent accuracy
cases. The earlier owner-reported all-unknown Isaac ROS cases remain failed;
this experiment does not reclassify those results.

## Exact configuration and compatibility work

- Jetson Orin Nano Super 8GB, reported `MAXN_SUPER` power mode; camera, cooling
  and power settings were not changed.
- Author checkpoint `Zhang199/TinyLLaVA-Video-Qwen2.5-3B-Group-16-512`, revision
  `490db36363bae6e6653e2ad09d2041a4a9a33f29`: 3,629,878,336 BF16 parameters,
  7,259,885,208 bytes across two weight shards. Downloads and Jetson transfers
  were size/SHA256-verified. [Asset manifest](evidence/2026-09-12-tinyllava-video/asset-manifest.json).
- Author source revision `44e162fa0ce6ea5f166cbfc6c1130465f82fd81a`.
- Isolated environment retained NVIDIA PyTorch `2.5.0a0+872d972e41.nv24.08`,
  CUDA 12.6; used Transformers 4.40.1 and bitsandbytes 0.48.2.
- Packaged bitsandbytes CUDA kernels failed an NF4 smoke probe. Source revision
  `b48ecdb3c7fe7bc0c467a015177258b35dfbc3ce`, built for SM87, passed afterward.
- Omitted eager training/dataset imports in a separate source copy. The wrapper
  explicitly passes quantization arguments omitted by upstream's loader.
- Maintained 16 uniformly sampled frames, original 384-pixel SigLIP processing,
  original 512-token Group Resampler, and original `qwen2_base` prompt template.
- All runs were local-only and offline after model transfer. No Runtime
  registration, Observation publication, provider call or user-facing action
  was performed by the experiment.

## Results

| Configuration | Outcome |
| --- | --- |
| v1: language linears NF4; vision/connector FP16 | 252 quantized linears, checkpoint load 33.22 s, no key mismatch. Kernel OOM killed PID 118819 before first output at 18:59:55 local. |
| v2: same precision; single Inductor compiler worker, cache release, CUDA allocation ceiling | Loaded in 28.36 s; vision and connector completed. Kernel OOM killed PID 119186 during language generation at 19:02:47. Loaded CUDA allocation was 3.76 GB. |
| v3: extended NF4 to vision/connector | Loaded, but SigLIP pooling attention directly used a quantized projection weight and failed with Half/Byte dtype mismatch. This was a compatibility failure. |
| v4: NF4 supported linears, preserving SigLIP pooling head in FP16; vision batch 1 | 430 quantized linears, all checkpoint keys matched. Load 22.40 s; first replay 13.89 s; warmed replays 9.58 and 9.40 s. Correct eating description. |
| v5: v4 precision; vision batch 4, last-position-only language logits | Same description. Load 22.56 s; first replay 13.23 s; warmed replays 9.21 and 8.97 s. Still fails five-second gate. |

v5's last-position projection avoids calculating vocabulary logits for unused
prefill positions during generation. It is an inference-only optimization, not
a training change. It and frame batching were changed together, so this small
comparison does not isolate their individual contributions. Output agreement
was checked on this clip only.

Warmed stage medians:

| Stage | v4 | v5 |
| --- | --- | --- |
| Clip decoding and preprocessing | 1.793 s | 1.828 s |
| Vision encoding | 3.723 s | 3.220 s |
| Group Resampler | 0.224 s | 0.231 s |
| Remaining generation path | 3.751 s | 3.809 s |
| Total completed response | 9.490 s | 9.089 s |

These are two warmed repeats per configuration, not a statistically accepted
P95 or a continuous-stream benchmark. Even generation alone remained around
7.2-7.7 seconds after preprocessing.

Across the complete v5 process window, including model loading, `tegrastats`
reported RAM peak 7498/7620 MB, swap peak 3312 MB, GR3D peak 99%, temperature
peak 62.375 C, and board-input power peak 22.186 W. Existing swap use was already
present before the run; nevertheless usage increased materially. This does not
establish a no-swap or sustained-resource operating profile. No BF16/FP16
unquantized semantic control was feasible in this check, so the effect of
aggressive quantization on quality is unmeasured.

Evidence: [v4 report](evidence/2026-09-12-tinyllava-video/all-nf4-v4-report.json),
[v4 summary](evidence/2026-09-12-tinyllava-video/all-nf4-v4-summary.json),
[v5 report](evidence/2026-09-12-tinyllava-video/all-nf4-v5-report.json),
[v5 summary](evidence/2026-09-12-tinyllava-video/all-nf4-v5-summary.json).
Full logs and failure reports remain in the Jetson's
`/home/jetson/openhalo-tinyllava-video/results-*` directories.

## Host cleanup and final state

The owner authorized cleanup unrelated to the validation. Regenerable pip and
uv caches plus unused Docker build cache were removed. Free disk increased
from approximately 12 GiB to 23 GiB before model transfer. APT cleanup required
sudo and was not performed. Existing Docker images/volumes, model files, source
trees and earlier experiment evidence were preserved. The old Isaac ROS preview
and its Argus children were stopped. The temporary capture and TinyLLaVA
benchmark processes ended; no resident TinyLLaVA service or autostart was added.

## Next boundary

This bounded check is complete with **latency failure**, one positive semantic
case, and substantial memory pressure. Do not describe the current recipe as
usable pending more ordinary scene tests. MobileVLM V2 remains the next
owner-selected comparison candidate; it was not deployed in this check.
Further TinyLLaVA work would require a specific new performance or hardware
hypothesis rather than repeating the unchanged recipe.

Reproduction scripts and dependency details:
[experiment README](../../experiments/tinyllava_video/README.md).
