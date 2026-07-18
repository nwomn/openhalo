"""Runtime-owned lifecycle supervision for the colocated Host Edge."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from random import random


class ManagedHostEdgeSupervisor:
    def __init__(
        self,
        *,
        daemon,
        url: str,
        status_writer: Callable[[dict], None],
        idle_timeout_s: float = 30.0,
        initial_delay_s: float = 0.5,
        backoff_multiplier: float = 2.0,
        max_delay_s: float = 30.0,
        max_jitter_s: float = 0.25,
        jitter_source: Callable[[], float] | None = None,
        sleep=asyncio.sleep,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.daemon = daemon
        self.url = url
        self.status_writer = status_writer
        self.idle_timeout_s = idle_timeout_s
        self.initial_delay_s = initial_delay_s
        self.backoff_multiplier = backoff_multiplier
        self.max_delay_s = max_delay_s
        self.max_jitter_s = max_jitter_s
        self.jitter_source = jitter_source
        self.sleep = sleep
        self.now = now or _utc_now
        self.retry_attempt = 0
        self.latest_failure_class: str | None = None
        self._task: asyncio.Task | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._stop_requested = False

    @property
    def task(self) -> asyncio.Task | None:
        return self._task

    async def start(self) -> None:
        async with self._lifecycle_lock:
            if self._task is not None and not self._task.done():
                return
            self._stop_requested = False
            self.retry_attempt = 0
            self._record_status("starting")
            self._task = asyncio.create_task(
                self._run(),
                name="openhalo-managed-host-edge",
            )

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            self._stop_requested = True
            task = self._task
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if self._task is task:
                self._task = None
            self._record_status("disconnected")

    async def _run(self) -> None:
        while not self._stop_requested:
            try:
                await self.daemon.run_websocket_daemon_session(
                    url=self.url,
                    observation_schedule=[],
                    observation_timestamp_provider=_utc_now,
                    idle_timeout_s=self.idle_timeout_s,
                    on_connected=self._on_connected,
                )
                if self._stop_requested:
                    return
                raise ConnectionError("host edge session ended")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._stop_requested:
                    return
                self.retry_attempt += 1
                self.latest_failure_class = type(exc).__name__
                delay = self._retry_delay()
                self._record_status(
                    "retrying",
                    next_retry_delay_s=delay,
                )
                await self.sleep(delay)

    def _on_connected(self) -> None:
        self.retry_attempt = 0
        self._record_status("connected")

    def _retry_delay(self) -> float:
        exponential_delay = min(
            self.initial_delay_s
            * self.backoff_multiplier ** max(self.retry_attempt - 1, 0),
            self.max_delay_s,
        )
        jitter_source = self.jitter_source or random
        jitter = max(0.0, min(jitter_source(), 1.0)) * self.max_jitter_s
        return min(exponential_delay + jitter, self.max_delay_s)

    def _record_status(
        self,
        state: str,
        *,
        next_retry_delay_s: float | None = None,
    ) -> None:
        status = {
            "state": state,
            "retry_attempt": self.retry_attempt,
            "latest_failure_class": self.latest_failure_class,
            "next_retry_delay_s": next_retry_delay_s,
            "updated_at": self.now(),
        }
        try:
            self.status_writer(status)
        except Exception:
            # Diagnostics cannot be allowed to terminate the Runtime or edge retry.
            pass


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


__all__ = ["ManagedHostEdgeSupervisor"]
