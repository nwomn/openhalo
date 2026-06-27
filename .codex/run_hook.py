from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from agent_guard.codex_hooks import main as hooks_main

    return hooks_main([*sys.argv[1:], str(repo_root)])


if __name__ == "__main__":
    raise SystemExit(main())
