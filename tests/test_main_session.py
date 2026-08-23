from __future__ import annotations

import unittest

from personal_runtime.main_session import MainSessionManager


class MainSessionManagerTests(unittest.TestCase):
    def test_restores_persisted_native_session(self) -> None:
        restored = []
        manager = MainSessionManager(
            state={"session_id": "openhalo-main", "generation": 2},
            restore=lambda session_id: restored.append(session_id) or True,
            create=lambda generation: f"created-{generation}",
        )

        session = manager.ensure_session()

        self.assertEqual(session.session_id, "openhalo-main")
        self.assertEqual(session.generation, 2)
        self.assertFalse(session.recovered)
        self.assertEqual(restored, ["openhalo-main"])

    def test_failed_restore_creates_audited_new_generation(self) -> None:
        state = {"session_id": "old-main", "generation": 2}
        manager = MainSessionManager(
            state=state,
            restore=lambda _: False,
            create=lambda generation: f"main-{generation}",
        )

        session = manager.ensure_session()

        self.assertEqual(session.session_id, "main-3")
        self.assertTrue(session.recovered)
        self.assertEqual(state["generation"], 3)
        self.assertEqual(state["recovery_audit"][-1]["reason"], "native_session_unavailable")
