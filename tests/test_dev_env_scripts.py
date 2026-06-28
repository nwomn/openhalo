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

    def test_bootstrap_script_exists_and_mentions_optional_local_worktree_venv(self) -> None:
        script_path = ROOT / "bin" / "bootstrap-worktree-venv"

        self.assertTrue(script_path.exists())
        self.assertTrue(os.access(script_path, os.X_OK))
        contents = script_path.read_text(encoding="utf-8")
        self.assertIn("python3 -m venv .venv", contents)
        self.assertIn("worktree-local", contents)
        self.assertIn("optional", contents)

    def test_dev_env_document_describes_branch_first_default_and_optional_worktree_mode(self) -> None:
        document_path = ROOT / "docs" / "dev-env.md"

        self.assertTrue(document_path.exists())
        contents = document_path.read_text(encoding="utf-8")
        self.assertIn("Default: work on a normal branch in the main workspace.", contents)
        self.assertIn("Optional: create a worktree-local `.venv`.", contents)
        self.assertIn("Advanced optional path: use a git worktree", contents)
        self.assertIn("CLI device validation is acceptable for early module testing", contents)
        self.assertIn("Host edge verification is required before documenting a module as implemented and operationally ready.", contents)
        self.assertIn("bin/verify-host-edge", contents)
        self.assertIn("stdin", contents)
        self.assertIn("live terminal session", contents)
        self.assertIn("/help", contents)
        self.assertIn("/status", contents)
        self.assertIn("/history", contents)
        self.assertIn("/quit", contents)
        self.assertIn("Session status", contents)
        self.assertIn("--tui", contents)
        self.assertIn("Textual", contents)
        self.assertIn("full-screen", contents)
        self.assertIn("status bar", contents)
        self.assertIn("transcript", contents)
        self.assertIn("input box", contents)
        self.assertIn("fallback", contents)
        self.assertIn("docs/terminal-tui.md", contents)
        self.assertIn(".venv/bin/python -m personal_runtime.main", contents)
        self.assertIn(
            ".venv/bin/python -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:8765 --token dev-token --tui",
            contents,
        )
        self.assertIn("hello runtime", contents)
        self.assertIn("check runtime status", contents)
        self.assertIn("real user-scenario foreground session", contents)

    def test_terminal_tui_guide_exists_and_describes_layout_controls_and_limits(self) -> None:
        document_path = ROOT / "docs" / "terminal-tui.md"

        self.assertTrue(document_path.exists())
        contents = document_path.read_text(encoding="utf-8")
        self.assertIn("Textual UI mode", contents)
        self.assertIn("--tui", contents)
        self.assertIn("status bar", contents)
        self.assertIn("transcript pane", contents)
        self.assertIn("input box", contents)
        self.assertIn("/help", contents)
        self.assertIn("/status", contents)
        self.assertIn("/history", contents)
        self.assertIn("/quit", contents)
        self.assertIn("Ctrl+C", contents)
        self.assertIn("Current Limits", contents)
        self.assertIn(".venv/bin/python -m personal_runtime.main", contents)
        self.assertIn(
            ".venv/bin/python -m device_edge.cli.terminal_daemon --url ws://127.0.0.1:8765 --token dev-token --tui",
            contents,
        )
        self.assertIn("real user scenario", contents)
        self.assertIn("check runtime status", contents)

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

    def test_host_edge_verification_script_exists_and_is_executable(self) -> None:
        script_path = ROOT / "bin" / "verify-host-edge"

        self.assertTrue(script_path.exists())
        self.assertTrue(os.access(script_path, os.X_OK))
        contents = script_path.read_text(encoding="utf-8")
        self.assertIn("personal_runtime.main", contents)
        self.assertIn("device_edge.host.host_daemon", contents)
        self.assertIn("--max-idle-cycles", contents)
        self.assertIn("--max-sessions", contents)
        self.assertIn(".runtime", contents)

    def test_host_edge_verification_script_supports_dry_run(self) -> None:
        script_path = ROOT / "bin" / "verify-host-edge"

        result = subprocess.run(
            [str(script_path), "--dry-run"],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        self.assertIn("personal_runtime.main", result.stdout)
        self.assertIn("device_edge.host.host_daemon", result.stdout)
        self.assertIn("direct-action", result.stdout)
        self.assertIn("initiative-action", result.stdout)
        self.assertIn("agent_initiative", result.stdout)
        self.assertIn("state-check", result.stdout)
        self.assertIn(".runtime/host-edge-verify-state.json", result.stdout)

    def test_terminal_edge_verification_script_exists_and_is_executable(self) -> None:
        script_path = ROOT / "bin" / "verify-terminal-edge"

        self.assertTrue(script_path.exists())
        self.assertTrue(os.access(script_path, os.X_OK))
        contents = script_path.read_text(encoding="utf-8")
        self.assertIn("personal_runtime.main", contents)
        self.assertIn("device_edge.cli.terminal_daemon", contents)
        self.assertIn("terminal.context", contents)
        self.assertIn("notification.show", contents)
        self.assertIn("terminal-local-help", contents)
        self.assertIn("delivered_via", contents)
        self.assertNotIn("Runtime heard: ${SCRIPTED_TEXT}", contents)
        self.assertIn(".runtime", contents)

    def test_terminal_edge_verification_script_supports_dry_run(self) -> None:
        script_path = ROOT / "bin" / "verify-terminal-edge"

        result = subprocess.run(
            [str(script_path), "--dry-run"],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        self.assertIn("personal_runtime.main", result.stdout)
        self.assertIn("device_edge.cli.terminal_daemon", result.stdout)
        self.assertIn("terminal-pull", result.stdout)
        self.assertIn("terminal-local-help", result.stdout)
        self.assertIn("runtime-push-active", result.stdout)
        self.assertIn("runtime-push-idle", result.stdout)
        self.assertIn("state-check", result.stdout)
        self.assertIn(".runtime/terminal-edge-verify-state.json", result.stdout)

    def test_prompt_contract_verification_script_exists_and_is_executable(self) -> None:
        script_path = ROOT / "bin" / "verify-prompt-contract"

        self.assertTrue(script_path.exists())
        self.assertTrue(os.access(script_path, os.X_OK))
        contents = script_path.read_text(encoding="utf-8")
        self.assertIn("device_edge.cli.cli_edge", contents)
        self.assertIn("--inspect-prompt-contract", contents)
        self.assertIn("prompt-context", contents)
        self.assertIn("behavior-contract", contents)
        self.assertIn("replay-eval", contents)

    def test_prompt_contract_verification_script_supports_dry_run(self) -> None:
        script_path = ROOT / "bin" / "verify-prompt-contract"

        result = subprocess.run(
            [str(script_path), "--dry-run"],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        self.assertIn("inspect-chain", result.stdout)
        self.assertIn("prompt-context", result.stdout)
        self.assertIn("behavior-contract", result.stdout)
        self.assertIn("replay-eval", result.stdout)
        self.assertIn("state-summary", result.stdout)

    def test_dev_env_document_mentions_prompt_contract_acceptance_path(self) -> None:
        document_path = ROOT / "docs" / "dev-env.md"

        contents = document_path.read_text(encoding="utf-8")
        self.assertIn("verify-prompt-contract", contents)
        self.assertIn("prompt/context", contents)
        self.assertIn("behavior contract", contents)
        self.assertIn("replay/eval", contents)

    def test_proposal_formation_verification_script_exists_and_is_executable(self) -> None:
        script_path = ROOT / "bin" / "verify-proposal-formation"

        self.assertTrue(script_path.exists())
        self.assertTrue(os.access(script_path, os.X_OK))
        contents = script_path.read_text(encoding="utf-8")
        self.assertIn("device_edge.cli.cli_edge", contents)
        self.assertIn("reply", contents)
        self.assertIn("action", contents)
        self.assertIn("clarification", contents)
        self.assertIn("no_intervention", contents)

    def test_proposal_formation_verification_script_supports_dry_run(self) -> None:
        script_path = ROOT / "bin" / "verify-proposal-formation"

        result = subprocess.run(
            [str(script_path), "--dry-run"],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        self.assertIn("reply-scenario", result.stdout)
        self.assertIn("action-scenario", result.stdout)
        self.assertIn("clarification-scenario", result.stdout)
        self.assertIn("no-intervention-scenario", result.stdout)
        self.assertIn("proposal-rationale-check", result.stdout)

    def test_dev_env_document_mentions_proposal_formation_acceptance_path(self) -> None:
        document_path = ROOT / "docs" / "dev-env.md"

        contents = document_path.read_text(encoding="utf-8")
        self.assertIn("verify-proposal-formation", contents)
        self.assertIn("reply", contents)
        self.assertIn("clarification", contents)
        self.assertIn("no_intervention", contents)

    def test_model_provider_verification_script_exists_and_supports_dry_run(self) -> None:
        script_path = ROOT / "bin" / "verify-model-provider"

        self.assertTrue(script_path.exists())
        self.assertTrue(os.access(script_path, os.X_OK))

        result = subprocess.run(
            [str(script_path), "--dry-run"],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        self.assertIn("provider-probe", result.stdout)
        self.assertIn("controlled-failure", result.stdout)
        self.assertIn("model-health", result.stdout)

        explicit_config_result = subprocess.run(
            [
                str(script_path),
                "--dry-run",
                "--runtime-config-path",
                "config/runtime-config.openai-local.toml",
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        self.assertIn(
            "--runtime-config-path config/runtime-config.openai-local.toml",
            explicit_config_result.stdout,
        )

    def test_dev_env_document_mentions_model_provider_acceptance_path(self) -> None:
        document_path = ROOT / "docs" / "dev-env.md"

        contents = document_path.read_text(encoding="utf-8")
        self.assertIn("verify-model-provider", contents)
        self.assertIn("provider-probe", contents)
        self.assertIn("controlled failure", contents)

    def test_action_loop_verification_script_exists_and_supports_dry_run(self) -> None:
        script_path = ROOT / "bin" / "verify-action-loop"

        self.assertTrue(script_path.exists())
        self.assertTrue(os.access(script_path, os.X_OK))
        contents = script_path.read_text(encoding="utf-8")
        self.assertIn("RuntimeGateway", contents)
        self.assertIn("post_action", contents)
        self.assertIn("post_observation", contents)

        result = subprocess.run(
            [str(script_path), "--dry-run"],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        self.assertIn("runtime-status-reentry", result.stdout)
        self.assertIn("fresh-observation-reentry", result.stdout)
        self.assertIn("follow-up-action", result.stdout)
        self.assertIn("silent-completion", result.stdout)
        self.assertIn("lineage-check", result.stdout)

        model_result = subprocess.run(
            [
                str(script_path),
                "--dry-run",
                "--runtime-config-path",
                "config/runtime-config.openai-local.toml",
                "--require-model-backed",
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        self.assertIn("config/runtime-config.openai-local.toml", model_result.stdout)
        self.assertIn("model-backed-check", model_result.stdout)

    def test_dev_env_document_mentions_action_loop_acceptance_path(self) -> None:
        document_path = ROOT / "docs" / "dev-env.md"

        contents = document_path.read_text(encoding="utf-8")
        self.assertIn("verify-action-loop", contents)
        self.assertIn("post-action", contents)
        self.assertIn("fresh observation", contents)
        self.assertIn("same interaction", contents)
        self.assertIn("require-model-backed", contents)


if __name__ == "__main__":
    unittest.main()
