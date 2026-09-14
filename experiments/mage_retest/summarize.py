"""Summarize archived replay rows and whole-device tegrastats samples."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import statistics

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('root',type=Path); args=ap.parse_args()
    samples=[]
    for line in (args.root/'telemetry.log').read_text().splitlines():
        m=re.match(r'(.{19}) RAM (\d+)/(\d+)MB .*?SWAP (\d+)/(\d+)MB',line)
        if m:
            t=datetime.strptime(m[1],'%m-%d-%Y %H:%M:%S').replace(tzinfo=timezone(timedelta(hours=8))).timestamp()
            samples.append((t,int(m[2]),int(m[4])))
    result={'telemetry_scope':'500 ms whole-device samples, 1 second boundary padding; inherited swap, not isolated model allocation','profiles':{}}
    for profile in ['full','codec']:
        rows=[json.loads(x) for x in (args.root/profile/'raw.jsonl').read_text().splitlines()]
        output={}
        for case in ['c14','c11','c12']:
            group=[x for x in rows if x['case']==case and not x['warmup']]
            assert len(group)==3 and all(x['input_checks_passed'] for x in group)
            measured=[s for s in samples if any(x['started_unix']-1<=s[0]<=x['started_unix']+x['seconds']+1 for x in group)]
            item=dict(seconds=[x['seconds'] for x in group],median_s=statistics.median(x['seconds'] for x in group),
                      output_tokens=[x['output_tokens'] for x in group],finish_reasons=[x['finish_reason'] for x in group],
                      texts=list(dict.fromkeys(x['text'] for x in group)),visual_tokens=group[0]['visual_tokens'],
                      represented_frames=group[0]['actual_input']['frames'],effective_frame_size=group[0]['effective_frame_size'],
                      ram_peak_mb=max(s[1] for s in measured),swap_min_mb=min(s[2] for s in measured),swap_max_mb=max(s[2] for s in measured),
                      warmup_s=[x['seconds'] for x in rows if x['case']==case and x['warmup']])
            for field in ['prepare_s','native_ms','vision_ms','prefill_ms','decode_ms']:
                item['median_'+field]=statistics.median(x[field] for x in group)
            output[case]=item
        result['profiles'][profile]=output
    (args.root/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
