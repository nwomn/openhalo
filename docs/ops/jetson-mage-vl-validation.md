# Jetson Mage-VL 4-bit validation

Status: 2026-09-10, native compilation and synthetic IQ4_NL/F16 plus target
Q4_K_M/Q8 image checks passed. Real-image quality, sustained latency/memory,
camera and Runtime acceptance remain pending.

The initial validation worker stopped because `/usr/bin/time` was absent.
The repaired worker uses Python wall-clock timing and tegrastats sampling.
Its existing-IQ4/F16 run exited 0 in 11.95 seconds including startup/loading,
correctly describing the red square on the left, blue circle on the right,
and OPENHALO text beneath them. This is one synthetic check, not a quality
benchmark or steady-state latency measurement. Both target downloads stopped
with HTTP/2 CANCEL errors; they were resumed with HTTP/1.1 and bounded retries.

## Scope and gates

Camera Edge v2 local inference experiment on the Orin Nano Super 8GB.
Keep the language backbone in 4-bit storage. First pass a synthetic single-image
load/shape/color/text check and record latency and memory, then review a real
image before enabling the camera. Continuous video and proactive streaming
need separate acceptance. No Runtime integration is part of this experiment.

## Verified starting point

- Jetson: ARM64, CUDA toolkit 12.6.85, Orin compute capability 8.7.
- SandLogic IQ4_NL model successfully downloaded and registered in Ollama.
- Ollama 0.11.4 failed image loading with `unknown projector type: magevl`.
  This failure does not establish whether memory is sufficient for inference.
- Ollama uses the owner's Windows Clash proxy at `192.168.0.15:7897`.
  Downloads depend on that host/address remaining reachable.

## Native runtime experiment

Author source: https://github.com/JohnTDI-cpu/mage-vl-gguf

- Author checkout: `f0df1fe6f13095a359ff38c7749279d5d6a8c60f`.
- Pinned llama.cpp: `a52077c4cabb4f3c0298329c9d2dd1324d5604cb`.
- Applied `patches/llama.cpp-mage-native-streammind.patch`; `git apply --check`
  passed. The additional codec/video patch is outside this single-image build.
- Author Dockerfile uses CUDA 12.8.1 and x86_64 stub paths, so it is not used
  as a validated Jetson image. Native CMake configuration passed with CUDA
  12.6, architecture 87, examples enabled, UI/tests disabled.
- Build target: `llama-mtmd-cli`, two parallel compiler jobs.
- Existing SandLogic projector reports `magevl`, 24 vision blocks, embedding
  size 1024, output size 2560, patch size 16 and spatial merge 2. Its digest
  differs from the author's F16 file; compatibility remains an empirical test.

Target files from https://huggingface.co/JohnTdi/Mage-VL-GGUF:

| File | Bytes | Expected SHA256 |
| --- | ---: | --- |
| mage-vl-backbone-Q4_K_M.gguf | 2716065152 | e8959bb666872d10cd826e0f76542a89e39e81dec18b2563ec3d281abfdd9fb0 |
| mage-vit-mmproj-Q8_0.gguf | 352742464 | 8a9d784e666f8178bc805b5a157ac56e52a66be9eef5a73035c746461df1d231 |

## Target Q4_K_M/Q8 check

The target pair completed a bounded native `llama-mtmd-cli` check on the
Jetson after both files reached their expected byte counts and SHA256 digests.
The command used the JohnTdi Q4_K_M backbone with the Q8 projector, GPU
offload (`-ngl 99`), the checked-in synthetic `shapes.png`, and the same
shape/color/text prompt used for the existing IQ4_NL/F16 comparison.

The process exited with code 0 in 9.9977 seconds wall time. It returned that a
red square is on the left, a blue circle is on the right, and `OPENHALO` is
visible below the shapes. Multimodal batch encoding took approximately 790 ms.
The resource trace observed up to about 5.6 GB of 7.6 GB RAM, about 1.0 GB of
swap, up to 99% GR3D utilization, and 57.2 C peak reported temperature during
the run. These are single-run observations, not sustained performance or
thermal limits. The llama.cpp warmup output also reported an existing flash
attention warning and does not change the successful exit or semantic result.

This accepts target-file integrity and one synthetic Q4_K_M/Q8 compatibility
check. It does not accept real-image quality, sustained latency/memory,
camera capture, structured Camera Edge output, or Personal Runtime integration.

## Example-image and repeated-run checks

The same verified Q4_K_M backbone plus Q8 projector completed bounded native
checks against the repository mage-vl-live-stream.png and mage-vl-studio.png
examples; both exited 0. The live-stream check described the paused video,
the man speaking into a microphone, the woman in a yellow vest, and visible
Mega Viz Media text. The studio check returned the visible coding-scene
caption. These are example-image checks, not owner-camera ground truth or a
general image-quality benchmark.

The follow-up repeated synthetic probe completed four cold-start runs. All
four exited 0 and matched the expected red-square, blue-circle, and OPENHALO
answer. Wall time was 9.156, 9.106, 9.094, and 8.454 seconds respectively,
for an 8.95-second average. Corrected parsing of 35 tegrastats samples
recorded peak RAM 5405/7620 MB, swap 1478 MB, GR3D 99%, and reported
temperature 58.812 C. This remains invocation-stability evidence; a
resident-process sustained resource capture is still a follow-up gate.

