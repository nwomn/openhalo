"""Pure local presentation state for the Quiet Terminal Edge."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace


_RECEIPT_KINDS = frozenset(
    {"request_received", "started", "delivery", "confirmed", "failed"}
)
_RECEIPT_STATES = frozenset({"completed", "failed", "cancelled"})
_PROGRESS_PHASES = frozenset(
    {
        "deliberating",
        "researching",
        "planning",
        "executing",
        "awaiting_action_result",
        "completing",
        "completed",
        "failed",
        "cancelled",
    }
)


@dataclass(frozen=True)
class TranscriptLine:
    kind: str
    text: str
    interaction_id: str | None = None


@dataclass(frozen=True)
class ReceiptEntry:
    sequence: int
    kind: str
    occurred_at: str
    device_name: str | None = None


@dataclass(frozen=True)
class OutcomeReceipt:
    interaction_id: str
    state: str
    entries: tuple[ReceiptEntry, ...]
    summary: str
    compact_line: str
    expanded: bool = False


@dataclass(frozen=True)
class PresentationState:
    transcript: tuple[TranscriptLine, ...] = ()
    active_progress: dict[str, str] = field(default_factory=dict)
    progress_sequences: dict[str, int] = field(default_factory=dict)
    receipts: dict[str, OutcomeReceipt] = field(default_factory=dict)
    settled_interactions: frozenset[str] = frozenset()
    connection_state: str = "disconnected"
    draft: str = ""
    transcript_limit: int = 200


def reduce_progress_frame(state: PresentationState, frame: dict) -> PresentationState:
    progress = frame.get("progress")
    if not isinstance(progress, dict):
        return state
    interaction_id = progress.get("interaction_id")
    sequence = progress.get("sequence")
    phase = progress.get("phase")
    progress_state = progress.get("state")
    if (
        progress.get("version") != 1
        or not isinstance(interaction_id, str)
        or not interaction_id
        or not isinstance(sequence, int)
        or sequence < 1
        or phase not in _PROGRESS_PHASES
        or progress_state not in {"active", "settled"}
        or interaction_id in state.settled_interactions
        or sequence <= state.progress_sequences.get(interaction_id, 0)
    ):
        return state
    sequences = dict(state.progress_sequences)
    sequences[interaction_id] = sequence
    active = dict(state.active_progress)
    if progress_state == "settled" or phase in {"completed", "failed", "cancelled"}:
        active.pop(interaction_id, None)
    else:
        active[interaction_id] = phase
    return replace(state, active_progress=active, progress_sequences=sequences)


def reduce_interaction_update(state: PresentationState, frame: dict) -> PresentationState:
    interaction = frame.get("interaction")
    if not isinstance(interaction, dict):
        return state
    interaction_id = interaction.get("interaction_id")
    status = interaction.get("status")
    summary = interaction.get("summary")
    if not isinstance(interaction_id, str) or not interaction_id:
        return state
    active = dict(state.active_progress)
    active.pop(interaction_id, None)
    settled = set(state.settled_interactions)
    if status in _RECEIPT_STATES or status == "completed":
        settled.add(interaction_id)
    receipt = _parse_receipt(
        interaction_id=interaction_id,
        summary=summary,
        raw_receipt=interaction.get("outcome_receipt"),
    )
    if receipt is not None:
        receipts = dict(state.receipts)
        previous = receipts.get(interaction_id)
        if previous is not None:
            receipt = replace(receipt, expanded=previous.expanded)
        receipts[interaction_id] = receipt
        transcript = _append(
            state.transcript,
            TranscriptLine("receipt", receipt.compact_line, interaction_id),
            state.transcript_limit,
        )
        return replace(
            state,
            transcript=transcript,
            active_progress=active,
            receipts=receipts,
            settled_interactions=frozenset(settled),
        )
    if isinstance(summary, str) and summary.strip():
        transcript = _append(
            state.transcript,
            TranscriptLine("runtime", summary.strip(), interaction_id),
            state.transcript_limit,
        )
        return replace(
            state,
            transcript=transcript,
            active_progress=active,
            settled_interactions=frozenset(settled),
        )
    return replace(
        state,
        active_progress=active,
        settled_interactions=frozenset(settled),
    )


def toggle_receipt(state: PresentationState, interaction_id: str) -> PresentationState:
    receipt = state.receipts.get(interaction_id)
    if receipt is None:
        return state
    receipts = dict(state.receipts)
    receipts[interaction_id] = replace(receipt, expanded=not receipt.expanded)
    return replace(state, receipts=receipts)


def _parse_receipt(
    *, interaction_id: str, summary: object, raw_receipt: object
) -> OutcomeReceipt | None:
    if not isinstance(raw_receipt, dict):
        return None
    if set(raw_receipt) != {"version", "state", "entries"}:
        return None
    if raw_receipt.get("version") != 1 or raw_receipt.get("state") not in _RECEIPT_STATES:
        return None
    raw_entries = raw_receipt.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        return None
    entries: list[ReceiptEntry] = []
    expected_sequence = 1
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict) or not set(raw_entry).issubset(
            {"sequence", "kind", "occurred_at", "device_name"}
        ):
            return None
        sequence = raw_entry.get("sequence")
        kind = raw_entry.get("kind")
        occurred_at = raw_entry.get("occurred_at")
        device_name = raw_entry.get("device_name")
        if (
            sequence != expected_sequence
            or kind not in _RECEIPT_KINDS
            or not isinstance(occurred_at, str)
            or not occurred_at
            or (device_name is not None and not isinstance(device_name, str))
        ):
            return None
        entries.append(ReceiptEntry(sequence, kind, occurred_at, device_name))
        expected_sequence += 1
    safe_summary = summary.strip() if isinstance(summary, str) else ""
    return OutcomeReceipt(
        interaction_id=interaction_id,
        state=raw_receipt["state"],
        entries=tuple(entries),
        summary=safe_summary,
        compact_line=_compact_line(raw_receipt["state"], entries[-1]),
    )


def _compact_line(state: str, entry: ReceiptEntry) -> str:
    status = {"completed": "Completed", "failed": "Failed", "cancelled": "Cancelled"}[state]
    detail = entry.device_name or _KIND_LABELS[entry.kind]
    time = entry.occurred_at[11:16] if len(entry.occurred_at) >= 16 else entry.occurred_at
    return f"✓ {status} · {detail} · {time}"


_KIND_LABELS = {
    "request_received": "Request received",
    "started": "OpenHalo started",
    "delivery": "Delivered",
    "confirmed": "Confirmed",
    "failed": "Could not complete",
}


def _append(
    transcript: tuple[TranscriptLine, ...], line: TranscriptLine, limit: int
) -> tuple[TranscriptLine, ...]:
    return (*transcript, line)[-max(limit, 1) :]
