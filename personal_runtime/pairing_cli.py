"""Local administrator commands for Runtime device pairing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from personal_runtime.pairing_store import PairingStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage OpenHalo device pairing.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a one-time pairing code.")
    create.add_argument("--store", type=Path, required=True)
    create.add_argument("--ttl-seconds", type=int, default=600)

    listing = subparsers.add_parser("list", help="List safe pairing metadata.")
    listing.add_argument("--store", type=Path, required=True)

    revoke = subparsers.add_parser("revoke", help="Revoke a paired device.")
    revoke.add_argument("--store", type=Path, required=True)
    revoke.add_argument("--device-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = PairingStore(args.store)
    if args.command == "create":
        pairing_code = store.create_pairing_code(ttl_seconds=args.ttl_seconds)
        print(
            json.dumps(
                {
                    "pairing_code": pairing_code,
                    "ttl_seconds": args.ttl_seconds,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.command == "list":
        print(
            json.dumps(
                {
                    "pairing_codes": store.list_pairing_codes(),
                    "devices": store.list_devices(),
                },
                sort_keys=True,
            )
        )
        return 0

    revoked = store.revoke_device(args.device_id)
    print(json.dumps({"device_id": args.device_id, "revoked": revoked}))
    return 0 if revoked else 1


if __name__ == "__main__":
    raise SystemExit(main())
