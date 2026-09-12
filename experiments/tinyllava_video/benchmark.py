"""Local-only TinyLLaVA-Video probe: fixed clips, resident repeats, no Runtime."""
import argparse
import ctypes
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import signal
import time
import types


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--video", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-new-tokens", type=int, default=48)
    parser.add_argument("--vision-batch", type=int, default=1)
    parser.add_argument("--cuda-memory-fraction", type=float, default=0.65)
    parser.add_argument("--quantize-vision", action="store_true")
    parser.add_argument("--last-token-logits", action="store_true")
    parser.add_argument("--prompt", default=(
        "Describe the person's visible action and what changes from the beginning "
        "to the end of this video in one short sentence. If no action change is "
        "visible, describe the visible state. Do not guess intention or identity."))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    # Avoid Inductor's worker pool duplicating a large process on unified RAM.
    os.environ["TORCHINDUCTOR_COMPILE_THREADS"] = "1"
    sys.path.insert(0, str(args.runtime))
    import torch
    import transformers
    import bitsandbytes as bnb
    import numpy as np
    from PIL import Image
    from transformers import BitsAndBytesConfig
    from tinyllava.model import TinyLlavaConfig, TinyLlavaForConditionalGeneration
    from tinyllava.data import TextPreprocess, VideoPreprocess
    from tinyllava.utils import Message

    torch.set_num_threads(4)
    torch.cuda.set_per_process_memory_fraction(args.cuda_memory_fraction)
    report = dict(status="loading", torch=torch.__version__, cuda=torch.version.cuda,
                  transformers=transformers.__version__, bitsandbytes=bnb.__version__,
                  prompt=args.prompt, frame_count=16, max_new_tokens=args.max_new_tokens,
                  vision_batch=args.vision_batch, quantization="LLM linear NF4 double-quant; vision/connector/head FP16",
                  cuda_memory_fraction=args.cuda_memory_fraction, inductor_compile_threads=1,
                  last_token_logits=args.last_token_logits,
                  runtime=json.loads((args.runtime / "runtime-manifest.json").read_text()),
                  cases=[], acceptance="not accepted; output requires ground-truth assessment")
    if args.quantize_vision:
        report["quantization"] = "all supported linear layers NF4 double-quant; embeddings/LM head/SigLIP pooling head/norms FP16"

    def save():
        (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    telemetry_file = (args.output / "tegrastats.log").open("w")
    def terminate_with_parent():
        ctypes.CDLL(None).prctl(1, signal.SIGTERM)

    telemetry = subprocess.Popen(["tegrastats", "--interval", "500"],
                                 stdout=telemetry_file, stderr=telemetry_file,
                                 preexec_fn=terminate_with_parent)
    save()
    try:
        config_data = json.loads((args.assets / "model/config.json").read_text())
        config_data["llm_model_name_or_path"] = str(args.assets / "qwen2")
        config_data["tokenizer_name_or_path"] = str(args.assets / "model")
        config_data["vision_model_name_or_path"] = str(args.assets / "siglip")
        config = TinyLlavaConfig(**config_data)
        # Preserve component-specific precision and bypass upstream's loader,
        # which constructs quantization kwargs but does not pass them onward.
        quantization = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4",
            llm_int8_skip_modules=(["lm_head", "vision_tower._vision_tower.vision_model.head"] if args.quantize_vision else
                                   ["vision_tower", "connector", "lm_head"]))
        start = time.perf_counter()
        model, loading = TinyLlavaForConditionalGeneration.from_pretrained(
            str(args.assets / "model"), config=config,
            quantization_config=quantization, torch_dtype=torch.float16,
            device_map={"": 0}, low_cpu_mem_usage=True, local_files_only=True,
            output_loading_info=True)
        model.eval()
        if args.last_token_logits:
            # Generation consumes only the last position's logits. Avoid the
            # 512+ position x 151936 vocabulary prefill projection in HF 4.40.
            # This hook is invalid for training/loss computation; this runner
            # is inference-only and never passes labels.
            model.language_model.lm_head.register_forward_pre_hook(
                lambda module, inputs: (inputs[0][:, -1:, :],))
        torch.cuda.synchronize()
        report["load_seconds"] = time.perf_counter() - start
        report["loading_info"] = loading
        if loading.get("missing_keys") or loading.get("unexpected_keys") or loading.get("mismatched_keys"):
            raise ValueError("checkpoint/model key mismatch; refuse semantic evaluation")
        report["quantized_linear_count"] = sum(isinstance(m, bnb.nn.Linear4bit) for m in model.modules())
        if report["quantized_linear_count"] == 0:
            raise ValueError("quantization not applied")
        gc.collect()
        torch.cuda.empty_cache()
        report["loaded_cuda_allocated_bytes"] = torch.cuda.memory_allocated()
        report["loaded_cuda_reserved_bytes"] = torch.cuda.memory_reserved()
        stages = {}

        def encode_videos(self, videos):
            print('phase=vision', flush=True)
            outputs = []
            for video in videos:
                torch.cuda.synchronize()
                start = time.perf_counter()
                features = []
                for batch in video.split(args.vision_batch):
                    feature = self.vision_tower(
                        batch.to(device="cuda", dtype=torch.float16),
                        vision_feature_layer=self.config.vision_feature_layer,
                        vision_feature_select_strategy=self.config.vision_feature_select_strategy)
                    features.append(feature)
                feature = torch.cat(features, dim=0)
                torch.cuda.synchronize()
                stages["vision_seconds"] = time.perf_counter() - start
                report["last_completed_stage"] = dict(stages)
                save()
                print('phase=connector', flush=True)
                start = time.perf_counter()
                output = self.connector(feature.reshape(1, -1, feature.shape[-1]))
                torch.cuda.synchronize()
                stages["connector_seconds"] = time.perf_counter() - start
                stages["visual_tokens"] = output.shape[1]
                report["last_completed_stage"] = dict(stages)
                save()
                outputs.append(output)
            print('phase=language', flush=True)
            return torch.cat(outputs, dim=0)

        model.encode_videos = types.MethodType(encode_videos, model)
        tokenizer = model.tokenizer
        text = TextPreprocess(tokenizer, "qwen2_base")
        preprocess = VideoPreprocess(model.vision_tower._image_processor, model.config)
        message = Message()
        message.add_message("<image>\n" + args.prompt)
        encoded = text(message.messages, mode="eval")
        input_ids = encoded["input_ids"].unsqueeze(0).cuda()
        report["status"] = "running"
        save()
        print(json.dumps({"loaded_seconds": report["load_seconds"], "quantized_linears": report["quantized_linear_count"]}), flush=True)
        for path in args.video:
            metadata = json.loads(subprocess.check_output([
                "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,nb_read_frames:format=duration",
                "-of", "json", str(path)], text=True))
            stream = metadata["streams"][0]
            count = int(stream["nb_read_frames"])
            indices = np.linspace(0, count - 1, 16, dtype=int).tolist()
            case = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        metadata=metadata, indices=indices, runs=[])
            report["cases"].append(case)
            save()
            for repeat in range(args.repeats):
                print(f'phase=preprocess repeat={repeat}', flush=True)
                start = time.perf_counter()
                unique = sorted(set(indices))
                select = "+".join(f"eq(n\\,{n})" for n in unique)
                raw = subprocess.check_output([
                    "ffmpeg", "-v", "error", "-threads", "1", "-i", str(path),
                    "-vf", f"select={select}", "-vsync", "0", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"])
                arrays = np.frombuffer(raw, dtype=np.uint8).reshape(
                    len(unique), stream["height"], stream["width"], 3)
                selected = dict(zip(unique, arrays))
                video = torch.stack([preprocess(Image.fromarray(selected[i])) for i in indices]).unsqueeze(0)
                prepared = time.perf_counter()
                torch.cuda.reset_peak_memory_stats()
                with torch.inference_mode():
                    output = model.generate(
                        input_ids, video=video, do_sample=False, num_beams=1,
                        pad_token_id=tokenizer.pad_token_id,
                        eos_token_id=tokenizer.eos_token_id,
                        max_new_tokens=args.max_new_tokens, use_cache=True)
                torch.cuda.synchronize()
                end = time.perf_counter()
                result = dict(repeat=repeat, first_inference=repeat == 0 and len(report["cases"]) == 1,
                              preprocessing_seconds=prepared-start, generation_seconds=end-prepared,
                              total_seconds=end-start, **stages,
                              output_tokens=output.shape[-1],
                              output=tokenizer.batch_decode(output, skip_special_tokens=True)[0].strip(),
                              cuda_peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                              cuda_peak_reserved_bytes=torch.cuda.max_memory_reserved())
                result["language_seconds"] = result["generation_seconds"] - stages["vision_seconds"] - stages["connector_seconds"]
                case["runs"].append(result)
                print(json.dumps(result), flush=True)
                save()
                del video, output
        report["status"] = "completed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        save()
        telemetry.terminate()
        try:
            telemetry.wait(timeout=5)
        except subprocess.TimeoutExpired:
            telemetry.kill()
            telemetry.wait()
        telemetry_file.close()


if __name__ == "__main__":
    main()
