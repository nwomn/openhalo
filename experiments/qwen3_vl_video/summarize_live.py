"""Validate retained live handoffs and compute latency/resource summaries."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import statistics


def distribution(values):
    ordered = sorted(values)
    # Linear-interpolated sample P95; this small probe is not a population bound.
    pos = .95*(len(ordered)-1)
    lo = int(pos)
    hi = min(lo+1,len(ordered)-1)
    return dict(min=min(values), median=statistics.median(values),
                p95=ordered[lo]+(ordered[hi]-ordered[lo])*(pos-lo), max=max(values))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    root = p.parse_args().run
    rows = [json.loads(s) for s in (root/'raw.jsonl').read_text().splitlines()]
    capture = [json.loads(s) for s in (root/'capture.jsonl').read_text().splitlines()]
    assert [r['seq'] for r in capture] == list(range(len(capture)))
    expected = 0
    for r in rows:
        assert r['source_first_seq']==expected
        expected = r['source_last_seq']+1
        assert r['captured_frames']==expected-r['source_first_seq']
        assert r['input_checks_passed'] and r['overflow']==0
    assert expected==len(capture)
    for a,b in zip(rows,rows[1:]):
        assert a['window_end']==b['window_start']
        assert b['started_mono']>=a['finished_mono']
    result = dict(batches=len(rows), captured_frames=len(capture),
        capture_span_s=capture[-1]['arrival_mono']-capture[0]['arrival_mono'],
        capture_average_fps=(len(capture)-1)/(capture[-1]['arrival_mono']-capture[0]['arrival_mono']),
        every_delivered_sequence_handed_off_once=True, overflow=0,
        natural_stops=sum(r['finish_reason']=='stop' for r in rows),
        under_8s=sum(r['seconds']<=8 for r in rows), under_10s=sum(r['seconds']<=10 for r in rows),
        padded_batches=[r['batch_id'] for r in rows if r['unique_selected']<16],
        inference_s=distribution([r['seconds'] for r in rows]),
        oldest_input_age_s=distribution([r['oldest_frame_age_s'] for r in rows]),
        newest_input_age_s=distribution([r['newest_frame_age_s'] for r in rows]),
        ongoing_newest_input_age_s=distribution([r['newest_frame_age_s'] for r in rows if not r['capture_done']]),
        window_s=distribution([r['window_s'] for r in rows]),
        handoff_gap_s=distribution([b['started_mono']-a['finished_mono'] for a,b in zip(rows,rows[1:])]),
        arrival_gap_s=distribution([b['arrival_mono']-a['arrival_mono'] for a,b in zip(capture,capture[1:])]))
    samples=[]
    pattern = re.compile(r'^(.*?) RAM (\d+)/(\d+)MB.*?SWAP (\d+)/\d+MB.*?CPU \[(.*?)\].*?GR3D_FREQ (\d+)%.*?tj@([\d.]+)C.*?VDD_IN (\d+)mW')
    for line in (root/'tegrastats.log').read_text().splitlines():
        m=pattern.search(line)
        if not m:
            continue
        stamp=datetime.strptime(m[1],'%m-%d-%Y %H:%M:%S').replace(tzinfo=timezone(timedelta(hours=8))).timestamp()
        if any(r['started_unix']<=stamp<r['started_unix']+r['seconds'] for r in rows):
            cpus=[int(x) for x in re.findall(r'(\d+)%',m[5])]
            samples.append(dict(ram=int(m[2]),swap=int(m[4]),gpu=int(m[6]),
                                tj=float(m[7]),watts=int(m[8])/1000,cpu_mean=statistics.mean(cpus)))
    result['telemetry']=dict(samples=len(samples),
        ram_mb=distribution([s['ram'] for s in samples]),
        swap_mb=distribution([s['swap'] for s in samples]),
        gpu_mean=statistics.mean(s['gpu'] for s in samples), gpu_max=max(s['gpu'] for s in samples),
        cpu_all_cores_mean=statistics.mean(s['cpu_mean'] for s in samples),
        power_w_mean=statistics.mean(s['watts'] for s in samples),power_w_max=max(s['watts'] for s in samples),
        tj_c_max=max(s['tj'] for s in samples))
    (root/'summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
