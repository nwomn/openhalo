"""Runtime-owned scheduling boundaries for Main and Child semantic work."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable
from collections.abc import Callable
from itertools import count


WorkHandler = Callable[[dict], Awaitable[None]]


async def _ignore_work(_: dict) -> None:
    return None


class InteractionScheduler:
    """Serializes Main work while allowing independent ordered Child queues."""

    def __init__(
        self,
        *,
        handle_main: WorkHandler = _ignore_work,
        handle_child: WorkHandler = _ignore_work,
        child_workers: int = 4,
    ) -> None:
        if child_workers < 1:
            raise ValueError("child_workers must be positive")
        self._handle_main = handle_main
        self._handle_child = handle_child
        self._main_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._sequence = count()
        self._child_queues: dict[str, list[dict]] = defaultdict(list)
        self._child_tasks: dict[str, asyncio.Task] = {}
        self._child_semaphore = asyncio.Semaphore(child_workers)
        self._main_task: asyncio.Task | None = None
        self._coalesced_main_keys: set[tuple[str | None, int | None]] = set()
        self._started = False
        self._closed = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._main_task = asyncio.create_task(self._run_main(), name="openhalo-main")
        for interaction_id in list(self._child_queues):
            self._start_child_queue(interaction_id)

    async def enqueue_main(self, work: dict, *, priority: int) -> bool:
        self._ensure_open()
        key = _coalesce_key(work)
        if key is not None and key in self._coalesced_main_keys:
            return False
        if key is not None:
            self._coalesced_main_keys.add(key)
        await self._main_queue.put((priority, next(self._sequence), work, key))
        return True

    async def enqueue_child(self, interaction_id: str, work: dict) -> None:
        self._ensure_open()
        self._child_queues[interaction_id].append(dict(work))
        if self._started:
            self._start_child_queue(interaction_id)

    async def join(self) -> None:
        await self._main_queue.join()
        while self._child_tasks:
            tasks = list(self._child_tasks.values())
            await asyncio.gather(*tasks)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._main_task is not None:
            await self._main_queue.put((99, next(self._sequence), None, None))
            await self._main_task
        if self._child_tasks:
            await asyncio.gather(*self._child_tasks.values(), return_exceptions=True)

    async def _run_main(self) -> None:
        while True:
            _, _, work, key = await self._main_queue.get()
            try:
                if work is None:
                    return
                await self._handle_main(work)
            finally:
                if key is not None:
                    self._coalesced_main_keys.discard(key)
                self._main_queue.task_done()

    def _start_child_queue(self, interaction_id: str) -> None:
        if interaction_id in self._child_tasks:
            return
        self._child_tasks[interaction_id] = asyncio.create_task(
            self._run_child_queue(interaction_id),
            name=f"openhalo-child:{interaction_id}",
        )

    async def _run_child_queue(self, interaction_id: str) -> None:
        try:
            while self._child_queues[interaction_id]:
                work = self._child_queues[interaction_id].pop(0)
                async with self._child_semaphore:
                    await self._handle_child(work)
        finally:
            self._child_tasks.pop(interaction_id, None)
            if not self._child_queues[interaction_id]:
                self._child_queues.pop(interaction_id, None)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("InteractionScheduler is closed")


def _coalesce_key(work: dict) -> tuple[str | None, int | None] | None:
    if work.get("kind") != "background":
        return None
    return work.get("interaction_id"), work.get("context_version")


__all__ = ["InteractionScheduler"]
