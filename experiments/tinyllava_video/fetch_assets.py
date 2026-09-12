"""Download pinned public evaluation assets; never downloads training state."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import time

import requests

MODEL = "Zhang199/TinyLLaVA-Video-Qwen2.5-3B-Group-16-512"
REVISION = "490db36363bae6e6653e2ad09d2041a4a9a33f29"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", type=Path, required=True)
    args = parser.parse_args()
    jobs = []
    for repo, folder, revision in [
        (MODEL, "model", REVISION),
        ("google/siglip-so400m-patch14-384", "siglip", "main"),
        ("Qwen/Qwen2.5-3B", "qwen2", "main"),
    ]:
        response = requests.get(
            f"https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true",
            timeout=60,
        )
        response.raise_for_status()
        meta = response.json()
        target = args.dest / folder
        target.mkdir(parents=True, exist_ok=True)
        for entry in meta["siblings"]:
            name = entry["rfilename"]
            wanted = (name.endswith((".json", ".txt", ".safetensors"))
                      and name not in {"trainer_state.json"}) if folder == "model" else name in {
                          "config.json", "preprocessor_config.json"}
            if wanted and "/" not in name:
                jobs.append(dict(repo=repo, revision=meta["sha"], name=name,
                                 folder=folder, size=entry.get("size"),
                                 expected_sha256=entry.get("lfs", {}).get("sha256")))

    def fetch(job):
        target = args.dest / job["folder"] / job["name"]
        if not (target.exists() and target.stat().st_size == job["size"]):
            part = target.with_suffix(target.suffix + ".partial")
            for attempt in range(4):
                try:
                    offset = part.stat().st_size if part.exists() else 0
                    headers = {"Range": f"bytes={offset}-"} if offset else {}
                    url = f"https://huggingface.co/{job['repo']}/resolve/{job['revision']}/{job['name']}"
                    with requests.get(url, headers=headers, stream=True, timeout=(30, 120)) as r:
                        r.raise_for_status()
                        append = offset > 0 and r.status_code == 206
                        count = offset if append else 0
                        last = time.monotonic()
                        with part.open("ab" if append else "wb") as out:
                            for data in r.iter_content(8 * 1024 * 1024):
                                out.write(data)
                                count += len(data)
                                if time.monotonic() - last > 25:
                                    print(f"{job['name']}: {count / 1e9:.2f} GB", flush=True)
                                    last = time.monotonic()
                    if job["size"] is not None and part.stat().st_size != job["size"]:
                        raise ValueError("size mismatch")
                    part.replace(target)
                    break
                except Exception as exc:
                    # Avoid printing signed download URLs from HTTP exceptions.
                    print(f"{job['name']}: retry {attempt + 1}: {type(exc).__name__}", flush=True)
                    if attempt == 3:
                        raise RuntimeError(f"download failed: {job['name']}") from None
                    time.sleep(2)
        job["sha256"] = digest(target)
        if job["expected_sha256"] and job["sha256"] != job["expected_sha256"]:
            raise ValueError(f"SHA256 mismatch: {job['name']}")
        print(f"verified {job['folder']}/{job['name']}", flush=True)
        return job

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(fetch, jobs))
    (args.dest / "asset-manifest.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
