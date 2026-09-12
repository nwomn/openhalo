"""Bounded chronological specialist replay with full raw traces and no VLM."""
import argparse
import ctypes
import gzip
import hashlib
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import time
from collections import Counter
from fusion import Fusion,CONFIG
from measurements import Specialists


def main():
    p=argparse.ArgumentParser();p.add_argument('--cases',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--hz',type=float,default=10)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    import cv2,numpy as np
    cv2.setNumThreads(2)
    cases=json.loads(a.cases.read_text())
    r=dict(status='running',config=CONFIG,sampling_hz=a.hz,opencv=cv2.__version__,cases=[],
        sources={v.name:hashlib.sha256(v.read_bytes()).hexdigest() for v in Path(__file__).parent.glob('*.py')},
        timing_boundary='chronological saved-video replay, no live capture/transport; index/fps source time; CPU model time separate',
        acceptance='not accepted; requires reference assessment, no semantics from VLM')
    def save():(a.output/'report.json').write_text(json.dumps(r,indent=2))
    log=(a.output/'tegrastats.log').open('w')
    tegra=subprocess.Popen(['tegrastats','--interval','500'],stdout=log,stderr=log,
        preexec_fn=lambda:ctypes.CDLL(None).prctl(1,signal.SIGTERM))
    model=None
    try:
        for case in cases:
            start=time.perf_counter();model=Specialists();init=time.perf_counter()-start
            r['models']=model.manifest();fusion=Fusion()
            cap=cv2.VideoCapture(case['video']);fps=cap.get(cv2.CAP_PROP_FPS)
            if not cap.isOpened() or fps<=0:raise ValueError('video cannot be decoded')
            cr=dict(**case,video_sha256=hashlib.sha256(Path(case['video']).read_bytes()).hexdigest(),
                model_create_seconds=init,source_fps=fps,events=[],samples=[])
            r['cases'].append(cr);rawpath=a.output/(case['name']+'-raw.jsonl.gz')
            i=0;next_t=0;frozen=None
            with gzip.open(rawpath,'wt') as raw:
                while True:
                    d0=time.perf_counter();okay=cap.grab()
                    if not okay:break
                    t=i/fps;i+=1
                    if t<case.get('start_s',0):continue
                    if t>case.get('end_s',float('inf')):break
                    if t+1e-6<next_t:continue
                    next_t=t+1/a.hz
                    okay,frame=cap.retrieve()
                    if not okay:raise ValueError('frame decode failed')
                    if case.get('freeze_frame'):
                        if frozen is None:frozen=frame.copy()
                        frame=frozen
                    rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
                    # For deliberate dropout controls, no hidden old observations
                    # are fed to fusion; model processing can continue independently.
                    obs=model.infer(rgb);mend=time.perf_counter()
                    if any(lo<=t<=hi for lo,hi in case.get('observation_dropouts',[])):
                        obs=dict(obs,hands=[],faces=[],pose=[])
                    fused=fusion.update(t,obs);end=time.perf_counter()
                    sample=dict(t=t,frame_index=i-1,hand_count=len(obs['hands']),face_count=len(obs['faces']),
                        body_available=bool(obs['pose']),fused=fused,model_seconds=obs['latency_seconds'],
                        fusion_seconds=end-mend,selected_frame_seconds=end-d0)
                    cr['samples'].append(sample);cr['events']+=fused['events']
                    raw.write(json.dumps(dict(**sample,observations=obs))+'\n')
                    if len(cr['samples'])<=2:print(json.dumps(dict(case=case['name'],sample=sample)),flush=True)
            cap.release();model.close();model=None
            samples=cr['samples'];warm=samples[1:]
            cr['summary']=dict(sample_count=len(samples),state_counts=dict(Counter(x['fused']['state'] for x in samples)),
                hand_detected_samples=sum(x['hand_count']>0 for x in samples),face_detected_samples=sum(x['face_count']==1 for x in samples),
                body_detected_samples=sum(x['body_available'] for x in samples),
                mean_model_ms=1000*statistics.mean(x['model_seconds']['total'] for x in warm),
                p95_selected_frame_ms=1000*float(np.percentile([x['selected_frame_seconds'] for x in warm],95)),
                max_selected_frame_ms=1000*max(x['selected_frame_seconds'] for x in warm),
                raw_trace=rawpath.name)
            print(json.dumps(dict(case=case['name'],summary=cr['summary'],events=cr['events'])),flush=True);save()
        r['status']='completed'
    except Exception as exc:r.update(status='failed',error=f'{type(exc).__name__}: {exc}');raise
    finally:
        if model:model.close()
        save();tegra.terminate()
        try:tegra.wait(timeout=5)
        except subprocess.TimeoutExpired:tegra.kill();tegra.wait()
        log.close()


if __name__=='__main__':main()
