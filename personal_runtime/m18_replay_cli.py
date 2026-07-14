"""Command-line entrypoint for safe M18 offline replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from personal_runtime.m18_replay import replay_m18_state_history


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay persisted observations through the M18 admission gate."
    )
    parser.add_argument(
        "--state",
        required=True,
        help="Path to a persisted RuntimeState JSON file.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = json.loads(Path(args.state).read_text(encoding="utf-8"))
    report = replay_m18_state_history(payload)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
