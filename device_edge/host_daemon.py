"""Independent host-edge daemon helpers for the first host slice."""

from __future__ import annotations

import json

import websockets

from device_edge.host_observers import build_host_metric_observations
from device_edge.host_observers import build_runtime_health_observations
from device_edge.session_client import SessionClient


class HostEdgeDaemon:
    def __init__(
        self,
        device_id: str,
        token: str,
        runtime_control_adapter,
        host_metrics_provider,
        runtime_health_provider,
    ) -> None:
        self.runtime_control_adapter = runtime_control_adapter
        self.host_metrics_provider = host_metrics_provider
        self.runtime_health_provider = runtime_health_provider
        self.client = SessionClient(
            device_id=device_id,
            device_type="server",
            token=token,
            capabilities=["host.metrics", "runtime.health", "runtime.control"],
        )

    def build_bootstrap_frames(self) -> list[dict]:
        return [
            self.client.build_connect_frame(),
            self.client.build_capability_announce_frame(),
        ]

    def build_observation_frames(self, observed_at: str) -> list[dict]:
        return [
            self.client.build_observation_event(
                capability="host.metrics",
                observations=build_host_metric_observations(
                    self.host_metrics_provider(),
                    observed_at=observed_at,
                ),
            ),
            self.client.build_observation_event(
                capability="runtime.health",
                observations=build_runtime_health_observations(
                    self.runtime_health_provider(),
                    observed_at=observed_at,
                ),
            ),
        ]

    def handle_action_request(self, frame: dict) -> dict:
        result = self.runtime_control_adapter.execute(frame["action"])
        return {
            "type": "action_result",
            "device_id": self.client.device_id,
            "result": result,
        }

    async def run_websocket_control_session(
        self,
        url: str,
        observed_at: str,
        ready_event=None,
        follow_up_observed_at: str | None = None,
    ) -> dict:
        async with websockets.connect(url) as websocket:
            for frame in self.build_bootstrap_frames():
                await websocket.send(json.dumps(frame))

            if ready_event is not None:
                ready_event.set()

            await websocket.recv()

            for frame in self.build_observation_frames(observed_at=observed_at):
                await websocket.send(json.dumps(frame))
                await websocket.recv()

            action_request = json.loads(await websocket.recv())
            action_result = self.handle_action_request(action_request)
            await websocket.send(json.dumps(action_result))

            if follow_up_observed_at is not None:
                follow_up_frames = self.build_observation_frames(
                    observed_at=follow_up_observed_at
                )
                for frame in follow_up_frames:
                    if frame["capability"] == "runtime.health":
                        await websocket.send(json.dumps(frame))
                        await websocket.recv()
                        break

            return action_result
