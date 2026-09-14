"""Resident Qwen; complete one request then drain the concurrent capture buffer."""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import sys
import time

os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                  VLLM_ENABLE_V1_MULTIPROCESSING='0', VLLM_VIDEO_LOADER_BACKEND='opencv')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'cosmos_video'))
from benchmark import PROMPT


def rpc(root, command):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect(str(root/'capture.sock'))
        sock.sendall((json.dumps(dict(command=command))+'\n').encode())
        with sock.makefile('rb') as stream:
            return json.loads(stream.readline())


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    root = args.output
    root.mkdir(parents=True, exist_ok=False)
    import cv2
    import numpy as np
    import torch
    from vllm import LLM, SamplingParams
    cv2.setNumThreads(1)
    llm_args = dict(model='/work/assets/runtime-model', dtype='auto',
        max_model_len=6144, max_num_seqs=1, max_num_batched_tokens=2048,
        kv_cache_memory_bytes=768*1024*1024, gpu_memory_utilization=.40,
        enable_prefix_caching=False, mm_processor_cache_gb=0, swap_space=0,
        async_scheduling=False, enforce_eager=False,
        limit_mm_per_prompt={'video': {'count': 1, 'num_frames': 16,
                                      'width': 832, 'height': 468}, 'image': 0, 'audio': 0},
        mm_processor_kwargs={'truncation': False, 'do_sample_frames': False},
        media_io_kwargs={'video': {'num_frames': 16, 'fps': 4}})
    decoding = dict(temperature=.7, top_p=.8, top_k=20, presence_penalty=1.5,
                    repetition_penalty=1., seed=0, max_tokens=96)
    (root/'config.json').write_text(json.dumps(dict(llm_args=llm_args,
        decoding=decoding, prompt=PROMPT, selected_frames=16,
        policy='snapshot accumulated capture immediately after previous completion',
        timestamp_encoding='integer milliseconds as indices on virtual 1000 Hz clock; not camera fps',
        model='cyankiwi/Qwen3-VL-2B-Instruct-AWQ-4bit',
        revision='db40a251bdba88fafabf8f3176e7488ed523ab51'), indent=2))
    started = time.monotonic()
    llm = LLM(**llm_args)
    tok = llm.get_tokenizer()
    prompt = tok.apply_chat_template([dict(role='user', content=[dict(type='video'),
        dict(type='text', text=PROMPT)])], tokenize=False, add_generation_prompt=True)
    sampling = SamplingParams(**decoding)

    def generate(frames, metadata):
        result = llm.generate(dict(prompt=prompt, multi_modal_data={'video': [(frames, metadata)]},
            mm_processor_kwargs={'do_sample_frames': False}), sampling_params=sampling,
            use_tqdm=False)[0]
        torch.cuda.synchronize()
        return result

    # Reused offline footage warms the engine before the camera is opened.
    from frame_ablation import read_frames
    frames, metadata, _ = read_frames(Path('/work/private/sampling-cases-v1/c14.mp4'), 'uniform16', 832)
    generate(frames, metadata)
    del frames
    (root/'ready.json').write_text(json.dumps(dict(load_and_warmup_s=time.monotonic()-started)))
    print('MODEL_READY_CAMERA_NOT_STARTED', flush=True)
    deadline = time.monotonic()+600
    while not (root/'capture.sock').exists():
        if time.monotonic()>deadline:
            raise TimeoutError('Camera not started within ten minutes')
        time.sleep(.25)
    while True:
        state = rpc(root, 'status')
        if state['error']:
            raise RuntimeError(state['error'])
        if state['buffered'] >= 36 or state['done']:
            break
        time.sleep(.1)
    batch_id = 0
    previous_seq = -1
    with (root/'raw.jsonl').open('w') as log:
        while True:
            start = time.monotonic()
            batch = rpc(root, 'snapshot')
            if batch['error'] or batch['overflow']:
                raise RuntimeError(f'Capture error/overflow: {batch}')
            source = batch['frames']
            if not source:
                if batch['done']:
                    break
                raise RuntimeError('Empty live batch')
            assert source[0]['seq'] == previous_seq+1
            assert all(b['seq']==a['seq']+1 for a,b in zip(source, source[1:]))
            previous_seq = source[-1]['seq']
            indices = np.linspace(0,len(source)-1,16).round().astype(int).tolist()
            chosen = [source[i] for i in indices]
            frames = np.stack([cv2.cvtColor(cv2.imread(str(root/r['path'])),cv2.COLOR_BGR2RGB) for r in chosen])
            relative_ms = [round((r['mono']-batch['start'])*1000) for r in chosen]
            assert min(relative_ms)>=0 and relative_ms==sorted(relative_ms)
            meta = dict(total_num_frames=max(relative_ms)+1, fps=1000.,
                duration=batch['end']-batch['start'], frames_indices=relative_ms.copy(),
                video_backend='opencv', do_sample_frames=False)
            result = generate(frames, meta)
            done = time.monotonic()
            output = result.outputs[0]
            actual = tok.decode(result.prompt_token_ids)
            stamps = re.findall(r'<[0-9.]+ seconds>', actual)
            expected = [f'<{(relative_ms[i]+relative_ms[i+1])/2000:.1f} seconds>' for i in range(0,16,2)]
            assert stamps==expected, (stamps,expected)
            assert actual.count('<|video_pad|>')==3120
            row = dict(batch_id=batch_id, started_unix=time.time()-(done-start),
                started_mono=start, finished_mono=done, seconds=done-start,
                window_start=batch['start'], window_end=batch['end'],
                window_s=batch['end']-batch['start'],
                source_first_seq=source[0]['seq'], source_last_seq=source[-1]['seq'],
                captured_frames=len(source), selected=chosen, unique_selected=len(set(indices)),
                oldest_frame_age_s=done-chosen[0]['mono'], newest_frame_age_s=done-chosen[-1]['mono'],
                capture_max_gap_s=max([b['mono']-a['mono'] for a,b in zip(source,source[1:])] or [0]),
                overflow=batch['overflow'], capture_done=batch['done'],
                text=output.text, output_tokens=len(output.token_ids), finish_reason=output.finish_reason,
                visual_tokens=3120, actual_timestamps=stamps, input_checks_passed=True)
            log.write(json.dumps(row)+'\n')
            log.flush()
            print(json.dumps({k:row[k] for k in ['batch_id','seconds','window_s','captured_frames','text']}),flush=True)
            batch_id += 1
            del frames, result
            if batch['done']:
                break
    (root/'worker-done.json').write_text(json.dumps(dict(batches=batch_id,last_seq=previous_seq)))


if __name__ == '__main__':
    main()
