from pathlib import Path
import json
from tempfile import TemporaryDirectory

from personal_runtime.main import build_runtime_server_parser
from personal_runtime.main import resolve_runtime_state_path


def test_runtime_parser_accepts_a_private_ready_file_path() -> None:
    args = build_runtime_server_parser().parse_args(
        ["--ready-file-path", "/tmp/openhalo-ready"]
    )

    assert args.ready_file_path == Path("/tmp/openhalo-ready")


def test_runtime_parser_defaults_to_sqlite_state_path() -> None:
    args = build_runtime_server_parser().parse_args([])

    assert args.state_path == ".runtime/state.sqlite3"


def test_runtime_start_migrates_legacy_personal_state_before_opening_gateway() -> None:
    with TemporaryDirectory() as directory:
        runtime = Path(directory) / "runtime"
        runtime.mkdir()
        legacy = runtime / "state.json"
        legacy.write_text(
            json.dumps({"events": [{"event_id": "legacy-event"}]}),
            encoding="utf-8",
        )

        resolved = resolve_runtime_state_path(legacy)

        assert resolved == runtime / "state.sqlite3"
        assert resolved.exists()
        assert legacy.exists()
