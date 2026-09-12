"""Extract exact saved B JSON, keeping original object order and formatting."""
import hashlib
import json


def cached_inputs(original,case):
    e=original['evidence']
    if e['frame_id']!=case['sha256'] or e['source_pts_seconds']!=case['source_pts_seconds'] or e['pair_skew_ms']!=0:
        raise ValueError('cached measurement/image identity or PTS mismatch')
    text=original['evidence_prompt']
    start=text.index('{')
    data,end=json.JSONDecoder().raw_decode(text[start:])
    raw=text[start:start+end]
    if set(data)!={'detections','poses'}:
        raise ValueError('unexpected old JSON schema')
    # Check the frozen old selection against the stored raw measurements,
    # without changing any content, ordering, formatting or uncertainty fields.
    boxes=sorted(e['detections'],key=lambda v:-v['confidence'])[:6]
    poses=[]
    for person in e['poses'][:2]:
        poses.append(dict(id=person['id'],keypoints={k:v for k,v in person['keypoints'].items()
            if k in ['nose','left_shoulder','right_shoulder','left_elbow','right_elbow','left_wrist','right_wrist']}))
    if data!=dict(detections=boxes,poses=poses):
        raise ValueError('saved prompt JSON differs from frozen selection')
    return dict(json_text=raw,json_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        removed_prefix=text[:start],removed_suffix=text[start+end:])
