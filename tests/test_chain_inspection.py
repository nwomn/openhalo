import subprocess
import unittest
from pathlib import Path

from device_edge.cli.cli_edge import inspect_agent_initiative_once, inspect_cli_once
from device_edge.cli.terminal_daemon import build_terminal_daemon_parser
from personal_runtime.chain_inspection import format_chain_report

ROOT = Path(__file__).resolve().parents[1]
TEST_LLM_CONFIG = ROOT / "tests" / "fixtures" / "llm-config-test.toml"


class ChainInspectionTests(unittest.TestCase):
    def test_terminal_daemon_parser_still_accepts_runtime_url_and_device_id(self) -> None:
        parser = build_terminal_daemon_parser()

        args = parser.parse_args(
            [
                "--url",
                "ws://127.0.0.1:8765",
                "--device-id",
                "terminal-edge-custom",
            ]
        )

        self.assertEqual(args.url, "ws://127.0.0.1:8765")
        self.assertEqual(args.device_id, "terminal-edge-custom")

    def test_inspect_cli_once_returns_structured_chain_report(self) -> None:
        report = inspect_cli_once("hello runtime", config_path=TEST_LLM_CONFIG)

        self.assertEqual(report["action_result"]["result"]["status"], "ok")
        self.assertTrue(report["trace_lines"])
        self.assertTrue(report["observations"])
        self.assertIn("user.current_location", report["snapshot"])
        self.assertIn("fields", report["snapshot_contract"])
        self.assertEqual(
            report["snapshot_contract"],
            report["intervention"]["snapshot_contract"],
        )
        self.assertEqual(report["proposal"]["kind"], "notify")
        self.assertEqual(report["proposal"]["source"], "sense_first")
        self.assertEqual(report["proposal"]["proposal_type"], "reply")
        self.assertEqual(
            report["proposal"]["metadata"]["llm_profile"],
            "proposal_formation",
        )
        self.assertTrue(report["proposal"]["metadata"]["used_deterministic_fallback"])
        self.assertIn("proposal_rationale", report["proposal"]["metadata"])
        self.assertEqual(report["grounding"]["bundle_version"], "m10.v1")
        self.assertIn("active_goals", report["grounding"])
        self.assertIn("recent_memory", report["grounding"])
        self.assertEqual(
            report["grounding"]["edge_history"]["history_kind"],
            "observation_window",
        )
        self.assertGreaterEqual(
            report["grounding"]["edge_history"]["returned_entries"], 1
        )
        self.assertIn("prompt_context", report)
        self.assertIn("version", report["prompt_context"])
        self.assertIn("sections", report["prompt_context"])
        self.assertIn("behavior_contract", report)
        self.assertIn("checks", report["behavior_contract"])
        self.assertIn("replay_eval", report)
        self.assertIn("checks", report["replay_eval"])
        self.assertIn(report["presence_decision"]["decision"], {"allow", "suppress"})

    def test_formatted_chain_report_contains_major_sections_in_order(self) -> None:
        report = inspect_cli_once("hello runtime", config_path=TEST_LLM_CONFIG)

        rendered = format_chain_report(report)

        self.assertIn("Trace:", rendered)
        self.assertIn("Observations:", rendered)
        self.assertIn("Compact Snapshot:", rendered)
        self.assertIn("Grounding Bundle:", rendered)
        self.assertIn("Prompt Context:", rendered)
        self.assertIn("Behavior Contract:", rendered)
        self.assertIn("Snapshot Contract:", rendered)
        self.assertIn("Proposal:", rendered)
        self.assertIn("Presence Decision:", rendered)
        self.assertIn("Recorded Intervention:", rendered)
        self.assertIn("Replay Eval:", rendered)
        self.assertIn('"llm_profile": "proposal_formation"', rendered)
        self.assertIn('"used_deterministic_fallback": true', rendered)
        self.assertIn('"proposal_type": "reply"', rendered)
        self.assertIn('"proposal_rationale"', rendered)
        self.assertIn('"bundle_version": "m10.v1"', rendered)
        self.assertIn('"prompt_context_version"', rendered)
        self.assertIn('"history_kind": "observation_window"', rendered)
        self.assertLess(rendered.index("Trace:"), rendered.index("Observations:"))
        self.assertLess(
            rendered.index("Observations:"), rendered.index("Compact Snapshot:")
        )
        self.assertLess(
            rendered.index("Compact Snapshot:"),
            rendered.index("Grounding Bundle:"),
        )
        self.assertLess(
            rendered.index("Grounding Bundle:"),
            rendered.index("Prompt Context:"),
        )
        self.assertLess(
            rendered.index("Prompt Context:"),
            rendered.index("Behavior Contract:"),
        )
        self.assertLess(
            rendered.index("Behavior Contract:"),
            rendered.index("Snapshot Contract:"),
        )
        self.assertLess(rendered.index("Proposal:"), rendered.index("Presence Decision:"))
        self.assertLess(
            rendered.index("Presence Decision:"),
            rendered.index("Recorded Intervention:"),
        )
        self.assertLess(
            rendered.index("Recorded Intervention:"),
            rendered.index("Replay Eval:"),
        )

    def test_inspect_agent_initiative_once_returns_structured_chain_report(self) -> None:
        report = inspect_agent_initiative_once()

        self.assertEqual(report["action_result"]["result"]["status"], "ok")
        self.assertEqual(report["proposal"]["source"], "agent_initiative")
        self.assertEqual(report["proposal"]["action_capability"], "runtime.status")
        self.assertEqual(report["presence_decision"]["target_device_id"], "host-edge-1")

    def test_inspect_cli_once_can_report_clarification_proposal(self) -> None:
        report = inspect_cli_once("help", config_path=TEST_LLM_CONFIG)

        self.assertEqual(report["proposal"]["proposal_type"], "clarification")
        self.assertEqual(report["proposal"]["action_capability"], "notification.show")
        self.assertIn("proposal_rationale", report["proposal"]["metadata"])

    def test_inspect_cli_once_can_report_no_intervention_proposal(self) -> None:
        report = inspect_cli_once("thanks", config_path=TEST_LLM_CONFIG)

        self.assertEqual(report["proposal"]["proposal_type"], "no_intervention")
        self.assertIsNone(report["proposal"]["action_capability"])
        self.assertEqual(report["action_result"]["result"]["status"], "completed")

    def test_inspect_cli_once_can_report_runtime_action_proposal(self) -> None:
        report = inspect_cli_once("check runtime status", config_path=TEST_LLM_CONFIG)

        self.assertEqual(report["proposal"]["proposal_type"], "action")
        self.assertEqual(report["proposal"]["action_capability"], "runtime.status")
        self.assertEqual(report["action_result"]["result"]["capability"], "runtime.status")
        self.assertEqual(
            report["interaction"]["summary"],
            "Runtime status: running (pid 4242).",
        )

    def test_cli_module_prints_chain_report_in_inspect_mode(self) -> None:
        result = subprocess.run(
            [
                str(ROOT / ".venv" / "bin" / "python"),
                "-m",
                "device_edge.cli.cli_edge",
                "--inspect-chain",
                "--text",
                "hello runtime",
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        self.assertIn("Trace:", result.stdout)
        self.assertIn("Recorded Intervention:", result.stdout)
        self.assertNotIn(
            "CLI edge ready. Type one line to send to the runtime:",
            result.stdout,
        )

    def test_cli_module_prints_prompt_contract_report_in_prompt_contract_mode(self) -> None:
        result = subprocess.run(
            [
                str(ROOT / ".venv" / "bin" / "python"),
                "-m",
                "device_edge.cli.cli_edge",
                "--inspect-prompt-contract",
                "--text",
                "hello runtime",
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        self.assertIn("Prompt Context:", result.stdout)
        self.assertIn("Behavior Contract:", result.stdout)
        self.assertIn("Replay Eval:", result.stdout)

    def test_cli_module_prints_chain_report_in_agent_initiative_mode(self) -> None:
        result = subprocess.run(
            [
                str(ROOT / ".venv" / "bin" / "python"),
                "-m",
                "device_edge.cli.cli_edge",
                "--inspect-agent-initiative",
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        self.assertIn("Proposal:", result.stdout)
        self.assertIn('"source": "agent_initiative"', result.stdout)
        self.assertIn("Action Result:", result.stdout)
