# OpenHalo Isaac ROS Argus input experiment

Current disposition (2026-09-12): the tested detection/pose/region route and
its temporal-feature-to-small-LLM extension failed the owner's minimum Camera
Edge usability requirements. The owner reports that the previously requested
real-scene cases were already tested and their relevant state/semantic outputs
were all `unknown`; per-case logs and numerical accuracy were not supplied in
this correction. Input FPS, detection output, fixture tracking, and JSON/gating
checks below remain component evidence, not usable perception acceptance.
The commands below are historical/reproduction procedures, not a recommendation
to repeat the same scene tests on the unchanged implementation. New work needs
a concrete change addressing the failure. See `Project.md` for current status.

This directory owns the first OpenHalo-specific Camera Edge input wrapper for
the Jetson IMX219 CSI camera. It is deliberately a data-plane experiment: it
does not register a Device Edge, write ContextFact, invoke Personal Runtime,
or retain image evidence.

## Configuration

`argus_imx219_mono.launch.py` loads the OpenHalo C++ component shim around
NVIDIA's `ArgusMonoNode` and explicitly passes:

- `camera_id=0`
- `module_id=0`
- `mode=4` (`1280x720` at `60 FPS` on the validated IMX219)
- `framerate=60` through a pre-load GXF parameter override
- `camera_info_url` pointing at `imx219_1280x720.yaml`

The wrapper preserves the official topics `/left/image_raw` and
`/left/camera_info`. The released Isaac ROS node has a `framerate: 30` value
hard-coded in its GXF YAML and does not expose it as a ROS parameter, so the
OpenHalo shim applies the requested rate before the graph is loaded. This is
why the experiment owns a small C++ component instead of only a Python launch
file.

The YAML uses the `rational_polynomial` model with eight zero coefficients so
the GXF/NITROS camera-info conversion has a supported, mode-matched shape. Its
intrinsics are an experimental pinhole estimate, not a measured calibration.
Do not use this file for metric geometry, rectification quality claims, or
production user-state inference until a checkerboard calibration is captured
for this exact sensor mode.

## Jetson run

Run from a shell where ROS 2 Humble is sourced:

```bash
source /opt/ros/humble/setup.bash
cd /tmp/openhalo-isaac-ros/ros_package
colcon build --symlink-install
source install/setup.bash
cd /tmp/openhalo-isaac-ros
./run_60s.sh --duration 10 --restart-duration 10 --output-dir /tmp/openhalo-argus-smoke
./run_60s.sh --duration 60 --restart-duration 10 --output-dir /tmp/openhalo-argus-60s
```

The runner starts the launch file, subscribes to both ROS topics, records
header-timestamp continuity, estimates dropped frames, captures launch-log
frame-drop/conversion/crash markers, samples `tegrastats` when available, and
then performs a fresh restart smoke. The report is written to
`<output-dir>/report.json`; phase logs remain under `main/` and `restart/`.

The default acceptance gate requires:

- the Argus process to stay alive for the requested phase;
- image and camera-info messages with `1280x720` dimensions;
- `rational_polynomial` camera info with eight coefficients;
- monotonic non-zero image header timestamps with no gap over `200 ms`;
- at least `45 FPS` effective header rate for the mode-4 target;
- estimated header-interval drop ratio no higher than `5%`;
- no detected frame-drop, unsupported-camera-info, or crash markers in the
  launch log; and
- the restart phase to pass the same checks.

An accepted report still means only that the camera input contract is stable;
it does not accept detection, pose, tracking, temporal fusion, semantic intent
or interruptibility inference, or Personal Runtime admission.

## Low-level visual feature validation

