import unittest

from personal_runtime.trace_recorder import TraceRecorder


class TraceRecorderTests(unittest.TestCase):
    def test_formats_human_readable_trace_lines(self) -> None:
        recorder = TraceRecorder()

        recorder.record("EDGE", "build connect frame")
        recorder.record("GATEWAY", "received connect", device_id="desktop-dev-1")

        self.assertEqual(
            recorder.format_lines(),
            [
                "EDGE build connect frame",
                "GATEWAY received connect [device_id=desktop-dev-1]",
            ],
        )

    def test_can_emit_trace_lines_without_retaining_history(self) -> None:
        emitted_lines: list[str] = []
        recorder = TraceRecorder(
            emitters=[emitted_lines.append],
            retain_entries=False,
        )

        recorder.record("HOST", "retrying websocket session", delay_s="2.0")

        self.assertEqual(
            emitted_lines,
            ["HOST retrying websocket session [delay_s=2.0]"],
        )
        self.assertEqual(recorder.format_lines(), [])


if __name__ == "__main__":
    unittest.main()
