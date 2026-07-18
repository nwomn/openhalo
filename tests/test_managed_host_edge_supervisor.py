import asyncio
import inspect
import importlib.util
import unittest
from unittest.mock import patch


class ManagedHostEdgeSupervisorTests(unittest.IsolatedAsyncioTestCase):
    def _supervisor_type(self):
        spec = importlib.util.find_spec("personal_runtime.managed_host_edge")
        self.assertIsNotNone(spec)
        from personal_runtime.managed_host_edge import ManagedHostEdgeSupervisor

        return ManagedHostEdgeSupervisor

    async def _wait_for(self, predicate) -> None:
        for _ in range(100):
            if predicate():
                return
            await asyncio.sleep(0)
        self.fail("condition was not reached")

    async def test_start_creates_one_session_and_records_starting_then_connected(
        self,
    ) -> None:
        ManagedHostEdgeSupervisor = self._supervisor_type()
        connected = asyncio.Event()
        release_session = asyncio.Event()
        statuses = []

        class Daemon:
            calls = 0

            async def run_websocket_daemon_session(self, **kwargs) -> None:
                self.calls += 1
                kwargs["on_connected"]()
                connected.set()
                await release_session.wait()

        daemon = Daemon()
        supervisor = ManagedHostEdgeSupervisor(
            daemon=daemon,
            url="ws://127.0.0.1:8765",
            status_writer=statuses.append,
            sleep=asyncio.sleep,
        )

        await supervisor.start()
        await connected.wait()
        await supervisor.start()

        self.assertEqual(daemon.calls, 1)
        self.assertEqual(statuses[0]["state"], "starting")
        self.assertEqual(statuses[-1]["state"], "connected")

        release_session.set()
        await supervisor.stop()

    async def test_delayed_gateway_readiness_retries_then_recovers(self) -> None:
        ManagedHostEdgeSupervisor = self._supervisor_type()
        retry_sleep_started = asyncio.Event()
        release_retry = asyncio.Event()
        connected = asyncio.Event()
        statuses = []
        delays = []

        class Daemon:
            calls = 0

            async def run_websocket_daemon_session(self, **kwargs) -> None:
                self.calls += 1
                if self.calls == 1:
                    raise ConnectionRefusedError("Gateway is not ready")
                kwargs["on_connected"]()
                connected.set()
                await asyncio.Event().wait()

        async def controlled_sleep(delay: float) -> None:
            delays.append(delay)
            retry_sleep_started.set()
            await release_retry.wait()

        supervisor = ManagedHostEdgeSupervisor(
            daemon=Daemon(),
            url="ws://127.0.0.1:8765",
            status_writer=statuses.append,
            initial_delay_s=1.0,
            max_delay_s=8.0,
            max_jitter_s=0.5,
            jitter_source=lambda: 0.5,
            sleep=controlled_sleep,
        )

        await supervisor.start()
        await retry_sleep_started.wait()

        self.assertEqual(delays, [1.25])
        self.assertEqual(statuses[-1]["state"], "retrying")
        self.assertEqual(
            statuses[-1]["latest_failure_class"],
            "ConnectionRefusedError",
        )

        release_retry.set()
        await connected.wait()

        self.assertEqual(supervisor.retry_attempt, 0)
        self.assertEqual(
            statuses[-1]["latest_failure_class"],
            "ConnectionRefusedError",
        )
        await supervisor.stop()

    async def test_successful_connection_resets_backoff_before_later_disconnect(
        self,
    ) -> None:
        ManagedHostEdgeSupervisor = self._supervisor_type()
        first_sleep_started = asyncio.Event()
        second_sleep_started = asyncio.Event()
        release_first_sleep = asyncio.Event()
        disconnect_connected_session = asyncio.Event()
        delays = []

        class Daemon:
            calls = 0

            async def run_websocket_daemon_session(self, **kwargs) -> None:
                self.calls += 1
                if self.calls == 1:
                    raise OSError("first connection failure")
                if self.calls == 2:
                    kwargs["on_connected"]()
                    await disconnect_connected_session.wait()
                    raise OSError("later disconnect")
                await asyncio.Event().wait()

        async def controlled_sleep(delay: float) -> None:
            delays.append(delay)
            if len(delays) == 1:
                first_sleep_started.set()
                await release_first_sleep.wait()
                return
            second_sleep_started.set()
            await asyncio.Event().wait()

        supervisor = ManagedHostEdgeSupervisor(
            daemon=Daemon(),
            url="ws://127.0.0.1:8765",
            status_writer=lambda status: None,
            initial_delay_s=1.0,
            backoff_multiplier=2.0,
            max_delay_s=8.0,
            jitter_source=lambda: 0.0,
            sleep=controlled_sleep,
        )

        await supervisor.start()
        await first_sleep_started.wait()
        release_first_sleep.set()
        await self._wait_for(lambda: supervisor.retry_attempt == 0)
        disconnect_connected_session.set()
        await second_sleep_started.wait()

        self.assertEqual(delays, [1.0, 1.0])
        await supervisor.stop()

    async def test_stop_cancels_current_session_and_clears_supervisor_task(self) -> None:
        ManagedHostEdgeSupervisor = self._supervisor_type()
        session_started = asyncio.Event()
        session_cancelled = asyncio.Event()
        statuses = []

        class Daemon:
            async def run_websocket_daemon_session(self, **kwargs) -> None:
                kwargs["on_connected"]()
                session_started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    session_cancelled.set()

        supervisor = ManagedHostEdgeSupervisor(
            daemon=Daemon(),
            url="ws://127.0.0.1:8765",
            status_writer=statuses.append,
            sleep=asyncio.sleep,
        )

        await supervisor.start()
        await session_started.wait()
        await supervisor.stop()

        self.assertTrue(session_cancelled.is_set())
        self.assertIsNone(supervisor.task)
        self.assertEqual(statuses[-1]["state"], "disconnected")

    async def test_forwards_idle_timeout_to_the_public_host_edge_session(self) -> None:
        ManagedHostEdgeSupervisor = self._supervisor_type()
        self.assertIn(
            "idle_timeout_s",
            inspect.signature(ManagedHostEdgeSupervisor).parameters,
        )
        session_started = asyncio.Event()
        received_kwargs = {}

        class Daemon:
            async def run_websocket_daemon_session(self, **kwargs) -> None:
                received_kwargs.update(kwargs)
                kwargs["on_connected"]()
                session_started.set()
                await asyncio.Event().wait()

        supervisor = ManagedHostEdgeSupervisor(
            daemon=Daemon(),
            url="ws://127.0.0.1:8765",
            status_writer=lambda status: None,
            idle_timeout_s=1.25,
            sleep=asyncio.sleep,
        )

        await supervisor.start()
        await session_started.wait()
        await supervisor.stop()

        self.assertEqual(received_kwargs["idle_timeout_s"], 1.25)

    async def test_default_backoff_adds_bounded_random_jitter(self) -> None:
        ManagedHostEdgeSupervisor = self._supervisor_type()
        module = __import__(
            "personal_runtime.managed_host_edge",
            fromlist=["ManagedHostEdgeSupervisor"],
        )
        self.assertTrue(hasattr(module, "random"))
        supervisor = ManagedHostEdgeSupervisor(
            daemon=object(),
            url="ws://127.0.0.1:8765",
            status_writer=lambda status: None,
            initial_delay_s=1.0,
            max_delay_s=8.0,
            max_jitter_s=0.5,
        )
        supervisor.retry_attempt = 1

        with patch(
            "personal_runtime.managed_host_edge.random",
            return_value=0.5,
        ):
            delay = supervisor._retry_delay()

        self.assertEqual(delay, 1.25)


if __name__ == "__main__":
    unittest.main()
