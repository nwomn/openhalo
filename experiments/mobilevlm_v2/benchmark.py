"""Resident, action-blinded MobileVLM V2 image probe; never publishes to Runtime."""
import argparse
import ctypes
import gc
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import types


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--runtime", type=Path, required=True)
    p.add_argument("--assets", type=Path, required=True)
    p.add_argument("--image", type=Path, action="append", default=[])
    p.add_argument("--sequences", type=Path, help="JSON list of {name, images}; experimental ordered multi-image input")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--max-new-tokens", type=int, default=48)
    p.add_argument("--nf4", action="store_true")
    p.add_argument("--last-token-logits", action="store_true")
    p.add_argument("--prompt", default="Describe the person's visible action and any object they are handling in one short sentence. Do not guess intent or identity.")
    a = p.parse_args()
    if bool(a.image) == bool(a.sequences):
        p.error("Provide images or a sequence manifest, exclusively")
    a.output.mkdir(parents=True, exist_ok=False)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TORCHINDUCTOR_COMPILE_THREADS="1")
    sys.path.insert(0, str(a.runtime))
    import torch
    import transformers
    from PIL import Image
    from transformers import AutoTokenizer, BitsAndBytesConfig
    from mobilevlm.model.mobilellama import MobileLlamaForCausalLM, MobileVLMConfig
    from mobilevlm.constants import IMAGE_TOKEN_INDEX, DEFAULT_IMAGE_TOKEN
    from mobilevlm.conversation import conv_templates, SeparatorStyle
    from mobilevlm.utils import process_images, tokenizer_image_token, KeywordsStoppingCriteria

    torch.set_num_threads(4)
    torch.cuda.set_per_process_memory_fraction(0.65)
    # NVIDIA's Jetson build omits distributed support. HF 4.33's FSDP probe
    # calls is_initialized without checking availability, even for one GPU.
    fsdp_probe_patch = not torch.distributed.is_available()
    if fsdp_probe_patch:
        transformers.modeling_utils.is_fsdp_enabled = lambda: False
    report = dict(status="loading", torch=torch.__version__, transformers=transformers.__version__,
                  cuda=torch.version.cuda, precision="NF4 language linear / FP16 vision-projector-head" if a.nf4 else "FP16",
                  prompt=a.prompt, max_new_tokens=a.max_new_tokens, last_token_logits=a.last_token_logits,
                  distributed_unavailable_fsdp_probe_disabled=fsdp_probe_patch,
                  input_mode="experimental ordered images, vision microbatch 1" if a.sequences else "single image",
                  runtime=json.loads((a.runtime / "runtime-manifest.json").read_text()),
                  conversion=json.loads((a.assets / "sharded/conversion.json").read_text()),
                  cases=[], acceptance="not accepted; bounded single-image check")

    def save():
        (a.output / "report.json").write_text(json.dumps(report, indent=2))

    log = (a.output / "tegrastats.log").open("w")
    telemetry = subprocess.Popen(["tegrastats", "--interval", "500"], stdout=log, stderr=log,
                                 preexec_fn=lambda: ctypes.CDLL(None).prctl(1, signal.SIGTERM))
    save()
    try:
        config = MobileVLMConfig.from_pretrained(str(a.assets / "sharded"))
        config.mm_vision_tower = str(a.assets / "clip")
        kwargs = {}
        if a.nf4:
            kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16,
                llm_int8_skip_modules=["vision_tower", "mm_projector", "lm_head"])
        start = time.perf_counter()
        model, loading = MobileLlamaForCausalLM.from_pretrained(str(a.assets / "sharded"), config=config,
            torch_dtype=torch.float16, device_map={"": 0}, low_cpu_mem_usage=True,
            local_files_only=True, output_loading_info=True, **kwargs)
        model.eval()
        torch.cuda.synchronize()
        report.update(load_seconds=time.perf_counter()-start, loading_info=loading)
        save()
        if any(loading.get(key) for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")):
            raise ValueError("Checkpoint key mismatch: refuse semantics test")
        if a.last_token_logits:
            model.lm_head.register_forward_pre_hook(lambda module, inputs: (inputs[0][:, -1:, :],))
        vision = model.get_vision_tower()
        vision.load_image_processor()
        if a.sequences:
            # Preserve per-image math; avoid simultaneous four-image vision
            # activations on unified RAM. This is not a video-trained model.
            def encode_images(self, images):
                return torch.cat([self.get_model().mm_projector(self.get_vision_tower()(im))
                                  for im in images.split(1)], dim=0)
            model.encode_images = types.MethodType(encode_images, model)
        tokenizer = AutoTokenizer.from_pretrained(str(a.assets / "sharded"), use_fast=False, local_files_only=True)
        if a.nf4:
            import bitsandbytes as bnb
            report["quantized_linear_count"] = sum(isinstance(m, bnb.nn.Linear4bit) for m in model.modules())
            if not report["quantized_linear_count"]:
                raise ValueError("NF4 requested but not applied")
        gc.collect()
        torch.cuda.empty_cache()
        report["loaded_cuda_allocated_bytes"] = torch.cuda.memory_allocated()
        stages, starts = {}, {}

        def before(name):
            def hook(module, inputs):
                torch.cuda.synchronize()
                starts[name] = time.perf_counter()
            return hook

        def after(name):
            def hook(module, inputs, result):
                torch.cuda.synchronize()
                stages[name + "_seconds"] = stages.get(name + "_seconds", 0) + time.perf_counter() - starts[name]
                if name == "projector":
                    stages["visual_tokens"] = stages.get("visual_tokens", 0) + result.shape[1]
            return hook

        for name, module in [("vision", vision), ("projector", model.get_model().mm_projector)]:
            module.register_forward_pre_hook(before(name))
            module.register_forward_hook(after(name))
        report["status"] = "running"
        save()
        print(json.dumps({"loaded_seconds":report["load_seconds"], "cuda_bytes":report["loaded_cuda_allocated_bytes"]}), flush=True)
        groups = json.loads(a.sequences.read_text()) if a.sequences else [dict(name=path.name, images=[str(path)]) for path in a.image]
        for group in groups:
            paths = [Path(v) for v in group["images"]]
            case = dict(path=group["name"], images=[dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in paths], runs=[])
            conv = conv_templates["v1"].copy()
            prefix = "\n".join(f"Frame {i+1}: {DEFAULT_IMAGE_TOKEN}" for i in range(len(paths))) if a.sequences else DEFAULT_IMAGE_TOKEN
            conv.append_message(conv.roles[0], prefix + "\n" + a.prompt)
            conv.append_message(conv.roles[1], None)
            ids = tokenizer_image_token(conv.get_prompt(), tokenizer, IMAGE_TOKEN_INDEX, return_tensors="pt").unsqueeze(0).cuda()
            stop = conv.sep if conv.sep_style != SeparatorStyle.TWO else conv.sep2
            report["cases"].append(case)
            for repeat in range(a.repeats):
                stages.clear()
                start = time.perf_counter()
                sources = []
                for path in paths:
                    with Image.open(path) as im:
                        sources.append(im.convert("RGB"))
                case["image_sizes"] = [list(source.size) for source in sources]
                tensor = process_images(sources, vision.image_processor, model.config).to("cuda", dtype=torch.float16)
                torch.cuda.synchronize()
                prepared = time.perf_counter()
                torch.cuda.reset_peak_memory_stats()
                with torch.inference_mode():
                    output = model.generate(ids, images=tensor, do_sample=False, num_beams=1,
                        max_new_tokens=a.max_new_tokens, use_cache=True, pad_token_id=tokenizer.eos_token_id,
                        stopping_criteria=[KeywordsStoppingCriteria([stop], tokenizer, ids)])
                torch.cuda.synchronize()
                end = time.perf_counter()
                generated = output[:, ids.shape[1]:]
                decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)[0].strip()
                if decoded.endswith(stop):
                    decoded = decoded[:-len(stop)].strip()
                result = dict(repeat=repeat, first_inference=len(report["cases"]) == 1 and repeat == 0,
                    preprocess_seconds=prepared-start, generation_seconds=end-prepared, total_seconds=end-start,
                    **stages, output_tokens=generated.shape[1], output=decoded,
                    hit_token_limit=generated.shape[1] == a.max_new_tokens and output[0, -1].item() != tokenizer.eos_token_id,
                    cuda_peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                    cuda_peak_reserved_bytes=torch.cuda.max_memory_reserved())
                result["language_seconds"] = result["generation_seconds"] - stages["vision_seconds"] - stages["projector_seconds"]
                case["runs"].append(result)
                save()
                print(json.dumps(dict(image=group["name"], **result)), flush=True)
                del tensor, output, generated
        report["status"] = "completed"
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        save()
        telemetry.terminate()
        try:
            telemetry.wait(timeout=5)
        except subprocess.TimeoutExpired:
            telemetry.kill()
            telemetry.wait()
        log.close()


if __name__ == "__main__":
    main()
