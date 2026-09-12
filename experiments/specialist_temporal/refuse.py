"""Re-evaluate frozen observations, explicitly not an independent accuracy test."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
from fusion import Fusion, CONFIG

p=argparse.ArgumentParser()
p.add_argument('--input',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
report=dict(config=CONFIG, boundary='fusion-only ablation of existing model observations; no new model timing',
            fusion_sha256=hashlib.sha256(Path(__file__).with_name('fusion.py').read_bytes()).hexdigest(),cases=[])
for path in sorted(a.input.glob('*-raw.jsonl.gz')):
    f=Fusion(); rows=[]; events=[]
    for line in gzip.open(path,'rt'):
        r=json.loads(line); result=f.update(r['t'],r['observations'])
        rows.append(dict(t=r['t'],**result)); events.extend(result['events'])
    report['cases'].append(dict(name=path.name,raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                               state_counts=dict(Counter(r['state'] for r in rows)),events=events,samples=rows))
with a.output.open('x') as out: json.dump(report,out,indent=2)
for r in report['cases']: print(r['name'],r['state_counts'],r['events'])
