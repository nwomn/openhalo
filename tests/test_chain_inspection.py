import subprocess
import unittest
from pathlib import Path

from device_edge.cli.cli_edge import inspect_agent_initiative_once, inspect_cli_once
from personal_runtime.chain_inspection import format_chain_report

ROOT = Path(__file__).resolve().parents[1]


class ChainInspectionTests(unittest.TestCase):
    def test_inspect_cli_once_returns_structured_chain_report(self) -> None:
        report = inspect_cli_once("hello runtime")

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
        self.assertIn(report["presence_decision"]["decision"], {"allow", "suppress"})

    def test_formatted_chain_report_contains_major_sections_in_order(self) -> None:
        report = inspect_cli_once("hello runtime")

        rendered = format_chain_report(report)

        self.assertIn("Trace:", rendered)
        self.assertIn("Observations:", rendered)
        self.assertIn("Compact Snapshot:", rendered)
        self.assertIn("Snapshot Contract:", rendered)
        self.assertIn("Proposal:", rendered)
        self.assertIn("Presence Decision:", rendered)
        self.assertIn("Recorded Intervention:", rendered)
        self.assertLess(rendered.index("Trace:"), rendered.index("Observations:"))
        self.assertLess(
            rendered.index("Observations:"), rendered.index("Compact Snapshot:")
        )
        self.assertLess(
            rendered.index("Compact Snapshot:"),
            rendered.index("Snapshot Contract:"),
        )
        self.assertLess(rendered.index("Proposal:"), rendered.index("Presence Decision:"))
        self.assertLess(
            rendered.index("Presence Decision:"),
            rendered.index("Recorded Intervention:"),
        )

    def test_inspect_agent_initiative_once_returns_structured_chain_report(self) -> None:
        report = inspect_agent_initiative_once()

        self.assertEqual(report["action_result"]["result"]["status"], "ok")
        self.assertEqual(report["proposal"]["source"], "agent_initiative")
        self.assertEqual(report["proposal"]["action_capability"], "runtime.status")
        self.assertEqual(report["presence_decision"]["target_device_id"], "host-edge-1")

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
