import unittest

from personal_runtime.presence_router import choose_response_device
from personal_runtime.runtime_state import RuntimeState


class RuntimeStateTests(unittest.TestCase):
    def test_registers_device_and_capability(self) -> None:
        state = RuntimeState()
        state.register_device("desktop-dev-1", "desktop-cli")
        state.register_capability("desktop-dev-1", "text.input")

        self.assertIn("desktop-dev-1", state.devices)
        self.assertIn("text.input", state.devices["desktop-dev-1"]["capabilities"])

    def test_presence_defaults_to_source_device(self) -> None:
        target = choose_response_device(source_device_id="desktop-dev-1")

        self.assertEqual(target, "desktop-dev-1")


if __name__ == "__main__":
    unittest.main()