Because each run starts and exits the native CLI, this measures repeated
invocation stability rather than a resident service steady-state budget. The
remaining gates are real camera input, a longer resident-process benchmark,
structured Camera Edge output, and Personal Runtime integration through the
normal Gateway/Context/Presence path.

## Real-camera single-frame probe

On 2026-09-10 the Jetson CSI camera was visible as the IMX219 path behind
`/dev/video0`; the validated capture route used `nvarguscamerasrc` and
produced one local 1280x720 JPEG frame of 68,430 bytes. The verified Q4_K_M
backbone plus Q8 projector processed that frame with native
`llama-mtmd-cli`, exited 0, and completed in 9,825 ms. The returned answer
was: `Two people are sitting on a couch.`

The frame remained in the Jetson probe directory and was not uploaded to the
repository or sent through Personal Runtime. This accepts one bounded
real-camera-to-model inference path. It does not accept scene-quality
accuracy, repeated capture, service ownership/recovery, privacy/evidence
retention, structured Camera Edge output, or Personal Runtime integration.

The surrounding probe wrapper printed a trailing `bash: ... syntax error`
after the inference output. The capture and model process themselves reported
success (`INFERENCE_EXIT=0`); wrapper cleanup remains separate before it can
serve as reusable automation.

## Repeated real-camera probe

The corrected runner captured three consecutive 1280x720 CSI JPEG frames
through `nvarguscamerasrc`; their sizes were 65,725, 68,026, and 68,651
bytes. Each frame was consumed by the verified Q4_K_M backbone plus Q8
projector through native `llama-mtmd-cli`, and all three inference processes
exited 0. Cold-start wall time was 9,225 ms, 12,559 ms, and 16,150 ms
respectively, averaging 12,645 ms.

The returned descriptions consistently identified a person facing a computer
monitor in a dimly lit room; the model recovered only partial background text
such as `MAN`. This is useful path evidence, not a scene-quality or OCR
accuracy result. The 41-sample device trace reached about 5.3 GB of 7.6 GB
RAM, 99% GR3D utilization, and 59.7 C in its final samples; it remains a
repeated-invocation observation rather than a sustained service budget.

The frames remained on the Jetson probe directory and were not uploaded to
the repository or sent through Personal Runtime. This strengthens the
repeated camera-to-model path, but does not accept privacy/evidence retention,
service ownership/recovery, structured Camera Edge output, or Runtime
integration. The runner reached `CAMERA_REPEAT=PASS`; launcher cleanup is
still separate because the outer SSH wrapper emitted a stray CR warning.

## Structured real-camera output probe

A fresh CSI frame was captured locally and passed to the verified Q4_K_M
backbone plus Q8 projector. The native CLI exited 0 in 10023 ms,
and a local parser accepted exactly one JSON object with the bounded fields
`people_count`, `scene`, `readable_text`, and `confidence`. The accepted
probe result reported `people_count=1` and 0 readable-text item(s);
the scene field began: `a person sitting in a chair in a dimly lit room`.

The frame and structured result remain in the Jetson-local directory
/home/jetson/mage-validation/structured-20260910-175920. Nothing was uploaded to the repository or sent through
Personal Runtime. This validates a bounded model-to-Observation-shaped
payload, but it does not yet register a Camera Edge capability, apply
ContextFact/ContextEnvelope admission, enforce Runtime policy, or exercise
Presence, Action, or result verification.

## Device evidence and progress

All following paths are on Jetson:

- `/home/jetson/mage-build.log`: native build output.
- `/home/jetson/mage-download.log`: Q4 backbone transfer.
- `/home/jetson/mage-projector-download.log`: Q8 vision transfer.
- `/home/jetson/mage-validation/worker.log`: bounded validation worker.
- `/home/jetson/mage-validation/validate.py`: records separate existing IQ4/F16
  and target Q4/Q8 runs after build readiness; target files require SHA256 checks.
- Each run has `.result.json`, `.output.log`, and `.resources.log` artifacts.
  The worker stops waiting after four hours and limits each inference process
  group to ten minutes. Completion of the worker still requires output review.

For Windows CMD or PowerShell, use double quotes:

```text
ssh jetson "tail -n 5 /home/jetson/mage-build.log"
ssh jetson "tail -n 5 /home/jetson/mage-validation/worker.log"
```

No system service/autostart was added for the experimental runtime. Existing
Ollama model files are read in place and are not altered by the validation.

## Runtime-boundary adapter

The existing Camera Edge contracts are typed base Features such as
`camera.person_presence.v1` and `camera.scene_quality.v1`; the Mage-VL JSON
scene description is not admitted as either contract. The new
`device_edge/camera/mage_vl_observation.py` adapter validates the exact
bounded fields `people_count`, `scene`, `readable_text`, and `confidence`,
rejects ambiguity and unbounded values, and produces only a local semantic
understanding annotation without raw frames or raw CLI output.

This adapter intentionally does not emit `observation_push`, register a new
capability, or write ContextFact. A future `camera.semantic_cue_candidate.v1`
integration must add deterministic candidate gating, provenance, freshness,
privacy policy, and the ordinary Gateway/ContextFact/Presence path.
