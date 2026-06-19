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


if __name__ == "__main__":
    unittest.main()
