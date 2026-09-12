"""Preserve frozen C-v1 and separately re-check it with diagnostic parser fixes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import time
from claims import check,VERSION

p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args()
r=json.loads((a.directory/'report.json').read_text())
s=dict(status=r['status'],nf4_linears=r['nf4_linears'],load_seconds=r['load_seconds'],arms={},cases=[],
    diagnostic_gate=VERSION,diagnostic_gate_sha256=hashlib.sha256(Path(__file__).with_name('claims.py').read_bytes()).hexdigest(),
    boundary='v1 raw outputs untouched; v1.1 is a post-result parser repair, not independent held-out validation; no accuracy statistic inferred')
diagnostic=[]
for c in r['cases']:
    row=dict(name=c['name'],split=c['split'])
    for arm in ['A','B']:
        runs=[x for x in c['runs'] if x['arm']==arm]
        row[arm]=dict(outputs=sorted(set(x['output'] for x in runs)),seconds=[x['total_seconds'] for x in runs])
    row['C_v1_all_withdrawn']=all(x['C']['all_withdrawn'] for x in c['runs'] if x['arm']=='B')
    fixes=[]
    for b in [x for x in c['runs'] if x['arm']=='B']:
        start=time.perf_counter();result=check(b['output'],b['evidence'],c['sha256'],c['source_pts_seconds'],not b['hit_token_limit'])
        result['offline_gate_seconds']=time.perf_counter()-start
        fixes.append(result)
    row['C_v1_1_all_withdrawn']=all(x['all_withdrawn'] for x in fixes)
    row['C_v1_1_retained']=fixes[0]['retained_claims']
    diagnostic.append(dict(case=c['name'],runs=fixes));s['cases'].append(row)
for arm in ['A','B']:
    runs=[x for c in r['cases'] for x in c['runs'] if x['arm']==arm]
    vals=[x['total_seconds'] for x in runs]
    s['arms'][arm]=dict(executions=len(vals),min_seconds=min(vals),median_seconds=statistics.median(vals),max_seconds=max(vals),
        token_range=[min(x['output_tokens'] for x in runs),max(x['output_tokens'] for x in runs)],
        input_token_range=[min(x['input_tokens'] for x in runs),max(x['input_tokens'] for x in runs)],
        truncated_count=sum(x['hit_token_limit'] for x in runs))
low=[x['evidence']['measurement_seconds'] for c in r['cases'] for x in c['runs'] if x['arm']=='B']
s['measurement_seconds']=dict(min=min(low),median=statistics.median(low),max=max(low))
s['C_v1_all_withdrawn_frames']=sum(c['C_v1_all_withdrawn'] for c in s['cases'])
s['C_v1_1_all_withdrawn_frames']=sum(c['C_v1_1_all_withdrawn'] for c in s['cases'])
s['C_v1_1_verified_claim_count']=sum(x['verified_claim_count'] for d in diagnostic for x in d['runs'])
raw=(a.directory/'tegrastats.log').read_text()
for name,pattern in [('ram_mb',r'RAM (\d+)/'),('swap_mb',r'SWAP (\d+)/'),('temperature_c',r'\w+@([\d.]+)C')]:
    values=list(map(float,re.findall(pattern,raw)));s['peak_'+name]=max(values) if values else None
(a.directory/'diagnostic-gate-v1.1.json').write_text(json.dumps(diagnostic,indent=2))
(a.directory/'summary.json').write_text(json.dumps(s,indent=2))
print(json.dumps(s,indent=2))
