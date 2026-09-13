"""Single-process, resident LLM replay of the same frozen private video cases."""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path

os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                  VLLM_ENABLE_V1_MULTIPROCESSING="0", VLLM_VIDEO_LOADER_BACKEND="opencv")

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cosmos_video"))
from benchmark import PROMPT

MODEL = "cyankiwi/Qwen3-VL-2B-Instruct-AWQ-4bit"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-dir", type=Path, default=Path("/baseline/private/cases-v1"))
    parser.add_argument("--root", type=Path, default=Path("/work"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--decoding", choices=["greedy", "qwen-recommended"], default="greedy")
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.48)
    parser.add_argument("--enforce-eager", action="store_true")
    parser.add_argument("--case-ids", nargs="+")
    parser.add_argument("--input-width", type=int, default=832)
    parser.add_argument("--compare-widths", type=int, nargs="+")
    parser.add_argument("--max-model-len", type=int, default=4096)
    parser.add_argument("--kv-cache-mib", type=int, default=512)
    args = parser.parse_args()
    widths = args.compare_widths or [args.input_width]
    from vllm import LLM, SamplingParams
    from vllm.multimodal.video import OpenCVVideoBackend
    import torch
    import cv2
    import numpy as np
    import re
    directory = args.cases_dir
    cases = json.loads((directory / "cases.json").read_text())
    if args.case_ids:
        cases = [c for c in cases if c["id"] in args.case_ids]
    assert cases and all(set(c) == {"id", "video"} for c in cases)
    args.output.mkdir(parents=True, exist_ok=False)
    llm_args = dict(
        model=str(args.root / "assets/runtime-model"), dtype="auto",
        max_model_len=args.max_model_len, max_num_seqs=1, max_num_batched_tokens=2048,
        kv_cache_memory_bytes=args.kv_cache_mib * 1024 * 1024,
        gpu_memory_utilization=args.gpu_memory_utilization,
        enable_prefix_caching=False, mm_processor_cache_gb=0,
        swap_space=0, async_scheduling=False,
        enforce_eager=args.enforce_eager,
        limit_mm_per_prompt={"video": {"count": 1, "num_frames": 12,
                                      "width": max(widths), "height": round(max(widths)*9/16)}, "image": 0, "audio": 0},
        media_io_kwargs={"video": {"num_frames": 12, "fps": 4}},
        mm_processor_kwargs={"truncation": False, "do_sample_frames": False},
    )
    decoding = dict(temperature=0, max_tokens=args.max_tokens, seed=0)
    if args.decoding == "qwen-recommended":
        decoding.update(temperature=0.7, top_p=0.8, top_k=20, presence_penalty=1.5,
                        repetition_penalty=1.0)
    config = dict(model=MODEL, prompt=PROMPT, llm_args=llm_args, max_tokens=args.max_tokens,
                  decoding=decoding, repeats=args.repeats, case_ids=[c["id"] for c in cases],
                  timing="read clip + decode + resize + model preprocess/inference to full reply",
                  exclusion="model initialization, previous clip extraction, capture, Runtime",
                  multiprocessing=False, input_width=args.input_width, compare_widths=widths,
                  input_mode="decoded frames plus original timestamps; explicit no HF resampling")
    (args.output / "config.json").write_text(json.dumps(config, indent=2))
    print(json.dumps({"config": config}), flush=True)
    started = time.perf_counter()
    llm = LLM(**llm_args)
    torch.cuda.synchronize()
    (args.output / "load.json").write_text(json.dumps({"seconds": time.perf_counter()-started}))
    sampling = SamplingParams(**decoding)
    tokenizer = llm.get_tokenizer()
    prompt = tokenizer.apply_chat_template([dict(role="user", content=[
        dict(type="video"), dict(type="text", text=PROMPT)])],
        tokenize=False, add_generation_prompt=True)
    runs = [(cases[0], -1, w) for w in widths] + [
        (c, r, w) for c in cases for r in range(args.repeats) for w in widths]
    with (args.output / "raw.jsonl").open("w") as log:
        for case, repeat, width in runs:
            row = dict(case_id=case["id"], repeat=repeat, warmup=repeat == -1,
                       input_width=width, started_unix=time.time())
            started = time.perf_counter()
            data = (directory / (case["id"] + ".mp4")).read_bytes()
            try:
                frames, metadata = OpenCVVideoBackend.load_bytes(data, num_frames=12, fps=4)
                metadata["do_sample_frames"] = False
                height = round(frames.shape[1] * width / frames.shape[2])
                frames = np.stack([cv2.resize(frame, (width, height)) for frame in frames])
                result = llm.generate(dict(prompt=prompt,
                    multi_modal_data={"video": [(frames, metadata)]},
                    mm_processor_kwargs={"do_sample_frames": False}),
                    sampling_params=sampling, use_tqdm=False)[0]
                torch.cuda.synchronize()
                elapsed = time.perf_counter() - started
                output = result.outputs[0]
                actual_prompt = tokenizer.decode(result.prompt_token_ids)
                row.update(seconds=elapsed, text=output.text,
                           finish_reason=output.finish_reason, stop_reason=output.stop_reason,
                           prompt_tokens=len(result.prompt_token_ids),
                           output_tokens=len(output.token_ids),
                           within_10s=elapsed <= 10, semantic_pass=None,
                           input_sha256=hashlib.sha256(data).hexdigest(),
                           input_shape=list(frames.shape), metadata=metadata,
                           visual_tokens=actual_prompt.count("<|video_pad|>"),
                           actual_timestamps=re.findall(r"(?:<[0-9.]+ seconds>|<\d{2}:\d{2}:\d{2}\.\d+>)", actual_prompt))
            except Exception as exc:
                row.update(seconds=time.perf_counter()-started, error_type=type(exc).__name__,
                           within_10s=False)
                # Fail fast; the engine may no longer be usable after CUDA errors.
                log.write(json.dumps(row)+"\n")
                log.flush()
                raise
            log.write(json.dumps(row, ensure_ascii=False)+"\n")
            log.flush()
            print(json.dumps(row, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
