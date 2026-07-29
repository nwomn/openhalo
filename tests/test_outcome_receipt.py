from __future__ import annotations

from personal_runtime.outcome_receipt import append_receipt_entry
from personal_runtime.outcome_receipt import project_outcome_receipt


def test_outcome_receipt_projects_only_allowed_device_names_without_device_ids() -> None:
    entries = append_receipt_entry([], kind="request_received", occurred_at="2030-01-01T10:42:00Z")
    entries = append_receipt_entry(
        entries,
        kind="confirmed",
        occurred_at="2030-01-01T10:43:00Z",
        device_id="android-edge-opaque",
    )

    receipt = project_outcome_receipt(
        entries=entries,
        state="completed",
        participant_device_ids={"terminal-edge-1", "android-edge-opaque"},
        device_names={"android-edge-opaque": "Maya's Phone"},
    )

    assert receipt == {
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
                "kind": "confirmed",
                "occurred_at": "2030-01-01T10:43:00Z",
                "device_name": "Maya's Phone",
            },
        ],
    }
    assert "android-edge-opaque" not in repr(receipt)


def test_outcome_receipt_omits_unrelated_device_name() -> None:
    receipt = project_outcome_receipt(
        entries=[
            {
                "sequence": 1,
                "kind": "delivery",
                "occurred_at": "2030-01-01T10:43:00Z",
                "device_id": "unrelated-device",
            }
        ],
        state="completed",
        participant_device_ids={"terminal-edge-1"},
        device_names={"unrelated-device": "Not Authorized"},
    )

    assert receipt["entries"] == [
        {
            "sequence": 1,
            "kind": "delivery",
            "occurred_at": "2030-01-01T10:43:00Z",
        }
    ]
