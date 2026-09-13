"""Minimal local-video client; model execution requires a prepared vLLM server."""
import argparse
import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

MODEL = "embedl/Cosmos-Reason2-2B-W4A16-Edge2-FlashHead"
PROMPT = (
    "Describe the visible hand gesture and any object visibly held in the hands. "
    "If they change, describe the changes in chronological order and the ending state. "
    "State when the hands are visibly empty. If the evidence is unclear, say so. "
    "Do not guess hidden objects or intentions. Answer concisely."
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:18081/v1")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=96)
    args = parser.parse_args()
    if urlparse(args.url).hostname not in ("127.0.0.1", "localhost", "::1"):
        parser.error("This experiment only sends private video to a loopback server.")
    if args.repeats < 1 or args.max_tokens < 1:
        parser.error("repeats and max-tokens must be positive")
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if not cases or any(set(c) != {"id", "video"} for c in cases):
        parser.error("Each case must contain only a neutral id and local video path")
    for case in cases:
        if not Path(case["video"]).is_file():
            parser.error("A case video does not exist")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    # Refuse to record another served model under this candidate's name.
    with opener.open(args.url.rstrip("/") + "/models", timeout=10) as response:
        served = json.load(response)
    if MODEL not in [entry["id"] for entry in served["data"]]:
        parser.error("The required model ID is not served; verify model and plugin")
    args.output.mkdir(parents=True, exist_ok=False)
    config = dict(model=MODEL, prompt=PROMPT, max_tokens=args.max_tokens,
                  temperature=0, fps=4, repeats=args.repeats,
                  timing="read clip + encode request + local server processing to full reply",
                  exclusion="model load, prior clip extraction, capture, Runtime",
                  caution="HTTP model ID alone does not verify FlashHead activation")
    (args.output / "config.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8")
    runs = [(cases[0], -1)] + [(c, r) for c in cases for r in range(args.repeats)]
    with (args.output / "raw.jsonl").open("w", encoding="utf-8") as log:
        for case, repeat in runs:
            clip = Path(case["video"])
            row = dict(case_id=case["id"], repeat=repeat, warmup=repeat == -1)
            started = time.perf_counter()
            try:
                media = clip.read_bytes()
                video_url = "data:video/mp4;base64," + base64.b64encode(media).decode("ascii")
                body = dict(model=MODEL, temperature=0, max_tokens=args.max_tokens,
                            stream=False, messages=[dict(role="user", content=[
                                dict(type="video_url", video_url=dict(url=video_url, fps=4)),
                                dict(type="text", text=PROMPT)])])
                request = urllib.request.Request(
                    args.url.rstrip("/") + "/chat/completions",
                    data=json.dumps(body).encode("utf-8"),
                    headers={"Content-Type": "application/json"})
                with opener.open(request, timeout=120) as response:
                    result = json.load(response)
                elapsed = time.perf_counter() - started
                choice = result["choices"][0]
                row.update(seconds=elapsed, response=result,
                           finish_reason=choice.get("finish_reason"),
                           within_10s=elapsed <= 10,
                           semantic_pass=None,
                           input_sha256=hashlib.sha256(media).hexdigest())
            except Exception as exc:
                # Do not log request data URLs or credential-bearing environment.
                row.update(seconds=time.perf_counter() - started,
                           error_type=type(exc).__name__, within_10s=False,
                           http_status=getattr(exc, "code", None))
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            log.flush()
            print(json.dumps({k: v for k, v in row.items() if k != "response"}), flush=True)


if __name__ == "__main__":
    main()
