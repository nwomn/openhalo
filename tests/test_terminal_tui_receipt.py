from __future__ import annotations

import queue
import unittest

from device_edge.cli.presentation import OutcomeReceipt
from device_edge.cli.presentation import ReceiptEntry
from device_edge.cli.terminal_daemon import TerminalEdgeDaemon
from device_edge.cli.terminal_tui import TerminalEdgeApp
from device_edge.cli.terminal_tui import OutcomeReceiptWidget


def test_receipt_widget_shows_compact_line_then_expanded_safe_timeline() -> None:
    receipt = OutcomeReceipt(
        interaction_id="interaction-1",
        state="completed",
        entries=(
            ReceiptEntry(1, "request_received", "2030-01-01T10:42:00Z"),
            ReceiptEntry(2, "confirmed", "2030-01-01T10:43:00Z", "Maya's Phone"),
        ),
        summary="Friday 14:00-17:00 is reserved for writing.",
        compact_line="✓ Completed · Maya's Phone · 10:43",
    )
    toggled = []
    widget = OutcomeReceiptWidget(receipt, on_toggle=toggled.append)

    assert "Maya's Phone" in str(widget.render())
    assert "Friday" not in str(widget.render())

    widget.toggle()
    widget.set_receipt(OutcomeReceipt(**{**receipt.__dict__, "expanded": True}))

    assert toggled == ["interaction-1"]
    assert "Friday 14:00-17:00" in str(widget.render())
    assert "10:42" in str(widget.render())


class TerminalTuiReceiptTests(unittest.IsolatedAsyncioTestCase):
    async def test_terminal_app_mounts_and_toggles_a_safe_receipt(self) -> None:
        daemon = TerminalEdgeDaemon(
            device_id="terminal-edge-1",
            audience="ws://127.0.0.1:8765",
        )
        daemon.handle_interaction_frame(
            {
                "interaction": {
                    "interaction_id": "interaction-1",
                    "status": "completed",
                    "summary": "Done.",
                    "outcome_receipt": {
                        "version": 1,
                        "state": "completed",
                        "entries": [
                            {
                                "sequence": 1,
                                "kind": "confirmed",
                                "occurred_at": "2030-01-01T10:43:00Z",
                                "device_name": "Maya's Phone",
                            }
                        ],
                    },
                }
            }
        )
        transcript_queue: queue.Queue[str] = queue.Queue()
        transcript_queue.put(daemon.transcript[-1])
        app = TerminalEdgeApp(
            daemon=daemon,
            input_queue=queue.Queue(),
            input_state_queue=queue.Queue(),
            transcript_queue=transcript_queue,
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            widget = app.query_one("#receipt-interaction-1", OutcomeReceiptWidget)
            widget.focus()
            await pilot.press("space")
            await pilot.pause()

        assert daemon.presentation.receipts["interaction-1"].expanded is True
