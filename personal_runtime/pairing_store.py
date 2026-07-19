"""Durable, Runtime-local device pairing and credential registry."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import tempfile
from collections.abc import Callable
from datetime import UTC
from datetime import datetime
from pathlib import Path


class PairingError(ValueError):
    """A public-safe pairing failure identified by ``code``."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class PairingStore:
    """Store one-time pairing codes and per-device credential hashes locally."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock_path = path.with_suffix(f"{path.suffix}.lock")

    def create_pairing_code(
        self,
        *,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> str:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        created_at = _timestamp(now)
        expires_at = _timestamp_from_epoch(
            _parse_timestamp(created_at).timestamp() + ttl_seconds
        )
        pairing_code = secrets.token_urlsafe(32)
        pairing_code_hash = _secret_hash(pairing_code)

        def create(payload: dict) -> None:
            payload["pairing_codes"][pairing_code_hash] = {
                "created_at": created_at,
                "expires_at": expires_at,
                "consumed_at": None,
                "consumed_by_device_id": None,
            }

        self._mutate(create)
        return pairing_code

    def claim_pairing_code(
        self,
        pairing_code: str,
        *,
        device_id: str,
        device_type: str,
        now: datetime | None = None,
    ) -> str:
        pairing_code_hash = _secret_hash(pairing_code)
        claimed_at = _timestamp(now)
        device_token = secrets.token_urlsafe(32)

        def claim(payload: dict) -> None:
            pairing_record = payload["pairing_codes"].get(pairing_code_hash)
            if pairing_record is None:
                raise PairingError("invalid_pairing_code")
            if pairing_record["consumed_at"] is not None:
                raise PairingError("pairing_code_consumed")
            if _parse_timestamp(pairing_record["expires_at"]) < _parse_timestamp(
                claimed_at
            ):
                raise PairingError("pairing_code_expired")
            existing_device = payload["devices"].get(device_id)
            if existing_device is not None and existing_device.get("revoked_at") is None:
                raise PairingError("device_already_paired")

            pairing_record["consumed_at"] = claimed_at
            pairing_record["consumed_by_device_id"] = device_id
            payload["devices"][device_id] = {
                "credential_hash": _secret_hash(device_token),
                "device_type": device_type,
                "paired_at": claimed_at,
                "last_authenticated_at": claimed_at,
                "revoked_at": None,
            }

        self._mutate(claim)
        return device_token

    def authenticate_device(
        self,
        device_id: str,
        device_token: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        authenticated_at = _timestamp(now)
        device_token_hash = _secret_hash(device_token)
        authenticated = False

        def authenticate(payload: dict) -> None:
            nonlocal authenticated
            device = payload["devices"].get(device_id)
            if (
                device is None
                or device.get("revoked_at") is not None
                or not secrets.compare_digest(
                    device.get("credential_hash", ""), device_token_hash
                )
            ):
                return
            device["last_authenticated_at"] = authenticated_at
            authenticated = True

        self._mutate(authenticate)
        return authenticated

    def revoke_device(
        self,
        device_id: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        revoked_at = _timestamp(now)
        revoked = False

        def revoke(payload: dict) -> None:
            nonlocal revoked
            device = payload["devices"].get(device_id)
            if device is None or device.get("revoked_at") is not None:
                return
            device["revoked_at"] = revoked_at
            revoked = True

        self._mutate(revoke)
        return revoked

    def list_pairing_codes(self) -> list[dict]:
        return self._read(
            lambda payload: [
                {
                    "created_at": record["created_at"],
                    "expires_at": record["expires_at"],
                    "consumed_at": record["consumed_at"],
                    "consumed_by_device_id": record["consumed_by_device_id"],
                }
                for record in payload["pairing_codes"].values()
            ]
        )

    def list_devices(self) -> list[dict]:
        return self._read(
            lambda payload: [
                {
                    "device_id": device_id,
                    "device_type": record["device_type"],
                    "paired_at": record["paired_at"],
                    "last_authenticated_at": record["last_authenticated_at"],
                    "revoked_at": record["revoked_at"],
                }
                for device_id, record in payload["devices"].items()
            ]
        )

    def _read(self, reader: Callable[[dict], object]):
        with self._locked():
            return reader(self._load_unlocked())

    def _mutate(self, mutator: Callable[[dict], None]) -> None:
        with self._locked():
            payload = self._load_unlocked()
            mutator(payload)
            self._save_unlocked(payload)

    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = self.lock_path.open("a+", encoding="utf-8")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        class LockedStore:
            def __enter__(self_nonlocal):
                return lock_file

            def __exit__(self_nonlocal, exc_type, exc, traceback) -> None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()

        return LockedStore()

    def _load_unlocked(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "pairing_codes": {}, "devices": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save_unlocked(self, payload: dict) -> None:
        descriptor, temporary_path = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(payload, output, sort_keys=True)
                output.write("\n")
            os.replace(temporary_path, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)


def _secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _timestamp(value: datetime | None) -> str:
    timestamp = value or datetime.now(UTC)
    return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _timestamp_from_epoch(value: float) -> str:
    return datetime.fromtimestamp(value, tz=UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
