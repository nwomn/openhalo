"""Unknown-only MobileVLM ROI fallback with paired full-frame diagnostic."""
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path

PROMPT="What object, if any, is physically held by the visible hand? Reply with only the object name, 'empty hand', or 'unclear'. Do not name background objects. If the visual evidence is insufficient, reply 'unclear'."

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('/home/jetson/openhalo-roi-fallback'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prompt',default=PROMPT);a=p.parse_args();a.output.mkdir(exist_ok=False,parents=True)
    base=Path('/home/jetson/openhalo-mobilevlm-v2')
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TORCHINDUCTOR_COMPILE_THREADS='1')
    sys.path.insert(0,str(base/'runtime'));sys.path.insert(0,'/home/jetson/openhalo-specialist-expanded/scripts')
    import cv2,numpy as np,torch,transformers,bitsandbytes as bnb
    from PIL import Image
    from transformers import AutoTokenizer,BitsAndBytesConfig
    from mobilevlm.model.mobilellama import MobileLlamaForCausalLM,MobileVLMConfig
    from mobilevlm.constants import IMAGE_TOKEN_INDEX
    from mobilevlm.conversation import conv_templates
    from mobilevlm.utils import process_images,tokenizer_image_token,KeywordsStoppingCriteria
    from expanded import Expanded
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.65)
    if not torch.distributed.is_available():transformers.modeling_utils.is_fsdp_enabled=lambda:False
    manifest=json.loads((a.root/'cases.json').read_text())
    report=dict(status='loading',prompt=a.prompt,precision='language NF4, vision/projector/head FP16',max_tokens=48,
        manifest=manifest,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        runtime=json.loads((base/'runtime/runtime-manifest.json').read_text()),cases=[],
        boundary='cached specialist routing, co-resident models allocated; saved PNG to text timings exclude specialist inference, live capture and Runtime; full-frame is counterfactual diagnosis')
    def save():(a.output/'report.json').write_text(json.dumps(report,indent=2))
    log=(a.output/'tegrastats.log').open('w');tegra=subprocess.Popen(['tegrastats','--interval','500'],stdout=log,stderr=log);specialists=None
    save()
    try:
        config=MobileVLMConfig.from_pretrained(str(base/'assets/sharded'));config.mm_vision_tower=str(base/'assets/clip')
        q=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,
                            bnb_4bit_compute_dtype=torch.float16,llm_int8_skip_modules=['vision_tower','mm_projector','lm_head'])
        start=time.perf_counter()
        model,loading=MobileLlamaForCausalLM.from_pretrained(str(base/'assets/sharded'),config=config,
            torch_dtype=torch.float16,device_map={'':0},low_cpu_mem_usage=True,local_files_only=True,
            quantization_config=q,output_loading_info=True)
        if any(loading.values()):raise ValueError('checkpoint mismatch')
        model.eval();report['loading_info']=loading
        report['nf4_linears']=sum(isinstance(m,bnb.nn.Linear4bit) for m in model.modules())
        if report['nf4_linears']!=168:raise ValueError('unexpected quantized module count')
        vision=model.get_vision_tower();vision.load_image_processor()
        tokenizer=AutoTokenizer.from_pretrained(str(base/'assets/sharded'),use_fast=False,local_files_only=True)
        specialists=Expanded(Path('/home/jetson/openhalo-specialist-expanded/models'))
        specialists.infer(np.zeros((720,1280,3),dtype=np.uint8),0)
        specialists.cls.predict(np.zeros((224,224,3),dtype=np.uint8),imgsz=224,device=0,verbose=False)
        report['load_and_context_warmup_seconds']=time.perf_counter()-start
        report['specialist_model_sha256']={x:hashlib.sha256(Path(x).read_bytes()).hexdigest() for x in specialists.paths}
        def infer(path):
            torch.cuda.synchronize();start=time.perf_counter()
            conv=conv_templates['v1'].copy();conv.append_message(conv.roles[0],'<image>\n'+a.prompt);conv.append_message(conv.roles[1],None)
            prompt=conv.get_prompt()
            ids=tokenizer_image_token(prompt,tokenizer,IMAGE_TOKEN_INDEX,return_tensors='pt').unsqueeze(0).cuda()
            with Image.open(path) as im:source=im.convert('RGB')
            tensor=process_images([source],vision.image_processor,model.config).to('cuda',dtype=torch.float16)
            with torch.inference_mode():
                output=model.generate(ids,images=tensor,do_sample=False,num_beams=1,max_new_tokens=48,use_cache=True,
                    pad_token_id=tokenizer.eos_token_id,stopping_criteria=[KeywordsStoppingCriteria([conv.sep2],tokenizer,ids)])
            generated=output[:,ids.shape[1]:];answer=tokenizer.batch_decode(generated,skip_special_tokens=True)[0].strip()
            if answer.endswith(conv.sep2):answer=answer[:-len(conv.sep2)].strip()
            torch.cuda.synchronize()
            return dict(text=answer,seconds=time.perf_counter()-start,full_prompt=prompt,output_tokens=generated.shape[1],
                        hit_token_limit=generated.shape[1]==48 and output[0,-1].item()!=tokenizer.eos_token_id)
        first=next(c for c in manifest['cases'] if c['trigger_vlm'])
        report['warmup']=infer(first['roi']);report['status']='running';save()
        for c in manifest['cases']:
            row=dict(**c,runs=[]);report['cases'].append(row)
            if not c['trigger_vlm']:
                row['cascade_result']=dict(source='classifier',text=c['classifier_top1']['label']);save();continue
            for repeat in range(2):
                arms=['roi','frame'] if (c['id']+repeat)%2==0 else ['frame','roi']
                for arm in arms:
                    path=Path(c[arm]);expected=c['roi_sha256' if arm=='roi' else 'frame_sha256']
                    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('input hash changed')
                    result=dict(arm=arm,repeat=repeat,**infer(path));row['runs'].append(result)
                    print(json.dumps(dict(case=c['name'],**{k:v for k,v in result.items() if k!='full_prompt'})),flush=True);save()
            row['cascade_result']=dict(source='MobileVLM ROI',texts=[r['text'] for r in row['runs'] if r['arm']=='roi'])
        report['status']='completed'
    except Exception as exc:report.update(status='failed',error=f'{type(exc).__name__}: {exc}');raise
    finally:
        if specialists:specialists.g.close()
        save();tegra.terminate()
        try:tegra.wait(timeout=5)
        except subprocess.TimeoutExpired:tegra.kill();tegra.wait()
        log.close()

if __name__=='__main__':main()
