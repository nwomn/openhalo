# Branch-First Development Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the repository's default development workflow explicitly branch-first in the main workspace, with worktrees treated as an optional advanced path.

**Architecture:** Keep the workflow guidance small and explicit. Update the developer-facing workflow document and project baseline to state that normal day-to-day work should happen in the current workspace on a feature branch, while optional worktree use remains available for parallel isolated tasks or dependency experiments.

**Tech Stack:** Markdown, Bash, Python `unittest`

### Task 1: Lock the branch-first workflow wording with tests

**Files:**
- Modify: `tests/test_dev_env_scripts.py`
- Test: `tests/test_dev_env_scripts.py`

**Step 1: Write the failing test**

Add assertions that require:
- the developer workflow document to say the default workflow is branch-first in the main workspace
- the optional worktree path to be described as an advanced or explicit opt-in path
- the optional bootstrap script text to describe the local `.venv` as worktree-local and optional

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_dev_env_scripts -v`
Expected: FAIL because the current wording still treats ordinary worktrees as part of the default workflow.

**Step 3: Write minimal implementation**

Update the document and helper script text to match the new branch-first wording without changing unrelated behavior.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_dev_env_scripts -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_dev_env_scripts.py docs/dev-env.md bin/bootstrap-worktree-venv
git commit -m "docs: make development workflow branch-first"
```

### Task 2: Update the project baseline

**Files:**
- Modify: `Project.md`

**Step 1: Write the update**

Change the project baseline so it says:
- ordinary development work is branch-first in the main workspace
- worktrees are optional for parallel isolated tasks
- dependency and packaging experiments may still use an explicitly created worktree-local `.venv`

**Step 2: Review for consistency**

Check that `Project.md` and `docs/dev-env.md` describe the same default workflow.

**Step 3: Commit**

```bash
git add Project.md docs/dev-env.md
git commit -m "docs: align project baseline with branch-first workflow"
```
