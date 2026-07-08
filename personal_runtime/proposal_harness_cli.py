"""CLI entrypoint for bounded proposal harness checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from personal_runtime.proposal_harness import classify_observed_runtime_state_file
from personal_runtime.proposal_harness import load_harness_cases_from_runtime_state
from personal_runtime.proposal_harness import replay_prompt_variants_with_provider
from personal_runtime.proposal_harness import run_fixture_prompt_variant_comparison


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run bounded Agent Runtime proposal harness checks."
    )
    parser.add_argument(
        "--fixture",
        default="m17-6-terminal-phone",
        choices=["m17-6-terminal-phone"],
    )
    parser.add_argument(
        "--state",
        help="Load a persisted RuntimeState JSON file and classify observed post-action proposals.",
    )
    parser.add_argument(
        "--provider-replay",
        action="store_true",
        help="Run raw_json and decision_brief variants through the configured provider for state-derived cases.",
    )
    parser.add_argument(
        "--runtime-config-path",
        default="config/runtime-config.toml",
        help="Runtime model config used for provider replay.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.state and args.provider_replay:
        state = json.loads(Path(args.state).read_text(encoding="utf-8"))
        report = replay_prompt_variants_with_provider(
            load_harness_cases_from_runtime_state(state),
            config_path=args.runtime_config_path,
        )
    elif args.state:
        report = classify_observed_runtime_state_file(Path(args.state))
    else:
        report = run_fixture_prompt_variant_comparison()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
