import unittest

from personal_runtime.runtime_console_presenter import RuntimeConsolePresenter


class RuntimeConsolePresenterTests(unittest.TestCase):
    def test_renders_a_human_readable_safe_phase(self) -> None:
        rendered = []
        presenter = RuntimeConsolePresenter(rendered.append)

        presenter.present(
            {
                "version": 1,
                "interaction_id": "interaction-1",
                "interaction_turn_id": "interaction-turn-1",
                "sequence": 1,
                "phase": "deliberating",
                "state": "active",
                "occurred_at": "2026-07-19T10:00:00Z",
                "presentation_hint": "working",
                "provider": "Hermes",
                "tool_args": {"body": "private request"},
            }
        )

        self.assertEqual(rendered, ["OpenHalo Runtime · 正在理解请求"])

    def test_output_failure_never_interrupts_runtime_work(self) -> None:
        def unavailable_console(_message: str) -> None:
            raise OSError("console unavailable")

        presenter = RuntimeConsolePresenter(unavailable_console)

        self.assertEqual(
            presenter.present(
                {
                    "version": 1,
                    "interaction_id": "interaction-1",
                    "interaction_turn_id": "interaction-turn-1",
                    "sequence": 1,
                    "phase": "completed",
                    "state": "settled",
                    "occurred_at": "2026-07-19T10:00:01Z",
                    "presentation_hint": "completed",
                }
            ),
            "OpenHalo Runtime · 本次处理已完成",
        )

    def test_malformed_progress_never_interrupts_runtime_work(self) -> None:
        rendered = []
        presenter = RuntimeConsolePresenter(rendered.append)

        self.assertIsNone(presenter.present({"phase": ["untrusted"]}))
        self.assertEqual(rendered, [])
