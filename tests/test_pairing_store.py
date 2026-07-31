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

    def test_claiming_fresh_code_registers_public_key_without_persisting_the_code(
        self,
    ) -> None:
        pairing_code = self.store.create_pairing_code(
            ttl_seconds=600,
            now=NOW,
        )

        public_key = "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEtest"
        self.store.claim_pairing_code(
            pairing_code,
            device_id="android-edge-1",
            device_type="android-phone",
            display_name="Maya's Phone",
            audience="wss://runtime.example/openhalo/edge",
            public_key=public_key,
            now=NOW,
        )

        persisted = self.store_path.read_text(encoding="utf-8")
        payload = json.loads(persisted)

        self.assertNotIn(pairing_code, persisted)
        self.assertEqual(payload["version"], 2)
        self.assertEqual(payload["devices"]["android-edge-1"]["public_key"], public_key)
        self.assertEqual(
            payload["devices"]["android-edge-1"]["display_name"], "Maya's Phone"
        )
        self.assertNotIn("credential_hash", payload["devices"]["android-edge-1"])
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
            display_name="Maya's Phone",
            audience="wss://runtime.example/openhalo/edge",
            public_key="public-key-1",
            now=NOW,
        )

        with self.assertRaisesRegex(PairingError, "pairing_code_consumed"):
            self.store.claim_pairing_code(
                pairing_code,
                device_id="android-edge-2",
                device_type="android-phone",
                display_name="Another Phone",
                audience="wss://runtime.example/openhalo/edge",
                public_key="public-key-2",
                now=NOW,
            )

    def test_consumed_pairing_code_can_retry_only_for_the_same_identity(self) -> None:
        pairing_code = self.store.create_pairing_code(
            ttl_seconds=600,
            now=NOW,
        )
        pairing = {
            "device_id": "android-edge-1",
            "device_type": "android-phone",
            "display_name": "Maya's Phone",
            "audience": "ws://198.51.100.15:8765",
            "public_key": "public-key-1",
        }
        self.store.claim_pairing_code(pairing_code, now=NOW, **pairing)

        self.store.claim_pairing_code(pairing_code, now=NOW, **pairing)

        for field, value in (
            ("device_id", "android-edge-2"),
            ("device_type", "android-tablet"),
            ("audience", "ws://198.51.100.16:8765"),
            ("public_key", "different-public-key"),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(PairingError, "pairing_code_consumed"):
                    self.store.claim_pairing_code(
                        pairing_code,
                        now=NOW,
                        **{**pairing, field: value},
                    )

    def test_public_key_record_survives_store_restart(self) -> None:
        pairing_code = self.store.create_pairing_code(
            ttl_seconds=600,
            now=NOW,
        )
        self.store.claim_pairing_code(
            pairing_code,
            device_id="android-edge-1",
            device_type="android-phone",
            display_name="Maya's Phone",
            audience="wss://runtime.example/openhalo/edge",
            public_key="public-key",
            now=NOW,
        )

        restarted_store = PairingStore(self.store_path)

        self.assertEqual(
            restarted_store.get_device("android-edge-1")["public_key"], "public-key"
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
                display_name="Maya's Phone",
                audience="wss://runtime.example/openhalo/edge",
                public_key="public-key",
                now=NOW + timedelta(seconds=61),
            )

    def test_revoked_device_public_key_is_rejected(self) -> None:
        pairing_code = self.store.create_pairing_code(
            ttl_seconds=600,
            now=NOW,
        )
        self.store.claim_pairing_code(
            pairing_code,
            device_id="android-edge-1",
            device_type="android-phone",
            display_name="Maya's Phone",
            audience="wss://runtime.example/openhalo/edge",
            public_key="public-key",
            now=NOW,
        )

        self.store.revoke_device("android-edge-1", now=NOW)

        self.assertIsNone(self.store.get_active_device("android-edge-1"))

    def test_loading_a_v1_registry_discards_bearer_records_and_pairing_codes(self) -> None:
        self.store_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "pairing_codes": {"old-code-hash": {"expires_at": "2030-01-02T00:00:00Z"}},
                    "devices": {"old-device": {"credential_hash": "secret"}},
                }
            ),
            encoding="utf-8",
        )

        self.assertEqual(self.store.list_devices(), [])
        migrated = json.loads(self.store_path.read_text(encoding="utf-8"))
        self.assertEqual(migrated, {"version": 2, "pairing_codes": {}, "devices": {}})

    def test_owner_can_provision_a_local_host_public_key_without_a_pairing_code(self) -> None:
        self.store.provision_local_device(
            device_id="host-edge-1",
            device_type="server",
            display_name="Runtime Host",
            audience="ws://127.0.0.1:8765",
            public_key="host-public-key",
            now=NOW,
        )

        host = self.store.get_active_device("host-edge-1")

        self.assertEqual(host["display_name"], "Runtime Host")
        self.assertEqual(host["public_key"], "host-public-key")
        self.assertEqual(self.store.list_pairing_codes(), [])
