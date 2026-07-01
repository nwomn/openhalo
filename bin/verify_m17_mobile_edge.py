from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edge_api.protocol import API_VERSION
from personal_runtime.gateway_server import RuntimeGateway


TEST_LLM_CONFIG = ROOT / "tests" / "fixtures" / "llm-config-test.toml"

SCENARIOS = [
    "android-edge-registers-public-api",
    "mobile-context-observation-accepted",
    "terminal-intent-routes-to-android-notification",
    "nonchosen-surfaces-record-filter-reasons",
    "android-action-result-preserves-interaction-lineage",
]


def _last_action(replies: list[dict]) -> dict | None:
    return next(
        (item for item in reversed(replies) if item["type"] == "action_request"),
        None,
    )


def _android_capabilities() -> list[dict]:
    return [
        {
            "name": "notification.show",
            "direction": "runtime_to_edge",
            "kind": "action",
            "affordances": ["notify_user", "deliver_private_text"],
            "modality": "visual_text",
            "content_capacity": "short_text",
            "privacy": "personal",
            "interruptiveness": "medium",
            "side_effect": "user_visible",
            "input_schema": {
                "type": "object",
                "required": ["message"],
                "properties": {"message": {"type": "string"}},
            },
        },
        {
            "name": "mobile.context",
            "direction": "edge_to_runtime",
            "kind": "observation_provider",
            "observations": [
                {
                    "name": "mobile.app_visibility",
                    "schema": {
                        "type": "string",
                        "enum": ["foreground", "background", "unknown"],
                    },
                    "semantics": ["device_activity"],
                    "privacy": "personal_device_state",
                    "freshness_seconds": 120,
                },
                {
                    "name": "mobile.notification_permission",
                    "schema": {
                        "type": "string",
                        "enum": ["granted", "denied", "unknown"],
                    },
                    "semantics": ["permission_state"],
                    "privacy": "personal_device_state",
                    "freshness_seconds": 300,
                },
            ],
        },
    ]


