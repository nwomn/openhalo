"""Bounded replay/eval helpers for the M12 prompt contract."""

from __future__ import annotations

from personal_runtime.prompt_context import build_behavior_contract


def build_replay_eval(
    prompt_context_package: dict,
    grounding_bundle: dict | None = None,
) -> dict:
    contract = build_behavior_contract(
        prompt_context_package=prompt_context_package,
        grounding_bundle=grounding_bundle,
    )
    checks = dict(contract.get("checks", {}))
    return {
        "status": "pass" if all(item.get("ok", False) for item in checks.values()) else "fail",
        "prompt_context_version": prompt_context_package.get("version"),
        "checks": checks,
    }


__all__ = ["build_replay_eval"]
