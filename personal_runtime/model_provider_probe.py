"""CLI entrypoint for bounded model-provider readiness probes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from personal_runtime.model_provider import DEFAULT_CONFIG_PATH
from personal_runtime.model_provider import probe_model_provider


def build_model_provider_probe_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe configured model provider.")
    parser.add_argument("--profile", default="proposal_formation")
    parser.add_argument(
        "--runtime-config-path",
        "--llm-config-path",
        dest="runtime_config_path",
        default=str(DEFAULT_CONFIG_PATH),
    )
    return parser


def main() -> None:
    parser = build_model_provider_probe_parser()
    args = parser.parse_args()

    result = probe_model_provider(
        profile_name=args.profile,
        config_path=Path(args.runtime_config_path),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
