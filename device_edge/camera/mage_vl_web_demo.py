#!/usr/bin/env python3
"""Browser demo for the local Jetson CSI -> Mage-VL StreamMind chain.

This is intentionally a standalone experiment UI. It owns one CSI GStreamer
pipeline, sends one branch to the native StreamMind runner, and exposes the
other branch as an in-memory MJPEG preview plus JSONL-derived status.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenHalo · Mage-VL 实时视觉体验</title>
<style>
:root{color-scheme:dark;font-family:system-ui,"Microsoft YaHei",sans-serif;background:#0e121a;color:#e8edf7}
*{box-sizing:border-box}body{margin:0;padding:22px;max-width:1440px;margin-inline:auto}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:16px}
h1{font-size:23px;margin:0 0 7px}.muted{color:#9ba8bd;font-size:14px;line-height:1.6}
button{border:1px solid #4b5872;background:#242c3d;color:#fff;border-radius:7px;padding:9px 14px;cursor:pointer}
.grid{display:grid;grid-template-columns:minmax(0,3fr) minmax(300px,1fr);gap:18px}
.card,.video{background:#171d29;border:1px solid #2b3549;border-radius:12px;overflow:hidden}
.video{position:relative;line-height:0;background:#050608}.video img{display:block;width:100%;min-height:220px;object-fit:contain}
.panel{padding:15px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin-top:12px}
.metric{background:#1b2332;border:1px solid #2c3850;border-radius:9px;padding:11px}.metric span{display:block;color:#9eabc1;font-size:12px}.metric b{display:block;font-size:19px;margin-top:5px}
.badge{display:inline-block;border-radius:14px;padding:5px 10px;background:#24342f;color:#9ee5cf;font-size:12px;margin-top:14px}
.answer{font-size:24px;line-height:1.45;color:#c8ffe9;min-height:74px;padding:14px;border-radius:9px;background:#10251f;border:1px solid #285345;margin:12px 0}
pre{white-space:pre-wrap;overflow-wrap:anywhere;color:#b9c8e5;font-size:12px;line-height:1.5;margin:8px 0 0}
h2{font-size:16px;margin:0 0 9px}.section{margin-top:18px}.warning{color:#ffb5a9}
@media(max-width:900px){body{padding:12px}.grid{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<header>
  <div><h1>OpenHalo · Mage-VL 实时视觉体验</h1><div class="muted">Jetson CSI → Mage‑VL / StreamMind · 当前只是本地模型演示，不进入 Runtime</div></div>
  <button id="stop">停止演示</button>
</header>
<div class="grid">
  <main>
    <div class="video"><img src="/mjpeg" alt="实时 CSI 摄像头画面"></div>
    <div class="metrics">
      <div class="metric"><span>状态</span><b id="status">启动中</b></div>
      <div class="metric"><span>已返回段数</span><b id="count">0</b></div>
      <div class="metric"><span>最近 native 耗时</span><b id="native">—</b></div>
      <div class="metric"><span>最近直播延迟</span><b id="delay">—</b></div>
    </div>
    <span id="badge" class="badge">正在连接模型…</span>
    <p id="diagnostic" class="muted"></p>
  </main>
  <aside class="card panel">
    <h2>最近一次理解</h2>
    <div id="answer" class="answer">等待 Mage‑VL 返回文字…</div>
    <div id="meta" class="muted"></div>
    <div class="section"><h2>最近事件</h2><pre id="event">等待事件…</pre></div>
    <div class="section"><h2>说明</h2><div class="muted">每 4 秒形成一个视频理解段。为适配 Jetson 7.6 GiB 内存，输入约为 672×384，生成上下文为 4096；结果通常会落后画面约 14–16 秒。</div></div>
  </aside>
</div>
<script>
const $ = id => document.getElementById(id);
function seconds(x){return x == null ? '—' : Number(x).toFixed(2) + ' s';}
function paint(s){
  const e=s.last_response || {};
  const event=s.last_event || {};
  $('status').textContent=s.status || '—';
  $('count').textContent=s.response_count || 0;
  $('native').textContent=seconds(e.native_total_ms ? e.native_total_ms/1000 : null);
  $('delay').textContent=seconds(e.live_delay_seconds);
  if(e.event === 'response') $('answer').textContent=e.answer || '(空回答)';
  else if(e.event === 'suppressed') $('answer').textContent='这一段被 StreamMind 静默门控';
  $('meta').textContent=e.event ? ('segment ' + e.segment + ' · ' + seconds(e.generation_ms ? e.generation_ms/1000 : null) + ' 生成 · peak=' + (e.peak_probability ?? '—')) : '尚无完整理解结果';
  $('event').textContent=JSON.stringify(event,null,2);
  $('badge').textContent=s.mage_alive ? (s.camera_alive ? '摄像头与 Mage‑VL 均在线' : 'Mage‑VL 在线，摄像头异常') : 'Mage‑VL 已停止';
  $('badge').style.color=s.mage_alive && s.camera_alive ? '#9ee5cf' : '#ffb5a9';
  $('diagnostic').textContent=(s.last_log || '') + (s.frame_age_s == null ? '' : ' · 最新预览帧 ' + Number(s.frame_age_s).toFixed(1) + ' 秒前');
}
async function poll(){
  try{const r=await fetch('/api/state',{cache:'no-store'}); paint(await r.json());}
  catch(e){$('badge').textContent='状态连接失败';$('diagnostic').textContent=e.message;}
  setTimeout(poll,500);
}
$('stop').onclick=async()=>{await fetch('/api/stop',{method:'POST'});};
poll();
</script>
</body>
</html>
"""


