"""One capture owner; consumers receive the latest immutable frame, never a queue."""
import threading
import time
from dataclasses import dataclass

import cv2


@dataclass(frozen=True)
class Frame:
    sequence: int
    captured_at: float
    image: object
    jpeg: bytes


class Camera:
    def __init__(self, config):
        self.config = config
        self.condition = threading.Condition()
        self.latest = None
        self.error = None
        self.fps = 0.0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="capture", daemon=True)

    def start(self):
        self.thread.start()

    def get(self, after=-1):
        with self.condition:
            self.condition.wait_for(
                lambda: self.error or self.stop.is_set() or
                (self.latest is not None and self.latest.sequence > after), timeout=2)
            if self.error:
                raise RuntimeError(self.error)
            return self.latest

    def _run(self):
        cap = None
        try:
            c = self.config
            still = None
            if c.source == "csi":
                pipeline = (
                    f"nvarguscamerasrc sensor-id={c.camera_id} ! "
                    f"video/x-raw(memory:NVMM),width={c.width},height={c.height},"
                    f"framerate={c.fps}/1,format=NV12 ! nvvidconv ! "
                    "video/x-raw,format=BGRx ! videoconvert ! video/x-raw,format=BGR ! "
                    "appsink max-buffers=1 drop=true sync=false")
                cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
                if not cap.isOpened():
                    raise RuntimeError("CSI camera could not open")
            else:
                still = cv2.imread(c.source)
                if still is None:
                    raise ValueError(f"Image could not open: {c.source}")
            sequence, count, start = 0, 0, time.monotonic()
            while not self.stop.is_set():
                if cap is not None:
                    ok, image = cap.read()
                    if not ok:
                        raise RuntimeError("CSI capture stopped delivering frames")
                else:
                    image = still
                    self.stop.wait(1 / c.fps)
                captured_at = time.time()
                ok, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 78])
                if not ok:
                    raise RuntimeError("Preview JPEG encoding failed")
                sequence += 1
                count += 1
                elapsed = time.monotonic() - start
                if elapsed >= 1:
                    self.fps = count / elapsed
                    count, start = 0, time.monotonic()
                with self.condition:
                    self.latest = Frame(sequence, captured_at, image, jpeg.tobytes())
                    self.condition.notify_all()
        except Exception as exc:
            with self.condition:
                self.error = str(exc)
                self.condition.notify_all()
        finally:
            if cap is not None:
                cap.release()

    def close(self):
        self.stop.set()
        with self.condition:
            self.condition.notify_all()
        self.thread.join(timeout=3)
