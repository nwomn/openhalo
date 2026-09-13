"""Map the checkpoint's Transformers 5 RoPE schema to installed 4.57.6."""
import hashlib
import json
from pathlib import Path

from transformers import AutoConfig

root = Path("/work/assets")
source = root / "model"
target = root / "runtime-model"
target.mkdir(exist_ok=False)
config = json.loads((source / "config.json").read_text())
text_config = config["text_config"]
rope = text_config.pop("rope_parameters")
assert rope == dict(mrope_interleaved=True, mrope_section=[24, 20, 20],
                    rope_theta=5000000, rope_type="default")
text_config["rope_theta"] = rope.pop("rope_theta")
text_config["rope_scaling"] = rope
for path in source.iterdir():
    if path.name != "config.json":
        (target / path.name).symlink_to(Path("../model") / path.name)
(target / "config.json").write_text(json.dumps(config, indent=2))
loaded = AutoConfig.from_pretrained(target, trust_remote_code=False)
assert loaded.text_config.rope_theta == 5000000
assert loaded.text_config.rope_scaling["mrope_section"] == [24, 20, 20]
record = dict(source_config_sha256=hashlib.sha256((source / "config.json").read_bytes()).hexdigest(),
              runtime_config_sha256=hashlib.sha256((target / "config.json").read_bytes()).hexdigest(),
              change="RoPE schema only: rope_parameters -> rope_theta + rope_scaling; values preserved",
              rope_theta=loaded.text_config.rope_theta, rope_scaling=loaded.text_config.rope_scaling)
(root / "runtime-config-adaptation.json").write_text(json.dumps(record, indent=2))
print(json.dumps(record))
