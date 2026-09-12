"""Summarize bounded replay runs without treating repeated clips as accuracy."""
import argparse
import json
from pathlib import Path
import re
import statistics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    report = json.loads((args.directory / "report.json").read_text())
    log = (args.directory / "tegrastats.log").read_text()
    summary = {"status": report["status"], "load_seconds": report.get("load_seconds"),
               "error": report.get("error"), "case_count": len(report["cases"]),
               "accuracy_acceptance": "not established by repeated inference on one clip",
               "timing_boundary": "local clip decode/preprocessing through completed model output; excludes capture and Runtime"}
    patterns = dict(ram_mb=r"RAM (\d+)/", swap_mb=r"SWAP (\d+)/",
                    gpu_percent=r"GR3D_FREQ (\d+)%", temperature_c=r"@([\d.]+)C",
                    input_power_mw=r"VDD_IN (\d+)mW")
    for name, pattern in patterns.items():
        values = [float(x) for x in re.findall(pattern, log)]
        summary["peak_" + name] = max(values) if values else None
    runs = [run for case in report["cases"] for run in case["runs"]]
    warmed = [run for run in runs if not run["first_inference"]]
    summary["outputs"] = [run["output"] for run in runs]
    summary["measured_runs"] = len(runs)
    summary["warmed_runs"] = len(warmed)
    for name in ["total_seconds", "preprocessing_seconds", "vision_seconds",
                 "connector_seconds", "language_seconds"]:
        values = [run[name] for run in warmed]
        summary[name] = ({"min": min(values), "median": statistics.median(values),
                          "max": max(values)} if values else None)
    summary["all_warmed_runs_exceed_5s"] = (all(run["total_seconds"] > 5 for run in warmed)
                                           if warmed else None)
    (args.directory / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