async def run_verifier() -> dict:
    gateway = RuntimeGateway(
        shared_token="dev-token",
        persist_state=False,
        llm_config_path=TEST_LLM_CONFIG,
    )
    replies = await gateway.handle_test_frames(
        [
            {
                "api_version": API_VERSION,
                "type": "connect",
                "device": {
                    "device_id": "terminal-edge-1",
                    "device_type": "desktop-cli",
                },
                "auth": {"token": "dev-token"},
            },
            {
                "api_version": API_VERSION,
                "type": "capability_announce",
                "device_id": "terminal-edge-1",
                "capabilities": ["text.input"],
            },
            {
                "api_version": API_VERSION,
                "type": "connect",
                "device": {
                    "device_id": "android-edge-1",
                    "device_type": "android-phone",
                    "role": "interactive_surface",
                },
                "auth": {"token": "dev-token"},
            },
            {
                "api_version": API_VERSION,
                "type": "capability_announce",
                "device_id": "android-edge-1",
                "capabilities": _android_capabilities(),
            },
            {
                "api_version": API_VERSION,
                "type": "connect",
                "device": {
                    "device_id": "speaker-edge-1",
                    "device_type": "speaker",
                },
                "auth": {"token": "dev-token"},
            },
            {
                "api_version": API_VERSION,
                "type": "capability_announce",
                "device_id": "speaker-edge-1",
                "capabilities": [
                    {
                        "name": "speaker.play_audio",
                        "direction": "runtime_to_edge",
                        "kind": "action",
                        "affordances": ["notify_user"],
                        "modality": "public_audio",
                        "content_capacity": "spoken_text",
                        "privacy": "public",
                        "interruptiveness": "high",
                        "side_effect": "user_visible",
                        "input_schema": {
                            "type": "object",
                            "required": ["message"],
                            "properties": {"message": {"type": "string"}},
                        },
                    }
                ],
            },
            {
                "api_version": API_VERSION,
                "type": "connect",
                "device": {
                    "device_id": "desk-light-edge-1",
                    "device_type": "ambient-light",
                },
                "auth": {"token": "dev-token"},
            },
            {
                "api_version": API_VERSION,
                "type": "capability_announce",
                "device_id": "desk-light-edge-1",
                "capabilities": [
                    {
                        "name": "light.pulse",
                        "direction": "runtime_to_edge",
                        "kind": "action",
                        "affordances": ["ambient_signal"],
                        "modality": "ambient_light",
                        "content_capacity": "none",
                        "privacy": "public",
                        "interruptiveness": "low",
                        "side_effect": "environment_visible",
                        "input_schema": {"type": "object"},
                    }
                ],
            },
            {
                "api_version": API_VERSION,
                "type": "observation_push",
                "device_id": "android-edge-1",
                "capability": "mobile.context",
                "observations": [
                    {
                        "name": "mobile.app_visibility",
                        "value": "foreground",
                        "observed_at": "2026-07-01T03:56:04Z",
                        "confidence": 1.0,
                    },
                    {
                        "name": "mobile.notification_permission",
                        "value": "granted",
                        "observed_at": "2026-07-01T03:56:04Z",
                        "confidence": 1.0,
                    },
                ],
            },
            {
                "api_version": API_VERSION,
                "type": "event_push",
                "device_id": "terminal-edge-1",
                "capability": "text.input",
                "payload": {
                    "text": "send me a private reminder",
                    "observed_at": "2026-07-01T03:57:00Z",
                },
            },
        ]
    )
    action = _last_action(replies)
    if action is None:
        raise RuntimeError("expected action_request")
    if action["device_id"] != "android-edge-1":
        raise RuntimeError(f"expected android-edge-1 target, got {action['device_id']}")
    if action["action"]["capability"] != "notification.show":
        raise RuntimeError("expected notification.show action")

    interaction = gateway.state.interactions[-1]
    intervention = gateway.state.interventions[-1]
    planning_record = intervention["planning_record"]
    filtered = {
        item["device_id"]: item["reasons"]
        for item in planning_record["filtered_candidates"]
    }
    if interaction["source_device_id"] != "terminal-edge-1":
        raise RuntimeError("expected terminal source lineage")
    if interaction["participant_device_ids"] != ["terminal-edge-1", "android-edge-1"]:
        raise RuntimeError("expected terminal/android participant lineage")
    if planning_record["chosen_candidate"]["device_id"] != "android-edge-1":
        raise RuntimeError("expected android chosen candidate")
    if "privacy:public" not in filtered.get("speaker-edge-1", []):
        raise RuntimeError("expected public speaker privacy rejection")
    if "content_capacity:none" not in filtered.get("desk-light-edge-1", []):
        raise RuntimeError("expected ambient light content-capacity rejection")

    result_replies = await gateway.handle_test_frames(
        [
            {
                "api_version": API_VERSION,
                "type": "action_result",
                "request_id": action["request_id"],
                "interaction_id": action["interaction_id"],
                "device_id": "android-edge-1",
                "result": {
                    "status": "ok",
                    "capability": "notification.show",
                    "observed_at": "2026-07-01T03:57:02Z",
                    "details": {
                        "message": action["action"]["payload"]["message"],
                    },
                },
            }
        ]
    )
    if gateway.state.action_results[-1]["status"] != "ok":
        raise RuntimeError("expected ok action result")
    if gateway.state.action_results[-1]["capability"] != "notification.show":
        raise RuntimeError("expected notification.show action result")

    return {
        "ok": True,
        "api_version": API_VERSION,
        "registered_devices": sorted(gateway.state.devices.keys()),
        "android_observations": [
            observation.to_dict()
            for observation in gateway.state.observations
            if observation.source_device_id == "android-edge-1"
        ],
        "selected_action": {
            "device_id": action["device_id"],
            "capability": action["action"]["capability"],
            "interaction_id": action["interaction_id"],
            "request_id": action["request_id"],
        },
        "interaction_lineage": interaction,
        "planning": {
            "chosen_candidate": planning_record["chosen_candidate"],
            "filtered_candidates": planning_record["filtered_candidates"],
        },
        "action_result": gateway.state.action_results[-1],
        "post_result_reply_types": [reply["type"] for reply in result_replies],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        for scenario in SCENARIOS:
            print(f"[verify-m17-mobile-edge] {scenario}")
        return
    print(json.dumps(asyncio.run(run_verifier()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
