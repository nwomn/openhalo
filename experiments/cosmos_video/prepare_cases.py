"""Freeze visually selected intervals from the owner's existing recording."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

# Reference descriptions are never sent to benchmark.py or the model.
WINDOWS = [
    ("c01", 3.0, 5.5, "phone front held in hand"),
    ("c02", 10.0, 14.5, "screwdriver held and rotated, then hand lowered"),
    ("c03", 19.5, 21.0, "visibly empty open palm, then lowered; waving not established"),
    ("c04", 29.0, 31.2, "empty closed fist"),
    ("c05", 32.0, 33.4, "thumbs-up, no held object"),
    ("c06", 34.0, 35.4, "V gesture, no held object"),
    ("c07", 39.0, 40.5, "phone back held in hand"),
    ("c08", 44.0, 48.5, "screwdriver held in hand"),
    ("c09", 51.0, 53.0, "visibly empty open palm after object put down"),
    ("c10", 26.5, 36.0, "hand initially down; open palm -> fist -> thumbs-up -> V, beginning to lower at end"),
    ("c11", 36.0, 43.0, "raise phone, show front/back, lower out of view"),
    ("c12", 43.0, 54.0, "show screwdriver, lower it, show empty palm, lower hand"),
    ("c13", 55.0, 58.0, "hands not clearly visible; empty-hand state not established"),
]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest, references = [], []
    for ident, start, end, reference in WINDOWS:
        target = args.output / (ident + ".mp4")
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-ss", str(start), "-i", str(args.source), "-t", str(end - start),
            "-an", "-vf", "fps=4", "-c:v", "libx264", "-preset", "fast",
            "-crf", "18", "-threads", "2", "-pix_fmt", "yuv420p", str(target)
        ], check=True)
        probe = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries",
            "stream=width,height,nb_frames,r_frame_rate:format=duration",
            "-of", "json", str(target)]))
        manifest.append(dict(id=ident, video=str(target.resolve())))
        references.append(dict(id=ident, source_start_s=start, source_end_s=end,
                               reference=reference, sha256=sha256(target), probe=probe))
    (args.output / "cases.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    reference_doc = dict(source_sha256=sha256(args.source),
                         source=str(args.source.resolve()),
                         limitations=["Reused recording, not independent holdout",
                                      "No mouse observed in inspected samples",
                                      "No confirmed greeting-wave reference"],
                         cases=references)
    (args.output / "references.json").write_text(
        json.dumps(reference_doc, indent=2), encoding="utf-8")
    print(json.dumps(dict(prepared=len(manifest), output=str(args.output))), flush=True)


if __name__ == "__main__":
    main()
