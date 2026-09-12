"""Summarize measured replays without calling them independent accuracy cases."""
import argparse
import json
from pathlib import Path
import re
import statistics

p = argparse.ArgumentParser()
p.add_argument("directory", type=Path)
a = p.parse_args()
r = json.loads((a.directory / "report.json").read_text())
summary = {"status": r["status"], "precision": r["precision"], "cases": []}
for case in r["cases"]:
    runs = [v for v in case["runs"] if not v["first_inference"]]
    summary["cases"].append({"image": Path(case["path"]).name,
        "replays": len(case["runs"]), "outputs": sorted(set(v["output"] for v in case["runs"])),
        "warmed_total_seconds": [v["total_seconds"] for v in runs],
        "warmed_median_seconds": statistics.median(v["total_seconds"] for v in runs) if runs else None,
        "truncated": any(v["hit_token_limit"] for v in case["runs"])})
log = (a.directory / "tegrastats.log").read_text()
for metric, pattern in [("ram_used_mb", r"RAM (\d+)/"), ("swap_used_mb", r"SWAP (\d+)/"),
                        ("temperature_c", r"[\w]+@([\d.]+)C")]:
    values = list(map(float, re.findall(pattern, log)))
    summary["peak_" + metric] = max(values) if values else None
summary["boundary"] = "image disk decode/preprocess through generation; excludes capture/event/Runtime; repeats are not accuracy samples or robust P95; token-limited outputs are not complete answers"
(a.directory / "summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
