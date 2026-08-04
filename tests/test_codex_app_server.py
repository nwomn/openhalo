from __future__ import annotations

import asyncio
import json
import unittest

from device_edge.cli.codex_app_server import CodexAppServerClient


class FakeJsonlTransport:
    def __init__(self) -> None:
        self.incoming: asyncio.Queue[str | None] = asyncio.Queue()
        self.sent: list[dict] = []
        self.closed = False

    async def send(self, message: dict) -> None:
        self.sent.append(message)

    async def recv(self) -> str | None:
        return await self.incoming.get()

    async def close(self) -> None:
        self.closed = True
        await self.incoming.put(None)

    async def push(self, message: dict) -> None:
        await self.incoming.put(json.dumps(message))


class CodexAppServerClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_initializes_jsonl_connection_and_sends_initialized_notification(self) -> None:
        transport = FakeJsonlTransport()
        client = CodexAppServerClient(transport=transport)

        start_task = asyncio.create_task(client.start())
        await asyncio.sleep(0)

        self.assertEqual(transport.sent[0]["method"], "initialize")
        self.assertEqual(
            transport.sent[0]["params"]["clientInfo"]["name"],
            "openhalo_terminal_edge",
        )
        await transport.push({"id": transport.sent[0]["id"], "result": {"serverInfo": {}}})
        await start_task

        self.assertEqual(transport.sent[1], {"method": "initialized", "params": {}})
        self.assertEqual(client.state, "ready")

        await client.close()

    async def test_correlates_thread_request_and_forwards_notifications(self) -> None:
        transport = FakeJsonlTransport()
        notifications: list[dict] = []
        client = CodexAppServerClient(
            transport=transport,
            notification_handler=notifications.append,
        )

        start_task = asyncio.create_task(client.start())
        await asyncio.sleep(0)
        initialize_id = transport.sent[0]["id"]
        await transport.push({"id": initialize_id, "result": {}})
        await start_task

        thread_task = asyncio.create_task(client.start_thread(cwd="/workspace"))
        await asyncio.sleep(0)
        request = transport.sent[2]
        self.assertEqual(request["method"], "thread/start")
        self.assertEqual(request["params"]["cwd"], "/workspace")
        await transport.push(
            {
                "method": "thread/started",
                "params": {"thread": {"id": "thread-1"}},
            }
        )
        await transport.push(
            {"id": request["id"], "result": {"thread": {"id": "thread-1"}}}
        )
        self.assertEqual((await thread_task)["id"], "thread-1")
        self.assertEqual(notifications[0]["method"], "thread/started")

        await client.close()

    async def test_responds_to_server_request_with_handler_result(self) -> None:
        transport = FakeJsonlTransport()
        requests: list[dict] = []

        async def handle_request(message: dict) -> dict:
            requests.append(message)
            return {"decision": "accept"}

        client = CodexAppServerClient(
            transport=transport,
            server_request_handler=handle_request,
        )
        start_task = asyncio.create_task(client.start())
        await asyncio.sleep(0)
        await transport.push({"id": transport.sent[0]["id"], "result": {}})
        await start_task

        await transport.push(
            {
                "id": 77,
                "method": "item/fileChange/requestApproval",
                "params": {"threadId": "thread-1", "turnId": "turn-1"},
            }
        )
        for _ in range(10):
            if any(message.get("id") == 77 for message in transport.sent):
                break
            await asyncio.sleep(0)

        response = next(message for message in transport.sent if message.get("id") == 77)
        self.assertEqual(response, {"id": 77, "result": {"decision": "accept"}})
        self.assertEqual(requests[0]["method"], "item/fileChange/requestApproval")

        await client.close()

    async def test_reports_transport_failure_and_fails_pending_request(self) -> None:
        transport = FakeJsonlTransport()
        client = CodexAppServerClient(transport=transport)
        start_task = asyncio.create_task(client.start())
        await asyncio.sleep(0)
        await transport.push({"id": transport.sent[0]["id"], "result": {}})
        await start_task

        request_task = asyncio.create_task(client.request("thread/list", {}))
        await asyncio.sleep(0)
        await transport.incoming.put(None)

        with self.assertRaises(ConnectionError):
            await request_task
        self.assertEqual(client.state, "disconnected")

    async def test_interrupt_targets_exact_thread_and_turn(self) -> None:
        transport = FakeJsonlTransport()
        client = CodexAppServerClient(transport=transport)
        start_task = asyncio.create_task(client.start())
        await asyncio.sleep(0)
        await transport.push({"id": transport.sent[0]["id"], "result": {}})
        await start_task

        interrupt_task = asyncio.create_task(
            client.interrupt(thread_id="thread-7", turn_id="turn-9")
        )
        await asyncio.sleep(0)
        request = transport.sent[2]
        self.assertEqual(request["method"], "turn/interrupt")
        self.assertEqual(
            request["params"], {"threadId": "thread-7", "turnId": "turn-9"}
        )
        await transport.push({"id": request["id"], "result": {}})
        await interrupt_task
        await client.close()


if __name__ == "__main__":
    unittest.main()
