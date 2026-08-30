"""Long-lived, governed session for a Proxy Interaction Edge.

The daemon deliberately treats ESP-KVM only as an adapter.  An associated
WLAN is not readiness: every recovery cycle reprobes the actual REST/video/HID
surface and only announces actions that are currently safe to execute.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import deque
from datetime import UTC
from datetime import datetime
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosed

from device_edge.proxy.adapter import EspKvmHttpAdapter
from device_edge.proxy.edge import ProxyInteractionEdge
from device_edge.shared.identity import load_or_create_identity


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ProxyEdgeDaemon:
    """Runs one Proxy Edge identity over the public Gateway session."""

    def __init__(self, edge: ProxyInteractionEdge, *, probe_interval_s: float = 5.0) -> None:
        if probe_interval_s <= 0:
            raise ValueError("probe_interval_s must be positive.")
        self.edge = edge
        self.probe_interval_s = probe_interval_s
        self._pairing_completed = False

    async def _send(self, websocket, frame: dict) -> None:
        await websocket.send(json.dumps(frame))

    async def _recv(self, websocket) -> dict:
        return json.loads(await websocket.recv())

    async def _recv_expected(self, websocket, expected_type: str, pending: deque[dict]) -> dict:
        while True:
            frame = await self._recv(websocket)
            if frame.get("type") == expected_type:
                return frame
            pending.append(frame)
            if frame.get("type") in {"action_request", "error"}:
                return frame

    async def _send_observation(self, websocket, frame: dict, pending: deque[dict]) -> None:
        await self._send(websocket, frame)
        await self._recv_expected(websocket, "event_ack", pending)

    async def _publish_state(
        self,
        websocket,
        pending: deque[dict],
        *,
        observed_at: str,
        include_screen_features: bool,
        action_request_id: str | None = None,
    ) -> None:
        self.edge.refresh_attachment(observed_at)
        await self._send(websocket, self.edge.build_capability_announce_frame())
        await self._send_observation(
            websocket,
            self.edge.build_attachment_observation_frame(),
            pending,
        )
        try:
            base_frame = self.edge.build_screen_base_observation_frame(
                action_request_id=action_request_id,
            )
        except Exception:
            # Keep the existing failure boundary: adapter errors become a later
            # attachment downgrade, never an unstructured public exception.
            base_frame = None
        if base_frame is not None:
            await self._send_observation(websocket, base_frame, pending)
        if include_screen_features:
            try:
                frame = self.edge.build_screen_feature_observation_frame(
                    action_request_id=action_request_id,
                )
            except Exception:
                # The next probe reports the adapter failure as unavailable; raw
                # adapter exceptions never cross the public Edge boundary.
                return
            if frame is not None:
                await self._send_observation(websocket, frame, pending)

    async def _bootstrap(self, websocket, pairing_code: str | None) -> None:
        connect = (
            self.edge.client.build_pairing_connect_frame(pairing_code)
            if pairing_code is not None
            else self.edge.build_connect_frame()
        )
        await self._send(websocket, connect)
        challenge = await self._recv(websocket)
        if challenge.get("type") == "error":
            raise RuntimeError(challenge.get("message", "Runtime rejected proxy pairing."))
        await self._send(websocket, self.edge.client.build_auth_proof_frame(challenge))
        connect_ok = await self._recv(websocket)
        if connect_ok.get("type") != "connect_ok":
            raise RuntimeError("Runtime rejected Proxy Edge authentication.")
        if pairing_code is not None:
            self._pairing_completed = True

    async def run_websocket_session(
        self,
        url: str,
        *,
        pairing_code: str | None = None,
        max_action_requests: int | None = None,
        max_idle_cycles: int | None = None,
    ) -> list[dict]:
        pending: deque[dict] = deque()
        action_results: list[dict] = []
        idle_cycles = 0
        async with websockets.connect(url) as websocket:
            await self._bootstrap(websocket, pairing_code)
            await self._publish_state(
                websocket,
                pending,
                observed_at=utc_now(),
                include_screen_features=True,
            )
            while max_action_requests is None or len(action_results) < max_action_requests:
                try:
                    frame = pending.popleft() if pending else await asyncio.wait_for(
                        self._recv(websocket), timeout=self.probe_interval_s
                    )
                except asyncio.TimeoutError:
                    await self._publish_state(
                        websocket,
                        pending,
                        observed_at=utc_now(),
                        include_screen_features=True,
                    )
                    idle_cycles += 1
                    if max_idle_cycles is not None and idle_cycles >= max_idle_cycles:
                        break
                    continue
                if frame.get("type") == "understanding_update":
                    try:
                        self.edge.handle_understanding_update(frame)
                    except ValueError:
                        # A stale or incompatible Runtime understanding must
                        # never be treated as an input authorization.
                        pass
                    continue
                if frame.get("type") != "action_request":
                    continue
                idle_cycles = 0
                result = self.edge.handle_action_request(frame)
                await self._send(websocket, result)
                action_results.append(result)
                await self._publish_state(
                    websocket,
                    pending,
                    observed_at=utc_now(),
                    include_screen_features=result.get("result", {}).get("status") == "ok",
                    action_request_id=frame.get("request_id"),
                )
        return action_results

    async def run_forever(
        self,
        url: str,
        *,
        pairing_code: str | None = None,
        reconnect_delay_s: float = 2.0,
        reconnect_max_delay_s: float = 30.0,
    ) -> None:
        if reconnect_delay_s <= 0 or reconnect_max_delay_s < reconnect_delay_s:
            raise ValueError("Invalid reconnect delay configuration.")
        failures = 0
        first_pairing_code = pairing_code
        while True:
            try:
                await self.run_websocket_session(url, pairing_code=first_pairing_code)
                first_pairing_code = None
                failures = 0
            except (ConnectionClosed, OSError, RuntimeError):
                if self._pairing_completed:
                    first_pairing_code = None
                delay = min(reconnect_delay_s * (2**failures), reconnect_max_delay_s)
                await asyncio.sleep(delay)
                failures += 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the OpenHalo Proxy Edge development harness."
    )
    parser.add_argument("--url", required=True, help="Public Runtime WebSocket URL.")
    parser.add_argument("--adapter-url", required=True, help="ESP-KVM adapter HTTP URL.")
    parser.add_argument("--device-id", default="proxy-edge-1")
    parser.add_argument("--display-name", default="Proxy Interaction Edge")
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--surface-id", required=True)
    parser.add_argument("--target-class", required=True, choices=("desktop", "laptop", "server", "tablet", "phone"))
    parser.add_argument("--adapter-id", default="esp-kvm-1")
    parser.add_argument("--adapter-username")
    parser.add_argument("--adapter-password-env", help="Environment variable holding the ESP-KVM password.")
    parser.add_argument("--pairing-code", help="One-time Runtime pairing code; omit after pairing.")
    parser.add_argument("--home", type=Path, help="Directory for this Edge's persistent P-256 identity.")
    parser.add_argument("--probe-interval", type=float, default=5.0)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    password = (
        os.environ.get(args.adapter_password_env)
        if args.adapter_password_env is not None
        else None
    )
    home = args.home or Path(os.environ.get("OPENHALO_HOME", Path.home() / ".openhalo"))
    adapter = EspKvmHttpAdapter(
        args.adapter_id,
        args.adapter_url,
        username=args.adapter_username,
        password=password,
        evidence_owner_id=args.device_id,
    )
    edge = ProxyInteractionEdge(
        device_id=args.device_id,
        audience=args.url,
        target_id=args.target_id,
        surface_id=args.surface_id,
        target_class=args.target_class,
        adapter=adapter,
        observed_at=utc_now(),
        identity=load_or_create_identity(home, args.device_id),
        display_name=args.display_name,
    )
    asyncio.run(
        ProxyEdgeDaemon(edge, probe_interval_s=args.probe_interval).run_forever(
            args.url,
            pairing_code=args.pairing_code,
        )
    )


if __name__ == "__main__":
    main()
