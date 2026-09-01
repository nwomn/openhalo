"""Local MaixCAM visual Features for the Camera Edge.

The Maix camera and detector are owned by one process.  A sampling cycle reads
one frame, derives the configured semantic values, and then drops the frame
and all detection geometry.  Only the small dataclasses in this module are
allowed to cross into the Camera Edge transport layer.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass


DEFAULT_MODEL_PATH = "/root/models/yolo11n.mud"


@dataclass(frozen=True)
class PersonPresenceSample:
    """One local inference result, before temporal debouncing."""

    state: str
    count: int | None
    confidence: float


@dataclass(frozen=True)
class PersonPresenceDecision:
    """A debounced, safe-to-publish presence observation."""

    state: str
    count: int | None
    confidence: float


@dataclass(frozen=True)
class RegionOccupancy:
    """Semantic occupancy for one configured normalized region."""

    occupied: bool | None
    count: int | None


@dataclass(frozen=True)
class VisualFeatureSample:
    """One shared, geometry-free visual sampling result.

    ``state`` describes whether the sensor/detector produced a usable frame.
    It is intentionally not a claim about perceptual sharpness or exposure;
    those metrics need a separately verified Maix image-quality API.
    """

    state: str
    person_state: str
    person_count: int | None
    person_confidence: float
    object_counts: dict[str, int]
    regions: dict[str, RegionOccupancy]
    width: int | None
    height: int | None


@dataclass(frozen=True)
class _DetectedObject:
    """Short-lived internal detection; never returned from a public method."""

    label: str
    score: float
    center_x: float
    center_y: float


def _read_detection_value(item, name: str, default=None):
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _normalise_object_labels(labels: Iterable[str] | None) -> tuple[str, ...]:
    if labels is None:
        return ()
    if isinstance(labels, str):
        labels = (labels,)
    result: list[str] = []
    for label in labels:
        normalized = str(label).strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return tuple(result)


def _normalise_regions(
    regions: Mapping[str, Iterable[float]] | None,
) -> dict[str, tuple[float, float, float, float]]:
    if regions is None:
        return {}
    normalized: dict[str, tuple[float, float, float, float]] = {}
    for name, bounds in regions.items():
        region_name = str(name).strip()
        if not region_name:
            raise ValueError("region names must not be empty")
        try:
            values = tuple(float(value) for value in bounds)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"region {region_name!r} must contain four normalized numbers"
            ) from error
        if len(values) != 4:
            raise ValueError(
                f"region {region_name!r} must contain four normalized numbers"
            )
        x1, y1, x2, y2 = values
        if not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
            raise ValueError(
                f"region {region_name!r} must be an ordered rectangle in [0, 1]"
            )
        normalized[region_name] = (x1, y1, x2, y2)
    return normalized


class MaixVisualFeaturePipeline:
    """Own one Maix camera/NPU pipeline and emit bounded visual semantics."""

    def __init__(
        self,
        *,
        model_path: str = DEFAULT_MODEL_PATH,
        confidence_threshold: float = 0.55,
        object_labels: Iterable[str] | None = None,
        regions: Mapping[str, Iterable[float]] | None = None,
        detector_factory=None,
        camera_factory=None,
    ) -> None:
        if not 0.0 < confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be in (0, 1].")
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.object_labels = _normalise_object_labels(object_labels)
        self.regions = _normalise_regions(regions)
        self._detector_factory = detector_factory
        self._camera_factory = camera_factory
        self._detector = None
        self._camera = None

    def _start_detector(self) -> None:
        if self._detector is not None:
            return
        if self._detector_factory is None:
            from maix import nn

            detector_factory = nn.YOLO11
        else:
            detector_factory = self._detector_factory
        self._detector = detector_factory(model=self.model_path, dual_buff=True)

    def _start_camera(self) -> None:
        if self._camera is not None:
            return
        if self._camera_factory is None:
            from maix import camera

            camera_factory = camera.Camera
        else:
            camera_factory = self._camera_factory
        self._start_detector()
        self._camera = camera_factory(
            self._detector.input_width(),
            self._detector.input_height(),
            self._detector.input_format(),
        )

    def _dimensions(self) -> tuple[int, int]:
        width = int(self._detector.input_width())
        height = int(self._detector.input_height())
        if width <= 0 or height <= 0:
            raise RuntimeError("MaixCAM detector returned invalid input dimensions.")
        return width, height

    def _normalise_detections(
        self,
        detected,
        *,
        width: int,
        height: int,
    ) -> list[_DetectedObject]:
        labels = getattr(self._detector, "labels", ())
        detections: list[_DetectedObject] = []
        for item in detected or ():
            try:
                class_id = int(_read_detection_value(item, "class_id"))
                label = str(labels[class_id])
                score = float(_read_detection_value(item, "score"))
                x = float(_read_detection_value(item, "x", 0.0))
                y = float(_read_detection_value(item, "y", 0.0))
                box_width = float(_read_detection_value(item, "w", 0.0))
                box_height = float(_read_detection_value(item, "h", 0.0))
            except (IndexError, TypeError, ValueError):
                # A malformed vendor detection must not make the whole camera
                # stream look like an empty room.
                continue
            if not label or score < self.confidence_threshold:
                continue
            detections.append(
                _DetectedObject(
                    label=label,
                    score=score,
                    center_x=(x + box_width / 2.0) / width,
                    center_y=(y + box_height / 2.0) / height,
                )
            )
        return detections

    def _unavailable_sample(self) -> VisualFeatureSample:
        return VisualFeatureSample(
            state="unavailable",
            person_state="unavailable",
            person_count=None,
            person_confidence=0.0,
            object_counts={},
            regions={
                name: RegionOccupancy(occupied=None, count=None)
                for name in self.regions
            },
            width=None,
            height=None,
        )

    def sample(self) -> VisualFeatureSample:
        """Read and infer once, returning semantic values without media."""

        frame = None
        try:
            self._start_camera()
            # MaixCAM may need a short ISP warm-up after this process becomes
            # the sensor owner.  A bounded blocking read avoids treating the
            # first non-blocking miss as a persistent Feature failure.
            frame = self._camera.read(block=True, block_ms=3000)
            if frame is None:
                raise RuntimeError("MaixCAM returned no frame before the bounded timeout.")
            return self.sample_frame(frame)
        except Exception:
            # An unavailable model or sensor must never be represented as an
            # empty room.  The detailed exception stays local to the process.
            self.close()
            return self._unavailable_sample()
        finally:
            # ``frame`` is deliberately not retained, rendered, written, or
            # sent.  Deleting the local reference also keeps the pipeline's
            # memory behaviour bounded across long-running sessions.
            del frame

    def sample_frame(self, frame) -> VisualFeatureSample:
        """Infer from a frame owned by ``CameraEdgeService``.

        Unlike :meth:`sample`, this method never opens or reads a camera. It
        makes the NPU a consumer of the one capture loop rather than a second
        competing camera owner.
        """

        try:
            self._start_detector()
            width, height = self._dimensions()
            detected = self._detector.detect(
                frame,
                conf_th=self.confidence_threshold,
                iou_th=0.45,
            )
            detections = self._normalise_detections(
                detected,
                width=width,
                height=height,
            )
            person_detections = [item for item in detections if item.label == "person"]
            person_scores = [item.score for item in person_detections]
            configured_counts = Counter({label: 0 for label in self.object_labels})
            for item in detections:
                if item.label in configured_counts:
                    configured_counts[item.label] += 1
            region_values = {}
            for name, (x1, y1, x2, y2) in self.regions.items():
                count = sum(1 for item in person_detections if x1 <= item.center_x <= x2 and y1 <= item.center_y <= y2)
                region_values[name] = RegionOccupancy(occupied=count > 0, count=count)
            return VisualFeatureSample(
                state="ready",
                person_state="present" if person_scores else "absent",
                person_count=len(person_scores),
                person_confidence=max(person_scores, default=0.0),
                object_counts=dict(configured_counts),
                regions=region_values,
                width=width,
                height=height,
            )
        except Exception:
            # A detector failure must not turn into an empty scene. Do not
            # close a Camera here: this pipeline no longer owns it.
            self._detector = None
            return self._unavailable_sample()

    def close(self) -> None:
        if self._camera is not None:
            try:
                self._camera.close()
            except Exception:
                pass
        self._camera = None
        self._detector = None


class MaixPersonPresenceFeature:
    """Backward-compatible person Feature backed by the shared visual pass."""

    supports_visual_features = True

    def __init__(
        self,
        *,
        model_path: str = DEFAULT_MODEL_PATH,
        confidence_threshold: float = 0.55,
        object_labels: Iterable[str] | None = None,
        regions: Mapping[str, Iterable[float]] | None = None,
        detector_factory=None,
        camera_factory=None,
    ) -> None:
        self._pipeline = MaixVisualFeaturePipeline(
            model_path=model_path,
            confidence_threshold=confidence_threshold,
            object_labels=object_labels,
            regions=regions,
            detector_factory=detector_factory,
            camera_factory=camera_factory,
        )
        self._last_visual_sample: VisualFeatureSample | None = None

    @property
    def last_visual_sample(self) -> VisualFeatureSample | None:
        return self._last_visual_sample

    def sample(self) -> PersonPresenceSample:
        visual = self._pipeline.sample()
        self._last_visual_sample = visual
        return PersonPresenceSample(
            state=visual.person_state,
            count=visual.person_count,
            confidence=visual.person_confidence,
        )

    def sample_frame(self, frame) -> PersonPresenceSample:
        """Consume a shared service-owned frame without touching the camera."""

        visual = self._pipeline.sample_frame(frame)
        self._last_visual_sample = visual
        return PersonPresenceSample(
            state=visual.person_state,
            count=visual.person_count,
            confidence=visual.person_confidence,
        )

    def close(self) -> None:
        self._pipeline.close()


class PresenceDebouncer:
    """Require repeated local samples before changing a published state."""

    def __init__(self, confirm_samples: int = 2) -> None:
        if confirm_samples <= 0:
            raise ValueError("confirm_samples must be positive.")
        self.confirm_samples = confirm_samples
        self._candidate: tuple[str, int | None] | None = None
        self._candidate_samples = 0
        self.confirmed: PersonPresenceDecision | None = None

    def observe(self, sample: PersonPresenceSample) -> PersonPresenceDecision | None:
        key = (sample.state, sample.count)
        if sample.state == "unavailable":
            self._candidate = None
            self._candidate_samples = 0
            decision = PersonPresenceDecision(**sample.__dict__)
            if self.confirmed != decision:
                self.confirmed = decision
                return decision
            return None

        if key == self._candidate:
            self._candidate_samples += 1
        else:
            self._candidate = key
            self._candidate_samples = 1
        if self._candidate_samples < self.confirm_samples:
            return None

        decision = PersonPresenceDecision(**sample.__dict__)
        if self.confirmed is None or (self.confirmed.state, self.confirmed.count) != key:
            self.confirmed = decision
            return decision
        self.confirmed = decision
        return None
