"""Safe public outcome-receipt projection for authorized Device Edges."""

from __future__ import annotations


SAFE_RECEIPT_KINDS = frozenset(
    {"request_received", "started", "delivery", "confirmed", "failed"}
)
SAFE_RECEIPT_STATES = frozenset({"completed", "failed", "cancelled"})


def append_receipt_entry(
    entries: list[dict],
    *,
    kind: str,
    occurred_at: str,
    device_id: str | None = None,
) -> list[dict]:
    if kind not in SAFE_RECEIPT_KINDS:
        raise ValueError(f"Unsupported receipt kind: {kind!r}")
    if not isinstance(occurred_at, str) or not occurred_at:
        raise ValueError("Receipt entry requires occurred_at.")
    entry = {
        "sequence": len(entries) + 1,
        "kind": kind,
        "occurred_at": occurred_at,
    }
    if isinstance(device_id, str) and device_id:
        entry["device_id"] = device_id
    return [*entries, entry]


def project_outcome_receipt(
    *,
    entries: object,
    state: object,
    participant_device_ids: object,
    device_names: object,
) -> dict | None:
    """Drop private/opaque fields while producing one versioned safe projection."""

    if state not in SAFE_RECEIPT_STATES or not isinstance(entries, list):
        return None
    allowed_devices = {
        device_id
        for device_id in participant_device_ids
        if isinstance(device_id, str) and device_id
    } if isinstance(participant_device_ids, (list, set, tuple, frozenset)) else set()
    names = device_names if isinstance(device_names, dict) else {}
    public_entries = []
    for expected_sequence, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            return None
        if (
            entry.get("sequence") != expected_sequence
            or entry.get("kind") not in SAFE_RECEIPT_KINDS
            or not isinstance(entry.get("occurred_at"), str)
            or not entry["occurred_at"]
        ):
            return None
        public_entry = {
            "sequence": expected_sequence,
            "kind": entry["kind"],
            "occurred_at": entry["occurred_at"],
        }
        device_id = entry.get("device_id")
        device_name = names.get(device_id) if device_id in allowed_devices else None
        if isinstance(device_name, str) and device_name.strip():
            public_entry["device_name"] = device_name.strip()
        public_entries.append(public_entry)
    if not public_entries:
        return None
    return {"version": 1, "state": state, "entries": public_entries}
