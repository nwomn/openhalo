"""Freeze causal full-image/specialist/ROI-cache comparison inputs before generation."""
import argparse,hashlib,json
from pathlib import Path

TIMES=[4,5,11,13,19,21,30,32.5,35,36.5,39,40.5,46,48,52.5,54,65,80]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    import cv2,numpy as np
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    a.root.mkdir(parents=True,exist_ok=False);(a.root/'media').mkdir()
    specialist=Path('/home/jetson/openhalo-specialist-expanded/run-fresh-v1/report.json')
    cache=Path('/home/jetson/openhalo-roi-singleflight/run-v2/report.json')
    original=json.loads(specialist.read_text())['cases'][0];prior=json.loads(cache.read_text())
    assert sha(original['video'])==original['video_sha256']
    observations=original['samples'];requests={r['id']:r for r in prior['requests']}
    cap=cv2.VideoCapture(original['video']);tiles=[]
    manifest=dict(selection='18 predeclared timestamps; no generation-output selection; reused development video',
        times=TIMES,source_hashes={str(specialist):sha(specialist),str(cache):sha(cache)},
        video_sha256=original['video_sha256'],prepare_sha256=sha(__file__),cases=[])
    for i,t in enumerate(TIMES):
        state=max((s for s in prior['samples'] if s['wall_t']<=t),key=lambda s:s['wall_t'])
        obs=min(observations,key=lambda s:abs(s['t']-state['source_t']))
        assert abs(obs['t']-state['source_t'])<1e-6
        cap.set(cv2.CAP_PROP_POS_FRAMES,obs['frame_index']);ok,frame=cap.read();assert ok
        path=a.root/'media'/f'{i:02}-full.png';cv2.imwrite(str(path),frame)
        hands=[]
        for h in obs['hands']:
            top=h['crop_top5'][0] if h['crop_top5'] else None
            hands.append(dict(bbox=[round(v,3) for v in h['bbox']],
                object_candidate=top if top and top['score']>=.7 else 'unknown',
                overlapping_objects=[dict(label=o['label'],score=round(o['score'],3)) for o in h['overlapping_objects']]))
        ctx=dict(gesture=obs['gesture_stable'],hands=hands,
            detected_objects=[dict(label=o['label'],score=round(o['score'],3)) for o in obs['objects']],
            recent_gesture_changes=[dict(age_s=round(obs['t']-e['t'],2),previous=e['previous'],current=e['current'])
                for s in observations if obs['t']-4<=s['t']<=obs['t'] for e in s['events']])
        caption=None;rid=state['cached_request']
        if rid is not None:
            r=requests[rid];assert r['accepted'] and r['completed']<=state['wall_t'] and r['key']==state['key']
            caption=dict(text=r['text'],status='unverified_model_caption',
                image_age_s=round(state['wall_t']-r['source']['source_t'],3),request_id=rid)
        manifest['cases'].append(dict(id=i,requested_t=t,source_t=obs['t'],available_at=state['wall_t'],
            frame=str(path),frame_sha256=sha(path),specialists=ctx,roi_cache=caption))
        tile=cv2.resize(frame,(384,216));cv2.putText(tile,f'{i:02} t={obs["t"]:.2f} cache={rid}',(8,23),cv2.FONT_HERSHEY_SIMPLEX,.55,(0,255,255),2)
        tiles.append(tile)
    cap.release()
    cv2.imwrite(str(a.root/'contact.jpg'),np.vstack([np.hstack(tiles[j:j+3]) for j in range(0,len(tiles),3)]))
    (a.root/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps([dict(id=c['id'],t=c['source_t'],cache=c['roi_cache']) for c in manifest['cases']]))

if __name__=='__main__':main()
