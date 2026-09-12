"""Expose the existing Isaac ROS experiment's TRT backend without ROS transport."""
import hashlib
import json
import time
from pathlib import Path

NAMES = ['nose','left_eye','right_eye','left_ear','right_ear','left_shoulder','right_shoulder',
         'left_elbow','right_elbow','left_wrist','right_wrist','left_hip','right_hip',
         'left_knee','right_knee','left_ankle','right_ankle']


class Measurements:
    def __init__(self):
        from ultralytics import YOLO
        self.paths = ['/home/jetson/ultralytics/yolo26n.engine', '/home/jetson/ultralytics/yolo26n-pose.engine']
        self.hashes = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in self.paths}
        self.detector = YOLO(self.paths[0], task='detect')
        self.pose = YOLO(self.paths[1], task='pose')

    def infer(self, frame, frame_id, pts):
        import torch
        h,w = frame.shape[:2]
        torch.cuda.synchronize(); start=time.perf_counter()
        det=self.detector.predict(frame,imgsz=640,conf=0.35,device=0,verbose=False)[0]
        torch.cuda.synchronize(); det_end=time.perf_counter()
        pose=self.pose.predict(frame,imgsz=640,conf=0.35,device=0,verbose=False)[0]
        torch.cuda.synchronize(); pose_end=time.perf_counter()
        boxes=[]
        for i,(cls,score,box) in enumerate(zip(det.boxes.cls,det.boxes.conf,det.boxes.xyxy)):
            boxes.append(dict(id=f'd{i}',label=det.names[int(cls)],confidence=round(float(score),4),
                bbox=[round(float(x)/scale,4) for x,scale in zip(box,[w,h,w,h])]))
        poses=[]
        if pose.keypoints is not None:
            for i,kps in enumerate(pose.keypoints.data.cpu().tolist()):
                points={name:dict(x=round(x/w,4),y=round(y/h,4),confidence=round(c,4),
                    usable=c>=0.5 and 0<x<w and 0<y<h) for name,(x,y,c) in zip(NAMES,kps)}
                poses.append(dict(id=f'p{i}',keypoints=points))
        return dict(frame_id=frame_id,source_pts_seconds=pts,pair_skew_ms=0,
            alignment='exact same decoded saved-frame pixels, not live timestamp synchronization',
            detections=boxes,poses=poses,detector_seconds=det_end-start,pose_seconds=pose_end-det_end,
            measurement_seconds=time.perf_counter()-start,
            missing_detection_means='unobserved by this detector, not absent',
            unmeasured=['grip/contact','gaze target','temporal action','intent'])


def prompt_evidence(e):
    # Preserve all classes in raw evidence; compact highest-confidence boxes
    # in the prompt. Do not selectively remove inconvenient false positives.
    boxes=sorted(e['detections'],key=lambda x:-x['confidence'])[:6]
    poses=[]
    for person in e['poses'][:2]:
        poses.append(dict(id=person['id'],keypoints={k:v for k,v in person['keypoints'].items()
            if k in ['nose','left_shoulder','right_shoulder','left_elbow','right_elbow','left_wrist','right_wrist']}))
    return ('Fallible measurements of this exact image (normalized coordinates; low-confidence points are uncertain): '
        +json.dumps(dict(detections=boxes,poses=poses),separators=(',',':'))
        +'\nA missed detection does not prove absence. Boxes or nearby wrists do not prove holding. '
        'These measurements do not establish gaze, intent, or temporal actions. Use the image as primary evidence.\n')
