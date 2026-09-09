"""Experiment factors, independent of camera and presentation code."""
import argparse
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    task: str = "caption"
    display: str = "subtitles"
    model: str = "qwen2.5vl:3b"
    endpoint: str = "http://127.0.0.1:11434"
    source: str = "csi"
    camera_id: int = 0
    width: int = 1280
    height: int = 720
    fps: int = 30
    input_width: int = 640
    max_tokens: int = 192
    context: int = 2048
    temperature: float = 0.0
    seed: int = 42
    interval: float = 1.0
    requests: int = 0
    paused: bool = False
    host: str = "127.0.0.1"
    port: int = 8765
    output: str = "runs"


def parse_config():
    parser = argparse.ArgumentParser(description="Jetson VLM camera ablation demo")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--task", choices=["caption", "grounded"])
    parser.add_argument("--display", choices=["subtitles", "boxes"])
    parser.add_argument("--source", help="csi or a fixed image path for controlled comparisons")
    parser.add_argument("--requests", type=int)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--paused", action="store_true", default=None)
    args = vars(parser.parse_args())
    values = json.loads(args.pop("config").read_text(encoding="utf-8"))
    values.update({k: v for k, v in args.items() if v is not None})
    config = Config(**values)
    if config.display == "boxes" and config.task != "grounded":
        parser.error("boxes requires task=grounded; caption does not produce coordinates")
    if min(config.width, config.height, config.fps, config.input_width,
           config.max_tokens, config.context) <= 0 or config.requests < 0:
        parser.error("dimensions/rates/token budgets must be positive; requests >= 0")
    if config.interval < 0:
        parser.error("interval >= 0 required")
    return config
