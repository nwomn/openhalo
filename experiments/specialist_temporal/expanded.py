"""Trained gesture classification, object detection and hand ROI classification.

No face recognition/identity, VLM or assertion that overlap proves holding.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time

CONFIG=dict(version='expanded-v1',gesture_threshold=.7,gesture_persistence_s=.4,
            detection_threshold=.35,hand_roi_scale=2.2,hand_roi_min_image_fraction=.15)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class Expanded:
    def __init__(self,model_dir):
        import mediapipe as mp
        from ultralytics import YOLO
        self.mp=mp
        self.paths=[str(model_dir/'gesture_recognizer.task'),'/home/jetson/ultralytics/yolo26n.engine',
                    '/home/jetson/ultralytics/yolo26n-cls.engine']
        opts=mp.tasks.vision.GestureRecognizerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=self.paths[0]),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,num_hands=2,
            min_hand_detection_confidence=.5,min_hand_presence_confidence=.5,min_tracking_confidence=.5)
        self.g=mp.tasks.vision.GestureRecognizer.create_from_options(opts)
        self.det=YOLO(self.paths[1],task='detect');self.cls=YOLO(self.paths[2],task='classify')
        self.candidate=None;self.since=0;self.stable='unknown'

    def infer(self,frame,t):
        import cv2,torch
        h,w=frame.shape[:2];torch.cuda.synchronize();begin=time.perf_counter()
        image=self.mp.Image(image_format=self.mp.ImageFormat.SRGB,data=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
        g=self.g.recognize_for_video(image,round(t*1000));ge=time.perf_counter()
        d=self.det.predict(frame,imgsz=640,conf=CONFIG['detection_threshold'],device=0,verbose=False)[0]
        torch.cuda.synchronize();de=time.perf_counter()
        objects=[dict(label=d.names[int(c)],score=float(s),bbox=[float(v)/z for v,z in zip(b,[w,h,w,h])])
                 for c,s,b in zip(d.boxes.cls,d.boxes.conf,d.boxes.xyxy)]
        hands=[]
        for i,pts in enumerate(g.hand_landmarks):
            xs=[p.x for p in pts];ys=[p.y for p in pts]
            box=[min(xs),min(ys),max(xs),max(ys)];cx=(box[0]+box[2])/2;cy=(box[1]+box[3])/2
            side=max((box[2]-box[0])*w,(box[3]-box[1])*h,min(w,h)*CONFIG['hand_roi_min_image_fraction'])*CONFIG['hand_roi_scale']
            x1=max(0,int(cx*w-side/2));y1=max(0,int(cy*h-side/2));x2=min(w,int(cx*w+side/2));y2=min(h,int(cy*h+side/2))
            classes=[]
            if x2>x1 and y2>y1:
                c=self.cls.predict(frame[y1:y2,x1:x2],imgsz=224,device=0,verbose=False)[0]
                classes=[dict(label=c.names[int(k)],score=float(c.probs.data[k])) for k in c.probs.top5]
            near=[]
            for obj in objects:
                if obj['label']=='person':continue
                ox1,oy1,ox2,oy2=obj['bbox']
                overlap=max(0,min(box[2],ox2)-max(box[0],ox1))*max(0,min(box[3],oy2)-max(box[1],oy1))
                if overlap>0:near.append(dict(**obj,relation='2d_hand_box_overlap; holding_unverified'))
            hands.append(dict(landmarks=[[p.x,p.y,p.z] for p in pts],bbox=box,
                gestures=[dict(label=c.category_name,score=c.score) for c in g.gestures[i]],
                crop_bbox=[x1/w,y1/h,x2/w,y2/h],crop_top5=classes,overlapping_objects=near))
        torch.cuda.synchronize();end=time.perf_counter()
        raw='unknown'
        if len(hands)==1 and hands[0]['gestures']:
            top=hands[0]['gestures'][0]
            if top['score']>=CONFIG['gesture_threshold'] and top['label']!='None':raw=top['label']
        if raw!=self.candidate:self.candidate=raw;self.since=t
        events=[]
        if raw!=self.stable and t-self.since>=CONFIG['gesture_persistence_s']-1e-6:
            events.append(dict(type='gesture_state_changed',previous=self.stable,current=raw,t=t,evidence_start=self.since));self.stable=raw
        return dict(t=t,hands=hands,objects=objects,gesture_raw=raw,gesture_stable=self.stable,events=events,
                    ms=dict(gesture=(ge-begin)*1000,detector=(de-ge)*1000,roi_classification=(end-de)*1000,total=(end-begin)*1000),
                    boundary='closed-set gesture/object classes; ROI top1 and 2D overlap do not establish held object')

def main():
    p=argparse.ArgumentParser();p.add_argument('--cases',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--models',type=Path,default=Path('/home/jetson/openhalo-specialist-expanded/models'))
    p.add_argument('--hz',type=float,default=5);a=p.parse_args();a.output.mkdir(exist_ok=False,parents=True)
    import cv2,numpy as np
    cv2.setNumThreads(2)
    report=dict(status='running',config=CONFIG,source_sha256=sha(__file__),sampling_hz=a.hz,cases=[],
                boundary='sequential saved-video replay, not live camera-to-event P95; no biometric identity')
    def save():(a.output/'report.json').write_text(json.dumps(report,indent=2))
    log=(a.output/'tegrastats.log').open('w');tegra=subprocess.Popen(['tegrastats','--interval','500'],stdout=log,stderr=log)
    model=None
    try:
        for case in json.loads(a.cases.read_text()):
            model=Expanded(a.models);report['model_sha256']={x:sha(x) for x in model.paths}
            cap=cv2.VideoCapture(case['video']);fps=cap.get(cv2.CAP_PROP_FPS)
            if not cap.isOpened() or fps<=0:raise ValueError('cannot open case video')
            r=dict(**case,video_sha256=sha(case['video']),source_fps=fps,samples=[]);report['cases'].append(r)
            i=0;next_t=case.get('start_s',0)
            while cap.grab():
                t=i/fps;i+=1
                if t>case.get('end_s',float('inf')):break
                if t+1e-6<next_t:continue
                next_t=t+1/a.hz;ok,frame=cap.retrieve()
                if not ok:raise ValueError('decode failed')
                out=model.infer(frame,t);out['frame_index']=i-1;r['samples'].append(out)
            cap.release();model.g.close();model=None
            warm=r['samples'][1:]
            r['summary']=dict(samples=len(r['samples']),gesture_states=dict(Counter(x['gesture_stable'] for x in r['samples'])),
                              hand_samples=sum(bool(x['hands']) for x in r['samples']),
                              model_mean_ms=statistics.mean(x['ms']['total'] for x in warm),
                              model_p95_ms=float(np.percentile([x['ms']['total'] for x in warm],95)))
            print(json.dumps(dict(case=case['name'],summary=r['summary'])),flush=True);save()
        report['status']='completed'
    except Exception as exc:report.update(status='failed',error=f'{type(exc).__name__}: {exc}');raise
    finally:
        if model:model.g.close()
        save();tegra.terminate()
        try:tegra.wait(timeout=5)
        except subprocess.TimeoutExpired:tegra.kill();tegra.wait()
        log.close()

if __name__=='__main__':main()
