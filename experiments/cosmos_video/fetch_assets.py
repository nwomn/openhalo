"""Download the selected gated checkpoint using Jetson's existing HF login."""
import argparse
import hashlib
import json
import time
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

MODEL = "embedl/Cosmos-Reason2-2B-W4A16-Edge2-FlashHead"
REVISION = "9e4e46b4accf298a34d6db02ba637e9ecc175b6c"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, required=True)
    args = parser.parse_args()
    started = time.time()
    info = HfApi().model_info(MODEL, revision=REVISION, files_metadata=True)
    print(json.dumps({"stage": "download", "model": MODEL, "revision": REVISION,
                      "bytes": sum(f.size or 0 for f in info.siblings)}), flush=True)
    snapshot_download(MODEL, revision=REVISION, local_dir=args.dest / "model",
                      max_workers=2)
    records = []
    for asset in info.siblings:
        path = args.dest / "model" / asset.rfilename
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        size = path.stat().st_size
        if asset.size is not None and size != asset.size:
            raise ValueError("Downloaded size mismatch")
        upstream_hash = getattr(asset.lfs, "sha256", None) if asset.lfs else None
        if upstream_hash and digest.hexdigest() != upstream_hash:
            raise ValueError("Downloaded LFS hash mismatch")
        records.append(dict(path=asset.rfilename, bytes=size, sha256=digest.hexdigest(),
                            upstream_lfs_sha256=upstream_hash))
    manifest = dict(model=MODEL, revision=REVISION, files=records,
                    elapsed_seconds=time.time() - started)
    (args.dest / "asset-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"stage": "verified", "files": len(records)}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Do not echo signed URLs, auth headers or secret-bearing request objects.
        print(json.dumps({"stage": "failed", "error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1)
