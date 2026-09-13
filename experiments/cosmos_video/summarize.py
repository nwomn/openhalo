"""Check replay evidence and attach manual, per-axis observations (not accuracy)."""
import argparse
import json
import statistics
from pathlib import Path

REVIEW = {
    "c01": "Phone noun correct; repetitive text hits length limit, not a complete usable reply.",
    "c02": "Screwdriver correct; falsely says hand stays in position, missing lowering at end.",
    "c03": "Open palm and no held object correct; lowering at end not reported.",
    "c04": "Fist recognized. No visible-object hallucination.",
    "c05": "Thumbs-up recognized.",
    "c06": "V/peace sign and no held object recognized.",
    "c07": "Phone back recognized as smartphone.",
    "c08": "Screwdriver recognized but same answer falsely says the hand is empty.",
    "c09": "Open palm recognized; explicit empty-hand state not returned.",
    "c10": "Palm -> fist -> thumbs-up -> V order correct; final beginning-to-lower motion omitted.",
    "c11": "Phone recognized, but invented thumbs-up; front/back/lowering sequence not recovered.",
    "c12": "Mentions palm and red/silver object, but treats sequential states as coexisting hands; no correct object-to-empty-to-lowered sequence.",
    "c13": "Correctly says hands are not visible; does not infer empty hands.",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    runs = [json.loads(line) for line in (args.evidence / "raw-v5.jsonl").read_text().splitlines()]
    refs = {r["id"]: r for r in json.loads((args.evidence / "references.json").read_text())["cases"]}
    formal = [r for r in runs if not r["warmup"]]
    assert len(runs) == 40 and len(formal) == 39
    cases = []
    for cid, review in REVIEW.items():
        rows = [r for r in formal if r["case_id"] == cid]
        assert len(rows) == 3 and {r["repeat"] for r in rows} == {0, 1, 2}
        for row in rows:
            assert row["input_sha256"] == refs[cid]["sha256"]
            n, h, w, channels = row["input_shape"]
            assert 1 <= n <= 12 and (h, w, channels) == (468, 832, 3)
            assert row["metadata"]["do_sample_frames"] is False
            assert row["visual_tokens"] == ((n + 1) // 2) * 390
            indices = row["metadata"]["frames_indices"][:n]
            if n % 2:
                indices.append(indices[-1])
            expected = [(indices[i] + indices[i+1]) / 8 for i in range(0, len(indices), 2)]
            actual = [float(t[1:].split()[0]) for t in row["actual_timestamps"]]
            assert len(expected) == len(actual)
            assert all(abs(a-b) <= 0.050001 for a, b in zip(expected, actual))
        times = [r["seconds"] for r in rows]
        cases.append(dict(id=cid, reference=refs[cid]["reference"], review=review,
                          min_s=min(times), max_s=max(times), median_s=statistics.median(times),
                          text=rows[0]["text"], finish_reason=rows[0]["finish_reason"],
                          distinct_answers=len({r["text"] for r in rows})))
    stopped = [r for r in formal if r["finish_reason"] == "stop"]
    summary = dict(formal_runs=len(formal), distinct_clips=len(cases),
                   stopped_runs=len(stopped), truncated_runs=len(formal)-len(stopped),
                   all_elapsed_range_s=[min(r["seconds"] for r in formal),max(r["seconds"] for r in formal)],
                   all_elapsed_median_s=statistics.median(r["seconds"] for r in formal),
                   completed_elapsed_median_s=statistics.median(r["seconds"] for r in stopped),
                   completed_within_8s=sum(r["seconds"]<=8 for r in stopped),
                   caution="Completion/speed is not semantic acceptance; repeats are not independent samples.",
                   cases=cases)
    (args.evidence / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k != "cases"}, indent=2))


if __name__ == "__main__":
    main()
