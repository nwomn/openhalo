"""Audit prompt ablation exactly and publish complete prompts without filtering."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
from replay_json import PROMPT
from replay_prompts import cached_inputs

p=argparse.ArgumentParser();p.add_argument('directory',type=Path)
p.add_argument('--original',type=Path,required=True);a=p.parse_args()
r=json.loads((a.directory/'report.json').read_text());old=json.loads(a.original.read_text())
assert r['status']=='completed' and len(r['cases'])==8
assert r['previous_report_sha256']==hashlib.sha256(a.original.read_bytes()).hexdigest()
s=dict(status=r['status'],arms={},cases=[],prompt_audit='pending',model_load_seconds=r['load_seconds'],
    boundary='same eight images replayed, no new holdout; cached measurements; raw outputs only; no C')
prompts=['# Actual complete model conversation prompts','',
    'These are the actual strings passed through image-token tokenization, including the official conversation template.',
    'The <image> marker is replaced by image embeddings during inference. Identical repeated prompts are shown once; repeat indices are listed.', '']
checks=0
for c in r['cases']:
    original=next(x for x in old['cases'] if x['name']==c['name'])
    row=dict(name=c['name'],prior_split=c['split'],arms={})
    prompts+=['## '+c['name'],'']
    for repeat in range(2):
        old_b=next(x for x in original['runs'] if x['arm']=='B' and x['repeat']==repeat)
        cached=cached_inputs(old_b,c)
        pair={x['arm']:x for x in c['runs'] if x['repeat']==repeat}
        assert set(pair)=={'A','J','B'}
        assert pair['A']['evidence_prompt']==''
        assert pair['J']['evidence_prompt']==cached['json_text']+'\n'
        assert pair['B']['evidence_prompt']==old_b['evidence_prompt']
        for arm,item in pair.items():
            assert 'C' not in item and item['json_sha256']==cached['json_sha256']
            assert PROMPT in item['full_prompt']
            assert item['full_prompt'].count('<image>\n'+item['evidence_prompt']+PROMPT)==1
            assert item['full_prompt'].replace('<image>\n'+item['evidence_prompt']+PROMPT,
                '<image>\n'+PROMPT,1)==pair['A']['full_prompt']
            checks+=1
    for arm in ['A','J','B']:
        runs=[x for x in c['runs'] if x['arm']==arm]
        row['arms'][arm]=dict(outputs=sorted(set(x['output'] for x in runs)),seconds=[x['total_seconds'] for x in runs],
            input_tokens=[x['input_tokens'] for x in runs],output_tokens=[x['output_tokens'] for x in runs])
        if arm!='J':
            row['arms'][arm]['matches_original_outputs']=all(x['output']==next(o['output'] for o in original['runs']
                if o['arm']==arm and o['repeat']==x['repeat']) for x in runs)
        for full in dict.fromkeys(x['full_prompt'] for x in runs):
            reps=[str(x['repeat']) for x in runs if x['full_prompt']==full]
            prompts += [f'### {arm}, repetitions '+', '.join(reps),'','```text',full,'```','']
    s['cases'].append(row)
for arm in ['A','J','B']:
    runs=[x for c in r['cases'] for x in c['runs'] if x['arm']==arm]
    times=[x['total_seconds'] for x in runs]
    s['arms'][arm]=dict(executions=len(runs),min_seconds=min(times),median_seconds=statistics.median(times),max_seconds=max(times),
        input_token_range=[min(x['input_tokens'] for x in runs),max(x['input_tokens'] for x in runs)],
        output_token_range=[min(x['output_tokens'] for x in runs),max(x['output_tokens'] for x in runs)],
        truncated=sum(x['hit_token_limit'] for x in runs))
log=(a.directory/'tegrastats.log').read_text()
for name,pattern in [('ram_mb',r'RAM (\d+)/'),('swap_mb',r'SWAP (\d+)/'),('temperature_c',r'\w+@([\d.]+)C')]:
    s['peak_'+name]=max(map(float,re.findall(pattern,log)))
s['prompt_audit']=f'{checks} complete prompts checked: only expected evidence insertion differs from unchanged A'
(a.directory/'summary.json').write_text(json.dumps(s,indent=2))
(a.directory/'actual-prompts.md').write_text('\n'.join(prompts),encoding='utf-8')
print(json.dumps(s,indent=2))
