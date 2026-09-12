"""Recompute bounded replay statistics and verify archived source bytes."""
import hashlib,json,math,re
from pathlib import Path

root=Path(__file__).resolve().parent
scripts=root.parents[3]/'experiments'/'specialist_temporal'
def percentile(values,p):
    v=sorted(values);k=(len(v)-1)*p;i=int(k)
    return v[i]+(v[min(i+1,len(v)-1)]-v[i])*(k-i)

out={}
for version in ['v1','v2']:
    path=root/f'run-{version}.json'
    if not path.exists():continue
    r=json.loads(path.read_text());requests=r['requests']
    for name,expected in r['source_hashes'].items():
        source=root/'async_roi_replay_v1.py' if version=='v1' and name=='async_roi_replay.py' else scripts/name
        assert hashlib.sha256(source.read_bytes()).hexdigest()==expected,(version,name)
    assert all(a['completed']<=b['started'] for a,b in zip(requests,requests[1:])), 'overlap'
    seconds=[q['seconds'] for q in requests]
    logs=(root/f'run-{version}-tegrastats.log').read_text()
    ram=[int(x) for x in re.findall(r'RAM (\d+)/',logs)]
    swap=[int(x) for x in re.findall(r'SWAP (\d+)/',logs)]
    out[version]=dict(**r['summary'],
        model_seconds=dict(min=min(seconds),median=percentile(seconds,.5),p95=percentile(seconds,.95),max=max(seconds)),
        avoided_vs_per_selected_unknown_frame=1-len(requests)/r['summary']['selected_unknown_frames'],
        maximum_backend_concurrency=1 if requests else 0,
        ram_peak_mb=max(ram),swap_min_mb=min(swap),swap_max_mb=max(swap),
        cached=[dict(id=q['id'],source_t=q['source']['source_t'],key=q['key'],text=q['text']) for q in requests if q['accepted']])
tests=json.loads((root/'tests.json').read_text())
for name,digest in tests['sources'].items():assert hashlib.sha256((scripts/name).read_bytes()).hexdigest()==digest
(root/'summary.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