class Demo:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.root = Path(args.root)
        self.models = Path(args.models)
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.latest_jpeg: bytes | None = None
        self.latest_frame_at = 0.0
        self.events: deque[dict] = deque(maxlen=40)
        self.last_response: dict | None = None
        self.last_log = ""
        self.status = "starting"
        self.response_count = 0
        self.started_at = time.time()
        self.camera: subprocess.Popen[str] | None = None
        self.mage: subprocess.Popen[str] | None = None
        self.threads: list[threading.Thread] = []

    @property
    def source(self) -> str:
        return f"udp://127.0.0.1:{self.args.camera_port}?fifo_size=1000000&overrun_nonfatal=1"

    def camera_command(self) -> list[str]:
        a = self.args
        return [
            "gst-launch-1.0", "-e",
            "nvarguscamerasrc", f"sensor-id={a.sensor_id}", f"sensor-mode={a.sensor_mode}", "!",
            f"video/x-raw(memory:NVMM),width={a.width},height={a.height},framerate={a.fps}/1",
            "!", "tee", "name=t",
            "t.", "!", "queue", "!", "nvvidconv",
            "!", f"video/x-raw,format=I420,width={a.width},height={a.height}",
            "!", "videorate", "!", "video/x-raw,framerate=15/1",
            "!", "x264enc", "bitrate=4000", "speed-preset=ultrafast",
            "tune=zerolatency", "key-int-max=15", "!", "h264parse",
            "config-interval=1", "!", "mpegtsmux", "!", "udpsink",
            "host=127.0.0.1", f"port={a.camera_port}", "sync=false",
            "t.", "!", "queue", "!", "nvvidconv",
            "!", "video/x-raw,format=I420,width=640,height=360",
            "!", "jpegenc", "quality=70", "!", "multipartmux",
            "boundary=frame", "!", "tcpserversink", "host=127.0.0.1",
            f"port={a.preview_port}", "sync=false",
        ]

    def mage_command(self) -> list[str]:
        python = self.root / ".venv-codec/bin/python"
        streammind = self.root / "tools/streammind_native.py"
        producer = self.root / "tools/live_codec_stream.py"
        return [
            str(python), str(streammind), self.source,
            "--runner", str(self.root / "../mage-llama/build/bin/llama-streammind-e2e"),
            "--backbone", str(self.models / "mage-vl-backbone-Q4_K_M.gguf"),
            "--mmproj", str(self.models / "mage-vit-mmproj-Q8_0.gguf"),
            "--epfe", str(self.models / "mage-streammind-epfe-Q8_0.gguf"),
            "--classifier", str(self.models / "mage-streammind-cls-Q8_0.gguf"),
            "--incremental-producer", str(producer),
            "--sample-fps", "1", "--min-group-frames", "4",
            "--max-pixels", "262144", "--readiness-threshold", "0",
            "--prompt", "Describe important changes in the scene briefly. Mention people, actions, and clearly readable text. Do not guess.",
            "--threshold", "0.0", "--max-tokens", "16",
            "--interval-segments", "1", "--startup-timeout", "40",
            "--vulkan-device", "0",
        ]

    def start(self) -> None:
        self.camera = subprocess.Popen(
            self.camera_command(), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        self._thread(self._read_diagnostics, self.camera, "camera")
        self._thread(self._preview_loop)
        env = os.environ.copy()
        env.update({
            "PYTHONUNBUFFERED": "1",
            "STREAMMIND_GEN_CTX": "4096",
            "STREAMMIND_GEN_BATCH": "2048",
            "STREAMMIND_GEN_UBATCH": "512",
            "GGML_VK_VISIBLE_DEVICES": "0",
        })
        self.mage = subprocess.Popen(
            self.mage_command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, text=True, bufsize=1, env=env,
        )
        self._thread(self._read_mage)
        self._thread(self._read_diagnostics, self.mage, "mage")

    def _thread(self, target, *args) -> None:
        thread = threading.Thread(target=target, args=args, daemon=True)
        self.threads.append(thread)
        thread.start()

    def _read_diagnostics(self, process: subprocess.Popen[str], _name: str) -> None:
        if process.stderr is None:
            return
        for line in process.stderr:
            line = line.strip()
            if line:
                with self.lock:
                    self.last_log = line[-500:]

    def _read_mage(self) -> None:
        if self.mage is None or self.mage.stdout is None:
            return
        for line in self.mage.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            with self.lock:
                self.events.append(event)
                kind = event.get("event")
                if kind == "ready":
                    self.status = "ready"
                elif kind == "group_submitted":
                    self.status = "processing"
                elif kind in {"response", "suppressed"}:
                    self.last_response = event
                    self.response_count += 1
                    self.status = "response"
        with self.lock:
            if not self.stop_event.is_set():
                self.status = "stopped"

    def _preview_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                sock = socket.create_connection(("127.0.0.1", self.args.preview_port), timeout=5)
                sock.settimeout(2)
            except OSError:
                self.stop_event.wait(0.5)
                continue
            buffer = bytearray()
            try:
                while not self.stop_event.is_set():
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    buffer.extend(chunk)
                    while True:
                        start = buffer.find(b"\xff\xd8")
                        if start < 0:
                            if len(buffer) > 1_000_000:
                                del buffer[:-2]
                            break
                        end = buffer.find(b"\xff\xd9", start + 2)
                        if end < 0:
                            if start:
                                del buffer[:start]
                            break
                        jpeg = bytes(buffer[start:end + 2])
                        del buffer[:end + 2]
                        with self.lock:
                            self.latest_jpeg = jpeg
                            self.latest_frame_at = time.time()
            except OSError:
                pass
            finally:
                sock.close()

    def state(self) -> dict:
        with self.lock:
            camera_alive = self.camera is not None and self.camera.poll() is None
            mage_alive = self.mage is not None and self.mage.poll() is None
            age = time.time() - self.latest_frame_at if self.latest_frame_at else None
            return {
                "status": self.status,
                "camera_alive": camera_alive,
                "mage_alive": mage_alive,
                "response_count": self.response_count,
                "last_response": self.last_response,
                "last_event": self.events[-1] if self.events else None,
                "frame_age_s": age,
                "last_log": self.last_log,
                "started_at": self.started_at,
            }

    def frame(self) -> bytes | None:
        with self.lock:
            return self.latest_jpeg

    def shutdown(self) -> None:
        self.stop_event.set()
        for process in (self.mage, self.camera):
            if process is None or process.poll() is not None:
                continue
            process.terminate()
        for process in (self.mage, self.camera):
            if process is None:
                continue
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def handler_for(demo: Demo):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            pass

        def send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/":
                self.send_bytes(PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/state":
                self.send_bytes(json.dumps(demo.state(), ensure_ascii=False).encode(), "application/json")
            elif path == "/frame.jpg":
                frame = demo.frame()
                self.send_bytes(frame or b"", "image/jpeg", 200 if frame else 503)
            elif path == "/mjpeg":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    while not demo.stop_event.is_set():
                        frame = demo.frame()
                        if frame:
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
                            self.wfile.flush()
                        time.sleep(0.12)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
            else:
                self.send_bytes(b"Not found", "text/plain", 404)

        def do_POST(self) -> None:
            if urlsplit(self.path).path == "/api/stop":
                demo.shutdown()
                self.send_bytes(b"{}", "application/json")
            else:
                self.send_bytes(b"Not found", "text/plain", 404)

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mage-VL browser demo for Jetson CSI")
    parser.add_argument("--root", default="/home/jetson/mage-vl-gguf")
    parser.add_argument("--models", default="/home/jetson/mage-models")
    parser.add_argument("--runner", default="/home/jetson/mage-llama/build/bin/llama-streammind-e2e")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--camera-port", type=int, default=5010)
    parser.add_argument("--preview-port", type=int, default=5011)
    parser.add_argument("--sensor-id", type=int, default=0)
    parser.add_argument("--sensor-mode", type=int, default=4)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=60)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    demo = Demo(args)
    demo.start()
    server = ThreadingHTTPServer((args.host, args.port), handler_for(demo))
    print("Mage-VL demo: http://%s:%s" % (args.host, args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        demo.shutdown()
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    raise SystemExit(main())
