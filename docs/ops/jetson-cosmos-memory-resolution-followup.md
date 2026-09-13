# Cosmos memory cleanup and 480p/720p follow-up

2026-09-13, 12:59–13:10 CST. **After temporary service/swap cleanup, true
12-frame 720p inference completed on this Orin Nano Super.** The earlier OOM
was real, but does not establish an unavoidable 720p hardware ceiling.
The cleanup changed several host conditions together; their individual memory
contributions were not isolated. This is a five-clip feasibility/quality probe,
not the publisher's exact benchmark or sustained Camera Edge acceptance.

## Owner disposition and next comparison

At 2026-09-13 13:21 CST, the owner assessed Cosmos Edge2-FlashHead as worth
trying, while still seeking a better alternative. Retain it as a trial candidate
and measured comparison baseline, with its environment, weights and raw evidence.
This assessment does not close the model search or establish Camera Edge acceptance.

Alternative-model evaluation remains open. Initially keep the external runner
simple and compare model capability on the same chronological input evidence:
gesture/action order, held-object changes, ending states, hallucination and
repetition. Prefer complete useful answers within 8 seconds; 8–10 seconds is
acceptable for this model screening, and a truncated answer is not a pass.
A replacement should improve semantic reliability within that budget; faster
completion alone is insufficient. Add fresh-video and missing mouse/greeting-wave
coverage before drawing broader conclusions. Sustained audiovisual scheduling
and Runtime integration remain later validation work. No new inference or
deployment was performed when recording this disposition.

## Actual memory findings and actions

- Before cleanup: 7619 MiB total, 4628 MiB available. No running experiment
  container or Ollama model. OpenClaw remained active, approximately 166 MiB
  service memory plus swapped pages; it was not interrupted.
- Root inspection identified nvargus-daemon, idle Ollama, Xorg and the GDM
  greeter as `/dev/nvmap` users. No process held `/dev/video0`; no desktop user
  was logged in beyond the greeter. Temporarily stopped `gdm.service`,
  `nvargus-daemon.service`, `ollama.service`. Available memory rose to 4810 MiB.
- Six ZRAM devices had higher swap priority than the existing 8 GiB NVMe swap
  file. Temporarily ran `swapoff` only on `/dev/zram0` through `/dev/zram5`;
  `/var/8GB.swap` stayed enabled. No files were removed, no boot configuration
  changed, and no reboot, driver/module replacement or OS upgrade occurred.
  Disabling ZRAM initially pages data back into RAM; the benefit under pressure
  is moving swapped CPU pages to the SSD instead of retaining compressed pages
  in physical memory needed by the GPU. This can introduce SSD paging latency.
- The old OOM log showed `kmalloc-256` using 843095 KiB, about 823 MiB, and
  roughly 938 MiB unreclaimable slab. After service cleanup this large kernel
  pool remained. Final available memory was 4848 MiB; unreclaimable slab
  937888 KiB. Stopping ordinary model processes did not eliminate it.

There is a closely matching first-party developer report for Argus on L4T
36.4.3: a per-frame `kmalloc-256`/host1x-fence leak, with an NVIDIA-provided
reference-release fix. The host version and pool match, **but this device lacks
a captured allocation stack proving the same cause**. Treat it as a suspected
driver leak, not a confirmed diagnosis. No patch or reboot was attempted.
[NVIDIA discussion and fix](https://forums.developer.nvidia.com/t/kernel-memory-leak-per-frame-with-argus-cameras-r36-4/325399).
The general temporary desktop/service and swap approach is also covered by
[Jetson AI Lab RAM guidance](https://www.jetson-ai-lab.com/tutorials/ram-optimization/).

## Paired resolution experiment

One resident engine ran c02, c08, c10, c11 and c12 at 832x468 and 1280x720,
alternating resolution within each case. All inputs contain exactly 12 uniformly
sampled frames; source hashes, frame indices, timestamps, prompt and decoding
parameters match within each pair. Actual visual token counts are 2340 and 5280.
Both arms use BF16/INT4 FlashHead, context 6144, 768 MiB KV, prefill batch 2048,
greedy decoding and 96 output tokens. Prefix/processor caching is off, preventing
cross-request encoder reuse. One warm-up per resolution and one formal request
per case/resolution: 12 total requests, 10 formal. This is not a repeatability test.

| Case | ~480p seconds / outcome | 720p seconds / outcome |
| --- | --- | --- |
| c02 screwdriver then lower | 3.867; tool correct, lowering omitted | 7.461; tool correct, lowering still omitted |
| c08 screwdriver | 3.625; tool correct, no empty-hand contradiction this run | 7.112; tool correct, no empty-hand contradiction |
| c10 palm → fist → thumb → V | 2.826; order correct | 7.740 to cap; repeats palm/thumb states, misses V |
| c11 phone front/back then lower | 2.912; invented thumbs-up, lowering omitted | 7.683; recognizes phone rotation and lowering, but claims empty hand when it is no longer clearly visible |
| c12 screwdriver → empty palm → lower | 4.161 to cap; vague object becomes repetitive needle labels | 6.151; screwdriver noun improves, but still treats sequential states as two simultaneous hands |

All five 720p requests returned without OOM; four naturally stopped at
6.151–7.683 s. The fifth was truncated and is not a complete usable answer.
Resolution affected the answers and improved some phone/tool descriptions, but
did not consistently improve temporal reasoning. The c08 contradiction from
the earlier run also disappeared in the new 480p arm; do not credit that change
specifically to 720p. Earlier runs had different engine context/cache settings.

Formal-request telemetry reached 7202/7620 MB RAM, 1974–2173 MB SSD swap and
69.937°C maximum reported junction temperature. Startup/warm-up are excluded
from these formal-window statistics. No live camera/audio processing, Runtime
connection, kernel leak reproduction or sustained thermal/P95 proof occurred.

## Retained state and evidence

The experiment container and telemetry are stopped; root SSH session closed.
Desktop greeter, Argus and idle Ollama remain temporarily stopped for this model
bench; ZRAM remains temporarily off, with SSD swap enabled. Their boot settings
are unchanged. OpenClaw and prior experiment/model/media assets remain.

To restore the temporarily paused facilities when needed:

```sh
sudo systemctl start gdm.service nvargus-daemon.service ollama.service
for z in /dev/zram0 /dev/zram1 /dev/zram2 /dev/zram3 /dev/zram4 /dev/zram5; do
    sudo swapon -p 5 "$z"
done
```

[Evidence bundle](evidence/2026-09-13-cosmos-memory-resolution/) includes paired
raw answers/config, exact runner, before/after memory and slab snapshots,
original OOM log and telemetry. Credentials were only used interactively and
were not written to experiment scripts or evidence files.
