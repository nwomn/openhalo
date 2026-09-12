"""Installed MediaPipe specialists; no package/environment mutation."""
import hashlib
import math
from pathlib import Path
import time


class Specialists:
    def __init__(self):
        import mediapipe as mp
        self.mp=mp
        self.hands=mp.solutions.hands.Hands(static_image_mode=False,max_num_hands=2,model_complexity=1,
            min_detection_confidence=.5,min_tracking_confidence=.5)
        self.face=mp.solutions.face_mesh.FaceMesh(static_image_mode=False,max_num_faces=2,
            refine_landmarks=False,min_detection_confidence=.5,min_tracking_confidence=.5)
        self.pose=mp.solutions.pose.Pose(static_image_mode=False,model_complexity=1,smooth_landmarks=True,
            enable_segmentation=False,min_detection_confidence=.5,min_tracking_confidence=.5)

    def manifest(self):
        base=Path(self.mp.__file__).parent
        names=['palm_detection/palm_detection_full.tflite','hand_landmark/hand_landmark_full.tflite',
            'face_detection/face_detection_short_range.tflite','face_landmark/face_landmark.tflite',
            'pose_detection/pose_detection.tflite','pose_landmark/pose_landmark_full.tflite']
        return dict(mediapipe=self.mp.__version__,models={n:hashlib.sha256((base/'modules'/n).read_bytes()).hexdigest() for n in names})

    def infer(self,rgb):
        start=time.perf_counter();hr=self.hands.process(rgb);he=time.perf_counter()
        fr=self.face.process(rgb);fe=time.perf_counter()
        pr=self.pose.process(rgb);pe=time.perf_counter()
        faces=[]
        for landmarks in fr.multi_face_landmarks or []:
            pts=[dict(x=p.x,y=p.y,z=p.z) for p in landmarks.landmark]
            xs=[p['x'] for p in pts];ys=[p['y'] for p in pts]
            faces.append(dict(center=[(min(xs)+max(xs))/2,(min(ys)+max(ys))/2],
                width=max(xs)-min(xs),height=max(ys)-min(ys),chin_y=pts[152]['y'],
                mouth=[(pts[13]['x']+pts[14]['x'])/2,(pts[13]['y']+pts[14]['y'])/2],
                landmarks=pts))
        hands=[]
        for i,landmarks in enumerate(hr.multi_hand_landmarks or []):
            pts=[dict(x=p.x,y=p.y,z=p.z) for p in landmarks.landmark]
            wrist=(pts[0]['x'],pts[0]['y'])
            fingers=sum(math.dist(wrist,(pts[tip]['x'],pts[tip]['y']))>
                1.15*math.dist(wrist,(pts[pip]['x'],pts[pip]['y'])) for tip,pip in [(8,6),(12,10),(16,14),(20,18)])
            palm=[sum(pts[k]['x'] for k in [0,5,9,13,17])/5,sum(pts[k]['y'] for k in [0,5,9,13,17])/5]
            md=None
            if len(faces)==1:
                f=faces[0];md=min(math.dist((pts[k]['x'],pts[k]['y']),f['mouth']) for k in [4,8,12,16,20])/max(f['width'],.04)
            # Handedness probability is not detection confidence; keep names explicit.
            handed=hr.multi_handedness[i].classification[0]
            hands.append(dict(landmarks=pts,palm=palm,open_fingers=int(fingers),
                mouth_distance_face_width=md,mirrored_handedness_label=handed.label,handedness_probability=handed.score))
        pose=[dict(x=p.x,y=p.y,z=p.z,visibility=p.visibility) for p in pr.pose_landmarks.landmark] if pr.pose_landmarks else []
        return dict(hands=hands,faces=faces,pose=pose,latency_seconds=dict(hand=he-start,face=fe-he,body=pe-fe,total=pe-start),
            quality_note='Hands/FaceMesh do not expose per-landmark confidence; pose visibility is separate; no gaze target')

    def close(self):
        self.hands.close();self.face.close();self.pose.close()
