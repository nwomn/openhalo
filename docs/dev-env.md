# Development Environment Workflow

## Default workflow

Default: reuse the repository root `.venv`.

That is the normal path for day-to-day coding in the main workspace and in ordinary worktrees that do not change dependency state. Run commands from the current workspace, but use the root interpreter so every workspace shares one stable dependency set.

Examples:

```bash
/root/personal-runtime-agent/.venv/bin/python -m unittest discover -s tests -v
```

```bash
bin/test -m unittest discover -s tests -v
```

## Exception workflow

Exception: create a worktree-local `.venv`.

Use an isolated environment only when a worktree is intentionally changing dependency versions, trying a new library, or modifying packaging and installation behavior. In that case, keep the experiment local to that worktree instead of mutating the shared root environment first.

Create it explicitly:

```bash
bin/bootstrap-worktree-venv
```

Then use the local interpreter from that worktree:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Merge-back rule

Do not copy or diff `.venv` directories between worktrees and the main workspace.

If a dependency experiment succeeds, commit the source-of-truth file changes such as `pyproject.toml`, merge those changes, and then update the repository root `.venv` from the main workspace.
