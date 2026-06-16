import importlib
import unittest


class ImportSmokeTests(unittest.TestCase):
    def test_runtime_package_imports(self) -> None:
        self.assertIsNotNone(importlib.import_module("personal_runtime"))
        self.assertIsNotNone(importlib.import_module("device_edge"))


if __name__ == "__main__":
    unittest.main()
