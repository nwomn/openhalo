"""Isolated Qwen3.5 FlashHead probe using the retained c14 sampling contract."""
import argparse
import faulthandler
import hashlib
import json
import logging
import math
import os
import re
import sys
import time
from pathlib import Path

os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                  VLLM_ENABLE_V1_MULTIPROCESSING="0", VLLM_VIDEO_LOADER_BACKEND="opencv")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cosmos_video"))
from benchmark import PROMPT

PROFILES = ["uniform16"]


def read_frames(path, profile, width=1280):
    import cv2
    import numpy as np
    started = time.perf_counter()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    decoded = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        decoded.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    cap.release()
    assert fps == 4 and len(decoded) >= 16, (fps, len(decoded))
    if profile.startswith("uniform"):
        count = int(profile.removeprefix("uniform"))
        assert 1 <= count <= len(decoded)
        indices = np.linspace(0, len(decoded) - 1, count).round().astype(int).tolist()
    else:
        indices = list(range(0, len(decoded), 4 if profile == "fps1" else 8))
    frames = np.stack([cv2.resize(decoded[i], (width, round(width*9/16))) for i in indices])
    metadata = dict(total_num_frames=len(decoded), fps=fps, duration=len(decoded)/fps,
                    video_backend="opencv", frames_indices=indices.copy(), do_sample_frames=False)
    record = dict(input_sha256=digest, input_shape=list(frames.shape),
                  sampled_frame_indices=indices, sampled_times_s=[i / fps for i in indices],
                  read_decode_resize_s=time.perf_counter() - started)
    return frames, metadata, record


