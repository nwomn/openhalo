"""Validate comparable input evidence and summarize a completed Qwen replay."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--run", type=Path, required=True)
parser.add_argument("--cosmos", type=Path, required=True)
args = parser.parse_args()
rows = [json.loads(line) for line in (args.run / "raw.jsonl").read_text().splitlines()]
reference_rows = [json.loads(line) for line in (args.cosmos / "raw.jsonl").read_text().splitlines()]
reference = {(r["case_id"], r["input_width"]): r for r in reference_rows if not r["warmup"]}
formal = [r for r in rows if not r["warmup"]]
assert formal and all("text" in r for r in formal)
checks = []
for row in formal:
    key = (row["case_id"], row["input_width"])
    assert row["actual_timestamps"], key
    if key in reference:
        old = reference[key]
        fields = ["input_sha256", "input_shape", "metadata", "visual_tokens", "actual_timestamps"]
        assert all(row[f] == old[f] for f in fields), key
        checks.append(dict(case_id=key[0], width=key[1], fields=fields, passed=True))
groups = {}
for width in sorted({r["input_width"] for r in formal}):
    selected = [r for r in formal if r["input_width"] == width]
    stopped = [r for r in selected if r["finish_reason"] == "stop"]
    times = [r["seconds"] for r in stopped]
    groups[width] = dict(requests=len(selected), stopped=len(stopped),
                         truncated=sum(r["finish_reason"] == "length" for r in selected),
                         stopped_within_8s=sum(t <= 8 for t in times),
                         stopped_within_10s=sum(t <= 10 for t in times),
                         stopped_min_s=min(times) if times else None,
                         stopped_max_s=max(times) if times else None,
                         stopped_median_s=statistics.median(times) if times else None)
summary = dict(formal_rows=len(formal), groups=groups, cosmos_input_checks=checks,
               raw_sha256=hashlib.sha256((args.run / "raw.jsonl").read_bytes()).hexdigest(),
               semantic_review="Separate manual review required; stop and latency do not imply correctness")
(args.run / "summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
