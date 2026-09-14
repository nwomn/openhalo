# Mage-VL resident retest evidence

2026-09-14 owner-authorized replay. See
[report](../../jetson-mage-vl-retest-20260914.md).

- `full/` and `codec/`: exact config, initialization event, stderr and raw
  warm-up/formal answers. Each contains three clips, one warm-up plus three
  formal repetitions per clip. No generated reply is manually corrected.
- `codec/*-codec-selection.json`: actual 16 sampled IDs, per-source patch
  counts and codec-video-prep metadata. No raw images included.
- `resident.cpp`, `benchmark-full-executed.py`, `benchmark-codec-executed.py`:
  snapshots of executed native and Python source. The canonical Python runner
  later adds the codec profile without changing the completed full-frame run.
- `identity.json`: freshly verified model SHA256, native executable and linked
  library hashes. Stored weights are retained Q4_K_M/Q8; no new download.
- `matched-input-check.json`: every replay's source IDs/times/hash and prompt/
  cap checked against the retained Qwen3.5 inputs; different visual encoders,
  token counts and geometry remain explicitly recorded.
- `telemetry.log`, `summary.json`: whole-device 500 ms samples and request-time
  interval summaries. Intervals have a one-second timestamp precision pad;
  inherited swap is not isolated model memory. Summarizer is in experiment code.
- `SHA256SUMS`: hashes of every other evidence file, with relative paths.

Private MAGECV1 bundles, sampled frames and codec canvases stay on Jetson under
`/home/jetson/openhalo-mage-retest`. No camera/Runtime session was started.
Old environments remain intact; probe processes and telemetry were stopped.
