from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path


AUDIT_HEADER = "Project.md Check:"
REQUIRED_SUMMARY_TEMPLATE = """Project.md Check:
- meaningful: yes|no
- phase_changed: yes|no
- architecture_changed: yes|no
- milestone_changed: yes|no
- subgoal_status_changed: yes|no
- completed_work_changed: yes|no
- acceptance_status_changed: yes|no
- project_updated: yes|no
- summary: One concise sentence.
"""


@dataclass(frozen=True)
class SessionState:
    session_id: str
    project_hash_at_start: str
    phase_at_start: str | None = None
    project_read: bool = False
    last_user_prompt: str | None = None
    turn_active: bool = False
    activity_since_check: bool = False
    last_tool_name: str | None = None


@dataclass(frozen=True)
class TurnAudit:
    meaningful: bool
    phase_changed: bool
    architecture_changed: bool
    milestone_changed: bool
    subgoal_status_changed: bool
    completed_work_changed: bool
    acceptance_status_changed: bool
    project_updated: bool
    summary: str


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_project_phase(project_text: str) -> str | None:
    lines = project_text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "Current phase:":
            continue
        for candidate in lines[index + 1 :]:
            stripped = candidate.strip()
            if not stripped:
                continue
            if stripped.startswith("- "):
                return stripped[2:].strip()
            break
    return None


def parse_project_check(message_text: str) -> TurnAudit | None:
    lines = message_text.splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == AUDIT_HEADER)
    except StopIteration:
        return None

    values: dict[str, str] = {}
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("- "):
            break
        key, _, raw_value = stripped[2:].partition(":")
        if not _:
            continue
        values[key.strip()] = raw_value.strip()

    required = [
        "meaningful",
        "phase_changed",
        "architecture_changed",
        "milestone_changed",
        "subgoal_status_changed",
        "completed_work_changed",
        "acceptance_status_changed",
        "project_updated",
        "summary",
    ]
    if any(key not in values for key in required):
        return None

    def parse_bool(key: str) -> bool:
        return values[key].lower() == "yes"

    return TurnAudit(
        meaningful=parse_bool("meaningful"),
        phase_changed=parse_bool("phase_changed"),
        architecture_changed=parse_bool("architecture_changed"),
        milestone_changed=parse_bool("milestone_changed"),
        subgoal_status_changed=parse_bool("subgoal_status_changed"),
        completed_work_changed=parse_bool("completed_work_changed"),
        acceptance_status_changed=parse_bool("acceptance_status_changed"),
        project_updated=parse_bool("project_updated"),
        summary=values["summary"],
    )


def validate_turn_audit(
    audit: TurnAudit,
    session: SessionState,
    current_project_hash: str,
) -> str | None:
    if not audit.meaningful:
        return None

    tracked_change = any(
        (
            audit.phase_changed,
            audit.architecture_changed,
            audit.milestone_changed,
            audit.subgoal_status_changed,
            audit.completed_work_changed,
            audit.acceptance_status_changed,
        )
    )

    project_changed = current_project_hash != session.project_hash_at_start

    if tracked_change and not audit.project_updated:
        return "Project.md must be updated when tracked project state changes."
    if audit.project_updated and not project_changed:
        return "This turn claimed Project.md was updated, but the Project.md hash did not change."
    if project_changed and not audit.project_updated:
        return "Project.md changed during this turn, but the audit footer did not declare a Project.md update."

    return None


def load_state(path: Path) -> SessionState | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return SessionState(**payload)


