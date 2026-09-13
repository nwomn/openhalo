"""Use the previous pinned resident model loader with a configurable second-stage prompt."""
import time
from vlm_session import Session

class ContextSession(Session):
    def infer(self,bgr,prompt_text='Describe this image briefly.'):
        import cv2
        from PIL import Image
        from mobilevlm.constants import IMAGE_TOKEN_INDEX
        from mobilevlm.conversation import conv_templates
        from mobilevlm.utils import process_images,tokenizer_image_token,KeywordsStoppingCriteria
        torch=self.torch;torch.cuda.synchronize();start=time.perf_counter()
        conv=conv_templates['v1'].copy();conv.append_message(conv.roles[0],'<image>\n'+prompt_text);conv.append_message(conv.roles[1],None)
        prompt=conv.get_prompt()
        ids=tokenizer_image_token(prompt,self.tokenizer,IMAGE_TOKEN_INDEX,return_tensors='pt').unsqueeze(0).cuda()
        source=Image.fromarray(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
        tensor=process_images([source],self.vision.image_processor,self.model.config).to('cuda',dtype=torch.float16)
        with torch.inference_mode():
            out=self.model.generate(ids,images=tensor,do_sample=False,num_beams=1,max_new_tokens=48,use_cache=True,
                pad_token_id=self.tokenizer.eos_token_id,stopping_criteria=[KeywordsStoppingCriteria([conv.sep2],self.tokenizer,ids)])
        generated=out[:,ids.shape[1]:];text=self.tokenizer.batch_decode(generated,skip_special_tokens=True)[0].strip()
        if text.endswith(conv.sep2):text=text[:-len(conv.sep2)].strip()
        torch.cuda.synchronize()
        return dict(text=text,seconds=time.perf_counter()-start,full_prompt=prompt,input_tokens=ids.shape[1],
            output_tokens=generated.shape[1],hit_token_limit=generated.shape[1]==48 and out[0,-1].item()!=self.tokenizer.eos_token_id)
