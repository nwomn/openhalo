import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import UTC
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from personal_runtime.pairing_cli import main
from personal_runtime.pairing_store import PairingStore


class PairingCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = TemporaryDirectory()
        self.store_path = Path(self.temp_directory.name) / "pairing.json"

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_create_emits_pairing_code_once_and_list_redacts_it(self) -> None:
        create_output = self._run_cli(
            "create",
            "--store",
            str(self.store_path),
            "--ttl-seconds",
            "600",
        )
        pairing_code = json.loads(create_output)["pairing_code"]

        list_output = self._run_cli("list", "--store", str(self.store_path))

        self.assertTrue(pairing_code)
        self.assertNotIn(pairing_code, list_output)
        self.assertEqual(len(json.loads(list_output)["pairing_codes"]), 1)

    def test_revoke_emits_safe_device_metadata(self) -> None:
        store = PairingStore(self.store_path)
        pairing_code = store.create_pairing_code(
            ttl_seconds=600,
            now=datetime(2030, 1, 1, tzinfo=UTC),
        )
        store.claim_pairing_code(
            pairing_code,
            device_id="android-edge-1",
            device_type="android-phone",
            now=datetime(2030, 1, 1, tzinfo=UTC),
        )

        output = self._run_cli(
            "revoke",
            "--store",
            str(self.store_path),
            "--device-id",
            "android-edge-1",
        )

        payload = json.loads(output)
        self.assertEqual(payload["device_id"], "android-edge-1")
        self.assertTrue(payload["revoked"])
        self.assertNotIn("credential", output)

    def _run_cli(self, *args: str) -> str:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(list(args))
        self.assertEqual(exit_code, 0)
        return output.getvalue()
