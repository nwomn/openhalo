"""Bounded CSI capture owner and atomic, processing-paced batch handoff.

Run with host Python (GStreamer-enabled OpenCV). Private JPEGs stay outside Git.
Timestamps are host frame-arrival times, not sensor exposure timestamps.
"""
import argparse
from collections import deque
import json
from pathlib import Path
import socketserver
import threading
import time


class Buffer:
    def __init__(self, capacity=240):
        self.frames = deque(maxlen=capacity)
        self.lock = threading.Lock()
        self.dropped = 0
        self.total = 0
        self.boundary = time.monotonic()
        self.done = False
        self.error = None

    def append(self, frame):
        with self.lock:
            if len(self.frames) == self.frames.maxlen:
                self.dropped += 1
            # Stamp publication inside the same lock as take(): a JPEG still
            # being written cannot appear retroactively in the previous window.
            frame['mono'] = time.monotonic()
            self.frames.append(frame)
            self.total += 1

    def take(self):
        with self.lock:
            end = time.monotonic()
            rows = list(self.frames)
            self.frames.clear()
            result = dict(frames=rows, start=self.boundary, end=end,
                          total=self.total, overflow=self.dropped,
                          done=self.done, error=self.error)
            self.boundary = end
            return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seconds', type=float, default=120)
    args = p.parse_args()
    import cv2
    cv2.setNumThreads(1)
    args.output.mkdir(parents=True, exist_ok=True)
    images = args.output / 'frames'
    images.mkdir(exist_ok=False)
    state = Buffer()
    pipeline = ('nvarguscamerasrc sensor-id=0 ! '
                'video/x-raw(memory:NVMM),width=1280,height=720,framerate=30/1,format=NV12 ! '
                'nvvidconv ! video/x-raw,width=832,height=468,format=BGRx ! '
                'videorate drop-only=true ! video/x-raw,framerate=8/1 ! '
                'videoconvert ! video/x-raw,format=BGR ! '
                'appsink max-buffers=1 drop=true sync=false')
    (args.output / 'capture-config.json').write_text(json.dumps(dict(
        pipeline=pipeline, max_seconds=args.seconds, ring_capacity=240,
        timestamp_kind='host monotonic buffer publication; arrival_mono separately records cap.read return; neither is sensor exposure',
        recording='8 fps JPEG evidence, not every sensor frame'), indent=2))

    def capture():
        cap = None
        try:
            cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
            if not cap.isOpened():
                raise RuntimeError('CSI camera failed to open')
            started = time.monotonic()
            with (args.output / 'capture.jsonl').open('w') as log:
                seq = 0
                while time.monotonic() - started < args.seconds:
                    ok, frame = cap.read()
                    arrived = time.monotonic()
                    if not ok:
                        raise RuntimeError('CSI capture stopped delivering frames')
                    name = f'frames/{seq:06d}.jpg'
                    if not cv2.imwrite(str(args.output/name), frame,
                                       [cv2.IMWRITE_JPEG_QUALITY, 90]):
                        raise RuntimeError('JPEG write failed')
                    row = dict(seq=seq, arrival_mono=arrived, unix=time.time(), path=name,
                               shape=list(frame.shape))
                    state.append(row)
                    log.write(json.dumps(row)+'\n')
                    log.flush()
                    seq += 1
        except Exception as exc:
            state.error = f'{type(exc).__name__}: {exc}'
        finally:
            if cap is not None:
                cap.release()
            state.done = True
            (args.output/'capture-done.json').write_text(json.dumps(dict(
                total=state.total, overflow=state.dropped, error=state.error)))

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            command = json.loads(self.rfile.readline())
            if command['command'] == 'snapshot':
                reply = state.take()
            else:
                with state.lock:
                    reply = dict(buffered=len(state.frames), done=state.done,
                                 total=state.total, error=state.error)
            self.wfile.write((json.dumps(reply)+'\n').encode())

    socket_path = args.output/'capture.sock'
    with socketserver.UnixStreamServer(str(socket_path), Handler) as server:
        server.timeout = 1
        thread = threading.Thread(target=capture, daemon=True)
        thread.start()
        # Keep serving until the worker drains the final frames, with a hard limit.
        deadline = time.monotonic()+args.seconds+90
        while time.monotonic() < deadline:
            server.handle_request()
            with state.lock:
                if state.done and not state.frames:
                    break
        thread.join(timeout=5)
    socket_path.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
