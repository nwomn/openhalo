"""Wall-clock paced recorded observations with real asynchronous MobileVLM calls."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import hashlib,json,subprocess,time
from pathlib import Path
from singleflight import Scheduler

def iou(a,b):
    area=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return area/max(1e-9,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-area)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(exist_ok=False,parents=True)
    import cv2,numpy as np
    from vlm_session import Session
    cv2.setNumThreads(2)
    path=Path('/home/jetson/openhalo-specialist-expanded/run-fresh-v1/report.json')
    old=json.loads(path.read_text())['cases'][0];cap=cv2.VideoCapture(old['video'])
    if hashlib.sha256(Path(old['video']).read_bytes()).hexdigest()!=old['video_sha256']:raise ValueError('video changed')
    s=Scheduler();report=dict(status='loading',config=asdict(s.config),appearance_mae_threshold=.12,
        association_iou_threshold=.1,source_report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_hashes={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest()
                       for n in ['singleflight.py','async_roi_replay.py','vlm_session.py']},
        boundary='paced saved video and cached specialist observations; actual VLM worker; no live camera, Runtime or verified object identity',
        requests=[],samples=[])
    def save():(a.output/'report.json').write_text(json.dumps(report,indent=2))
    log=(a.output/'tegrastats.log').open('w');tegra=subprocess.Popen(['tegrastats','--interval','500'],stdout=log,stderr=log)
    session=None;pool=ThreadPoolExecutor(max_workers=1);future=None;job=None
    try:
        session=Session();report['model']=session.info
        cap.set(cv2.CAP_PROP_POS_FRAMES,0);ok,first=cap.read()
        if not ok:raise ValueError('video decode failed')
        report['warmup']=session.infer(first)
        report['status']='running';save();start=time.monotonic();last_box=None;anchor=None;epoch=0;revision=0;last_hand=-1e9
        def collect(t):
            nonlocal future,job
            if future is not None and future.done():
                try:result=future.result()
                except Exception as exc:result=dict(text='',usable=False,error=str(exc))
                accepted=s.complete(job['id'],t,result.get('text',''),result.get('usable',False))
                report['requests'].append(dict(id=job['id'],key=job['key'],started=job['started'],completed=t,
                    source=job['payload']['meta'],accepted=accepted,**result))
                print(json.dumps(report['requests'][-1]),flush=True);future=None;job=None
        for obs in old['samples']:
            wait=obs['t']-(time.monotonic()-start)
            if wait>0:time.sleep(wait)
            now=time.monotonic()-start
            hands=[h for h in obs['hands'] if h['crop_top5']]
            chosen=None;dist=None
            if hands:
                chosen=max(hands,key=lambda h:iou(last_box,h['bbox'])) if last_box is not None else max(hands,key=lambda h:(h['bbox'][2]-h['bbox'][0])*(h['bbox'][3]-h['bbox'][1]))
                cap.set(cv2.CAP_PROP_POS_FRAMES,obs['frame_index']);ok,frame=cap.read()
                if not ok:raise ValueError('decode failed')
                h,w=frame.shape[:2];x1,y1,x2,y2=[round(v*z) for v,z in zip(chosen['crop_bbox'],[w,h,w,h])]
                roi=frame[y1:y2,x1:x2].copy();signature=cv2.resize(cv2.GaussianBlur(roi,(5,5),0),(16,16)).astype(np.float32)/255
                if last_box is None or now-last_hand>.65 or iou(last_box,chosen['bbox'])<.1:
                    epoch+=1;revision=1;anchor=signature
                else:
                    dist=float(np.mean(np.abs(signature-anchor)))
                    if dist>=.12:revision+=1;anchor=signature
                last_hand=now;last_box=chosen['bbox'];key=f't{epoch}:r{revision}'
                payload=dict(image=roi,meta=dict(source_t=obs['t'],frame_index=obs['frame_index'],crop=chosen['crop_bbox'],
                                               classifier=chosen['crop_top5'][0]))
                s.observe(now,key,payload,unknown=chosen['crop_top5'][0]['score']<.7)
            elif now-last_hand>.65:
                last_box=None;anchor=None;s.observe(now,None)
            # Current observation is applied before accepting any completed response.
            now=time.monotonic()-start;collect(now)
            request=s.dispatch(now)
            if request is not None:
                job=request;future=pool.submit(session.infer,request['payload']['image'])
            report['samples'].append(dict(source_t=obs['t'],wall_t=now,lag_s=now-obs['t'],key=s.key,
                hand_visible=bool(hands),selected_unknown=bool(chosen and chosen['crop_top5'][0]['score']<.7),
                appearance_distance=dist,pending_id=s.pending['id'] if s.pending else None,
                cached_request=s.cache['source_request'] if s.cache and now<s.cache['expires'] else None))
        if future is not None:future.result();collect(time.monotonic()-start)
        report['events']=s.events;report['summary']=dict(samples=len(report['samples']),requests=len(report['requests']),
            selected_unknown_frames=sum(x['selected_unknown'] for x in report['samples']),
            accepted_captions=sum(x['accepted'] for x in report['requests']),
            events=dict(Counter(e['type'] for e in s.events)),wall_seconds=time.monotonic()-start,
            max_replay_lag_s=max(x['lag_s'] for x in report['samples']))
        report['status']='completed';print(json.dumps(report['summary']),flush=True)
    except Exception as exc:report.update(status='failed',error=str(exc));raise
    finally:
        pool.shutdown(wait=True)
        if session:session.close()
        cap.release();report['events']=s.events;save();tegra.terminate()
        try:tegra.wait(timeout=5)
        except subprocess.TimeoutExpired:tegra.kill();tegra.wait()
        log.close()

if __name__=='__main__':main()
