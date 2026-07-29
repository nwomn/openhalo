from __future__ import annotations

from device_edge.cli.presentation import PresentationState
from device_edge.cli.presentation import reduce_interaction_update
from device_edge.cli.presentation import reduce_progress_frame
from device_edge.cli.presentation import toggle_receipt
from device_edge.cli.terminal_daemon import TerminalEdgeDaemon


def _receipt(*, device_name: str = "Maya's Phone") -> dict:
    return {
        "version": 1,
        "state": "completed",
        "entries": [
            {
                "sequence": 1,
                "kind": "request_received",
                "occurred_at": "2030-01-01T10:42:00Z",
            },
            {
                "sequence": 2,
                "kind": "delivery",
                "device_name": device_name,
                "occurred_at": "2030-01-01T10:43:00Z",
            },
            {
                "sequence": 3,
                "kind": "confirmed",
                "device_name": device_name,
                "occurred_at": "2030-01-01T10:44:00Z",
            },
        ],
    }


def test_settled_outcome_receipt_is_compact_then_expands_locally() -> None:
    state = PresentationState()

    next_state = reduce_interaction_update(
        state,
        {
            "interaction": {
                "interaction_id": "interaction-1",
                "status": "completed",
                "summary": "Friday 14:00-17:00 is reserved for writing.",
                "outcome_receipt": _receipt(),
            }
        },
    )
    receipt = next_state.receipts["interaction-1"]

    assert receipt.expanded is False
    assert receipt.entries[-1].device_name == "Maya's Phone"
    assert "Maya's Phone" in receipt.compact_line

    expanded = toggle_receipt(next_state, "interaction-1")

    assert expanded.receipts["interaction-1"].expanded is True
    assert expanded.receipts["interaction-1"].summary == "Friday 14:00-17:00 is reserved for writing."


def test_unsafe_or_out_of_order_receipts_degrade_to_summary() -> None:
    state = PresentationState()
    unsafe = _receipt()
    unsafe["entries"][1]["tool"] = "shell.exec"
    unsafe["entries"][2]["sequence"] = 2

    next_state = reduce_interaction_update(
        state,
        {
            "interaction": {
                "interaction_id": "interaction-1",
                "status": "completed",
                "summary": "The request completed.",
                "outcome_receipt": unsafe,
            }
        },
    )

    assert next_state.receipts == {}
    assert next_state.transcript[-1].text == "The request completed."


def test_progress_reducer_ignores_stale_sequence_and_never_reopens_settled_receipt() -> None:
    state = PresentationState()
    state = reduce_progress_frame(
        state,
        {
            "progress": {
                "version": 1,
                "interaction_id": "interaction-1",
                "sequence": 2,
                "phase": "executing",
                "state": "active",
            }
        },
    )
    state = reduce_interaction_update(
        state,
        {
            "interaction": {
                "interaction_id": "interaction-1",
                "status": "completed",
                "summary": "Done.",
                "outcome_receipt": _receipt(),
            }
        },
    )

    next_state = reduce_progress_frame(
        state,
        {
            "progress": {
                "version": 1,
                "interaction_id": "interaction-1",
                "sequence": 3,
                "phase": "executing",
                "state": "active",
            }
        },
    )

    assert next_state.active_progress == {}
    assert next_state.receipts["interaction-1"].summary == "Done."


def test_terminal_daemon_reduces_safe_receipts_without_rendering_runtime_trace() -> None:
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
                "outcome_receipt": _receipt(),
            }
        }
    )

    assert daemon.presentation.receipts["interaction-1"].summary == "Done."
    assert daemon.transcript[-1].startswith("[receipt]")
