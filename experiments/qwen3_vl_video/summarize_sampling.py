"""Summarize fixed-clip frame-count latency; semantic review remains separate."""
import argparse
import json
import statistics
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--run", type=Path, required=True)
args = parser.parse_args()
rows = [json.loads(x) for x in (args.run / "raw.jsonl").read_text().splitlines()]
config = json.loads((args.run / "config.json").read_text())
profiles, repeats = config["profiles"], config["repeats"]
formal = [r for r in rows if not r["warmup"]]
assert len(formal) == len(profiles) * repeats and len({r["input_sha256"] for r in formal}) == 1
assert all(r["input_checks_passed"] for r in formal)
result = dict(formal_requests=len(formal), source_sha256=formal[0]["input_sha256"],
              all_same_source=True, profiles={})
for name in profiles:
    group = [r for r in formal if r["profile"] == name]
    assert sorted(r["repeat"] for r in group) == list(range(repeats))
    for key in ["sampled_times_s", "input_shape", "visual_tokens", "actual_timestamps"]:
        assert all(r[key] == group[0][key] for r in group)
    times = [r["seconds"] for r in group]
    result["profiles"][name] = dict(
        selected_frames=group[0]["input_shape"][0], visual_tokens=group[0]["visual_tokens"],
        processor_frame_pairs=group[0]["processor_frame_pairs"],
        sampled_times_s=group[0]["sampled_times_s"],
        seconds=times, median_s=statistics.median(times), min_s=min(times), max_s=max(times),
        natural_stops=sum(r["finish_reason"] == "stop" for r in group),
        output_tokens=[r["output_tokens"] for r in group],
        distinct_answers=len({r["text"] for r in group}),
        answers=list(dict.fromkeys(r["text"] for r in group)),
        median_read_decode_resize_s=statistics.median(r["read_decode_resize_s"] for r in group))
baseline = result["profiles"]["uniform12"]["median_s"]
for group in result["profiles"].values():
    group["median_latency_reduction_vs_12_pct"] = 100 * (1 - group["median_s"] / baseline)
(args.run / "summary.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
