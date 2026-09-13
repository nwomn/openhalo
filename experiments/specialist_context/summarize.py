"""Verify causal inputs/repeats and recompute manually reviewed semantic metrics."""
import hashlib,json,re
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pct(v,p):
    v=sorted(v);k=(len(v)-1)*p;i=int(k)
    return v[i]+(v[min(i+1,len(v)-1)]-v[i])*(k-i)

root=Path(__file__).resolve().parents[2]
e=root/'docs/ops/evidence/2026-09-13-specialist-context'
r=json.loads((e/'report.json').read_text());m=json.loads((e/'manifest.json').read_text())
assert r['status']=='completed' and r['manifest_sha256']==sha(e/'manifest.json')
assert m['prepare_sha256']==sha(Path(__file__).with_name('prepare.py'))
for name,h in r['source_hashes'].items():
    p=root/'experiments/specialist_temporal/vlm_session.py' if name=='vlm_session.py' else Path(__file__).with_name(name)
    assert sha(p)==h,name
prior=root/'docs/ops/evidence/2026-09-12-roi-singleflight/run-v2.json'
assert sha(prior)==m['source_hashes']['/home/jetson/openhalo-roi-singleflight/run-v2/report.json']
old=json.loads(prior.read_text());req={x['id']:x for x in old['requests']}
for c in m['cases']:
    if c['roi_cache']:
        q=req[c['roi_cache']['request_id']]
        assert q['accepted'] and q['completed']<=c['available_at'] and q['text']==c['roi_cache']['text']
        state=next(s for s in old['samples'] if s['wall_t']==c['available_at'])
        assert state['cached_request']==q['id'] and state['key']==q['key']
    runs=next(x['runs'] for x in r['cases'] if x['id']==c['id'])
    assert len(runs)==6
    if not c['roi_cache']:
        assert next(x['full_prompt'] for x in runs if x['arm']=='specialists')==next(x['full_prompt'] for x in runs if x['arm']=='cascade')
out=dict(images=len(m['cases']),cache_present=sum(bool(c['roi_cache']) for c in m['cases']),
    formal_generations=sum(len(c['runs']) for c in r['cases']),arms={},hashes=dict(report=sha(e/'report.json'),reference=sha(e/'reference.json')))
for arm in ['image','specialists','cascade']:
    runs=[x for c in r['cases'] for x in c['runs'] if x['arm']==arm];v=[x['seconds'] for x in runs]
    out['arms'][arm]=dict(min_s=min(v),median_s=pct(v,.5),p95_s=pct(v,.95),max_s=max(v),
        token_limit=sum(x['hit_token_limit'] for x in runs),
        repeat_matching_images=sum(len({x['text'] for x in c['runs'] if x['arm']==arm})==1 for c in r['cases']))
review=e/'review.json'
if review.exists():
    reviewed=json.loads(review.read_text())
    for arm in out['arms']:
        rows=[x for x in reviewed['rows'] if x['arm']==arm]
        assert len(rows)==len(m['cases'])
        for row in rows:
            actual=[x['text'] for c in r['cases'] if c['id']==row['id'] for x in c['runs'] if x['arm']==arm]
            assert len(set(actual))==1 and row['text']==actual[0]
        out['arms'][arm]['review']={key:sum(x[key] for x in rows) for key in ['object_correct','gesture_correct','empty_confirmed','target_error','other_error']}
stats=(e/'tegrastats.log').read_text()
out['resources']=dict(ram_peak_mb=max(map(int,re.findall(r'RAM (\d+)/',stats))),
    swap_min_mb=min(map(int,re.findall(r'SWAP (\d+)/',stats))),swap_max_mb=max(map(int,re.findall(r'SWAP (\d+)/',stats))))
(e/'summary.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
