"""Paired full-image and causal candidate-context semantic ablation, no Runtime."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from context_session import ContextSession

QUESTION='Describe what the person is visibly doing and any object visibly held, in one short sentence.'
GUIDANCE='The following observations are uncertain candidates. Check them against the image; do not treat them as confirmed facts. '
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    import cv2
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);cv2.setNumThreads(2)
    mpath=a.root/'manifest.json';m=json.loads(mpath.read_text())
    report=dict(status='loading',manifest_sha256=sha(mpath),manifest=m,question=QUESTION,guidance=GUIDANCE,
        source_hashes={n:sha(Path(__file__).with_name(n)) for n in ['benchmark.py','context_session.py','vlm_session.py']},
        boundary='real second-stage VLM; cached causal stage-one measurements and captions; not integrated scheduling or live latency',cases=[])
    def save():(a.output/'report.json').write_text(json.dumps(report,indent=2))
    log=(a.output/'tegrastats.log').open('w');tegra=subprocess.Popen(['tegrastats','--interval','500'],stdout=log,stderr=log);session=None
    try:
        session=ContextSession();report['model']=session.info
        report['warmup']=session.infer(cv2.imread(m['cases'][0]['frame']),QUESTION);report['status']='running';save()
        for c in m['cases']:
            assert sha(c['frame'])==c['frame_sha256'];frame=cv2.imread(c['frame'])
            small=GUIDANCE+json.dumps(c['specialists'],separators=(',',':'))+'\n'+QUESTION
            enriched=dict(**c['specialists'],roi_cache=c['roi_cache']) if c['roi_cache'] else c['specialists']
            cascade=GUIDANCE+json.dumps(enriched,separators=(',',':'))+'\n'+QUESTION
            prompts=dict(image=QUESTION,specialists=small,cascade=cascade)
            row=dict(id=c['id'],source_t=c['source_t'],runs=[]);report['cases'].append(row)
            for repeat in range(2):
                arms=['image','specialists','cascade'];shift=(c['id']+repeat)%3;arms=arms[shift:]+arms[:shift]
                for arm in arms:
                    result=dict(arm=arm,repeat=repeat,**session.infer(frame,prompts[arm]));row['runs'].append(result)
                    print(json.dumps(dict(id=c['id'],**{k:v for k,v in result.items() if k!='full_prompt'})),flush=True);save()
        report['status']='completed'
    except Exception as exc:report.update(status='failed',error=str(exc));raise
    finally:
        if session:session.close()
        save();tegra.terminate()
        try:tegra.wait(timeout=5)
        except subprocess.TimeoutExpired:tegra.kill();tegra.wait()
        log.close()

if __name__=='__main__':main()
