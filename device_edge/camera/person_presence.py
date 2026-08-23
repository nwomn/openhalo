"""Local-only YOLO11 person-presence Feature for the MaixCAM Camera Edge.

The module deliberately exposes only a small, privacy-minimized result.  Raw
frames and detection geometry remain inside the MaixCAM process and are
discarded after each inference call.
"""

from __future__ import annotations

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


class MaixPersonPresenceFeature:
    """Own one Maix camera/NPU pipeline without retaining camera media."""

    def __init__(
        self,
        *,
        model_path: str = DEFAULT_MODEL_PATH,
        confidence_threshold: float = 0.55,
        detector_factory=None,
        camera_factory=None,
    ) -> None:
        if not 0.0 < confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be in (0, 1].")
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self._detector_factory = detector_factory
        self._camera_factory = camera_factory
        self._detector = None
        self._camera = None

    def _start(self) -> None:
        if self._camera is not None:
            return
        if self._detector_factory is None or self._camera_factory is None:
            from maix import camera, nn

            detector_factory = nn.YOLO11
            camera_factory = camera.Camera
        else:
            detector_factory = self._detector_factory
            camera_factory = self._camera_factory
        self._detector = detector_factory(model=self.model_path, dual_buff=True)
        self._camera = camera_factory(
            self._detector.input_width(),
            self._detector.input_height(),
            self._detector.input_format(),
        )

    def sample(self) -> PersonPresenceSample:
        """Infer person count once; no frame or bounding box escapes this method."""

        try:
            self._start()
            # MaixCAM may need a short ISP warm-up after this process becomes
            # the sensor owner.  A bounded blocking read avoids treating the
            # first non-blocking miss as a persistent Feature failure.
            frame = self._camera.read(block=True, block_ms=3000)
            if frame is None:
                raise RuntimeError("MaixCAM returned no frame before the bounded timeout.")
            detected = self._detector.detect(
                frame,
                conf_th=self.confidence_threshold,
                iou_th=0.45,
            )
            person_scores = [
                float(item.score)
                for item in detected
                if self._detector.labels[item.class_id] == "person"
            ]
            if person_scores:
                return PersonPresenceSample(
                    state="present",
                    count=len(person_scores),
                    confidence=max(person_scores),
                )
            return PersonPresenceSample(state="absent", count=0, confidence=0.0)
        except Exception:
            # An unavailable model or sensor must never be represented as an
            # empty room.  The detailed exception stays local to the process.
            self.close()
            return PersonPresenceSample(state="unavailable", count=None, confidence=0.0)
        finally:
            # ``frame`` is deliberately not retained, rendered, written, or sent.
            try:
                del frame
            except UnboundLocalError:
                pass

    def close(self) -> None:
        if self._camera is not None:
            try:
                self._camera.close()
            except Exception:
                pass
        self._camera = None
        self._detector = None


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
