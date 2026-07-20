from pathlib import Path

from personal_runtime.main import build_runtime_server_parser


def test_runtime_parser_accepts_a_private_ready_file_path() -> None:
    args = build_runtime_server_parser().parse_args(
        ["--ready-file-path", "/tmp/openhalo-ready"]
    )

    assert args.ready_file_path == Path("/tmp/openhalo-ready")
