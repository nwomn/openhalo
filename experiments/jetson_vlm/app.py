"""Small experiment composition root: camera, one model worker, read-only UI."""
import hashlib
import json
import platform
import signal
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2

from camera import Camera
from config import config_dict, parse_config
from model import infer, parse_result, runtime_info, task_spec


class Experiment:
    def __init__(self, config):
        self.config = config
        self.camera = Camera(config)
        self.stop = threading.Event()
        self.enabled = threading.Event()
        if not config.paused:
            self.enabled.set()
        self.lock = threading.Lock()
        self.state = {"status": "waiting", "result": None, "error": None, "completed": 0}
        self.snapshot = None
        self.run_dir = Path(config.output) / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.run_dir.mkdir(parents=True)
        metadata = {"config": config_dict(config), "python": platform.python_version(),
                    "opencv": cv2.__version__, "prompt_and_schema": task_spec(config.task),
                    "ollama": runtime_info(config)}
        (self.run_dir / "config.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
        self.worker = threading.Thread(target=self._work, name="inference", daemon=True)

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def view(self):
        with self.lock:
            return {**self.state, "config": config_dict(self.config),
                    "enabled": self.enabled.is_set(), "capture_fps": self.camera.fps,
                    "camera_error": self.camera.error, "server_time": time.time(),
                    "run_dir": str(self.run_dir)}

    def _work(self):
        count = 0
        while not self.stop.is_set():
            if not self.enabled.wait(timeout=0.2):
                continue
            frame = self.camera.get()
            if frame is None:
                continue
            count += 1
            row = {"request": count, "frame": frame.sequence, "captured_at": frame.captured_at,
                   "task": self.config.task, "display": self.config.display,
                   "started_at": time.time()}
            self.update(status="analyzing", error=None)
            try:
                height, width = frame.image.shape[:2]
                target_width = min(width, self.config.input_width)
                image = cv2.resize(frame.image, (target_width, round(height * target_width / width)))
                ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if not ok:
                    raise RuntimeError("Model input JPEG encoding failed")
                jpeg = encoded.tobytes()
                row.update(input_sha256=hashlib.sha256(jpeg).hexdigest(),
                           input_size=[image.shape[1], image.shape[0]])
                raw, metrics = infer(self.config, jpeg)
                row.update(metrics, raw=raw)
                items = parse_result(raw, self.config.task)
                row.update(items=items, ok=True)
            except Exception as exc:
                row.update(ok=False, error=f"{type(exc).__name__}: {exc}")
                self.enabled.clear()  # No retry loop hiding a failed experiment.
            row.update(completed_at=time.time(), capture_fps=self.camera.fps)
            row["frame_to_result_s"] = row["completed_at"] - frame.captured_at
            row["end_to_end_s"] = row["completed_at"] - row["started_at"]
            with (self.run_dir / "requests.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps(row, ensure_ascii=False) + "\n")
            with self.lock:
                self.snapshot = frame.jpeg
                self.state.update(result=row, completed=count,
                    status="ready" if row["ok"] else "error", error=row.get("error"))
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if self.config.requests and count >= self.config.requests:
                self.enabled.clear()
            self.stop.wait(self.config.interval)


def handler_for(experiment):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, data, content_type, status=200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if path == "/":
                self.send(Path(__file__).with_name("index.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/state":
                self.send(json.dumps(experiment.view(), ensure_ascii=False).encode(), "application/json")
            elif path == "/snapshot.jpg":
                with experiment.lock:
                    jpeg = experiment.snapshot
                self.send(jpeg or b"", "image/jpeg", 200 if jpeg else 404)
            elif path == "/frame.jpg":
                frame = experiment.camera.get()
                self.send(frame.jpeg if frame else b"", "image/jpeg", 200 if frame else 503)
            elif path == "/stream.mjpg":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                sequence = -1
                try:
                    while not experiment.stop.is_set():
                        frame = experiment.camera.get(sequence)
                        if frame is None or frame.sequence == sequence:
                            continue
                        sequence = frame.sequence
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                            + str(len(frame.jpeg)).encode() + b"\r\n\r\n" + frame.jpeg + b"\r\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, RuntimeError):
                    return
            else:
                self.send(b"Not found", "text/plain", 404)

        def do_POST(self):
            # Only same-origin controls; no arbitrary endpoint/model/path mutations.
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                self.send(b"Forbidden", "text/plain", 403)
                return
            if self.path == "/api/pause":
                experiment.enabled.clear()
            elif self.path == "/api/resume":
                experiment.enabled.set()
            else:
                self.send(b"Not found", "text/plain", 404)
                return
            self.send(b"{}", "application/json")
    return Handler


def main():
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    config = parse_config()
    experiment = Experiment(config)
    server = ThreadingHTTPServer((config.host, config.port), handler_for(experiment))
    experiment.camera.start()
    experiment.worker.start()
    print(f"Preview http://{config.host}:{config.port} ; logs {experiment.run_dir}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        experiment.stop.set()
        experiment.enabled.set()
        server.server_close()
        experiment.camera.close()


if __name__ == "__main__":
    main()
