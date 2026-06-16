import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DevEnvWorkflowTests(unittest.TestCase):
    def test_shared_test_script_exists_and_targets_root_venv(self) -> None:
        script_path = ROOT / "bin" / "test"

        self.assertTrue(script_path.exists())
        self.assertTrue(os.access(script_path, os.X_OK))
        self.assertIn('.venv/bin/python', script_path.read_text(encoding="utf-8"))

    def test_bootstrap_script_exists_and_mentions_local_worktree_venv(self) -> None:
        script_path = ROOT / "bin" / "bootstrap-worktree-venv"

        self.assertTrue(script_path.exists())
        self.assertTrue(os.access(script_path, os.X_OK))
        contents = script_path.read_text(encoding="utf-8")
        self.assertIn("python3 -m venv .venv", contents)
        self.assertIn("worktree-local", contents)

    def test_dev_env_document_describes_shared_and_isolated_modes(self) -> None:
        document_path = ROOT / "docs" / "dev-env.md"

        self.assertTrue(document_path.exists())
        contents = document_path.read_text(encoding="utf-8")
        self.assertIn("Default: reuse the repository root `.venv`", contents)
        self.assertIn("Exception: create a worktree-local `.venv`", contents)

    def test_shared_test_script_runs_using_root_venv(self) -> None:
        script_path = ROOT / "bin" / "test"
        probe = (
            "import pathlib,sys; "
            "print(pathlib.Path(sys.executable).resolve())"
        )
        result = subprocess.run(
            [str(script_path), "-c", probe],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        self.assertEqual(
            Path(result.stdout.strip()),
            (ROOT / ".venv" / "bin" / "python").resolve(),
        )

    def test_bootstrap_script_creates_local_venv_when_run_explicitly(self) -> None:
        script_path = ROOT / "bin" / "bootstrap-worktree-venv"

        with tempfile.TemporaryDirectory() as temp_dir:
            subprocess.run(
                [str(script_path)],
                check=True,
                capture_output=True,
                text=True,
                cwd=temp_dir,
            )

            self.assertTrue(Path(temp_dir, ".venv", "bin", "python").exists())


if __name__ == "__main__":
    unittest.main()
