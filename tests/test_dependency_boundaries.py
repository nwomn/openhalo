import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DependencyBoundaryTests(unittest.TestCase):
    def test_device_edge_runtime_paths_do_not_import_personal_runtime(self) -> None:
        checked_paths = [
            ROOT / "device_edge" / "shared" / "session_client.py",
            ROOT / "device_edge" / "host" / "host_daemon.py",
            ROOT / "device_edge" / "cli" / "terminal_daemon.py",
        ]

        for path in checked_paths:
            with self.subTest(path=path):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                imports = [
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                ]
                imported_names = []
                for node in imports:
                    if isinstance(node, ast.ImportFrom):
                        imported_names.append(node.module or "")
                    else:
                        imported_names.extend(alias.name for alias in node.names)

                self.assertFalse(
                    any(name.startswith("personal_runtime") for name in imported_names),
                    f"{path} imports personal_runtime: {imported_names}",
                )


if __name__ == "__main__":
    unittest.main()
