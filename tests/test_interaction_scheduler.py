from __future__ import annotations

import asyncio
import unittest

from personal_runtime.interaction_scheduler import InteractionScheduler


class InteractionSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_work_is_serialized_and_user_priority_wins(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        handled: list[str] = []

        async def handle_main(work: dict) -> None:
            handled.append(work["kind"])
            if work["kind"] == "background":
                started.set()
                await release.wait()

        scheduler = InteractionScheduler(handle_main=handle_main)
        await scheduler.start()
        try:
            await scheduler.enqueue_main({"kind": "background"}, priority=2)
            await asyncio.wait_for(started.wait(), timeout=1)
            await scheduler.enqueue_main({"kind": "user"}, priority=0)
            release.set()
            await scheduler.join()
        finally:
            await scheduler.close()

        self.assertEqual(handled, ["background", "user"])

    async def test_children_for_different_interactions_run_concurrently(self) -> None:
        both_started = asyncio.Event()
        release = asyncio.Event()
        active = 0
        maximum_active = 0
        lock = asyncio.Lock()

        async def handle_child(work: dict) -> None:
            nonlocal active, maximum_active
            async with lock:
                active += 1
                maximum_active = max(maximum_active, active)
                if active == 2:
                    both_started.set()
            await release.wait()
            async with lock:
                active -= 1

        scheduler = InteractionScheduler(handle_child=handle_child, child_workers=4)
        await scheduler.start()
        try:
            await scheduler.enqueue_child("interaction-1", {"kind": "child"})
            await scheduler.enqueue_child("interaction-2", {"kind": "child"})
            await asyncio.wait_for(both_started.wait(), timeout=1)
            release.set()
            await scheduler.join()
        finally:
            await scheduler.close()

        self.assertEqual(maximum_active, 2)

    async def test_background_work_for_same_context_version_coalesces(self) -> None:
        handled: list[dict] = []

        async def handle_main(work: dict) -> None:
            handled.append(work)

        scheduler = InteractionScheduler(handle_main=handle_main)
        await scheduler.enqueue_main(
            {"kind": "background", "interaction_id": "interaction-1", "context_version": 5},
            priority=2,
        )
        await scheduler.enqueue_main(
            {"kind": "background", "interaction_id": "interaction-1", "context_version": 5},
            priority=2,
        )
        await scheduler.start()
        try:
            await scheduler.join()
        finally:
            await scheduler.close()

        self.assertEqual(len(handled), 1)
