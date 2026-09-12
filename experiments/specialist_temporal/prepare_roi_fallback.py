"""Freeze classifier-unknown routing and automatic ROIs from previous observations."""
import hashlib,json
from pathlib import Path
import cv2

src=Path('/home/jetson/openhalo-specialist-expanded')
dest=Path('/home/jetson/openhalo-roi-fallback');(dest/'media').mkdir(parents=True,exist_ok=True)
rp=src/'run-fresh-v1/report.json';old=json.loads(rp.read_text());case=old['cases'][0]
refs=json.loads((src/'reference-windows.json').read_text())['windows']
samples=case['samples'];selected=[]
for ref in refs:
    rows=[s for s in samples if ref['start']<=s['t']<=ref['end'] and s['hands']]
    s=min(rows,key=lambda s:abs(s['t']-(ref['start']+ref['end'])/2))
    hand=max(s['hands'],key=lambda h:(h['bbox'][2]-h['bbox'][0])*(h['bbox'][3]-h['bbox'][1]))
    selected.append((ref['name'],s,hand,'nearest midpoint, largest hand box; reused reference windows'))
    if ref['name'] in ['phone-front','screwdriver-a','screwdriver-b']:
        pairs=[(s,h) for s in rows for h in s['hands'] if h['crop_top5']]
        s,h=max(pairs,key=lambda pair:pair[1]['crop_top5'][0]['score'])
        selected.append((ref['name']+'-high-score',s,h,'maximum classifier confidence stress case; deliberately selected, not accuracy sample'))
cap=cv2.VideoCapture(case['video']);out=dict(config=dict(threshold=.7,route='ROI classifier top1 score < 0.7 triggers VLM; no hand means no ROI; detector/gesture scores do not control this isolated ablation'),
    previous_report_sha256=hashlib.sha256(rp.read_bytes()).hexdigest(),source_video_sha256=case['video_sha256'],cases=[])
for i,(name,s,h,selection) in enumerate(selected):
    cap.set(cv2.CAP_PROP_POS_FRAMES,s['frame_index']);ok,frame=cap.read()
    if not ok:raise ValueError('cannot decode frozen sample')
    height,width=frame.shape[:2]
    x1,y1,x2,y2=[round(v*z) for v,z in zip(h['crop_bbox'],[width,height,width,height])]
    roi=frame[y1:y2,x1:x2]
    fullpath=dest/'media'/f'{i:02}-full.png';roipath=dest/'media'/f'{i:02}-roi.png'
    cv2.imwrite(str(fullpath),frame);cv2.imwrite(str(roipath),roi)
    top=h['crop_top5'][0];trigger=top['score']<out['config']['threshold']
    out['cases'].append(dict(id=i,name=name,selection=selection,t=s['t'],frame_index=s['frame_index'],
        roi_bbox_pixels=[x1,y1,x2,y2],classifier_top1=top,trigger_vlm=trigger,
        frame=str(fullpath),roi=str(roipath),frame_sha256=hashlib.sha256(fullpath.read_bytes()).hexdigest(),
        roi_sha256=hashlib.sha256(roipath.read_bytes()).hexdigest(),frozen_specialist_ms=s['ms']))
cap.release();(dest/'cases.json').write_text(json.dumps(out,indent=2))
print(json.dumps([{k:c[k] for k in ['name','t','classifier_top1','trigger_vlm']} for c in out['cases']]))