`visual_features.py` is the next bounded experiment. It subscribes to the
validated `/left/image_raw` topic, keeps only the newest image, and runs the
Jetson TensorRT engines for COCO object detection and human pose. It projects
person centers into normalized `left`, `center`, and `right` regions and emits
local-only summaries corresponding to the future
`camera.person_presence.v1`, `camera.object_presence.v1`,
`camera.region_occupancy.v1`, and experimental `camera.pose.v1` surfaces. It
does not publish observations, retain frames, or connect to Personal Runtime.

On the Jetson, after the Argus wrapper package has been built:

```bash
source /opt/ros/humble/setup.bash
source /tmp/openhalo-isaac-ros/ros_package/install/setup.bash
cd /tmp/openhalo-isaac-ros
./run_visual_features.sh --duration 20 --output-dir /tmp/openhalo-isaac-ros/results-visual-features
```

The report records effective feature rate, detector/pose/end-to-end latency
percentiles, object and region counts, coarse standing/sitting/unknown pose
counts, keypoint visibility/body coverage, and `tegrastats` RAM/GR3D/temperature
samples. The pose label is a bounded landmark heuristic, not a validated
activity classifier; insufficient lower-body visibility remains `unknown`.

Accuracy requires explicit owner-controlled scene labels. For example, after
staging one person in view and selecting the expected regions/objects:

```bash
./run_visual_features.sh --duration 20 \
  --case-name person-at-desk \
  --expected-person-count 1 \
  --expected-objects laptop,chair \
  --expected-regions center=1 \
  --expected-posture sitting \
  --output-dir /tmp/openhalo-isaac-ros/results-person-at-desk
```

The runner also applies in-memory `upper`, `center`, and `lower` masks to
periodic frames. Its occlusion result is relative retention against the same
unmasked frame; it is not a substitute for a labeled occlusion dataset. A
report with no person in the unmasked baseline marks occlusion accuracy as
`insufficient_baseline_person` rather than passing trivially.

For a deterministic model/feature sanity check using the Jetson's existing
Ultralytics fixtures:

```bash
source /opt/ros/humble/setup.bash
python3 /tmp/openhalo-isaac-ros/visual_fixture_eval.py \
  --output /tmp/openhalo-isaac-ros/results-visual-fixtures.json
```

The fixture checks the known `person`/`bus` counts in `bus.jpg`, the known
`person`/`tie` counts in `zidane.jpg`, and that the pose model returns at least
one person. It is a model wiring sanity check, not a camera-domain mAP or
posture-accuracy claim. Real accuracy acceptance still needs owner-labeled
standing, sitting, multi-person, object, region, and physical-occlusion cases.

## Tracking and temporal features

`temporal_features.py` is a bounded Camera Edge state layer over normalized
detections and pose keypoints. It keeps only numeric histories and derives:

- short-lived person/object track IDs, continuity, misses, re-acquisition, and
  long-gap termination;
- smoothed trajectory, direction, motion trend, dwell time, and normalized
  jitter;
- pose visibility, posture transitions, and short-window pose-change state;
- person-to-object `near`/`overlapping` relations and region dwell/transitions;
- window-level person-count and region-occupancy stability.

Run the real-camera temporal probe after the Argus package is available:

```bash
source /opt/ros/humble/setup.bash
source /tmp/openhalo-isaac-ros/ros_package/install/setup.bash
./run_visual_temporal.sh --duration 20 \
  --output-dir /tmp/openhalo-isaac-ros/results-visual-temporal
```

The runner writes structured numeric state only. Its built-in dropout probe
removes person detections for two samples and then applies a long gap so that
short-loss re-acquisition and long-loss new-ID behavior are measured
separately. A real-camera run with no visible person is reported as an empty
baseline, not as successful person-tracking accuracy.

For deterministic multi-person tracking and relation checks using the existing
Ultralytics fixtures:

```bash
source /opt/ros/humble/setup.bash
python3 /tmp/openhalo-isaac-ros/visual_temporal_fixture_eval.py \
  --output /tmp/openhalo-isaac-ros/results-visual-temporal-fixtures.json
```

