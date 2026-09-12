"""Human-selected object regions: classifier diagnosis, NOT autonomous detection."""
import hashlib
import json
from pathlib import Path
import cv2
from ultralytics import YOLO

root=Path('/home/jetson/openhalo-specialist-expanded')
model=YOLO('/home/jetson/ultralytics/yolo26n-cls.engine',task='classify')
# Coordinates selected from image inspection before these predictions.
cases=[('phone-front',[.285,.19,.435,.71]),('phone-back',[.375,.09,.60,.66]),
       ('screwdriver',[.38,.14,.52,.58]),('empty-palm',[.25,.14,.56,.81])]
out=dict(boundary='manual oracle ROI, JPEG frames at 4/39.5/45.5/52 seconds; not autonomous ROI accuracy',cases=[])
for name,box in cases:
    path=root/'fresh-2157'/(name+'.jpg');f=cv2.imread(str(path));h,w=f.shape[:2]
    x1,y1,x2,y2=[int(v*z) for v,z in zip(box,[w,h,w,h])];crop=f[y1:y2,x1:x2]
    ch,cw=crop.shape[:2];side=max(ch,cw)
    square=cv2.copyMakeBorder(crop,(side-ch)//2,side-ch-(side-ch)//2,
                              (side-cw)//2,side-cw-(side-cw)//2,cv2.BORDER_CONSTANT,value=(114,114,114))
    row=dict(name=name,bbox=box,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),variants={})
    for variant,image in [('default_center_crop',crop),('square_padded',square)]:
        r=model.predict(image,imgsz=224,device=0,verbose=False)[0]
        row['variants'][variant]=[dict(label=r.names[int(k)],score=float(r.probs.data[k])) for k in r.probs.top5]
    out['cases'].append(row);print(json.dumps(row),flush=True)
(root/'crop-diagnostic.json').write_text(json.dumps(out,indent=2))
