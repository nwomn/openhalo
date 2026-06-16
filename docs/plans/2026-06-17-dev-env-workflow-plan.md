# Development Environment Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Codify how this repository uses the main-workspace `.venv` by default while allowing opt-in isolated worktree virtual environments for dependency experiments.

**Architecture:** Keep the workflow explicit and small. Add one shared test runner script that always prefers the repository root `.venv`, one opt-in bootstrap script for creating a local worktree `.venv`, and a short developer-facing document that explains when to use each path. Avoid magic syncing or auto-copying environments.

**Tech Stack:** Bash, Python `unittest`, Markdown

### Task 1: Lock the shared-venv contract with tests

**Files:**
- Create: `tests/test_dev_env_scripts.py`
- Modify: `tests/test_protocol_v0.py`

**Step 1: Write the failing tests**

Add tests that verify:
- `bin/test` exists and points at the repository root `.venv/bin/python`
- `bin/bootstrap-worktree-venv` exists and creates a local `.venv` only when explicitly run
- The developer document states the default shared-venv rule and the isolated-worktree exception rule

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m unittest tests.test_dev_env_scripts -v`
Expected: FAIL because the scripts and document do not exist yet.

**Step 3: Write minimal implementation**

Create the scripts and document with the smallest behavior needed to satisfy the tests.

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest tests.test_dev_env_scripts -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_dev_env_scripts.py bin/test bin/bootstrap-worktree-venv docs/dev-env.md
git commit -m "chore: codify dev environment workflow"
```

### Task 2: Verify the scripts against the real main workspace

**Files:**
- Modify: `tests/test_dev_env_scripts.py`
- Modify: `.gitignore` if needed

**Step 1: Write the failing behavior test**

Add a test showing that `bin/test` can be invoked from the repo root and uses the root `.venv`.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_dev_env_scripts -v`
Expected: FAIL until the script is executable and wired correctly.

**Step 3: Write minimal implementation**

Make the script executable and ensure it resolves the repository root robustly.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_dev_env_scripts -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_dev_env_scripts.py bin/test
git commit -m "test: verify shared venv helper scripts"
```

### Task 3: Full verification and baseline update

**Files:**
- Modify: `Project.md` if this environment workflow becomes a tracked project workflow decision

**Step 1: Re-evaluate project baseline**

If this repository-level environment workflow is now a stable project convention, record it in `Project.md`.

**Step 2: Run full verification**

Run: `.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS

**Step 3: Commit the stable result**

```bash
git add Project.md
git commit -m "docs: record development environment workflow"
```
