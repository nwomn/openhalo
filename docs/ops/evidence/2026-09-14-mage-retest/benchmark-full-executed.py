"""Matched-frame resident Mage replay; uncompressed full-frame MAGECV1 input."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import struct
import subprocess
import sys
import threading
import time

import cv2
import numpy as np
from PIL import Image

PROMPT = "Describe the visible hand gesture and any object visibly held in the hands. If they change, describe the changes in chronological order and the ending state. State when the hands are visibly empty. If the evidence is unclear, say so. Do not guess hidden objects or intentions. Answer concisely."
CASES = {
    "c14": ("/home/jetson/openhalo-qwen3-vl-video/private/sampling-cases-v1/c14.mp4", "e675189332990a6256e42c8350745ce487d88e9bd82ac5da89bc56b1d6793d6e", [28.5,35.5]),
    "c11": ("/home/jetson/openhalo-cosmos-video/private/cases-v1/c11.mp4", "a822a301d10fee79ff61ae152b4a2deadec1e6521373238e1b583f07bbcb4eeb", [36,43]),
    "c12": ("/home/jetson/openhalo-cosmos-video/private/cases-v1/c12.mp4", "1b9371e005da5efafcee18ffe1f67b2f3712b2830063c5e9f28707a15ddc38db", [43,54]),
}

def prepare(case, directory):
    path, expected, interval = CASES[case]
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    assert digest == expected
    cap = cv2.VideoCapture(path)
    frames = []
    while True:
        ok, bgr = cap.read()
        if not ok: break
        frames.append(bgr)
    cap.release()
    indices = np.rint(np.linspace(0, len(frames)-1, 16)).astype(int).tolist()
    assert len(set(indices)) == 16
    paths = []
    # MAGECV1 full-frame patches retain the original 4-fps source frame IDs.
    # Four bundles bound vision batch size; all 16 frames enter one request.
    h, w = 480, 832
    yy, xx = np.meshgrid(np.arange(h//16), np.arange(w//16), indexing="ij")
    order = np.arange(yy.size).reshape(1,h//32,2,w//32,2).transpose(0,1,3,2,4).reshape(-1)
    for group in range(4):
        positions, encoded = [], []
        for frame_id in indices[group*4:group*4+4]:
            rgb = cv2.cvtColor(cv2.resize(frames[frame_id], (832,468), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
            # Explicit geometry adapter to the native 32-pixel grid, no crop.
            rgb = cv2.resize(rgb, (w,h), interpolation=cv2.INTER_LINEAR)
            buf = io.BytesIO(); Image.fromarray(rgb).save(buf, format="PNG")
            encoded.append(buf.getvalue())
            pos = np.stack([np.full_like(yy,frame_id),yy,xx],axis=-1).reshape(-1,3)
            positions.append(pos[order])
        positions = np.concatenate(positions).astype("<i4")
        dest = directory / f"{case}-{group}.mcv"
        with dest.open("wb") as f:
            f.write(b"MAGECV1\0" + struct.pack("<fIII",4.0,4,len(positions),0))
            f.write(positions.tobytes())
            for payload in encoded:
                f.write(struct.pack("<I",len(payload))); f.write(payload)
        paths.append(str(dest))
    return paths, dict(input_sha256=digest,source_interval_s=interval,sampled_frame_indices=indices,
                       sampled_times_s=[i/4 for i in indices],input_shape=[16,468,832,3],
                       effective_frame_size=[480,832],visual_tokens=16*390,
                       geometry_adapter="832x468 RGB resized to 832x480, PNG lossless, full patches; four 4-frame bundles in one prompt")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--cases",nargs="+",default=list(CASES)); ap.add_argument("--repeats",type=int,default=3)
    args=ap.parse_args(); args.root.mkdir(parents=True,exist_ok=True)
    (args.root/"prompt.txt").write_text(PROMPT)
    command=[str(args.root.parent/"resident"),"/home/jetson/mage-models/mage-vl-backbone-Q4_K_M.gguf",
             "/home/jetson/mage-models/mage-vit-mmproj-Q8_0.gguf",str(args.root/"prompt.txt")]
    (args.root/"config.json").write_text(json.dumps(dict(command=command,prompt=PROMPT,max_tokens=96,
        cases=args.cases,repeats=args.repeats,decoding="greedy",n_ctx=8192,n_batch=1024,n_ubatch=256,
        n_threads=4,flash_attention=True,resident_context=True,request_memory_cleared=True,gate=False,
        timing="clip read/hash/decode/resize/pack plus native preprocessing and generation; loading separate"),indent=2))
    events=queue.Queue()
    with (args.root/"native.stderr.log").open("w") as err:
        proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,text=True,bufsize=1)
        def drain():
            try:
                for line in proc.stdout:
                    events.put(json.loads(line))
            except Exception as e: events.put(e)
            finally: events.put(None)
        threading.Thread(target=drain,daemon=True).start()
        def get():
            event=events.get(timeout=240)
            if not isinstance(event,dict): raise RuntimeError(f"native event failed: {event}, exit {proc.poll()}")
            return event
        try:
            ready=get(); assert ready["event"]=="ready"
            (args.root/"load.json").write_text(json.dumps(ready)); print(json.dumps(ready),flush=True)
            with (args.root/"raw.jsonl").open("w") as out:
                for case in args.cases:
                    for repeat in range(-1,args.repeats):
                        unix=time.time(); start=time.perf_counter()
                        paths,metadata=prepare(case,args.root); prep_s=time.perf_counter()-start
                        proc.stdin.write("\t".join(paths)+"\n"); proc.stdin.flush()
                        actual=get(); assert actual["event"]=="input"
                        assert actual["frames"]==metadata["sampled_frame_indices"],actual
                        assert actual["seconds"]==metadata["sampled_times_s"],actual
                        assert actual["visual_tokens"]==metadata["visual_tokens"]
                        result=get(); assert result["event"]=="response"
                        row=dict(case=case,repeat=repeat,warmup=repeat<0,started_unix=unix,
                                 seconds=time.perf_counter()-start,prepare_s=prep_s,input_checks_passed=True,
                                 actual_input=actual,**metadata,**result)
                        out.write(json.dumps(row)+"\n");out.flush();print(json.dumps(row),flush=True)
            proc.stdin.close(); assert proc.wait(timeout=30)==0
        finally:
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired: proc.kill();proc.wait()

if __name__=="__main__": main()