def save_state(path: Path, state: SessionState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")


def repo_paths(root: Path) -> tuple[Path, Path]:
    project = root / "Project.md"
    state = root / ".codex" / "audit" / "state.json"
    return project, state


def allow(message: str = "") -> int:
    if message:
        print(json.dumps({"continue": True, "message": message}))
    else:
        print(json.dumps({"continue": True}))
    return 0


def block(message: str) -> int:
    print(json.dumps({"decision": "block", "reason": message}))
    return 2


def handle_session_start(root: Path, payload: dict) -> int:
    project_path, state_path = repo_paths(root)
    project_text = project_path.read_text(encoding="utf-8")
    state = SessionState(
        session_id=str(payload.get("session_id", "unknown-session")),
        project_hash_at_start=hash_file(project_path),
        phase_at_start=extract_project_phase(project_text),
        project_read=True,
        turn_active=False,
        activity_since_check=False,
    )
    save_state(state_path, state)
    return allow("Project.md baseline loaded for this session.")


def handle_user_prompt_submit(root: Path, payload: dict) -> int:
    _, state_path = repo_paths(root)
    state = load_state(state_path)
    if state is None or not state.project_read:
        return block("Session must start by reading Project.md before continuing.")
    if state.turn_active:
        return block("Previous turn is missing a verified Project.md Check audit block.")
    state = SessionState(
        **{
            **asdict(state),
            "last_user_prompt": payload.get("prompt"),
            "turn_active": True,
            "activity_since_check": False,
            "last_tool_name": None,
        }
    )
    save_state(state_path, state)
    return allow()


def handle_pre_tool_use(root: Path, _payload: dict) -> int:
    _, state_path = repo_paths(root)
    state = load_state(state_path)
    if state is None or not state.project_read:
        return block("Project.md session baseline is missing.")
    if not state.turn_active:
        return block("Start the turn through UserPromptSubmit before using tools.")
    return allow()


def handle_post_tool_use(root: Path, payload: dict) -> int:
    _, state_path = repo_paths(root)
    state = load_state(state_path)
    if state is None:
        return block("Project.md session baseline is missing.")
    state = SessionState(
        **{
            **asdict(state),
            "activity_since_check": True,
            "last_tool_name": payload.get("tool_name"),
        }
    )
    save_state(state_path, state)
    return allow()


def handle_stop(root: Path, payload: dict) -> int:
    project_path, state_path = repo_paths(root)
    state = load_state(state_path)
    if state is None:
        return block("Project.md session baseline is missing.")
    if not state.turn_active:
        return allow()

    transcript = (
        payload.get("output_text", "")
        or payload.get("assistant_response", "")
        or payload.get("last_assistant_message", "")
    )
    current_project_hash = hash_file(project_path)
    audit = parse_project_check(transcript)
    if audit is None:
        if current_project_hash != state.project_hash_at_start:
            message = (
                "Project.md changed during this turn. Add a Project.md Check block "
                "to explicitly declare whether tracked project state changed.\n\n"
                + REQUIRED_SUMMARY_TEMPLATE
            )
            print(
                json.dumps(
                    {
                        "decision": "block",
                        "reason": message,
                        "continue": True,
                    }
                )
            )
            return 2

        next_state = SessionState(
            **{
                **asdict(state),
                "project_hash_at_start": current_project_hash,
                "phase_at_start": extract_project_phase(project_path.read_text(encoding="utf-8")),
                "turn_active": False,
                "activity_since_check": False,
            }
        )
        save_state(state_path, next_state)
        return allow()

    error = validate_turn_audit(
        audit=audit,
        session=state,
        current_project_hash=current_project_hash,
    )
    if error is not None:
        print(json.dumps({"decision": "block", "reason": error, "continue": True}))
        return 2

    next_state = SessionState(
        **{
            **asdict(state),
            "project_hash_at_start": current_project_hash,
            "phase_at_start": extract_project_phase(project_path.read_text(encoding="utf-8")),
            "turn_active": False,
            "activity_since_check": False,
        }
    )
    save_state(state_path, next_state)
    return allow()


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 2:
        raise SystemExit("usage: codex_hooks.py <event> <repo-root>")

    event = argv[0]
    root = Path(argv[1]).resolve()
    payload = json.loads(sys.stdin.read() or "{}")

    handlers = {
        "SessionStart": handle_session_start,
        "UserPromptSubmit": handle_user_prompt_submit,
        "PreToolUse": handle_pre_tool_use,
        "PostToolUse": handle_post_tool_use,
        "Stop": handle_stop,
    }
    if event not in handlers:
        return allow()
    return handlers[event](root, payload)


if __name__ == "__main__":
    raise SystemExit(main())
