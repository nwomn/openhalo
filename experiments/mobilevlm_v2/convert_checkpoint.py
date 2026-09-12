"""Memory-map the original public state dict and produce bounded-size shards."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--assets", type=Path, required=True)
    a = p.parse_args()
    import torch
    from safetensors.torch import save_file
    manifest = json.loads((a.assets / "asset-manifest.json").read_text())
    for entry in manifest:
        path = a.assets / entry["folder"] / entry["name"]
        h = hashlib.sha256()
        with path.open("rb") as f:
            for data in iter(lambda: f.read(8 * 1024 * 1024), b""):
                h.update(data)
        if h.hexdigest() != entry["sha256"]:
            raise ValueError(f"Transferred asset mismatch: {path.name}")
    source = a.assets / "model"
    target = a.assets / "sharded"
    target.mkdir(exist_ok=False)
    for path in source.iterdir():
        if path.suffix != ".bin":
            shutil.copy2(path, target / path.name)
    state = torch.load(source / "pytorch_model.bin", map_location="cpu", mmap=True, weights_only=True)
    shards, shard, size, total = [], {}, 0, 0
    for key, value in state.items():
        nbytes = value.numel() * value.element_size()
        if shard and size + nbytes > 450_000_000:
            shards.append(shard)
            shard, size = {}, 0
        shard[key] = value
        size += nbytes
        total += nbytes
    if shard:
        shards.append(shard)
    index = {"metadata": {"total_size": total}, "weight_map": {}}
    for i, shard in enumerate(shards):
        name = f"model-{i+1:05d}-of-{len(shards):05d}.safetensors"
        save_file(shard, str(target / name), metadata={"format": "pt"})
        index["weight_map"].update({key: name for key in shard})
        print(name, flush=True)
    (target / "model.safetensors.index.json").write_text(json.dumps(index, indent=2))
    (target / "conversion.json").write_text(json.dumps({
        "method": "torch.load weights_only mmap; lossless safetensors sharding",
        "tensor_count": len(state), "total_bytes": total,
        "vision_key_count": sum("vision_tower" in key for key in state),
        "source_sha256": next(e["sha256"] for e in manifest if e["name"] == "pytorch_model.bin"),
    }, indent=2))


if __name__ == "__main__":
    main()
