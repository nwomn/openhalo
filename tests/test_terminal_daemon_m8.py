import asyncio
import io
import json
import unittest

from device_edge.cli.terminal_daemon import TerminalEdgeDaemon
from device_edge.cli.terminal_daemon import build_terminal_daemon_parser


class TerminalEdgeDaemonTests(unittest.TestCase):
    def test_parser_accepts_optional_live_startup_timestamp_override(self) -> None:
        parser = build_terminal_daemon_parser()

        args = parser.parse_args(
            [
                "--url",
                "ws://127.0.0.1:8765",
            ]
        )

        self.assertEqual(args.url, "ws://127.0.0.1:8765")
        self.assertIsNone(args.startup_observed_at)

    def test_parser_accepts_optional_first_stdin_timestamp_override(self) -> None:
        parser = build_terminal_daemon_parser()

        args = parser.parse_args(
            [
                "--url",
                "ws://127.0.0.1:8765",
                "--stdin-observed-at",
                "2026-06-22T10:00:00Z",
            ]
        )

        self.assertEqual(args.stdin_observed_at, "2026-06-22T10:00:00Z")

    def test_builds_bootstrap_frames_for_terminal_edge(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )

        bootstrap_frames = daemon.build_bootstrap_frames()

        self.assertEqual(bootstrap_frames[0]["type"], "connect")
        self.assertEqual(bootstrap_frames[1]["type"], "capability_announce")
        self.assertEqual(
            bootstrap_frames[1]["capabilities"],
            ["text.input", "notification.show", "terminal.context"],
        )

    def test_builds_terminal_activity_observation_frame(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )

        frame = daemon.build_terminal_activity_frame(
            activity_state="active",
            observed_at="2026-06-22T10:10:00Z",
        )

        self.assertEqual(frame["type"], "event_push")
        self.assertEqual(frame["capability"], "terminal.context")
        self.assertEqual(
            frame["payload"]["observations"][0]["name"],
            "terminal.activity_state",
        )
        self.assertEqual(
            frame["payload"]["observations"][0]["value"],
            "active",
        )

    def test_builds_pull_text_event_after_marking_terminal_active(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )

        frames = daemon.build_user_input_frames(
            text="hello runtime",
            observed_at="2026-06-22T10:10:00Z",
        )

        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0]["capability"], "terminal.context")
        self.assertEqual(
            frames[0]["payload"]["observations"][0]["value"],
            "active",
        )
        self.assertEqual(frames[1]["capability"], "text.input")
        self.assertEqual(frames[1]["payload"]["text"], "hello runtime")


class TerminalEdgeAsyncSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_daemon_session_reads_live_terminal_input_from_stdin(
        self,
    ) -> None:
        observed_at_values = iter(
            [
                "2026-06-22T10:09:00Z",
                "2026-06-22T10:10:00Z",
            ]
        )
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            input_stream=io.StringIO("\nhello runtime\n"),
            timestamp_provider=lambda: next(observed_at_values),
        )
        sent_frames: list[dict] = []
        class FakeWebSocket:
            def __init__(self) -> None:
                self.recv_count = 0

            async def send(self, payload: str) -> None:
                sent_frames.append(json.loads(payload))

            async def recv(self) -> str:
                self.recv_count += 1
                if self.recv_count == 1:
                    return json.dumps({"type": "connect_ok"})
                if self.recv_count in {2, 3, 4}:
                    return json.dumps({"type": "event_ack"})
                while not any(
                    frame.get("capability") == "text.input" for frame in sent_frames
                ):
                    await asyncio.sleep(0)
                return json.dumps(
                    {
                        "type": "action_request",
                        "device_id": "terminal-edge-1",
                        "action": {
                            "capability": "notification.show",
                            "payload": {"message": "Runtime heard: hello runtime"},
                        },
                    }
                )

        results = await daemon.run_scripted_session(
            websocket=FakeWebSocket(),
            scripted_inputs=[],
            startup_observed_at=None,
            idle_after_inputs=True,
            enable_live_input=True,
            max_action_requests=1,
        )

        self.assertEqual(len(results), 1)
        activity_frames = [
            frame
            for frame in sent_frames
            if frame.get("capability") == "terminal.context"
        ]
        text_frames = [
            frame for frame in sent_frames if frame.get("capability") == "text.input"
        ]

        self.assertGreaterEqual(len(activity_frames), 2)
        self.assertEqual(
            activity_frames[0]["payload"]["observations"][0]["observed_at"],
            "2026-06-22T10:09:00Z",
        )
        self.assertEqual(
            activity_frames[-1]["payload"]["observations"][0]["observed_at"],
            "2026-06-22T10:10:00Z",
        )
        self.assertEqual(len(text_frames), 1)
        self.assertEqual(text_frames[0]["payload"]["text"], "hello runtime")
        self.assertEqual(
            text_frames[0]["payload"]["observed_at"],
            "2026-06-22T10:10:00Z",
        )

    async def test_daemon_session_reads_multiple_live_terminal_inputs_from_stdin(
        self,
    ) -> None:
        observed_at_values = iter(
            [
                "2026-06-22T10:09:00Z",
                "2026-06-22T10:10:00Z",
                "2026-06-22T10:11:00Z",
            ]
        )
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            input_stream=io.StringIO("hello?\nstatus?\n"),
            timestamp_provider=lambda: next(observed_at_values),
        )
        sent_frames: list[dict] = []
        recv_queue: list[dict] = [
            {"type": "connect_ok"},
            {"type": "event_ack"},
        ]

        class FakeWebSocket:
            async def send(self, payload: str) -> None:
                frame = json.loads(payload)
                sent_frames.append(frame)
                if frame.get("capability") == "terminal.context":
                    recv_queue.append({"type": "event_ack"})
                if frame.get("capability") == "text.input":
                    recv_queue.append({"type": "event_ack"})
                    recv_queue.append(
                        {
                            "type": "action_request",
                            "device_id": "terminal-edge-1",
                            "action": {
                                "capability": "notification.show",
                                "payload": {
                                    "message": f"Runtime heard: {frame['payload']['text']}"
                                },
                            },
                        }
                    )

            async def recv(self) -> str:
                while not recv_queue:
                    await asyncio.sleep(0)
                return json.dumps(recv_queue.pop(0))

        results = await daemon.run_scripted_session(
            websocket=FakeWebSocket(),
            scripted_inputs=[],
            startup_observed_at=None,
            idle_after_inputs=True,
            enable_live_input=True,
            max_action_requests=2,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(
            [result["result"]["details"]["message"] for result in results],
            ["Runtime heard: hello?", "Runtime heard: status?"],
        )
        text_frames = [
            frame for frame in sent_frames if frame.get("capability") == "text.input"
        ]
        self.assertEqual(
            [frame["payload"]["text"] for frame in text_frames],
            ["hello?", "status?"],
        )

    async def test_daemon_session_sends_scripted_pull_input_and_terminal_activity(
        self,
    ) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )
        sent_frames: list[dict] = []
        recv_frames = iter(
            [
                {"type": "connect_ok"},
                {"type": "event_ack"},
                {"type": "event_ack"},
                {"type": "event_ack"},
                {
                    "type": "action_request",
                    "device_id": "terminal-edge-1",
                    "action": {
                        "capability": "notification.show",
                        "payload": {"message": "Runtime heard: hello runtime"},
                    },
                },
            ]
        )

        class FakeWebSocket:
            async def send(self, payload: str) -> None:
                sent_frames.append(json.loads(payload))

            async def recv(self) -> str:
                return json.dumps(next(recv_frames))

        results = await daemon.run_scripted_session(
            websocket=FakeWebSocket(),
            scripted_inputs=[
                {
                    "text": "hello runtime",
                    "observed_at": "2026-06-22T10:10:00Z",
                }
            ],
            startup_observed_at="2026-06-22T10:09:00Z",
            idle_after_inputs=True,
            max_action_requests=1,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(sent_frames[2]["capability"], "terminal.context")
        self.assertEqual(sent_frames[3]["capability"], "terminal.context")
        self.assertEqual(sent_frames[4]["capability"], "text.input")
        self.assertEqual(sent_frames[4]["payload"]["text"], "hello runtime")

    async def test_daemon_session_handles_runtime_push_and_returns_action_result(
        self,
    ) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
        )
        sent_frames: list[dict] = []
        recv_frames = iter(
            [
                {"type": "connect_ok"},
                {"type": "event_ack"},
                {
                    "type": "action_request",
                    "device_id": "terminal-edge-1",
                    "action": {
                        "capability": "notification.show",
                        "payload": {"message": "runtime push"},
                    },
                },
            ]
        )

        class FakeWebSocket:
            async def send(self, payload: str) -> None:
                sent_frames.append(json.loads(payload))

            async def recv(self) -> str:
                return json.dumps(next(recv_frames))

        results = await daemon.run_scripted_session(
            websocket=FakeWebSocket(),
            scripted_inputs=[],
            startup_observed_at="2026-06-22T10:10:00Z",
            idle_after_inputs=True,
            max_action_requests=1,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["result"]["status"], "ok")
        self.assertEqual(
            results[0]["result"]["details"]["delivered_via"],
            "terminal.stdout",
        )
        self.assertEqual(sent_frames[0]["type"], "connect")
        self.assertEqual(sent_frames[1]["type"], "capability_announce")
        self.assertEqual(sent_frames[2]["capability"], "terminal.context")
        self.assertEqual(sent_frames[-1]["type"], "action_result")

    async def test_daemon_session_emits_idle_activity_after_timeout(
        self,
    ) -> None:
        observed_at_values = iter(
            [
                "2026-06-22T10:10:00Z",
                "2026-06-22T10:11:00Z",
            ]
        )
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            token="dev-token",
            timestamp_provider=lambda: next(observed_at_values),
        )
        sent_frames: list[dict] = []

        class FakeWebSocket:
            def __init__(self) -> None:
                self.recv_count = 0

            async def send(self, payload: str) -> None:
                sent_frames.append(json.loads(payload))

            async def recv(self) -> str:
                self.recv_count += 1
                if self.recv_count == 1:
                    return json.dumps({"type": "connect_ok"})
                if self.recv_count == 2:
                    return json.dumps({"type": "event_ack"})
                if self.recv_count == 3:
                    await asyncio.sleep(0.05)
                    raise RuntimeError("StopIteration")
                return json.dumps({"type": "event_ack"})

        results = await daemon.run_scripted_session(
            websocket=FakeWebSocket(),
            scripted_inputs=[],
            startup_observed_at=None,
            idle_after_inputs=True,
            idle_timeout_s=0.01,
            idle_observed_at=None,
            max_idle_cycles=1,
        )

        self.assertEqual(results, [])
        self.assertEqual(sent_frames[-1]["capability"], "terminal.context")
        self.assertEqual(
            sent_frames[-1]["payload"]["observations"][0]["value"],
            "idle",
        )
        self.assertEqual(
            sent_frames[-1]["payload"]["observations"][0]["observed_at"],
            "2026-06-22T10:11:00Z",
        )


if __name__ == "__main__":
    unittest.main()
