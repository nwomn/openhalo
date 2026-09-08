"""Summarize request metrics; explicitly exclude first request by default."""
import argparse
import json
import statistics
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("run", type=Path)
parser.add_argument("--include-first", action="store_true")
args = parser.parse_args()
rows = [json.loads(line) for line in (args.run / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
selected = rows if args.include_first else rows[1:]
print(f"requests={len(rows)}, selected={len(selected)}, failures={sum(not r['ok'] for r in selected)}")
print("First request included:", args.include_first)
for key in ("first_content_s", "request_s", "frame_to_result_s", "load_s", "prompt_eval_s", "eval_s", "output_tokens", "capture_fps"):
    values = sorted(row[key] for row in selected if row.get("ok") and row.get(key) is not None)
    if values:
        # Nearest-rank P95: descriptive only; tiny samples cannot establish a latency SLA.
        import math
        print(f"{key}: n={len(values)} median={statistics.median(values):.3f} p95={values[math.ceil(.95*len(values))-1]:.3f}")
