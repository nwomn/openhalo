"""Create a local runtime config view without modifying downloaded assets."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=Path("/work/assets"))
    args = parser.parse_args()
    source = args.assets / "model"
    target = args.assets / "runtime-model"
    config = json.loads((source / "config.json").read_text())
    assert config["model_type"] == "qwen3_5"
    assert config["architectures"] == ["FlashHeadQwen3_5ForCausalLM"]
    index = json.loads((source / "model.safetensors.index.json").read_text())
    assert any(k.startswith("model.visual.") for k in index["weight_map"])
    target.mkdir(exist_ok=True)
    for asset in source.iterdir():
        if asset.name == "config.json":
            continue
        link = target / asset.name
        if link.exists():
            assert link.is_symlink() and link.resolve() == asset.resolve()
        else:
            link.symlink_to(asset.resolve())
    config["architectures"] = ["FlashHeadQwen3_5ForConditionalGeneration"]
    config["flash_head_cache_dir"] = str((source / "flash_head_assets").resolve())
    (target / "config.json").write_text(json.dumps(config, indent=2) + "\n")


if __name__ == "__main__":
    main()
