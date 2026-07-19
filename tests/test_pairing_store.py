import json
import unittest
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from personal_runtime.pairing_store import PairingError
from personal_runtime.pairing_store import PairingStore


NOW = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


class PairingStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = TemporaryDirectory()
        self.store_path = Path(self.temp_directory.name) / "pairing.json"
        self.store = PairingStore(self.store_path)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_claiming_fresh_code_issues_device_token_without_persisting_secrets(
        self,
    ) -> None:
        pairing_code = self.store.create_pairing_code(
            ttl_seconds=600,
            now=NOW,
        )

        device_token = self.store.claim_pairing_code(
            pairing_code,
            device_id="android-edge-1",
            device_type="android-phone",
            now=NOW,
        )

        persisted = self.store_path.read_text(encoding="utf-8")
        payload = json.loads(persisted)

        self.assertTrue(device_token)
        self.assertNotIn(pairing_code, persisted)
        self.assertNotIn(device_token, persisted)
        self.assertTrue(
            self.store.authenticate_device(
                "android-edge-1",
                device_token,
                now=NOW,
            )
        )
        self.assertEqual(
            payload["devices"]["android-edge-1"]["device_type"],
            "android-phone",
        )

    def test_pairing_code_is_single_use(self) -> None:
        pairing_code = self.store.create_pairing_code(
            ttl_seconds=600,
            now=NOW,
        )
        self.store.claim_pairing_code(
            pairing_code,
            device_id="android-edge-1",
            device_type="android-phone",
            now=NOW,
        )

        with self.assertRaisesRegex(PairingError, "pairing_code_consumed"):
            self.store.claim_pairing_code(
                pairing_code,
                device_id="android-edge-2",
                device_type="android-phone",
                now=NOW,
            )

    def test_device_credential_survives_store_restart(self) -> None:
        pairing_code = self.store.create_pairing_code(
            ttl_seconds=600,
            now=NOW,
        )
        device_token = self.store.claim_pairing_code(
            pairing_code,
            device_id="android-edge-1",
            device_type="android-phone",
            now=NOW,
        )

        restarted_store = PairingStore(self.store_path)

        self.assertTrue(
            restarted_store.authenticate_device(
                "android-edge-1",
                device_token,
                now=NOW,
            )
        )

    def test_expired_pairing_code_is_rejected(self) -> None:
        pairing_code = self.store.create_pairing_code(
            ttl_seconds=60,
            now=NOW,
        )

        with self.assertRaisesRegex(PairingError, "pairing_code_expired"):
            self.store.claim_pairing_code(
                pairing_code,
                device_id="android-edge-1",
                device_type="android-phone",
                now=NOW + timedelta(seconds=61),
            )

    def test_revoked_device_token_is_rejected(self) -> None:
        pairing_code = self.store.create_pairing_code(
            ttl_seconds=600,
            now=NOW,
        )
        device_token = self.store.claim_pairing_code(
            pairing_code,
            device_id="android-edge-1",
            device_type="android-phone",
            now=NOW,
        )

        self.store.revoke_device("android-edge-1", now=NOW)

        self.assertFalse(
            self.store.authenticate_device(
                "android-edge-1",
                device_token,
                now=NOW,
            )
        )