This fixture report passed for 4 people in `bus.jpg` and 2 people in
`zidane.jpg`, including bounded jitter, short forced dropout, long-gap ID
termination, pose/region state, and person-object relation output. It is
tracker behavior evidence, not camera-domain tracking accuracy or physical
occlusion acceptance.

## Structured semantic interpretation

`structured_semantics.py` is a local-only experiment for the next layer. It
reads the `/api/state` output of the live feature page, removes raw boxes and
trajectories, and sends only the bounded temporal feature window to an Ollama
text model. The model returns candidate user states and interruptibility with
confidence, evidence references, uncertainty, and a short validity period.
It does not receive images, publish observations, or connect to Personal
Runtime.

Run it on the Jetson while the live feature page is available:

```bash
python3 /tmp/openhalo-isaac-ros/structured_semantics.py \
  --input-url http://127.0.0.1:8876/api/state \
  --model qwen3:1.7b \
  --requests 3 \
  --output-dir /tmp/openhalo-isaac-ros/results-structured-semantics-v1
```

The report stores the structured input, the bounded model result, the
deterministically gated result, gate reasons, and model timing. The gate
blocks claims such as `possible_object_interaction` when the low-level window
contains no person-object relationship, caps uncertain `likely_busy` claims,
and limits validity to the current five-second feature window. Model results
are evaluation evidence only; they are not accepted Runtime context.

To see the current recognition result visually, generate one annotated frame:

```bash
source /opt/ros/humble/setup.bash
source /tmp/openhalo-isaac-ros/ros_package/install/setup.bash
python3 /tmp/openhalo-isaac-ros/visual_preview.py \
  --output /tmp/openhalo-isaac-ros/visual-preview.jpg
```

The JPEG overlays detector boxes/confidence, pose keypoints, normalized region
occupancy, and the measured detector/pose latency. It is an explicit preview
artifact and is not retained by the Camera Edge or sent to Personal Runtime.

For a live browser view like the earlier VLM demo, use the resident preview
server instead. It keeps the ROS camera stream and the newest completed local
recognition result in memory, and serves an MJPEG page with detection boxes,
pose keypoints, region occupancy, feature counts, and current latency:

```bash
source /opt/ros/humble/setup.bash
source /tmp/openhalo-isaac-ros/ros_package/install/setup.bash
python3 /tmp/openhalo-isaac-ros/visual_live.py --host 0.0.0.0 --port 8876
```

Open `http://<jetson-ip>:8876` from a trusted local browser. The page's pause
button pauses only the local inference worker; it does not publish observations
or connect to Personal Runtime. The live page does not write frames to disk by
default. Stop it with `Ctrl+C`.

## Copy from Windows

The repository is shared with the Windows development machine. A simple
Jetson-side copy can use the configured SSH alias:

```powershell
$remoteDir = "/tmp/openhalo-isaac-ros"
ssh jetson "mkdir -p $remoteDir"
scp experiments/isaac_ros/* jetson:$remoteDir/
scp -r experiments/isaac_ros/ros_package jetson:$remoteDir/
ssh jetson "cd $remoteDir/ros_package; source /opt/ros/humble/setup.bash; colcon build --symlink-install"
ssh jetson "chmod +x $remoteDir/run_60s.sh; source /opt/ros/humble/setup.bash; source $remoteDir/ros_package/install/setup.bash; $remoteDir/run_60s.sh --duration 10 --restart-duration 10 --output-dir $remoteDir/results-smoke"
```

After the smoke passes, run the 60-second command with a new output directory
and inspect `report.json`, `launch.log`, and `tegrastats.log` before advancing
to detection/tracking or Camera Edge semantic-feature work.

If mode 4 remains unstable, test mode 3 (`1640x1232` at `30 FPS`) by passing
`mode:=3` to the launch wrapper and adjusting the target dimensions and
thresholds. Do not pass a standalone `framerate` override.