def main():
    logging.basicConfig(level=logging.INFO)
    faulthandler.dump_traceback_later(180, repeat=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--profiles", nargs="+", choices=["uniform12", "uniform16", "uniform24", "uniform28", "fps1", "fps0.5"], default=PROFILES)
    parser.add_argument("--max-model-len", type=int, default=6144)
    parser.add_argument("--kv-cache-mib", type=int, default=768)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--input-width", type=int, default=832)
    parser.add_argument("--case", choices=["c14", "c11", "c12"], default="c14")
    parser.add_argument("--compiled", action="store_true")
    parser.add_argument("--model-dir", default="/work/assets/runtime-model")
    parser.add_argument("--model-id", default="embedl/Qwen3.5-0.8B-FlashHead")
    parser.add_argument("--revision", default="6208c90544971d154eefc047e6f84d05326fa031")
    parser.add_argument("--oom-score-adj", type=int, choices=range(0, 1001), default=None,
                        metavar="0..1000", help="Prioritize this experiment for OOM termination")
    args = parser.parse_args()
    if args.oom_score_adj is not None:
        Path("/proc/self/oom_score_adj").write_text(str(args.oom_score_adj))
    profiles = args.profiles
    max_frames = max(int(p.removeprefix("uniform")) if p.startswith("uniform") else (7 if p == "fps1" else 4) for p in profiles)
    intervals = {"c14": [28.5, 35.5], "c11": [36, 43], "c12": [43, 54]}
    clip = (Path("/comparison/private/sampling-cases-v1/c14.mp4") if args.case == "c14"
            else Path("/baseline/private/cases-v1") / (args.case + ".mp4"))
    args.output.mkdir(parents=True, exist_ok=False)
    if args.prepare_only:
        from PIL import Image, ImageDraw
        records = []
        for profile in profiles:
            frames, metadata, record = read_frames(clip, profile, args.input_width)
            canvas = Image.new("RGB", (4 * 384, math.ceil(len(frames)/4) * 240), "white")
            draw = ImageDraw.Draw(canvas)
            for i, frame in enumerate(frames):
                x, y = (i % 4) * 384, (i // 4) * 240
                canvas.paste(Image.fromarray(frame).resize((384, 216)), (x, y))
                draw.text((x + 3, y + 220), f'{profile} clip={record["sampled_times_s"][i]:.2f}s source={intervals[args.case][0]+record["sampled_times_s"][i]:.2f}s', fill="black")
            canvas.save(args.output / (profile + ".jpg"))
            records.append(dict(profile=profile, **record, metadata=metadata))
        (args.output / "sampled-inputs.json").write_text(json.dumps(records, indent=2))
        return

    from vllm import LLM, SamplingParams
    import torch
    llm_args = dict(model=args.model_dir, dtype="bfloat16", max_model_len=args.max_model_len,
                    max_num_seqs=1, max_num_batched_tokens=2048,
                    kv_cache_memory_bytes=args.kv_cache_mib * 1024 * 1024, gpu_memory_utilization=0.30,
                    enable_prefix_caching=False, mm_processor_cache_gb=0, swap_space=0,
                    async_scheduling=False, enforce_eager=not args.compiled,
                    limit_mm_per_prompt={"video": {"count": 1, "num_frames": max_frames,
                                                  "width": args.input_width, "height": round(args.input_width*9/16)}, "image": 0, "audio": 0},
                    mm_processor_kwargs={"truncation": False, "do_sample_frames": False},
                    media_io_kwargs={"video": {"num_frames": max_frames, "fps": 4}})
    decoding = dict(temperature=0.7, top_p=0.8, top_k=20, presence_penalty=1.5,
                    repetition_penalty=1.0, seed=0, max_tokens=96)
    config = dict(model=args.model_id,
                  revision=args.revision, clip=str(clip),
                  source_interval_s=intervals[args.case],
                  clip_seconds=intervals[args.case][1]-intervals[args.case][0], llm_args=llm_args,
                  prompt=PROMPT, decoding=decoding, profiles=profiles, repeats=args.repeats,
                  input_width=args.input_width,
                  oom_score_adj=args.oom_score_adj,
                  timing="read/hash/decode/resize clip plus model preprocessing to full returned answer",
                  excluded="model initialization, prior clip extraction, live capture, Runtime",
                  order="warm each profile, then rotate profile order over three repeats",
                  enable_thinking=False, eager_mode=not args.compiled,
                  decoding_note="FlashHead 0.1.10 selects approximate greedy tokens directly; requested sampler parameters are not equivalent to ordinary Qwen decoding.")
    (args.output / "config.json").write_text(json.dumps(config, indent=2))
    start = time.perf_counter()
    llm = LLM(**llm_args)
    faulthandler.cancel_dump_traceback_later()
    torch.cuda.synchronize()
    (args.output / "load.json").write_text(json.dumps(dict(seconds=time.perf_counter()-start)))
    tokenizer = llm.get_tokenizer()
    prompt = tokenizer.apply_chat_template([dict(role="user", content=[dict(type="video"),
                                            dict(type="text", text=PROMPT)])],
                                           tokenize=False, add_generation_prompt=True, enable_thinking=False)
    runs = [(p, -1) for p in profiles]
    for repeat in range(args.repeats):
        shift = repeat % len(profiles)
        runs.extend((p, repeat) for p in profiles[shift:] + profiles[:shift])
    with (args.output / "raw.jsonl").open("w") as log:
        for profile, repeat in runs:
            row = dict(profile=profile, repeat=repeat, warmup=repeat < 0, started_unix=time.time())
            start = time.perf_counter()
            frames, metadata, record = read_frames(clip, profile, args.input_width)
            row.update(record)
            result = llm.generate(dict(prompt=prompt, multi_modal_data={"video": [(frames, metadata)]},
                                      mm_processor_kwargs={"do_sample_frames": False}),
                                  sampling_params=SamplingParams(**decoding), use_tqdm=False)[0]
            torch.cuda.synchronize()
            elapsed = time.perf_counter() - start
            output = result.outputs[0]
            import flash_head.patches.logits_processor as fh_patch
            flash_head = fh_patch._flash_head
            assert isinstance(flash_head, torch.nn.Module), "FlashHead did not activate"
            actual = tokenizer.decode(result.prompt_token_ids)
            tokens = actual.count("<|video_pad|>")
            timestamps = re.findall(r"<[0-9.]+ seconds>", actual)
            n = len(record["sampled_frame_indices"])
            from transformers.models.qwen3_vl.video_processing_qwen3_vl import smart_resize
            model_h, model_w = smart_resize(n, frames.shape[1], frames.shape[2],
                                             min_pixels=4096, max_pixels=25165824)
            expected_tokens = math.ceil(n / 2) * (model_h // 32) * (model_w // 32)
            assert tokens == expected_tokens, (profile, n, tokens, expected_tokens)
            pair_indices = record["sampled_frame_indices"].copy()
            if len(pair_indices) % 2:
                pair_indices.append(pair_indices[-1])
            expected = [f'<{(pair_indices[i]+pair_indices[i+1])/8:.1f} seconds>'
                        for i in range(0, len(pair_indices), 2)]
            assert timestamps == expected, (profile, timestamps, expected)
            row.update(seconds=elapsed, inference_s=elapsed-record["read_decode_resize_s"],
                       text=output.text, finish_reason=output.finish_reason,
                       output_tokens=len(output.token_ids), prompt_tokens=len(result.prompt_token_ids),
                       visual_tokens=tokens, actual_timestamps=timestamps,
                       processor_frame_pairs=len(timestamps), metadata_after_processor=metadata,
                       flash_head_class=type(flash_head).__name__,
                       effective_frame_size=[model_h, model_w],
                       input_checks_passed=True)
            log.write(json.dumps(row, ensure_ascii=False)+"\n")
            log.flush()
            print(json.dumps(row, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
