"""Controlled A/B/C, co-resident TRT plus image VLM; no Runtime or live ROS."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

PROMPT="What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding."


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--base',type=Path,default=Path('/home/jetson/openhalo-mobilevlm-v2'))
    p.add_argument('--cases',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--gate-version',choices=['frozen-v1','diagnostic-v1.1'],default='diagnostic-v1.1')
    a=p.parse_args();a.output.mkdir(exist_ok=False,parents=True)
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TORCHINDUCTOR_COMPILE_THREADS='1')
    sys.path.insert(0,str(a.base/'runtime'))
    import cv2
    import torch
    import transformers
    import bitsandbytes as bnb
    from PIL import Image
    from transformers import AutoTokenizer,BitsAndBytesConfig
    from mobilevlm.model.mobilellama import MobileLlamaForCausalLM,MobileVLMConfig
    from mobilevlm.constants import IMAGE_TOKEN_INDEX
    from mobilevlm.conversation import conv_templates
    from mobilevlm.utils import process_images,tokenizer_image_token,KeywordsStoppingCriteria
    from evidence import Measurements,prompt_evidence
    if a.gate_version=='frozen-v1':
        from claims_v1_frozen import check,VERSION
    else:
        from claims import check,VERSION
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(0.65)
    if not torch.distributed.is_available():transformers.modeling_utils.is_fsdp_enabled=lambda:False
    cases=json.loads(a.cases.read_text())
    r=dict(status='loading',prompt=PROMPT,prompt_version='conservative-v1+fallible-measurements-v1',
        gate_version=VERSION,precision='language NF4 double quant / FP16 vision projector head',max_new_tokens=48,
        torch=torch.__version__,transformers=transformers.__version__,bitsandbytes=bnb.__version__,
        controls='A=image+fixed prompt; B=identical image/prompt plus evidence; C=exact B text deterministically checked',
        timing='saved-frame decode through text reply/check; co-resident serial backends; excludes live capture/ROS/Runtime',
        source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')},
        cases=[])
    def save():(a.output/'report.json').write_text(json.dumps(r,indent=2))
    log=(a.output/'tegrastats.log').open('w')
    tegra=subprocess.Popen(['tegrastats','--interval','500'],stdout=log,stderr=log,
        preexec_fn=lambda:ctypes.CDLL(None).prctl(1,signal.SIGTERM))
    save()
    try:
        start=time.perf_counter()
        config=MobileVLMConfig.from_pretrained(str(a.base/'assets/sharded'))
        config.mm_vision_tower=str(a.base/'assets/clip')
        q=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,llm_int8_skip_modules=['vision_tower','mm_projector','lm_head'])
        model,loading=MobileLlamaForCausalLM.from_pretrained(str(a.base/'assets/sharded'),config=config,
            torch_dtype=torch.float16,device_map={'':0},low_cpu_mem_usage=True,local_files_only=True,
            quantization_config=q,output_loading_info=True)
        model.eval();r['loading_info']=loading
        if any(loading.values()):raise ValueError('checkpoint mismatch')
        r['nf4_linears']=sum(isinstance(m,bnb.nn.Linear4bit) for m in model.modules())
        vision=model.get_vision_tower();vision.load_image_processor()
        tokenizer=AutoTokenizer.from_pretrained(str(a.base/'assets/sharded'),use_fast=False)
        measurements=Measurements();r['engine_sha256']=measurements.hashes
        r['load_seconds']=time.perf_counter()-start

        def infer(frame,extra):
            conv=conv_templates['v1'].copy()
            conv.append_message(conv.roles[0],'<image>\n'+extra+PROMPT);conv.append_message(conv.roles[1],None)
            ids=tokenizer_image_token(conv.get_prompt(),tokenizer,IMAGE_TOKEN_INDEX,return_tensors='pt').unsqueeze(0).cuda()
            source=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            tensor=process_images([source],vision.image_processor,model.config).to('cuda',dtype=torch.float16)
            torch.cuda.synchronize();start=time.perf_counter()
            with torch.inference_mode():
                output=model.generate(ids,images=tensor,do_sample=False,num_beams=1,max_new_tokens=48,use_cache=True,
                    pad_token_id=tokenizer.eos_token_id,stopping_criteria=[KeywordsStoppingCriteria([conv.sep2],tokenizer,ids)])
            torch.cuda.synchronize();end=time.perf_counter()
            generated=output[:,ids.shape[1]:];text=tokenizer.batch_decode(generated,skip_special_tokens=True)[0].strip()
            if text.endswith(conv.sep2):text=text[:-len(conv.sep2)].strip()
            return dict(output=text,output_tokens=generated.shape[1],input_tokens=ids.shape[1],generation_seconds=end-start,
                hit_token_limit=generated.shape[1]==48 and output[0,-1].item()!=tokenizer.eos_token_id)

        warm=cv2.imread(cases[0]['image'])
        measurements.infer(warm,cases[0]['sha256'],cases[0]['source_pts_seconds'])
        r['warmup']=infer(warm,'');r['status']='running';save()
        for i,case in enumerate(cases):
            path=Path(case['image'])
            if hashlib.sha256(path.read_bytes()).hexdigest()!=case['sha256']:raise ValueError('frame hash changed')
            cr=dict(**case,runs=[]);r['cases'].append(cr)
            for repeat in range(2):
                order=['A','B'] if (i+repeat)%2==0 else ['B','A']
                for arm in order:
                    start=time.perf_counter();frame=cv2.imread(str(path));e=None
                    if arm=='B':e=measurements.infer(frame,case['sha256'],case['source_pts_seconds'])
                    extra=prompt_evidence(e) if e else ''
                    torch.cuda.reset_peak_memory_stats()
                    result=infer(frame,extra)
                    end=time.perf_counter()
                    record=dict(arm=arm,repeat=repeat,**result,total_seconds=end-start,
                        evidence=e,evidence_prompt=extra,cuda_peak_allocated_bytes=torch.cuda.max_memory_allocated())
                    if e:
                        gate_start=time.perf_counter();record['C']=check(result['output'],e,case['sha256'],case['source_pts_seconds'],not result['hit_token_limit'])
                        gate_end=time.perf_counter();record['C']['gate_seconds']=gate_end-gate_start
                        record['C']['total_seconds']=record['total_seconds']+gate_end-gate_start
                    cr['runs'].append(record);save()
                    print(json.dumps(dict(case=case['name'],arm=arm,repeat=repeat,output=result['output'],seconds=end-start)),flush=True)
        r['status']='completed'
    except Exception as exc:
        r.update(status='failed',error=f'{type(exc).__name__}: {exc}');raise
    finally:
        save();tegra.terminate()
        try:tegra.wait(timeout=5)
        except subprocess.TimeoutExpired:tegra.kill();tegra.wait()
        log.close()


if __name__=='__main__':main()
