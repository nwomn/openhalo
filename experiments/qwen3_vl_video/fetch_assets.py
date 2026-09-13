"""Download pinned AWQ weights on Jetson; never execute checkpoint code."""
import hashlib
import json
import os
from pathlib import Path

import requests

MODEL = "cyankiwi/Qwen3-VL-2B-Instruct-AWQ-4bit"
REVISION = "db40a251bdba88fafabf8f3176e7488ed523ab51"


def main():
    root = Path("/home/jetson/openhalo-qwen3-vl-video/assets")
    dest = root / "model"
    dest.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    info = session.get(f"https://huggingface.co/api/models/{MODEL}/revision/{REVISION}",
                       params={"blobs": "true"}, timeout=30)
    info.raise_for_status()
    records = []
    for asset in info.json()["siblings"]:
        name = asset["rfilename"]
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        expected = (asset.get("lfs") or {}).get("sha256")
        if not path.exists() or path.stat().st_size != asset["size"]:
            response = session.get(f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}",
                                   stream=True, timeout=(30, 120))
            response.raise_for_status()
            temporary = path.with_name(path.name + ".partial")
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(8 * 1024 * 1024):
                    handle.write(chunk)
            os.replace(temporary, path)
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        assert path.stat().st_size == asset["size"]
        assert not expected or digest.hexdigest() == expected
        records.append(dict(path=name, bytes=path.stat().st_size,
                            sha256=digest.hexdigest(), upstream_lfs_sha256=expected))
        print(json.dumps(records[-1]), flush=True)
    (root / "asset-manifest.json").write_text(json.dumps(dict(
        model=MODEL, revision=REVISION, files=records), indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1)
