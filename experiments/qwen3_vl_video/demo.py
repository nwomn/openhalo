"""LAN-only model demo; explicit camera start, bounded sessions, original answers."""
import argparse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import signal
import subprocess
import threading
import time
from urllib.parse import parse_qs, urlparse

CONTAINER = 'openhalo-qwen3-vl-probe-20260913'


def records(path):
    try:
        # Ignore an incomplete last line while the producer appends.
        lines = path.read_text().splitlines(keepends=True)
        return [json.loads(x) for x in lines if x.endswith('\n')]
    except FileNotFoundError:
        return []


def latest_record(path):
    try:
        with path.open('rb') as f:
            f.seek(0,2)
            size=f.tell()
            f.seek(max(0,size-8192))
            lines=f.read().splitlines(keepends=True)
        for line in reversed(lines):
            if line.endswith(b'\n'):
                return json.loads(line)
    except (OSError,ValueError):
        pass
    return None


class Demo:
    def __init__(self, root, seconds):
        self.root=root
        self.seconds=seconds
        self.lock=threading.Lock()
        self.stop=threading.Event()
        self.thread=None
        self.run=None
        self.phase='idle'
        self.error=None
        self.capture_started=None

    def update(self, **values):
        with self.lock:
            for key,value in values.items():
                setattr(self,key,value)

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                return False
            self.stop.clear()
            self.run=self.root/'private'/('demo-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            self.phase='loading'
            self.error=None
            self.capture_started=None
            self.thread=threading.Thread(target=self.work,daemon=True)
            self.thread.start()
            return True

    def work(self):
        worker=capture=None
        run=self.run
        handles=[]
        try:
            if subprocess.run(['systemctl','is-active','--quiet','nvargus-daemon']).returncode:
                raise RuntimeError('摄像头服务尚未启动，请在 Jetson 启动 nvargus-daemon。')
            # Do not compete with another owner of this dedicated probe container.
            running=subprocess.check_output(['docker','inspect','--format','{{.State.Running}}',CONTAINER],text=True).strip()
            if running=='true':
                raise RuntimeError('Qwen 实验容器正在使用，请先结束已有实验。')
            subprocess.run(['docker','start',CONTAINER],check=True,stdout=subprocess.DEVNULL)
            log=(run.parent/(run.name+'-worker.log')).open('w')
            handles.append(log)
            worker=subprocess.Popen(['docker','exec',CONTAINER,'python3','/work/scripts/live_benchmark.py',
                '--output','/work/private/'+run.name],stdout=log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+300
            while not (run/'ready.json').exists():
                if self.stop.wait(.25):
                    return
                if worker.poll() is not None:
                    raise RuntimeError('模型加载失败；详见本轮 worker 日志。')
                if time.monotonic()>deadline:
                    raise TimeoutError('模型预热超时。')
            if self.stop.is_set():
                return
            caplog=(run.parent/(run.name+'-capture.log')).open('w')
            handles.append(caplog)
            capture=subprocess.Popen(['/usr/bin/python3',str(self.root/'scripts/live_capture.py'),
                '--output',str(run),'--seconds',str(self.seconds)],stdout=caplog,stderr=subprocess.STDOUT)
            self.update(phase='capturing',capture_started=time.time())
            deadline=time.monotonic()+self.seconds+60
            while worker.poll() is None:
                if self.stop.wait(.25):
                    self.update(phase='stopping')
                    capture.terminate()
                    try:
                        worker.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        pass
                    return
                done=run/'capture-done.json'
                if done.exists():
                    detail=json.loads(done.read_text())
                    if detail.get('error'):
                        raise RuntimeError(detail['error'])
                if capture.poll() is not None and not done.exists():
                    raise RuntimeError('摄像头启动失败；详见本轮 capture 日志。')
                if time.monotonic()>deadline:
                    raise TimeoutError('实验超时，已停止。')
            if worker.returncode:
                raise RuntimeError('模型推理失败；保留已完成结果，请查看本轮日志。')
        except Exception as exc:
            self.update(error=f'{type(exc).__name__}: {exc}')
        finally:
            # Only stop a container when this session successfully launched its worker.
            if capture and capture.poll() is None:
                capture.terminate()
                try:
                    capture.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    capture.kill()
                    capture.wait()
            if worker:
                subprocess.run(['docker','stop','-t','5',CONTAINER],stdout=subprocess.DEVNULL)
                worker.wait(timeout=10)
            for handle in handles:
                handle.close()
            self.update(phase='error' if self.error else 'stopped')

    def view(self):
        with self.lock:
            run=self.run
            state=dict(phase=self.phase,error=self.error,run=run.name if run else None,
                capture_started=self.capture_started,session_seconds=self.seconds,
                active=bool(self.thread and self.thread.is_alive()),server_time=time.time())
        rows=records(run/'raw.jsonl') if run else []
        latest=latest_record(run/'capture.jsonl') if run else None
        state.update(results=rows,latest_frame=latest,
                     camera_live=bool(latest and time.time()-latest['unix']<2 and state['active']))
        return state


def handler_for(demo):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def send(self,data,mime='application/json',status=200):
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):
                pass

        def do_GET(self):
            request=urlparse(self.path)
            if request.path=='/':
                return self.send(Path(__file__).with_name('demo.html').read_bytes(),'text/html; charset=utf-8')
            if request.path=='/api/state':
                return self.send(json.dumps(demo.view()).encode())
            state=demo.view()
            if not state['run']:
                return self.send(b'{}',status=404)
            run=demo.root/'private'/state['run']
            row=state['latest_frame']
            if request.path=='/sample.jpg':
                try:
                    query=parse_qs(request.query)
                    if query['run'][0]!=state['run']:
                        return self.send(b'{}',status=409)
                    batch=int(query['batch'][0]); index=int(query['index'][0])
                    if not (0<=batch<len(state['results']) and 0<=index<16):
                        raise ValueError()
                    row=state['results'][batch]['selected'][index]
                except (ValueError,KeyError,IndexError):
                    return self.send(b'{}',status=404)
            elif request.path!='/frame.jpg':
                return self.send(b'{}',status=404)
            if row:
                try:
                    return self.send((run/row['path']).read_bytes(),'image/jpeg')
                except OSError:
                    pass
            self.send(b'{}',status=404)

        def do_POST(self):
            if self.headers.get('Origin') not in (None,'http://'+self.headers.get('Host','')):
                return self.send(b'{}',status=403)
            if self.path=='/api/start':
                started=demo.start()
                return self.send(json.dumps(dict(started=started)).encode(),status=200 if started else 409)
            if self.path=='/api/stop':
                demo.stop.set()
                return self.send(b'{"stopping":true}')
            self.send(b'{}',status=404)
    return Handler


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path('/home/jetson/openhalo-qwen3-vl-video'))
    p.add_argument('--host',default='0.0.0.0')
    p.add_argument('--port',type=int,default=8766)
    p.add_argument('--seconds',type=int,default=600)
    args=p.parse_args()
    assert 10<=args.seconds<=600
    demo=Demo(args.root,args.seconds)
    server=ThreadingHTTPServer((args.host,args.port),handler_for(demo))
    signal.signal(signal.SIGTERM,signal.default_int_handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        demo.stop.set()
        if demo.thread:
            demo.thread.join(timeout=35)
        server.server_close()


if __name__=='__main__':
    main()
