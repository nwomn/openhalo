"""Bounded measurement-derived temporal states, not open-world semantics."""
from collections import deque
import math

CONFIG = dict(version='specialist-temporal-v1',debounce_s=.3,lost_after_s=.5,
              wave_window_s=1.6,wave_min_span_face_width=.35,wave_step_face_width=.12,
              wave_reversals=2,association_max_face_width=2.5)


class Fusion:
    def __init__(self):
        self.state='unknown';self.candidate=None;self.candidate_since=0
        self.last_seen=None;self.last_t=None;self.track=0;self.face_center=None
        self.history=deque();self.wave=False;self.last_wave_t=None
        self.near=False;self.near_candidate=None;self.near_since=0
        self.last_face_t=None

    def reset_motion(self):
        self.history.clear();self.wave=False;self.last_wave_t=None

    def update(self,t,obs):
        events=[]
        if self.last_t is not None and t<=self.last_t:raise ValueError('timestamps must increase')
        if self.last_t is not None and t-self.last_t>.6:
            self.reset_motion();self.state='unknown';events.append(dict(type='input_gap',t=t))
        self.last_t=t
        faces=obs['faces'];hands=obs['hands'];pose=obs['pose']
        if len(faces)!=1:
            raw='unknown';quality='no_face' if not faces else 'multiple_faces_ambiguous'
            self.reset_motion()
            face=None;selected=None
            if self.face_center is not None and self.last_face_t is not None and t-self.last_face_t>.5:
                self.face_center=None;events.append(dict(type='local_track_lost',track=self.track,t=t))
        else:
            face=faces[0];fx,fy=face['center'];fw=max(face['width'],.04)
            self.last_face_t=t
            if self.face_center is None or math.dist(self.face_center,(fx,fy))>.25:
                self.track+=1;self.reset_motion();self.state='unknown'
                events.append(dict(type='local_track_started',track=self.track,t=t))
            self.face_center=(fx,fy)
            eligible=[h for h in hands if abs(h['palm'][0]-fx)/fw<CONFIG['association_max_face_width']]
            selected=min(eligible,key=lambda h:h['palm'][1]) if eligible else None
            cut=face['chin_y']+.2*face['height']
            raw='unknown';quality='hand_unobserved'
            if selected:
                self.last_seen=t
                raw='hand_raised_zone' if selected['palm'][1]<=cut else 'hand_below_face'
                quality='dedicated_hand_landmarks'
            elif pose:
                wrists=[p for p in [pose[15],pose[16]] if p['visibility']>=.7 and .01<p['x']<.99 and .01<p['y']<.97]
                if wrists and all(p['y']>cut+.1*face['height'] for p in wrists):
                    raw='hand_below_face';quality='body_wrist_only; not hand absence'
            if len(eligible)>1:self.history.clear()
            if len(eligible)==1 and selected and raw=='hand_raised_zone' and selected['open_fingers']>=3:
                self.history.append((t,(selected['palm'][0]-fx)/fw))
            elif raw!='hand_raised_zone':self.history.clear()
            while self.history and t-self.history[0][0]>CONFIG['wave_window_s']:self.history.popleft()
            directions=[];anchor=self.history[0][1] if self.history else 0
            for _,x in self.history:
                if abs(x-anchor)>=CONFIG['wave_step_face_width']:
                    d=1 if x>anchor else -1
                    if not directions or d!=directions[-1]:directions.append(d)
                    anchor=x
            span=max((x for _,x in self.history),default=0)-min((x for _,x in self.history),default=0)
            detected=len(directions)-1>=CONFIG['wave_reversals'] and span>=CONFIG['wave_min_span_face_width']
            if detected:
                self.last_wave_t=t
                if not self.wave:
                    self.wave=True;events.append(dict(type='wave_motion_detected',t=t,
                        evidence_start=self.history[0][0],span_face_width=span,reversals=len(directions)-1))
            if self.wave and (self.last_wave_t is None or t-self.last_wave_t>.5):
                self.wave=False;events.append(dict(type='wave_motion_ended',t=t))
        if raw!=self.candidate:self.candidate=raw;self.candidate_since=t
        if raw!=self.state and t-self.candidate_since>=CONFIG['debounce_s']-1e-6:
            previous=self.state;self.state=raw
            event='state_changed'
            if previous=='hand_below_face' and raw=='hand_raised_zone':event='hand_raised'
            elif previous=='hand_raised_zone' and raw=='hand_below_face':event='hand_lowered'
            elif previous=='hand_raised_zone' and raw=='unknown':event='hand_observation_lost'
            elif raw=='hand_raised_zone':event='raised_hand_observed'
            events.append(dict(type=event,t=t,previous=previous,state=raw,evidence_start=self.candidate_since))
        # Absence or ambiguous association never becomes a fabricated lowered hand.
        near_raw=bool(face and selected and selected['mouth_distance_face_width'] is not None
                      and selected['mouth_distance_face_width']<.3)
        if near_raw!=self.near_candidate:self.near_candidate=near_raw;self.near_since=t
        if near_raw!=self.near and t-self.near_since>=.3-1e-6:
            self.near=near_raw;events.append(dict(type='hand_near_mouth' if near_raw else 'mouth_proximity_ended',t=t))
        return dict(raw_state=raw,state=self.state,quality=quality,local_track_id=self.track,
                    wave_motion=self.wave,hand_near_mouth=self.near,events=events,
                    boundary='image-plane measurements; no eating/holding-object/gaze/intent inference')
