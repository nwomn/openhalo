"""Existing pinned MobileVLM NF4 stack, callable from a single worker."""
import os,sys,time
from pathlib import Path

class Session:
    def __init__(self):
        base=Path('/home/jetson/openhalo-mobilevlm-v2')
        os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
        sys.path.insert(0,str(base/'runtime'));sys.path.insert(0,'/home/jetson/openhalo-specialist-expanded/scripts')
        import torch,transformers,bitsandbytes as bnb,numpy as np
        from transformers import AutoTokenizer,BitsAndBytesConfig
        from mobilevlm.model.mobilellama import MobileLlamaForCausalLM,MobileVLMConfig
        from expanded import Expanded
        self.torch=torch;torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.65)
        if not torch.distributed.is_available():transformers.modeling_utils.is_fsdp_enabled=lambda:False
        config=MobileVLMConfig.from_pretrained(str(base/'assets/sharded'));config.mm_vision_tower=str(base/'assets/clip')
        q=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,
                            bnb_4bit_compute_dtype=torch.float16,llm_int8_skip_modules=['vision_tower','mm_projector','lm_head'])
        self.model,info=MobileLlamaForCausalLM.from_pretrained(str(base/'assets/sharded'),config=config,
            torch_dtype=torch.float16,device_map={'':0},low_cpu_mem_usage=True,local_files_only=True,
            quantization_config=q,output_loading_info=True)
        if any(info.values()):raise ValueError('checkpoint mismatch')
        self.model.eval();self.vision=self.model.get_vision_tower();self.vision.load_image_processor()
        self.tokenizer=AutoTokenizer.from_pretrained(str(base/'assets/sharded'),use_fast=False,local_files_only=True)
        self.specialists=Expanded(Path('/home/jetson/openhalo-specialist-expanded/models'))
        self.specialists.infer(np.zeros((720,1280,3),np.uint8),0)
        self.specialists.cls.predict(np.zeros((224,224,3),np.uint8),imgsz=224,device=0,verbose=False)
        self.info=dict(loading_info=info,nf4_linears=sum(isinstance(m,bnb.nn.Linear4bit) for m in self.model.modules()),
                       torch=torch.__version__,transformers=transformers.__version__)
        if self.info['nf4_linears']!=168:raise ValueError('NF4 mismatch')

    def infer(self,bgr):
        import cv2
        from PIL import Image
        from mobilevlm.constants import IMAGE_TOKEN_INDEX
        from mobilevlm.conversation import conv_templates
        from mobilevlm.utils import process_images,tokenizer_image_token,KeywordsStoppingCriteria
        torch=self.torch;torch.cuda.synchronize();start=time.perf_counter()
        conv=conv_templates['v1'].copy();conv.append_message(conv.roles[0],'<image>\nDescribe this image briefly.');conv.append_message(conv.roles[1],None)
        prompt=conv.get_prompt()
        ids=tokenizer_image_token(prompt,self.tokenizer,IMAGE_TOKEN_INDEX,return_tensors='pt').unsqueeze(0).cuda()
        source=Image.fromarray(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
        tensor=process_images([source],self.vision.image_processor,self.model.config).to('cuda',dtype=torch.float16)
        with torch.inference_mode():
            out=self.model.generate(ids,images=tensor,do_sample=False,num_beams=1,max_new_tokens=48,use_cache=True,
                pad_token_id=self.tokenizer.eos_token_id,stopping_criteria=[KeywordsStoppingCriteria([conv.sep2],self.tokenizer,ids)])
        generated=out[:,ids.shape[1]:];text=self.tokenizer.batch_decode(generated,skip_special_tokens=True)[0].strip()
        if text.endswith(conv.sep2):text=text[:-len(conv.sep2)].strip()
        torch.cuda.synchronize();limited=generated.shape[1]==48 and out[0,-1].item()!=self.tokenizer.eos_token_id
        return dict(text=text,seconds=time.perf_counter()-start,hit_token_limit=limited,
                    usable=bool(text) and not limited and text.lower().strip(' .') not in ['unclear','unknown'],
                    full_prompt=prompt,output_tokens=generated.shape[1])

    def close(self):self.specialists.g.close()
