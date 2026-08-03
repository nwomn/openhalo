"""Small JSONL client for the locally hosted Codex App Server."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from typing import Any, Protocol


class JsonlTransport(Protocol):
    async def send(self, message: dict) -> None: ...

    async def recv(self) -> str | None: ...

    async def close(self) -> None: ...


class SubprocessJsonlTransport:
    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: str | None = None,
        environment: dict[str, str] | None = None,
    ) -> None:
        self.command = tuple(command)
        self.cwd = cwd
        self.environment = environment
        self.process: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task | None = None

    async def start(self) -> None:
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            cwd=self.cwd,
            env=self.environment,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def send(self, message: dict) -> None:
        if self.process is None or self.process.stdin is None:
            raise ConnectionError("Codex App Server is not running.")
        self.process.stdin.write((json.dumps(message, separators=(",", ":")) + "\n").encode())
        await self.process.stdin.drain()

    async def recv(self) -> str | None:
        if self.process is None or self.process.stdout is None:
            raise ConnectionError("Codex App Server is not running.")
        line = await self.process.stdout.readline()
        if not line:
            return None
        return line.decode(errors="replace").rstrip("\r\n")

    async def close(self) -> None:
        process = self.process
        self.process = None
        if process is not None:
            if process.returncode is None:
                process.terminate()
                with suppress(asyncio.TimeoutError, ProcessLookupError):
                    await asyncio.wait_for(process.wait(), timeout=1.0)
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                with suppress(Exception):
                    await process.wait()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._stderr_task
            self._stderr_task = None

    async def _drain_stderr(self) -> None:
        process = self.process
        if process is None or process.stderr is None:
            return
        while await process.stderr.readline():
            pass


NotificationHandler = Callable[[dict], Any]
ServerRequestHandler = Callable[[dict], Awaitable[dict] | dict]


class CodexAppServerClient:
    def __init__(
        self,
        *,
        transport: JsonlTransport | None = None,
        command: Sequence[str] = ("codex", "app-server", "--listen", "stdio://"),
        cwd: str | None = None,
        environment: dict[str, str] | None = None,
        notification_handler: NotificationHandler | None = None,
        server_request_handler: ServerRequestHandler | None = None,
        request_timeout_s: float = 30.0,
    ) -> None:
        self.transport = transport or SubprocessJsonlTransport(
            command,
            cwd=cwd,
            environment=environment,
        )
        self.notification_handler = notification_handler
        self.server_request_handler = server_request_handler
        self.request_timeout_s = request_timeout_s
        self.state = "disconnected"
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._write_lock = asyncio.Lock()
        self._closed = False

    async def start(self) -> None:
        if self.state == "ready":
            return
        self._closed = False
        self.state = "connecting"
        start = getattr(self.transport, "start", None)
        if start is not None:
            await start()
        self._reader_task = asyncio.create_task(self._reader_loop())
        try:
            await self.request(
                "initialize",
                {
                    "clientInfo": {
                        "name": "openhalo_terminal_edge",
                        "title": "OpenHalo Terminal Edge",
                        "version": "0.1.0",
                    }
                },
            )
            await self.notify("initialized", {})
            self.state = "ready"
        except Exception:
            self.state = "disconnected"
            await self.close()
            raise

    async def close(self) -> None:
        self._closed = True
        reader_task = self._reader_task
        self._reader_task = None
        if reader_task is not None and reader_task is not asyncio.current_task():
            reader_task.cancel()
            with suppress(asyncio.CancelledError):
                await reader_task
        await self.transport.close()
        self._fail_pending(ConnectionError("Codex App Server connection closed."))
        self.state = "disconnected"

    async def request(self, method: str, params: dict) -> dict:
        if self._closed:
            raise ConnectionError("Codex App Server connection is closed.")
        self._request_id += 1
        request_id = self._request_id
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[request_id] = future
        try:
            await self._send({"id": request_id, "method": method, "params": params})
            result = await asyncio.wait_for(future, timeout=self.request_timeout_s)
        except Exception:
            self._pending.pop(request_id, None)
            raise
        return result

    async def notify(self, method: str, params: dict) -> None:
        if self._closed:
            raise ConnectionError("Codex App Server connection is closed.")
        await self._send({"method": method, "params": params})

    async def start_thread(self, *, cwd: str | None = None) -> dict:
        params = {"serviceName": "openhalo"}
        if cwd is not None:
            params["cwd"] = cwd
        result = await self.request("thread/start", params)
        thread = result.get("thread")
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
            raise ValueError("Codex App Server returned an invalid thread.")
        return thread

    async def start_turn(self, *, thread_id: str, text: str, cwd: str | None = None) -> dict:
        params: dict[str, Any] = {
            "threadId": thread_id,
            "input": [{"type": "text", "text": text}],
        }
        if cwd is not None:
            params["cwd"] = cwd
        result = await self.request("turn/start", params)
        turn = result.get("turn")
        if not isinstance(turn, dict) or not isinstance(turn.get("id"), str):
            raise ValueError("Codex App Server returned an invalid turn.")
        return turn

    async def steer(
        self,
        *,
        thread_id: str,
        expected_turn_id: str,
        text: str,
    ) -> str:
        result = await self.request(
            "turn/steer",
            {
                "threadId": thread_id,
                "input": [{"type": "text", "text": text}],
                "expectedTurnId": expected_turn_id,
            },
        )
        turn_id = result.get("turnId")
        if not isinstance(turn_id, str):
            raise ValueError("Codex App Server returned an invalid steer result.")
        return turn_id

    async def _send(self, message: dict) -> None:
        async with self._write_lock:
            await self.transport.send(message)

    async def _reader_loop(self) -> None:
        failure: BaseException | None = None
        try:
            while not self._closed:
                raw_message = await self.transport.recv()
                if raw_message is None:
                    raise ConnectionError("Codex App Server closed the connection.")
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError as exc:
                    raise ValueError("Codex App Server returned invalid JSON.") from exc
                if not isinstance(message, dict):
                    raise ValueError("Codex App Server returned a non-object JSON message.")
                if "id" in message and ("result" in message or "error" in message):
                    self._resolve_response(message)
                    continue
                if "id" in message and isinstance(message.get("method"), str):
                    asyncio.create_task(self._handle_server_request(message))
                    continue
                await self._handle_notification(message)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            failure = exc
        finally:
            if failure is not None and not self._closed:
                self.state = "disconnected"
                self._fail_pending(
                    failure if isinstance(failure, Exception) else ConnectionError(str(failure))
                )

    def _resolve_response(self, message: dict) -> None:
        request_id = message.get("id")
        if not isinstance(request_id, int):
            return
        future = self._pending.pop(request_id, None)
        if future is None or future.done():
            return
        if "error" in message:
            error = message.get("error")
            if isinstance(error, dict):
                detail = error.get("message", "Codex App Server request failed.")
            else:
                detail = "Codex App Server request failed."
            future.set_exception(RuntimeError(str(detail)))
            return
        result = message.get("result")
        future.set_result(result if isinstance(result, dict) else {})

    async def _handle_notification(self, message: dict) -> None:
        if self.notification_handler is None:
            return
        result = self.notification_handler(message)
        if inspect.isawaitable(result):
            await result

    async def _handle_server_request(self, message: dict) -> None:
        if self.server_request_handler is None:
            await self._send(
                {
                    "id": message.get("id"),
                    "error": {
                        "code": -32601,
                        "message": "OpenHalo does not support this App Server request.",
                    },
                }
            )
            return
        try:
            result = self.server_request_handler(message)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, dict):
                raise ValueError("App Server request handler returned a non-object result.")
        except Exception as exc:
            await self._send(
                {
                    "id": message.get("id"),
                    "error": {"code": -32000, "message": str(exc)},
                }
            )
            return
        await self._send({"id": message.get("id"), "result": result})

    def _fail_pending(self, error: Exception) -> None:
        pending = tuple(self._pending.values())
        self._pending.clear()
        for future in pending:
            if not future.done():
                future.set_exception(error)


__all__ = [
    "CodexAppServerClient",
    "JsonlTransport",
    "SubprocessJsonlTransport",
]
