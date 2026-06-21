import json
import unittest
from pathlib import Path

import websockets

from device_edge.shared.session_client import SessionClient
from personal_runtime.gateway_server import RuntimeGateway
from personal_runtime.runtime_state import RuntimeState


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_connect_event_and_action_roundtrip(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token")
        reply = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "hello"},
                },
            ]
        )

        self.assertEqual(reply[-1]["type"], "action_request")
        self.assertEqual(reply[-1]["action"]["capability"], "notification.show")

    async def test_sync_roundtrip_wrapper_returns_replies(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token")
        replies = gateway.run_roundtrip(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "hello"},
                },
            ]
        )

        self.assertEqual(replies[-1]["type"], "action_request")

    async def test_persists_state_after_connect_event_and_action_result(self) -> None:
        state_path = Path(
            "/root/personal-runtime-agent/.worktrees/v0-single-edge-loop/.runtime-test/gateway-state.json"
        )
        gateway = RuntimeGateway(shared_token="dev-token", state_path=state_path)
        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "hello"},
                },
                {
                    "type": "action_result",
                    "device_id": "desktop-dev-1",
                    "result": {"status": "ok"},
                },
            ]
        )

        persisted = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(replies[-1]["type"], "action_request")
        self.assertEqual(
            persisted["devices"]["desktop-dev-1"]["capabilities"],
            ["notification.show", "text.input"],
        )
        self.assertEqual(persisted["events"][-1]["payload"]["text"], "hello")
        self.assertEqual(persisted["action_results"][-1]["status"], "ok")

    async def test_websocket_server_emits_connect_ack_and_action_request(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token")
        async with gateway.run_test_server() as server_info:
            async with websockets.connect(server_info["url"]) as websocket:
                await websocket.send(
                    json.dumps(
                        {
                            "type": "connect",
                            "device": {
                                "device_id": "desktop-dev-1",
                                "device_type": "desktop-cli",
                            },
                            "auth": {"token": "dev-token"},
                        }
                    )
                )
                await websocket.send(
                    json.dumps(
                        {
                            "type": "capability_announce",
                            "device_id": "desktop-dev-1",
                            "capabilities": ["text.input", "notification.show"],
                        }
                    )
                )
                await websocket.send(
                    json.dumps(
                        {
                            "type": "event_push",
                            "device_id": "desktop-dev-1",
                            "capability": "text.input",
                            "payload": {"text": "hello"},
                        }
                    )
                )

                connect_ok = json.loads(await websocket.recv())
                event_ack = json.loads(await websocket.recv())
                action_request = json.loads(await websocket.recv())

        self.assertEqual(connect_ok["type"], "connect_ok")
        self.assertEqual(event_ack["type"], "event_ack")
        self.assertEqual(action_request["type"], "action_request")

    async def test_direct_action_event_bypasses_router_but_is_still_persisted(self) -> None:
        state_path = Path(
            "/root/personal-runtime-agent/.worktrees/v0-single-edge-loop/.runtime-test/direct-action-state.json"
        )
        gateway = RuntimeGateway(shared_token="dev-token", state_path=state_path)
        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "urgent ping",
                        "direct_action": {
                            "capability": "notification.show",
                            "payload": {"message": "urgent ping"},
                        },
                    },
                },
            ]
        )

        persisted = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(replies[-2]["type"], "event_ack")
        self.assertEqual(replies[-1]["type"], "action_request")
        self.assertEqual(replies[-1]["action"]["payload"]["message"], "urgent ping")
        self.assertEqual(
            persisted["events"][-1]["payload"]["direct_action"]["payload"]["message"],
            "urgent ping",
        )

    async def test_normal_path_can_target_other_registered_device(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token")
        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-2",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-2",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "hello routed runtime"},
                },
            ]
        )

        self.assertEqual(replies[-1]["type"], "action_request")
        self.assertEqual(replies[-1]["device_id"], "desktop-dev-2")
        self.assertEqual(replies[-1]["action"]["capability"], "notification.show")
        self.assertEqual(gateway.state.interventions[-1]["decision"], "allow")
        self.assertEqual(gateway.state.interventions[-1]["target_device_id"], "desktop-dev-2")
        self.assertEqual(gateway.state.interventions[-1]["proposal"]["action_capability"], "notification.show")
        self.assertEqual(gateway.state.interventions[-1]["proposal"]["kind"], "notify")

    async def test_normal_path_falls_back_to_source_when_peer_is_not_online(self) -> None:
        state = RuntimeState()
        state.register_device("desktop-dev-2", "desktop-cli")
        state.register_capability("desktop-dev-2", "notification.show")
        state.register_capability("desktop-dev-2", "text.input")
        gateway = RuntimeGateway(shared_token="dev-token", state=state)

        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "stay local"},
                },
            ]
        )

        self.assertEqual(replies[-1]["type"], "action_request")
        self.assertEqual(replies[-1]["device_id"], "desktop-dev-1")

    async def test_normal_path_suppresses_user_facing_action_when_location_context_is_ambiguous(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token", persist_state=False)
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show", "desktop_context"],
        )

        replies = await gateway.handle_test_frames(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
                client.build_observation_event(
                    capability="desktop_context",
                    observations=[
                        {
                            "name": "user.location",
                            "value": "office",
                            "observed_at": "2026-06-19T10:30:00Z",
                            "confidence": 0.81,
                        }
                    ],
                ),
                {
                    "type": "event_push",
                    "device_id": "phone-1",
                    "capability": "mobile_context",
                    "event_id": "evt-mobile-1",
                    "payload": {
                        "observations": [
                            {
                                "name": "user.location",
                                "value": "train",
                                "observed_at": "2026-06-19T10:29:00Z",
                                "confidence": 0.80,
                            }
                        ]
                    },
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {"text": "should be suppressed"},
                },
            ]
        )

        self.assertEqual(replies[-1]["type"], "event_ack")
        self.assertEqual(len([reply for reply in replies if reply["type"] == "action_request"]), 0)
        self.assertEqual(gateway.state.interventions[-1]["decision"], "suppress")
        self.assertEqual(gateway.state.interventions[-1]["reason"], "context_ambiguous")

    async def test_normal_path_ignores_stale_conflicting_location_evidence(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token", persist_state=False)
        client = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show", "desktop_context"],
        )

        replies = await gateway.handle_test_frames(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
                client.build_observation_event(
                    capability="desktop_context",
                    observations=[
                        {
                            "name": "user.location",
                            "value": "office",
                            "observed_at": "2026-06-19T10:30:00Z",
                            "confidence": 0.81,
                        }
                    ],
                ),
                {
                    "type": "event_push",
                    "device_id": "phone-1",
                    "capability": "mobile_context",
                    "event_id": "evt-mobile-1",
                    "payload": {
                        "observations": [
                            {
                                "name": "user.location",
                                "value": "train",
                                "observed_at": "2026-06-19T10:29:00Z",
                                "confidence": 0.80,
                            }
                        ]
                    },
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "fresh enough to notify",
                        "observed_at": "2026-06-19T10:36:00Z",
                    },
                },
            ]
        )

        self.assertEqual(replies[-1]["type"], "action_request")
        self.assertEqual(replies[-1]["action"]["capability"], "notification.show")
        self.assertEqual(gateway.state.interventions[-1]["decision"], "allow")
        self.assertEqual(gateway.state.interventions[-1]["reason"], "context_clear")
        self.assertEqual(
            gateway.state.interventions[-1]["snapshot_contract"]["fields"][
                "user.current_location"
            ]["status"],
            "stale",
        )

    async def test_normal_path_records_fresh_runtime_health_contract_for_intervention(
        self,
    ) -> None:
        gateway = RuntimeGateway(shared_token="dev-token", persist_state=False)
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        replies = await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                host.build_observation_event(
                    capability="runtime.health",
                    observations=[
                        {
                            "name": "runtime.health_state",
                            "value": "healthy",
                            "observed_at": "2026-06-21T10:08:00Z",
                            "confidence": 1.0,
                        },
                        {
                            "name": "runtime.process_pid",
                            "value": 4242,
                            "observed_at": "2026-06-21T10:08:00Z",
                            "confidence": 1.0,
                        },
                    ],
                ),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "notify me",
                        "observed_at": "2026-06-21T10:10:00Z",
                    },
                },
            ]
        )

        self.assertEqual(replies[-1]["type"], "action_request")
        snapshot_contract = gateway.state.interventions[-1]["snapshot_contract"]
        self.assertEqual(snapshot_contract["snapshot_time"], "2026-06-21T10:10:00Z")
        self.assertEqual(
            snapshot_contract["fields"]["runtime.current_health_state"]["value"],
            "healthy",
        )
        self.assertEqual(
            snapshot_contract["fields"]["runtime.current_health_state"]["status"],
            "fresh",
        )
        self.assertEqual(
            snapshot_contract["fields"]["runtime.current_process_pid"]["value"],
            4242,
        )
        self.assertEqual(
            snapshot_contract["fields"]["runtime.current_process_pid"]["status"],
            "fresh",
        )

    async def test_normal_path_records_stale_runtime_health_contract_for_intervention(
        self,
    ) -> None:
        gateway = RuntimeGateway(shared_token="dev-token", persist_state=False)
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        replies = await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                host.build_observation_event(
                    capability="runtime.health",
                    observations=[
                        {
                            "name": "runtime.health_state",
                            "value": "healthy",
                            "observed_at": "2026-06-21T10:00:00Z",
                            "confidence": 1.0,
                        }
                    ],
                ),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "notify me anyway",
                        "observed_at": "2026-06-21T10:10:00Z",
                    },
                },
            ]
        )

        self.assertEqual(replies[-1]["type"], "action_request")
        snapshot_contract = gateway.state.interventions[-1]["snapshot_contract"]
        self.assertEqual(
            snapshot_contract["fields"]["runtime.current_health_state"]["value"],
            "unknown",
        )
        self.assertEqual(
            snapshot_contract["fields"]["runtime.current_health_state"]["status"],
            "stale",
        )
        self.assertEqual(
            snapshot_contract["fields"]["runtime.current_health_state"]["evidence"][0][
                "name"
            ],
            "runtime.health_state",
        )

    async def test_agent_initiative_path_routes_runtime_status_through_presence_and_records_source(
        self,
    ) -> None:
        gateway = RuntimeGateway(shared_token="dev-token", persist_state=False)
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        replies = await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                host.build_observation_event(
                    capability="runtime.health",
                    observations=[
                        {
                            "name": "runtime.health_state",
                            "value": "healthy",
                            "observed_at": "2026-06-21T10:08:00Z",
                            "confidence": 1.0,
                        }
                    ],
                ),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "observed_at": "2026-06-21T10:10:00Z",
                        "agent_initiative": {
                            "action_capability": "runtime.status",
                            "action_payload": {},
                            "reason": "runtime_health_check",
                            "target_device_hint": "host-edge-1",
                        },
                    },
                },
            ]
        )

        self.assertEqual(replies[-1]["type"], "action_request")
        self.assertEqual(replies[-1]["device_id"], "host-edge-1")
        self.assertEqual(replies[-1]["action"]["capability"], "runtime.status")
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["source"],
            "agent_initiative",
        )
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["action_capability"],
            "runtime.status",
        )
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["metadata"]["reason"],
            "runtime_health_check",
        )
        self.assertEqual(
            gateway.state.interventions[-1]["snapshot_contract"]["snapshot_time"],
            "2026-06-21T10:10:00Z",
        )

    async def test_agent_initiative_path_still_respects_presence_cooldown(self) -> None:
        state = RuntimeState()
        state.record_intervention(
            {
                "target_device_id": "host-edge-1",
                "action_capability": "runtime.status",
                "decision": "allow",
                "reason": "context_clear",
                "proposal": {
                    "source": "agent_initiative",
                    "action_capability": "runtime.status",
                },
                "recorded_at": "2026-06-21T10:06:00Z",
            }
        )
        gateway = RuntimeGateway(shared_token="dev-token", state=state, persist_state=False)
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        replies = await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "observed_at": "2026-06-21T10:10:00Z",
                        "agent_initiative": {
                            "action_capability": "runtime.status",
                            "action_payload": {},
                            "reason": "runtime_health_check",
                            "target_device_hint": "host-edge-1",
                        },
                    },
                },
            ]
        )

        self.assertEqual(replies[-1]["type"], "event_ack")
        self.assertEqual(
            len([reply for reply in replies if reply["type"] == "action_request"]),
            0,
        )
        self.assertEqual(gateway.state.interventions[-1]["decision"], "suppress")
        self.assertEqual(gateway.state.interventions[-1]["reason"], "cooldown_active")
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["source"],
            "agent_initiative",
        )

    async def test_runtime_can_trigger_agent_initiative_without_edge_text_event(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token", persist_state=False)
        source = SessionClient(
            device_id="desktop-dev-1",
            device_type="desktop-cli",
            token="dev-token",
            capabilities=["text.input", "notification.show"],
        )
        host = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        await gateway.handle_test_frames(
            [
                source.build_connect_frame(),
                source.build_capability_announce_frame(),
                host.build_connect_frame(),
                host.build_capability_announce_frame(),
            ]
        )

        replies = gateway.trigger_agent_initiative(
            source_device_id="desktop-dev-1",
            initiative_request={
                "action_capability": "runtime.status",
                "action_payload": {},
                "reason": "runtime_health_check",
                "target_device_hint": "host-edge-1",
            },
            observed_at="2026-06-21T10:10:00Z",
        )

        self.assertEqual(replies[-1]["type"], "action_request")
        self.assertEqual(replies[-1]["device_id"], "host-edge-1")
        self.assertEqual(replies[-1]["action"]["capability"], "runtime.status")
        self.assertEqual(
            gateway.state.interventions[-1]["proposal"]["source"],
            "agent_initiative",
        )

    async def test_normal_path_suppresses_repeated_intervention_during_cooldown(self) -> None:
        state = RuntimeState()
        state.record_intervention(
            {
                "target_device_id": "desktop-dev-1",
                "action_capability": "notification.show",
                "decision": "allow",
                "reason": "context_clear",
                "recorded_at": "2026-06-19T10:30:00Z",
            }
        )
        gateway = RuntimeGateway(shared_token="dev-token", state=state, persist_state=False)

        replies = await gateway.handle_test_frames(
            [
                {
                    "type": "connect",
                    "device": {
                        "device_id": "desktop-dev-1",
                        "device_type": "desktop-cli",
                    },
                    "auth": {"token": "dev-token"},
                },
                {
                    "type": "capability_announce",
                    "device_id": "desktop-dev-1",
                    "capabilities": ["text.input", "notification.show"],
                },
                {
                    "type": "event_push",
                    "device_id": "desktop-dev-1",
                    "capability": "text.input",
                    "payload": {
                        "text": "repeat too soon",
                        "observed_at": "2026-06-19T10:32:00Z",
                    },
                },
            ]
        )

        self.assertEqual(replies[-1]["type"], "event_ack")
        self.assertEqual(len([reply for reply in replies if reply["type"] == "action_request"]), 0)
        self.assertEqual(gateway.state.interventions[-1]["decision"], "suppress")
        self.assertEqual(gateway.state.interventions[-1]["reason"], "cooldown_active")

    async def test_records_host_observations_with_runtime_provenance(self) -> None:
        gateway = RuntimeGateway(shared_token="dev-token", persist_state=False)
        client = SessionClient(
            device_id="host-edge-1",
            device_type="server",
            token="dev-token",
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

        replies = await gateway.handle_test_frames(
            [
                client.build_connect_frame(),
                client.build_capability_announce_frame(),
                client.build_observation_event(
                    capability="runtime.health",
                    observations=[
                        {
                            "name": "runtime.health_state",
                            "value": "healthy",
                            "observed_at": "2026-06-19T09:30:00Z",
                            "confidence": 0.9,
                        }
                    ],
                ),
            ]
        )

        self.assertEqual(replies[-1]["type"], "event_ack")
        self.assertEqual(gateway.state.events[-1]["capability"], "runtime.health")
        self.assertEqual(gateway.state.observations[-1].name, "runtime.health_state")
        self.assertEqual(
            gateway.state.observations[-1].source_device_id,
            "host-edge-1",
        )
        self.assertEqual(
            gateway.state.observations[-1].source_capability,
            "runtime.health",
        )
        self.assertTrue(gateway.state.observations[-1].source_event_id)


if __name__ == "__main__":
    unittest.main()
